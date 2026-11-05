"""Aceptación reproducible con documentos sintéticos; no certifica validez legal ni modelos."""
from pathlib import Path
import pymupdf
import pytest
from fastapi.testclient import TestClient
from test_backend import pdf_bytes
from src.application.workflow import MunicipalWorkflow
from src.domain.privacy import LocalPrivacyFilter
from src.domain.workflow import RoutingPrediction
from src.infrastructure.adapters.output.database import SQLDossierRepository
from src.infrastructure.adapters.output.workflow import JSONProcedureCatalog, SQLWorkflowRepository, UnavailableAdministrativeGateway
from src.infrastructure.main import create_app
from src.infrastructure.settings import Settings

TOKEN = 'solo-pruebas-pmv-' + 'x' * 40
AUTH = {'Authorization': 'Bearer ' + TOKEN}
TEXTS = ['FORMULARIO UNICO DE TRAMITE\nASUNTO: Parámetros urbanísticos\nSOLICITO: Certificado\nDNI: 12345678',
         'DOCUMENTO NACIONAL DE IDENTIDAD\nRENIEC\nDNI: 12345678',
         'PLANO DE UBICACION\nESCALA: 1:500\nLAMINA: U01\nFIRMA: Prueba de texto, no firma verificada']


@pytest.fixture
def settings(tmp_path):
    return Settings(database_url=f"sqlite:///{tmp_path / 'pmv.sqlite'}", storage_dir=str(tmp_path / 'pdf'),
                    protect_dossier_routes=True, reviewer_id='evaluador-pmv', reviewer_token=TOKEN)


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as client:
        yield client


def upload(client, content=None):
    result = client.post('/api/expedientes', headers=AUTH,
                         files={'archivo': ('ficticio.pdf', content or pdf_bytes(TEXTS), 'application/pdf')})
    assert result.status_code == 201, result.text
    return result.json()['id']


def validation(client, dossier_id, checks=None, revision=0):
    return client.post(f'/api/expedientes/{dossier_id}/validacion', headers=AUTH,
                       json={'codigo_tupa': 'PA12115285', 'revision': revision, 'verificaciones': checks or {}})


def checks():
    return {key: {'estado': 'CUMPLE', 'nota': 'Verificación ficticia para prueba, sin efecto legal.', 'paginas': []}
            for key in ['solicitud', 'identidad', 'plano_firmado', 'pago']}


@pytest.mark.parametrize('dpi', [72, 149, 149.8])
def test_effective_dpi_strictly_below_150_stops_processing(client, dpi):
    with pymupdf.open(stream=pdf_bytes(TEXTS[:1]), filetype='pdf') as source:
        pixels = source[0].get_pixmap(dpi=150)
    with pymupdf.open() as scanned:
        page = scanned.new_page(width=pixels.width * 72 / dpi, height=pixels.height * 72 / dpi)
        page.insert_image(page.rect, stream=pixels.tobytes('png'))
        content = scanned.tobytes(deflate=True)
    result = client.post('/api/expedientes', headers=AUTH,
                         files={'archivo': ('dpi.pdf', content, 'application/pdf')})
    assert result.status_code == 422
    detail = result.json()['detail']
    assert detail['mensaje'] == 'Documento ilegible, por favor vuelva a cargar el archivo'
    saved = client.get(f"/api/expedientes/{detail['id']}", headers=AUTH).json()
    assert saved['estado'] == 'ILEGIBLE' and saved['documentos'] == []


def test_ocr_presence_does_not_validate_signature_or_payment(client):
    dossier_id = upload(client)
    result = validation(client, dossier_id).json()
    assert result['validation']['estado'] == 'PENDIENTE_REVISION'
    assert result['validation']['habilitado_enrutamiento'] is False
    assert all(r['estado'] == 'PENDIENTE' for r in result['validation']['requisitos'])
    assert client.post(f'/api/expedientes/{dossier_id}/enrutamiento', headers=AUTH, json={'revision': 1}).status_code == 409
    integrations = client.get('/api/capacidades').json()['integraciones']
    assert not any(integrations.values())


def test_missing_payment_alert_and_observation_editor_keep_versions(client, settings):
    dossier_id = upload(client)
    review = checks()
    review['pago'] = {'estado': 'FALTA', 'nota': 'No se acreditó el pago en esta prueba.', 'paginas': [1, 2, 3]}
    first = validation(client, dossier_id, review).json()
    assert first['validation']['estado'] == 'OBSERVADO'
    assert first['validation']['alertas'][0]['requisito'] == 'pago'
    assert 'No se acreditó el pago' in first['drafts'][0]['contenido']
    assert '1, 2, 3' in first['drafts'][0]['contenido']
    edited = client.post(f'/api/expedientes/{dossier_id}/borradores', headers=AUTH,
                         json={'revision': 1, 'contenido': 'Esquela corregida por el evaluador.'})
    assert edited.status_code == 201
    second = edited.json()
    assert second['drafts'][0]['contenido'] == first['drafts'][0]['contenido']
    assert second['drafts'][0]['vigente'] is False
    assert second['drafts'][1]['tipo'] == 'OBSERVACION'
    assert second['audit'][-1]['detail'] == {'version': 2, 'version_anterior': 1, 'tipo': 'OBSERVACION'}
    assert second['audit'][-1]['actor'] == 'evaluador-pmv'
    stale = client.post(f'/api/expedientes/{dossier_id}/borradores', headers=AUTH,
                        json={'revision': 1, 'contenido': 'Edición obsoleta que no debe guardarse.'})
    assert stale.status_code == 409
    with TestClient(create_app(settings)) as restarted:
        assert restarted.get(f'/api/expedientes/{dossier_id}/flujo', headers=AUTH).json() == second


def test_conforme_routes_manually_but_never_emits_an_administrative_act(client, settings):
    dossier_id = upload(client)
    result = validation(client, dossier_id, checks()).json()
    assert result['validation']['estado'] == 'CONFORME'
    assert result['validation']['habilitado_enrutamiento'] is True
    draft = client.post(f'/api/expedientes/{dossier_id}/borradores', headers=AUTH,
                        json={'revision': 1, 'contenido': 'Proyecto técnico de prueba; sin validez administrativa.'}).json()
    assert draft['drafts'][-1]['tipo'] == 'PROYECTO'
    routed = client.post(f'/api/expedientes/{dossier_id}/enrutamiento', headers=AUTH, json={'revision': 2}).json()
    assert routed['routing']['estado'] == 'CLASIFICACION_MANUAL'
    assert routed['routing']['alerta'] is True and routed['routing']['confianza'] is None
    assigned = client.post(f'/api/expedientes/{dossier_id}/asignacion', headers=AUTH,
                           json={'revision': 3, 'destino': 'Gerencia de Desarrollo Urbano'}).json()
    assert assigned['routing']['estado'] == 'DERIVADO_LOCAL'
    assert assigned['routing']['origen'] == 'ASIGNACION_HUMANA'
    assert client.post(f'/api/expedientes/{dossier_id}/aprobar-firmar', headers=AUTH, json={'revision': 4}).status_code == 503
    assert client.get(f'/api/expedientes/{dossier_id}/flujo', headers=AUTH).json() == assigned
    with TestClient(create_app(settings)) as restarted:
        assert restarted.get(f'/api/expedientes/{dossier_id}/flujo', headers=AUTH).json() == assigned


def test_new_conforme_validation_does_not_turn_old_observation_into_new_observation(client):
    dossier_id = upload(client)
    missing = checks()
    missing['pago'] = {'estado': 'FALTA', 'nota': 'Pendiente de acreditar.', 'paginas': []}
    assert validation(client, dossier_id, missing).json()['drafts'][-1]['tipo'] == 'OBSERVACION'
    conform = validation(client, dossier_id, checks(), revision=1).json()
    assert conform['drafts'][-1]['vigente'] is False
    project = client.post(f'/api/expedientes/{dossier_id}/borradores', headers=AUTH,
                          json={'revision': 2, 'contenido': 'Nuevo proyecto revisado.'}).json()
    assert project['drafts'][0]['tipo'] == 'OBSERVACION'
    assert project['drafts'][1]['tipo'] == 'PROYECTO'


@pytest.mark.parametrize('confidence,expected', [(0.86, 'DERIVADO_LOCAL'), (0.85, 'CLASIFICACION_MANUAL'), (0.84, 'CLASIFICACION_MANUAL')])
def test_routing_threshold_in_workflow_with_test_double(client, settings, confidence, expected):
    # Únicamente prueba la orquestación del puerto, no entrena ni valida un modelo real.
    class ModelForTest:
        def predict(self, dossier):
            return RoutingPrediction('Gerencia de Desarrollo Urbano', confidence, 'DOBLE_SOLO_PRUEBAS')

    dossier_id = upload(client)
    assert validation(client, dossier_id, checks()).status_code == 200
    repository = SQLDossierRepository(settings.database_url)
    catalog = JSONProcedureCatalog(Path(__file__).parents[1] / 'config/tupa_huancayo.json')
    service = MunicipalWorkflow(repository, SQLWorkflowRepository(repository.engine), catalog,
                                ModelForTest(), UnavailableAdministrativeGateway(), LocalPrivacyFilter())
    try:
        result = service.route(dossier_id, 1, 'evaluador-pmv')
        assert result.routing['estado'] == expected
        assert result.routing['alerta'] is (confidence <= 0.85)
        assert service.get(dossier_id).routing == result.routing
    finally:
        repository.engine.dispose()
