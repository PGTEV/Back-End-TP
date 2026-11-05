"""Regresiones de las funciones propias del backend desplegado en Render."""
import pytest
from fastapi.testclient import TestClient
from src.infrastructure.adapters.output.database import normalize_database_url
from src.infrastructure.main import create_app
from src.infrastructure.settings import Settings


@pytest.mark.parametrize('scheme', ['postgres', 'postgresql', 'postgresql+psycopg'])
def test_cloud_database_url_retains_psycopg_and_ssl(scheme):
    url = normalize_database_url(f'{scheme}://test:fake-password@pooler.example:5432/postgres')
    assert url.drivername == 'postgresql+psycopg'
    assert url.query['sslmode'] == 'require'
    assert url.host == 'pooler.example'


def test_health_diagnostics_preserved_with_protected_dossiers(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'health.sqlite'}",
                        storage_dir=str(tmp_path / 'pdf'), protect_dossier_routes=True)
    with TestClient(create_app(settings)) as client:
        assert client.get('/health').json() == {'estado': 'ok'}
        database = client.get('/health/db')
        assert database.status_code == 200
        assert database.json()['motor'] == 'sqlite'
        ocr = client.get('/health/ia')
        assert ocr.status_code == 200, ocr.text
        assert ocr.json()['modelo'] == 'PP_OCR_ONNX'
        assert ocr.json()['confianza'] >= settings.min_ocr_confidence
