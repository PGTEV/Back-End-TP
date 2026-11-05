"""Contratos usados por React y compatibilidad del modo público local."""
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from src.domain.valueObjects import Page
from src.infrastructure.main import create_app
from src.infrastructure.settings import Settings

TOKEN = "credencial-ficticia-de-pruebas-" + "x" * 32
AUTH = {"Authorization": "Bearer " + TOKEN}


class Reader:
    def extract(self, content):
        return [Page(1, "FORMULARIO UNICO DE TRAMITE\nDNI: 12345678", 1, "TEXTO_PDF")]


def configuration(tmp_path, **overrides):
    return Settings(database_url=f"sqlite:///{tmp_path / 'db.sqlite'}", storage_dir=str(tmp_path / 'pdf'),
                    reviewer_token=TOKEN, reviewer_id="evaluador-test", **overrides)


@pytest.mark.parametrize("protected", [False, True])
def test_existing_routes_and_protected_mode(tmp_path, protected):
    settings = configuration(tmp_path, protect_dossier_routes=protected)
    with TestClient(create_app(settings, reader=Reader())) as client:
        assert client.get('/api/capacidades').json()['seguridad']['expedientes_protegidos'] is protected
        catalog = client.get('/api/tupa/procedimientos')
        assert catalog.status_code == (401 if protected else 200)
        files = {'archivo': ('test.pdf', b'%PDF-test', 'application/pdf')}
        if protected:
            assert client.post('/api/expedientes', files=files).status_code == 401
            assert client.get(f'/api/expedientes/{uuid4()}').status_code == 401
            assert client.get('/api/tupa/procedimientos', headers={'Authorization': 'Bearer invalid'}).status_code == 401
        assert client.get('/api/tupa/procedimientos', headers=AUTH).status_code == 200
        created = client.post('/api/expedientes', files=files, headers=AUTH)
        assert created.status_code == 201
        data = created.json()
        assert data['estado'] == 'PROCESADO'
        assert data['documentos'][0]['metodo_extraccion'] == 'TEXTO_PDF'
        assert client.get(f"/api/expedientes/{data['id']}", headers=AUTH).json() == data
        flow_path = f"/api/expedientes/{data['id']}/flujo"
        assert client.get(flow_path, headers=AUTH).json()['revision'] == 0
        validation = client.post(f"/api/expedientes/{data['id']}/validacion", headers=AUTH,
                                 json={'codigo_tupa': 'PA12115285', 'revision': 0, 'verificaciones': {}})
        assert validation.status_code == 200
        assert validation.json()['validation']['estado'] == 'PENDIENTE_REVISION'
        assert client.get(flow_path, headers=AUTH).json()['revision'] == 1
        assert client.post(f"/api/expedientes/{data['id']}/validacion", headers=AUTH,
                           json={'codigo_tupa': 'PA12115285', 'revision': 0, 'verificaciones': {}}).status_code == 409
    # Reabrir app/BD demuestra persistencia, no una respuesta en memoria.
    with TestClient(create_app(settings, reader=Reader())) as client:
        assert client.get(f"/api/expedientes/{data['id']}", headers=AUTH).json() == data
        assert client.get(flow_path, headers=AUTH).json()['revision'] == 1


def test_protected_mode_without_server_credential_fails_closed(tmp_path):
    settings = configuration(tmp_path, protect_dossier_routes=True)
    settings.reviewer_id = ''
    with TestClient(create_app(settings, reader=Reader())) as client:
        assert client.get('/api/tupa/procedimientos', headers=AUTH).status_code == 503
        assert client.post('/api/expedientes', headers=AUTH).status_code == 503


def test_vercel_preflight_and_disallowed_origin(tmp_path):
    origin = 'https://municipal-test.vercel.app'
    settings = configuration(tmp_path, protect_dossier_routes=True, cors_origins=[origin])
    with TestClient(create_app(settings, reader=Reader())) as client:
        for method in ['GET', 'POST']:
            response = client.options('/api/expedientes', headers={
                'Origin': origin, 'Access-Control-Request-Method': method,
                'Access-Control-Request-Headers': 'authorization,content-type',
            })
            assert response.status_code == 200
            assert response.headers['access-control-allow-origin'] == origin
        response = client.get('/api/tupa/procedimientos', headers={'Origin': origin})
        assert response.status_code == 401
        assert response.headers['access-control-allow-origin'] == origin
        response = client.options('/api/expedientes', headers={
            'Origin': 'https://otro-dominio.example', 'Access-Control-Request-Method': 'POST',
        })
        assert response.status_code == 400
        assert 'access-control-allow-origin' not in response.headers
