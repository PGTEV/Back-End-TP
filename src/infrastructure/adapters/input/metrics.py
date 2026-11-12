"""Opt-in measurements for API routes and service diagnostics."""

import json
import logging
from time import perf_counter

from starlette.types import ASGIApp, Message, Receive, Scope, Send


logger = logging.getLogger("uvicorn.error.furps_metrics")
DIAGNOSTIC_ROUTES = {"/health", "/health/db", "/health/ia"}


class RequestMetricsMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = perf_counter()
        status = None

        async def track_status(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, track_status)
        except Exception:
            if status is None:
                status = 500
            raise
        finally:
            # FastAPI sets the registered route template on the scope. The raw
            # URL, parameters, headers and bodies are never read by this logger.
            route = getattr(scope.get("route"), "path", "")
            if status is not None and (route.startswith("/api/") or route in DIAGNOSTIC_ROUTES):
                method = scope["method"]
                logger.info("furps_request %s", json.dumps({
                    "route": route,
                    "method": method if method in {"GET", "POST", "HEAD", "OPTIONS"} else "OTHER",
                    "status": status,
                    "duration_ms": round((perf_counter() - start) * 1000, 3),
                }))
