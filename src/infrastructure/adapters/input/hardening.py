"""Opt-in request controls; never log bodies, credentials, query strings or raw URLs."""
from collections import OrderedDict
import json
import logging
from threading import BoundedSemaphore, Lock
from time import monotonic
from uuid import UUID
from starlette.responses import JSONResponse

logger = logging.getLogger('uvicorn.error.security_events')
CSP_REPORT = (
    "default-src 'self'; script-src 'self' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net; "
    "font-src 'self' https://fonts.gstatic.com; img-src 'self' data: blob: https://fastapi.tiangolo.com; "
    "connect-src 'self'; frame-src 'self' blob:; object-src 'self' blob:; "
    "base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
)

class WindowCounter:
    """Bounded fixed windows. Do not trust client-supplied forwarding headers."""
    def __init__(self, seconds, capacity):
        self.seconds, self.capacity = seconds, capacity
        self.entries = OrderedDict()
        self.lock = Lock()

    def check(self, key, maximum, *, consume=False):
        with self.lock:
            now = monotonic()
            while self.entries and next(iter(self.entries.values()))[0] <= now:
                self.entries.popitem(last=False)
            if key not in self.entries:
                if len(self.entries) >= self.capacity:
                    return False
                if not consume:
                    return True
                self.entries[key] = [now + self.seconds, 0]
            entry = self.entries[key]
            if entry[1] >= maximum:
                return False
            if consume:
                entry[1] += 1
            return True

class SecurityMiddleware:
    def __init__(self, app, settings):
        self.app, self.settings = app, settings
        self.failures = WindowCounter(settings.security_window_seconds, settings.security_max_origins)
        self.uploads = WindowCounter(settings.security_window_seconds, settings.security_max_origins)
        self.account_uploads = WindowCounter(settings.security_window_seconds, settings.security_max_origins)
        self.ocr = BoundedSemaphore(settings.ocr_max_concurrent)

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        settings = self.settings
        path, method = scope['path'], scope['method']
        origin = (scope.get('client') or ('unknown', 0))[0]
        controlled = (path.startswith('/api/') and path != '/api/capacidades') or path in {'/health/ia', '/health/db'}
        expensive = (path == '/api/expedientes' and method == 'POST') or path == '/health/ia'
        status, acquired = None, False
        if settings.ocr_limits_enabled and path == "/api/expedientes" and method == "POST":
            scope.setdefault("state", {})["ocr_account_quota"] = self.account_uploads

        async def wrapped_send(message):
            nonlocal status
            if message['type'] == 'http.response.start':
                status = message['status']
                if settings.security_headers_enabled:
                    headers = list(message.get('headers', []))
                    existing = {key.lower() for key, _ in headers}
                    additions = {
                        b'x-content-type-options': b'nosniff', b'x-frame-options': b'DENY',
                        b'referrer-policy': b'no-referrer',
                        b'content-security-policy-report-only': CSP_REPORT.encode(),
                    }
                    if settings.hsts_enabled:
                        additions[b'strict-transport-security'] = b'max-age=31536000'
                    if controlled:
                        additions[b'cache-control'] = b'no-store'
                    headers.extend((k, v) for k, v in additions.items() if k not in existing)
                    message = {**message, 'headers': headers}
            await send(message)

        async def reject():
            response = JSONResponse({'detail': 'Límite temporal de solicitudes. Intente de nuevo más tarde.'},
                                    status_code=429, headers={'Retry-After': str(settings.security_window_seconds)})
            await response(scope, receive, wrapped_send)
        try:
            if method != 'OPTIONS' and controlled and settings.auth_rate_limit_enabled:
                if not self.failures.check(origin, settings.auth_failures_per_window):
                    return await reject()
            if method != 'OPTIONS' and expensive and settings.ocr_limits_enabled:
                if not self.uploads.check(origin, settings.ocr_requests_per_window, consume=True):
                    return await reject()
                acquired = self.ocr.acquire(blocking=False)
                if not acquired:
                    return await reject()
            await self.app(scope, receive, wrapped_send)
        except Exception:
            status = status or 500
            raise
        finally:
            if acquired:
                self.ocr.release()
            if controlled and status == 401 and settings.auth_rate_limit_enabled:
                self.failures.check(origin, settings.auth_failures_per_window, consume=True)
            if settings.security_events_enabled and (controlled or path == '/api/capacidades'):
                route = getattr(scope.get('route'), 'path', '')
                event = {'event': 'authentication_failed' if status == 401 else 'request',
                         'route': route or 'security_limit_or_unmatched',
                         'method': method if method in {'GET', 'POST', 'OPTIONS', 'HEAD'} else 'OTHER',
                         'status': status, 'actor': scope.get('state', {}).get('security_actor')}
                raw_id = scope.get('path_params', {}).get('dossier_id')
                try:
                    if raw_id is not None:
                        event['dossier_id'] = str(UUID(str(raw_id)))
                except ValueError:
                    pass
                logger.info('security_event %s', json.dumps(event, ensure_ascii=True))
