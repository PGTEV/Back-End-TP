import json
from uuid import uuid4
from pathlib import Path
import pymupdf
import pytest
from fastapi.testclient import TestClient
from src.domain.entities import Document, Dossier
from src.domain.intake import protect_and_compare
from src.domain.privacy import LocalPrivacyFilter
from src.application.useCases import GetDossier
from src.infrastructure.adapters.output.database import SQLDossierRepository
from src.infrastructure.main import create_app
from src.infrastructure.settings import Settings
from scripts.academic_examples import demo_pdf

TOKEN = 'solo-pruebas-privacidad-' + 'x' * 40
AUTH = {'Authorization': 'Bearer ' + TOKEN}


def content(dni_receipt='11111111', ruc_receipt='20111111111', demo=False):
    texts = [
        'FORMULARIO UNICO DE TRAMITE\nDNI: 11111111\nRUC: 20111111111\n'
        'NOMBRES: Persona Ficticia Alfa\nDOMICILIO: Avenida de Prueba 123\n'
        'TELEFONO: 999000111\nCORREO: persona@example.invalid\nSOLICITO: certificado\nEVIDENCIA DEMO: solicitud',
        'DOCUMENTO NACIONAL DE IDENTIDAD\nRENIEC\nDNI: 11111111\nNOMBRES: Persona Ficticia Alfa\nEVIDENCIA DEMO: identidad',
        'PLANO DE UBICACION\nESCALA: 1:500\nLAMINA: U01\nEVIDENCIA DEMO: plano_firmado\nFIRMA DEMO: PROFESIONAL FICTICIO',
        f'RECIBO DE PAGO\nIMPORTE: 10.00\nDNI: {dni_receipt}\nRUC: {ruc_receipt}\nEVIDENCIA DEMO: pago',
    ]
    with pymupdf.open() as pdf:
        pdf.set_metadata({'author': 'Autor Ficticio Original'})
        for text in texts:
            pdf.new_page().insert_text((45, 60), ('EXPEDIENTE FICTICIO\n' if demo else '') + text, fontsize=12)
        return pdf.tobytes(deflate=True)


@pytest.fixture
def settings(tmp_path):
    return Settings(database_url=f"sqlite:///{tmp_path / 'intake.sqlite'}", storage_dir=str(tmp_path / 'pdf'),
                    protect_dossier_routes=True, reviewer_token=TOKEN, reviewer_id='evaluador-prueba')


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as client:
        yield client


def upload(client, **kwargs):
    result = client.post('/api/expedientes', headers=AUTH,
                         files={'archivo': ('ficticio.pdf', content(**kwargs), 'application/pdf')})
    assert result.status_code == 201, result.text
    assert result.headers['cache-control'] == 'no-store'
    return result.json()


def test_privacy_is_prepared_on_ingress_and_consistent_across_annexes(client):
    data = upload(client)
    assert [d['tipo'] for d in data['documentos']] == ['FUT', 'DNI', 'PLANO', 'RECIBO_PAGO']
    protected = data['privacidad']
    assert protected['transmision_externa_habilitada'] is False
    assert protected['anonimizacion_garantizada'] is False
    serialized = json.dumps(protected, ensure_ascii=False)
    for value in ['11111111', '20111111111', 'Persona Ficticia Alfa', 'Avenida de Prueba 123', '999000111', 'persona@example.invalid']:
        assert value not in serialized
    tokens = [protected['documentos'][i]['campos']['dni'] for i in [0, 1, 3]]
    assert tokens == ['[DNI_1]'] * 3
    assert data['consistencia']['estado'] == 'SIN_CONTRADICCIONES_DETECTADAS'
    assert data['consistencia']['fraude_determinado'] is False
    assert data['documentos'][0]['campos']['dni'] == '11111111'  # Original solo en circuito autorizado.
    queried = client.get(f"/api/expedientes/{data['id']}", headers=AUTH)
    assert queried.headers['cache-control'] == 'no-store'
    assert queried.json() == data


def test_conflicting_dni_and_ruc_alerts_do_not_disclose_values(client):
    data = upload(client, dni_receipt='22222222', ruc_receipt='20222222222')
    report = data['consistencia']
    assert report['estado'] == 'REQUIERE_REVISION'
    assert {a['codigo'] for a in report['alertas']} == {'DNI_DIFIERE_ENTRE_ANEXOS', 'RUC_DIFIERE_ENTRE_ANEXOS'}
    assert report['requiere_revision_humana'] is True and report['fraude_determinado'] is False
    assert '22222222' not in json.dumps(report)
    dni_alert = next(a for a in report['alertas'] if a['campo'] == 'dni')
    assert dni_alert['fuentes'][-1]['paginas'] == [4]
    assert dni_alert['fuentes'][-1]['valor_protegido'] == '[DNI_2]'


def test_cross_conflict_prevents_false_conforme_even_with_all_human_checks(client):
    data = upload(client, dni_receipt='22222222')
    checks = {key: {'estado': 'CUMPLE', 'nota': 'Revisión ficticia.', 'paginas': []}
              for key in ['solicitud', 'identidad', 'plano_firmado', 'pago']}
    result = client.post(f"/api/expedientes/{data['id']}/validacion", headers=AUTH,
                         json={'codigo_tupa': 'PA12115285', 'revision': 0, 'verificaciones': checks})
    assert result.status_code == 200, result.text
    flow = result.json()
    assert flow['validation']['estado'] == 'PENDIENTE_REVISION'
    assert flow['validation']['habilitado_enrutamiento'] is False
    assert flow['validation']['inconsistencias_cruzadas']
    assert flow['drafts'][-1]['tipo'] == 'OBSERVACION'
    assert client.post(f"/api/expedientes/{data['id']}/enrutamiento", headers=AUTH, json={'revision': 1}).status_code == 409


def test_conflict_also_blocks_academic_automatic_approval(settings):
    settings.academic_demo = True
    with TestClient(create_app(settings)) as client:
        data = upload(client, dni_receipt='22222222', demo=True)
        flow = client.post(f"/api/expedientes/{data['id']}/validacion", headers=AUTH,
                           json={'codigo_tupa': 'PA12115285', 'revision': 0, 'verificaciones': {}}).json()
        assert flow['validation']['estado'] == 'PENDIENTE_REVISION'
        assert client.post(f"/api/expedientes/{data['id']}/aprobar-firmar", headers=AUTH, json={'revision': 1}).status_code == 409


def test_downloadable_academic_example_demonstrates_receipt_conflict(settings):
    settings.academic_demo = True
    with TestClient(create_app(settings)) as client:
        result = client.post('/api/expedientes', headers=AUTH,
            files={'archivo': ('ejemplo-08.pdf', demo_pdf(dni_conflict=True), 'application/pdf')})
        data = result.json()
        assert result.status_code == 201
        assert data['documentos'][-1]['tipo'] == 'RECIBO_PAGO'
        assert data['consistencia']['estado'] == 'REQUIERE_REVISION'
        flow = client.post(f"/api/expedientes/{data['id']}/validacion", headers=AUTH,
            json={'codigo_tupa': 'PA12115285', 'revision': 0, 'verificaciones': {}}).json()
        assert flow['validation']['estado'] == 'PENDIENTE_REVISION'


def test_pdf_segment_contains_only_selected_page_and_requires_authorization(client):
    data = upload(client)
    url = f"/api/expedientes/{data['id']}/documentos/3/pdf"
    assert client.get(url).status_code == 401
    response = client.get(url, headers=AUTH)
    assert response.status_code == 200
    assert response.headers['content-type'] == 'application/pdf'
    assert response.headers['cache-control'] == 'no-store'
    with pymupdf.open(stream=response.content, filetype='pdf') as pdf:
        assert len(pdf) == 1
        assert 'RECIBO DE PAGO' in pdf[0].get_text()
        assert 'FORMULARIO UNICO' not in pdf[0].get_text()
        assert not pdf.metadata['author']
    assert client.get(f"/api/expedientes/{data['id']}/documentos/99/pdf", headers=AUTH).status_code == 404
    assert client.get(f"/api/expedientes/{data['id']}/documentos/-1/pdf", headers=AUTH).status_code == 404
    assert client.get(f'/api/expedientes/{uuid4()}/documentos/0/pdf', headers=AUTH).status_code == 404


def test_missing_original_reports_404_without_fabricating_a_pdf(client, settings):
    data = upload(client)
    (Path(settings.storage_dir) / f"{data['id']}.pdf").unlink()
    assert client.get(f"/api/expedientes/{data['id']}/documentos/0/pdf", headers=AUTH).status_code == 404


def test_multiple_roles_and_insufficient_data_are_not_declared_fraud():
    doc = Document('FUT', [1], 'DNI: 11111111\nDNI: 22222222', {'dni': '11111111'}, 1)
    _, report = protect_and_compare([doc])
    assert report['alertas'][0]['codigo'] == 'MULTIPLES_DNI_EN_UN_ANEXO'
    assert report['fraude_determinado'] is False
    _, empty = protect_and_compare([Document('PLANO', [1], 'Plano sin identidad', {}, 1)])
    assert empty['estado'] == 'DATOS_INSUFICIENTES'


def test_unlabelled_names_remain_explicitly_untrusted_for_external_ai():
    result = LocalPrivacyFilter().preview('Texto libre con Persona No Etiquetada', [])
    assert result['transmision_externa_habilitada'] is False
    assert 'Persona No Etiquetada' in result['texto_enmascarado']
    assert 'no anonimización garantizada' in result['advertencia']


def test_legacy_payload_is_readable_and_protected_without_schema_migration(settings):
    repository = SQLDossierRepository(settings.database_url)
    dossier = Dossier(str(uuid4()), 'ficticio.pdf', 'sha', status='PROCESADO', documents=[
        Document('DNI', [1], 'DNI: 11111111', {'dni': '11111111'}, 1)])
    repository.save(dossier)
    with repository.engine.begin() as connection:
        row = connection.execute(repository.table.select()).first()
        payload = dict(row.payload)
        payload.pop('privacy'); payload.pop('consistency')
        connection.execute(repository.table.update().values(payload=payload))
    try:
        loaded = GetDossier(repository).execute(dossier.id)
        assert loaded.privacy['documentos'][0]['campos']['dni'] == '[DNI_1]'
    finally:
        repository.engine.dispose()
