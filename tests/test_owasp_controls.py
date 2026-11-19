"""Contract and security regressions for the opt-in OWASP implementation."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
from threading import Event
from uuid import uuid4

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
import pytest

from src.domain.errors import ProcessingUnavailable
from src.domain.valueObjects import Page
from src.infrastructure.adapters.input.hardening import logger, WindowCounter
from src.infrastructure.adapters.output.storage import LocalFileStorage
from src.infrastructure.main import create_app
from src.infrastructure.settings import Settings

TOKEN = 'ficticio-' + 'x' * 40
AUTH = {'Authorization': 'Bearer ' + TOKEN}
FILES = {'archivo': ('ficticio.pdf', b'%PDF-ficticio', 'application/pdf')}

class Reader:
    def extract(self, content):
        return [Page(1, 'FORMULARIO UNICO DE TRAMITE\nDNI: 12345678', 1, 'TEXTO_PDF')]

def configured(tmp_path, **changes):
    return Settings(_env_file=None, database_url=f'sqlite:///{tmp_path / "db.sqlite"}',
                    storage_dir=str(tmp_path / 'pdf'), reviewer_id='evaluador-test',
                    reviewer_token=TOKEN, protect_dossier_routes=True, **changes)

def test_production_refuses_public_access_and_keeps_local_mode():
    assert Settings(_env_file=None).protect_dossier_routes is False
    with pytest.raises(ValueError):
        Settings(_env_file=None, app_environment='production', protect_dossier_routes=False)

def test_protected_contract_headers_and_diagnostics_cache(tmp_path):
    class CountReader(Reader):
        calls = 0
        def extract(self, content):
            self.calls += 1
            return super().extract(content)
    reader = CountReader()
    settings = configured(tmp_path, protect_diagnostics=True, disable_api_docs=True,
                          security_headers_enabled=True, hsts_enabled=True)
    with TestClient(create_app(settings, reader)) as client:
        assert client.get('/health').json() == {'estado': 'ok'}
        caps = client.get('/api/capacidades').json()
        assert caps['seguridad']['expedientes_protegidos'] is True and caps['demo'] is False
        for route in ['/docs', '/redoc', '/openapi.json']:
            assert client.get(route).status_code == 404
        for route in ['/health/db', '/health/ia', f'/api/expedientes/{uuid4()}',
                      f'/api/expedientes/{uuid4()}/documentos/0/pdf']:
            response = client.get(route)
            assert response.status_code == 401
            assert response.headers['cache-control'] == 'no-store'
            assert response.headers['x-content-type-options'] == 'nosniff'
            assert 'blob:' in response.headers['content-security-policy-report-only']
        assert client.post('/api/expedientes', files=FILES).status_code == 401
        assert client.get('/health/db', headers=AUTH).status_code == 200
        assert client.get('/health/ia', headers=AUTH).status_code == 200
        assert client.get('/health/ia', headers=AUTH).status_code == 200
        assert reader.calls == 1
        created = client.post('/api/expedientes', headers=AUTH, files=FILES)
        assert created.status_code == 201
        path = '/api/expedientes/' + created.json()['id']
        assert client.get(path, headers=AUTH).json() == created.json()
        assert client.get('/health').headers['strict-transport-security'] == 'max-age=31536000'

def test_auth_limits_do_not_block_health_or_capabilities_and_ignore_forwarded_spoof(tmp_path):
    app = create_app(configured(tmp_path, auth_rate_limit_enabled=True, auth_failures_per_window=2), Reader())
    with TestClient(app) as client:
        for _ in range(2):
            assert client.get('/api/tupa/procedimientos').status_code == 401
        response = client.get('/api/tupa/procedimientos', headers={**AUTH, 'X-Forwarded-For': 'other'})
        assert response.status_code == 429 and response.headers['retry-after'] == '60'
        assert client.get('/health').status_code == 200
        assert client.get('/api/capacidades').status_code == 200

def test_ocr_quota_and_concurrency_release_after_failure(tmp_path):
    app = create_app(configured(tmp_path, ocr_limits_enabled=True, ocr_requests_per_window=2), Reader())
    with TestClient(app) as client:
        assert client.post('/api/expedientes', files=FILES).status_code == 401
        assert client.post('/api/expedientes', files=FILES, headers=AUTH).status_code == 201
        assert client.post('/api/expedientes', files=FILES, headers=AUTH).status_code == 429
        assert client.get('/health').status_code == 200

def test_ocr_concurrency_is_enforced(tmp_path):
    entered, release = Event(), Event()
    class WaitingReader(Reader):
        def extract(self, content):
            entered.set()
            assert release.wait(timeout=5)
            return super().extract(content)
    app = create_app(configured(tmp_path, ocr_limits_enabled=True, ocr_max_concurrent=1), WaitingReader())
    with TestClient(app) as client, ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(client.post, '/api/expedientes', files=FILES, headers=AUTH)
        try:
            assert entered.wait(timeout=5)
            assert client.post('/api/expedientes', files=FILES, headers=AUTH).status_code == 429
        finally:
            release.set()
        assert future.result().status_code == 201
        assert client.post('/api/expedientes', files=FILES, headers=AUTH).status_code == 201

def test_tokens_rotate_without_cutoff_and_expired_tokens_are_denied(tmp_path):
    new, expired = 'n' * 40, 'e' * 40
    settings = configured(tmp_path, reviewer_tokens=[{'token': new},
        {'token': expired, 'expires_at': datetime.now(timezone.utc) - timedelta(seconds=1)}])
    with TestClient(create_app(settings, Reader())) as client:
        for value, status in [(TOKEN, 200), (new, 200), (expired, 401)]:
            assert client.get('/api/tupa/procedimientos', headers={'Authorization': 'Bearer ' + value}).status_code == status
    expired_legacy = settings.model_copy(update={'reviewer_token_expires_at': datetime.now(timezone.utc) - timedelta(seconds=1)})
    with TestClient(create_app(expired_legacy, Reader())) as client:
        assert client.get('/api/tupa/procedimientos', headers=AUTH).status_code == 401

def test_individual_accounts_isolate_non_demo_dossiers_without_restricting_legacy(tmp_path):
    settings = configured(tmp_path, individual_accounts_enabled=True, academic_accounts=[
        {'id': 'persona-uno', 'role': 'evaluador', 'token': 'a' * 40},
        {'id': 'persona-dos', 'role': 'evaluador', 'token': 'b' * 40},
        {'id': 'admin-personas', 'role': 'administrador', 'token': 'c' * 40},
    ])
    with TestClient(create_app(settings, Reader())) as client:
        caps = client.get('/api/capacidades').json()
        assert not caps['demo'] and caps['seguridad']['cuentas_individuales']
        assert 'predicciones_academicas' not in caps
        one, two, admin = [{'Authorization': 'Bearer ' + token * 40} for token in ['a', 'b', 'c']]
        assert client.get('/api/sesion', headers=one).json()['id'] == 'persona-uno'
        assert client.get('/api/sesion').status_code == 401
        created = client.post('/api/expedientes', files=FILES, headers=one)
        assert created.status_code == 201  # No fictional marker requirement outside academic mode.
        path = '/api/expedientes/' + created.json()['id']
        assert client.get(path, headers=one).status_code == 200
        assert client.get(path, headers=two).status_code == 404
        assert client.get(path, headers=AUTH).status_code == 404
        assert client.get(path, headers=admin).status_code == 200
        assert client.post('/api/expedientes', files=FILES, headers=admin).status_code == 403
        old = client.post('/api/expedientes', files=FILES, headers=AUTH).json()
        assert client.get('/api/expedientes/' + old['id'], headers=AUTH).status_code == 200

def test_security_logs_never_include_ocr_credentials_or_query(tmp_path, caplog):
    caplog.set_level('INFO', logger=logger.name)
    app = create_app(configured(tmp_path, security_events_enabled=True), Reader())
    with TestClient(app) as client:
        assert client.get('/api/tupa/procedimientos?dni=12345678', headers={'Authorization': 'Bearer secreto-invalido'}).status_code == 401
        created = client.post('/api/expedientes', files=FILES, headers=AUTH).json()
        assert client.get('/api/expedientes/' + created['id'], headers=AUTH).status_code == 200
    events = [json.loads(r.getMessage().removeprefix('security_event ')) for r in caplog.records if r.name == logger.name]
    assert any(e['event'] == 'authentication_failed' for e in events)
    assert any(e.get('dossier_id') == created['id'] and e['actor'] == 'evaluador-test' for e in events)
    encoded = json.dumps(events)
    for secret in [TOKEN, 'secreto-invalido', '12345678', 'FORMULARIO', 'ficticio.pdf']:
        assert secret not in encoded

def test_dual_read_encryption_rotation_tampering_and_missing_key(tmp_path):
    first, second = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    plain_id, secure_id = str(uuid4()), str(uuid4())
    plain = LocalFileStorage(str(tmp_path))
    plain.save(plain_id, b'%PDF-legacy')
    encrypted = LocalFileStorage(str(tmp_path), True, [first])
    encrypted.save(secure_id, b'%PDF-secure')
    assert b'%PDF-secure' not in (tmp_path / (secure_id + '.pdf.enc')).read_bytes()
    assert encrypted.read(plain_id) == b'%PDF-legacy'
    assert LocalFileStorage(str(tmp_path), True, [second, first]).read(secure_id) == b'%PDF-secure'
    with pytest.raises(ProcessingUnavailable):
        plain.read(secure_id)
    with pytest.raises(FileExistsError):
        encrypted.save(secure_id, b'replace')
    (tmp_path / (secure_id + '.pdf.enc')).write_bytes(b'OWASP-PDF-v1\ninvalid')
    with pytest.raises(ProcessingUnavailable):
        encrypted.read(secure_id)
    assert plain.read(plain_id) == b'%PDF-legacy'
    with pytest.raises(ValueError):
        plain.read('../escape')

def test_limiter_memory_is_bounded_and_expiry_recovers(monkeypatch):
    clock = [10]
    monkeypatch.setattr('src.infrastructure.adapters.input.hardening.monotonic', lambda: clock[0])
    limiter = WindowCounter(60, 1)
    assert limiter.check('one', 2, consume=True)
    assert not limiter.check('two', 2, consume=True)
    clock[0] += 61
    assert limiter.check('two', 2, consume=True)


def test_original_integrity_is_checked_before_download(tmp_path):
    from scripts.academic_examples import demo_pdf
    from src.infrastructure.adapters.output.ocr import PDFReader
    app = create_app(configured(tmp_path), PDFReader(30, 150, .65))
    with TestClient(app) as client:
        created = client.post('/api/expedientes', headers=AUTH,
                              files={'archivo': ('test.pdf', demo_pdf(), 'application/pdf')}).json()
        path = '/api/expedientes/' + created['id'] + '/documentos/0/pdf'
        assert client.get(path, headers=AUTH).status_code == 200
        (tmp_path / 'pdf' / (created['id'] + '.pdf')).write_bytes(demo_pdf(missing='pago'))
        assert client.get(path, headers=AUTH).status_code == 503


def test_ciphertext_cannot_be_swapped_between_dossiers(tmp_path):
    key = Fernet.generate_key().decode()
    storage = LocalFileStorage(str(tmp_path), True, [key])
    first, second = str(uuid4()), str(uuid4())
    storage.save(first, b'%PDF-first')
    storage.save(second, b'%PDF-second')
    (tmp_path / (second + '.pdf.enc')).write_bytes((tmp_path / (first + '.pdf.enc')).read_bytes())
    with pytest.raises(ProcessingUnavailable, match='otro expediente'):
        storage.read(second)


@pytest.mark.parametrize('provider', ['openai', 'gemini'])
def test_outgoing_hosts_remain_fixed_and_redirects_are_not_followed(provider):
    import httpx
    from src.domain.workflow import DependencyUnavailable
    from src.infrastructure.adapters.output.openai_drafts import OpenAIDraftGenerator
    from src.infrastructure.adapters.output.gemini_drafts import GeminiDraftGenerator
    seen = []
    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(302, headers={'Location': 'http://169.254.169.254/private'})
    generator = (OpenAIDraftGenerator if provider == 'openai' else GeminiDraftGenerator)(
        'ficticio', 'gemini-test' if provider == 'gemini' else 'model-test', transport=httpx.MockTransport(handler))
    with pytest.raises(DependencyUnavailable):
        generator.generate({'url': 'http://127.0.0.1/private', 'callback_url': 'http://169.254.169.254/'})
    assert seen == (['https://api.openai.com/v1/responses'] if provider == 'openai' else
                    ['https://generativelanguage.googleapis.com/v1beta/models/gemini-test:generateContent'])


def test_ocr_account_quota_is_shared_across_origins(tmp_path):
    app = create_app(configured(tmp_path, ocr_limits_enabled=True, ocr_requests_per_window=1), Reader())
    with TestClient(app, client=('origin-one', 123)) as first, TestClient(app, client=('origin-two', 456)) as second:
        assert first.post('/api/expedientes', files=FILES, headers=AUTH).status_code == 201
        response = second.post('/api/expedientes', files=FILES, headers=AUTH)
        assert response.status_code == 429 and response.headers['retry-after'] == '60'
        assert second.get('/api/tupa/procedimientos', headers=AUTH).status_code == 200
