"""Demostración universitaria completa: datos sintéticos y servicios explícitamente simulados."""
from pathlib import Path
import json
import pytest
from fastapi.testclient import TestClient
from scripts.academic_examples import demo_pdf, low_dpi_pdf
from src.infrastructure.main import create_app
from src.infrastructure.settings import Settings

TOKEN = 'demo-solo-tests-' + 'x' * 40
AUTH = {'Authorization': 'Bearer ' + TOKEN}


@pytest.fixture
def settings(tmp_path):
    return Settings(database_url=f"sqlite:///{tmp_path / 'academic.sqlite'}", storage_dir=str(tmp_path / 'pdf'),
                    academic_demo=True, protect_dossier_routes=True, reviewer_id='evaluador-demo', reviewer_token=TOKEN)


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as client:
        yield client


def upload(client, content=None):
    result = client.post('/api/expedientes', headers=AUTH,
                         files={'archivo': ('ficticio.pdf', content or demo_pdf(), 'application/pdf')})
    assert result.status_code == 201, result.text
    return result.json()['id']


def audit(client, dossier_id, code='PA12115285'):
    return client.post(f'/api/expedientes/{dossier_id}/validacion', headers=AUTH,
                       json={'codigo_tupa': code, 'revision': 0, 'verificaciones': {}})


def test_academic_approval_versions_routing_and_simulated_receipts_persist(client, settings):
    dossier_id = upload(client)
    flow_path = f'/api/expedientes/{dossier_id}/flujo'
    first = audit(client, dossier_id)
    assert first.status_code == 200, first.text
    flow = first.json()
    assert flow['demo'] is True and flow['validation']['simulado'] is True
    assert flow['validation']['estado'] == 'CONFORME'
    assert flow['drafts'][-1]['tipo'] == 'PROYECTO'
    second = client.post(f'/api/expedientes/{dossier_id}/borradores', headers=AUTH,
                         json={'revision': 1, 'contenido': flow['drafts'][0]['contenido'] + '\nCorrección del evaluador.'}).json()
    assert len(second['drafts']) == 2 and second['drafts'][0]['vigente'] is False
    routed = client.post(f'/api/expedientes/{dossier_id}/enrutamiento', headers=AUTH, json={'revision': 2}).json()
    assert routed['routing']['confianza'] > 0.85
    assert routed['routing']['estado'] == 'DERIVADO_LOCAL'
    assert routed['routing']['simulado'] is True
    emitted = client.post(f'/api/expedientes/{dossier_id}/aprobar-firmar', headers=AUTH, json={'revision': 3})
    assert emitted.status_code == 200, emitted.text
    final = emitted.json()
    draft = final['drafts'][-1]
    assert draft['estado'] == 'EMITIDO_DEMO' and draft['validez_legal'] is False
    assert draft['firma']['tipo'] == 'FIRMA_SIMULADA'
    assert draft['firma']['firmante'] == 'evaluador-demo'
    assert draft['sisgedoc']['registro'].startswith('DEMO-')
    assert draft['sisgedoc']['transmision_externa'] is False
    assert draft['notificacion']['envio_real'] is False
    assert final['audit'][-1]['action'] == 'EMISION_SIMULADA'
    duplicate = client.post(f'/api/expedientes/{dossier_id}/aprobar-firmar', headers=AUTH, json={'revision': 4})
    assert duplicate.json() == final
    assert client.post(f'/api/expedientes/{dossier_id}/borradores', headers=AUTH,
                       json={'revision': 4, 'contenido': 'No debe alterar el emitido.'}).status_code == 409
    with TestClient(create_app(settings)) as restarted:
        assert restarted.get(flow_path, headers=AUTH).json() == final


@pytest.mark.parametrize('missing,unsigned,requirement', [('pago', False, 'pago'), (None, True, 'plano_firmado')])
def test_academic_missing_evidence_automatically_creates_observation(client, missing, unsigned, requirement):
    dossier_id = upload(client, demo_pdf(missing=missing, unsigned=unsigned))
    flow = audit(client, dossier_id).json()
    assert flow['validation']['estado'] == 'OBSERVADO'
    assert flow['validation']['alertas'][0]['requisito'] == requirement
    assert flow['drafts'][0]['tipo'] == 'OBSERVACION'
    assert client.post(f'/api/expedientes/{dossier_id}/aprobar-firmar', headers=AUTH, json={'revision': 1}).status_code == 409


def test_academic_ambiguous_subject_is_manual_and_can_be_assigned(client):
    dossier_id = upload(client, demo_pdf(ambiguous=True))
    assert audit(client, dossier_id).json()['validation']['estado'] == 'CONFORME'
    routed = client.post(f'/api/expedientes/{dossier_id}/enrutamiento', headers=AUTH, json={'revision': 1}).json()
    assert routed['routing']['estado'] == 'CLASIFICACION_MANUAL'
    assert routed['routing']['confianza'] < 0.85 and routed['routing']['alerta'] is True
    assigned = client.post(f'/api/expedientes/{dossier_id}/asignacion', headers=AUTH,
                           json={'revision': 2, 'destino': 'Gerencia de Desarrollo Urbano'}).json()
    assert assigned['routing']['origen'] == 'ASIGNACION_HUMANA'


@pytest.mark.parametrize('code,department', [
    ('PA121121B0', 'Sub Gerencia de Planes y Cooperación Técnica Internacional'),
    ('PE1027344C1', 'Gerencia de Promoción Económica y Turismo'),
])
def test_demo_catalog_procedures_keep_their_source_departments(client, code, department):
    dossier_id = upload(client, demo_pdf(code))
    flow = audit(client, dossier_id, code).json()
    assert flow['validation']['estado'] == 'CONFORME'
    routed = client.post(f'/api/expedientes/{dossier_id}/enrutamiento', headers=AUTH, json={'revision': 1}).json()
    assert routed['routing']['destino'] == department
    assert routed['routing']['confianza'] > 0.85


def test_demo_low_resolution_has_the_original_error(client):
    result = client.post('/api/expedientes', headers=AUTH,
                         files={'archivo': ('ficticio.pdf', low_dpi_pdf(), 'application/pdf')})
    assert result.status_code == 422
    assert result.json()['detail']['mensaje'] == 'Documento ilegible, por favor vuelva a cargar el archivo'


def test_demo_capabilities_never_claim_real_integrations(client):
    data = client.get('/api/capacidades').json()
    assert data['demo'] is True and data['simulaciones']['habilitadas'] is True
    assert not any(data['integraciones'].values())
    assert client.get('/api/tupa/procedimientos').status_code == 401


def test_demo_auditor_refuses_unmarked_documents(client):
    import pymupdf
    with pymupdf.open() as pdf:
        pdf.new_page().insert_text((45, 80), 'FORMULARIO UNICO DE TRAMITE\nSOLICITO: Certificado')
        content = pdf.tobytes()
    dossier_id = upload(client, content)
    response = audit(client, dossier_id)
    assert response.status_code == 422 and 'EXPEDIENTE FICTICIO' in response.text
    assert client.get(f'/api/expedientes/{dossier_id}/flujo', headers=AUTH).json()['revision'] == 0


def test_source_verification_matches_catalog_sha_and_pages():
    root = Path(__file__).parents[1] / 'config'
    verification = json.loads((root / 'tupa_source_verification.json').read_text(encoding='utf-8'))
    catalog = json.loads((root / 'tupa_huancayo.json').read_text(encoding='utf-8'))
    assert verification['sha256'] == catalog['source_sha256']
    assert verification['paginas'] == 605
    assert {p['codigo'] for p in verification['procedimientos']} == {p['code'] for p in catalog['procedures']}
