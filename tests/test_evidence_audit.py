import json
from copy import deepcopy
import httpx
import pytest
from fastapi.testclient import TestClient
from src.domain.entities import Document
from src.domain.evidence_audit import evidence_facts, validate_ai_audit
from src.domain.workflow import DependencyUnavailable, Procedure, Requirement
from src.infrastructure.main import create_app
from src.infrastructure.settings import Settings
from src.infrastructure.adapters.output.gemini_drafts import GeminiDraftGenerator
from test_intake_privacy_crosscheck import content

TOKEN = 'solo-pruebas-auditoria-' + 'x' * 40
AUTH = {'Authorization': 'Bearer ' + TOKEN}


def findings(facts):
    return [{'requisito': r['id'], 'hallazgo': r['hallazgo_local'],
             'documentos': r['documentos_candidatos'],
             'explicacion': 'Evidencia candidata según categorías; verificar contenido, firmas y pagos con revisión humana.'}
            for r in facts['requisitos']]


@pytest.fixture
def service(tmp_path, monkeypatch):
    state = {'requests': [], 'mutate': lambda result: result, 'status': 200}
    def handler(request):
        body = json.loads(request.content)
        state['requests'].append(body)
        assert 'candidateCount' not in body['generationConfig']
        assert body['generationConfig']['responseJsonSchema']['required'] == ['hallazgos']
        facts = json.loads(body['contents'][0]['parts'][0]['text'])
        payload = state['mutate']({'hallazgos': findings(facts)})
        return httpx.Response(state['status'], json={
            'responseId': 'audit_test', 'modelVersion': 'gemini-test',
            'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': json.dumps(payload)}]}}]})
    adapter = GeminiDraftGenerator('clave-ficticia', 'gemini-test', transport=httpx.MockTransport(handler))
    monkeypatch.setattr('src.infrastructure.main.GeminiDraftGenerator', lambda *args: adapter)
    settings = Settings(_env_file=None, database_url=f'sqlite:///{tmp_path / "db.sqlite"}',
                        storage_dir=str(tmp_path / 'pdf'), ai_provider='gemini',
                        gemini_enabled=True, gemini_api_key='clave-ficticia', gemini_model='gemini-test',
                        protect_dossier_routes=True, reviewer_token=TOKEN, reviewer_id='revisor')
    return settings, state


def prepared(client, **kwargs):
    data = client.post('/api/expedientes', headers=AUTH,
        files={'archivo': ('nombre-personal-privado.pdf', content(**kwargs), 'application/pdf')}).json()
    path = '/api/expedientes/' + data['id']
    response = client.post(path + '/validacion', headers=AUTH,
        json={'codigo_tupa': 'PA12115285', 'revision': 0, 'verificaciones': {}})
    assert response.status_code == 200, response.text
    return path, response.json()


def test_ai_audit_uses_minimized_facts_and_persists_without_modifying_verification(service):
    settings, state = service
    with TestClient(create_app(settings)) as client:
        assert client.get('/api/capacidades').json()['ia_generativa']['auditoria_tupa'] is True
        path, before = prepared(client)
        report = before['validation']['preauditoria_local']
        assert all(r['hallazgo_local'] == 'EVIDENCIA_CANDIDATA' for r in report['requisitos'])
        result = client.post(path + '/auditoria/ia', headers=AUTH, json={'revision': 1})
        assert result.status_code == 201, result.text
        assert result.headers['cache-control'] == 'no-store'
        flow = result.json()
        audit = flow['validation'].pop('auditoria_ia')
        assert flow['validation'] == before['validation']
        flow['validation']['auditoria_ia'] = audit
        assert flow['drafts'] == before['drafts'] and flow['routing'] == before['routing']
        assert audit['proveedor'] == 'GEMINI' and audit['respuesta_id'] == 'audit_test'
        assert audit['transmision'] == {'ocr': False, 'pdf': False, 'valores_personales': False}
        assert audit['fraude_determinado'] is False and audit['requiere_revision_humana'] is True
        assert flow['audit'][-1]['action'] == 'AUDITORIA_IA' and flow['revision'] == 2
        assert next(f for f in audit['hallazgos'] if f['requisito'] == 'pago')['paginas'] == [4]
        outbound = json.dumps(state['requests'])
        for secret in ['11111111', '20111111111', 'Persona Ficticia Alfa', 'Avenida de Prueba 123',
                       '999000111', 'persona@example.invalid', 'nombre-personal-privado', path.split('/')[-1]]:
            assert secret not in outbound
        assert client.post(path + '/auditoria/ia', headers=AUTH, json={'revision': 1}).status_code == 409
        assert len(state['requests']) == 1
    with TestClient(create_app(settings)) as restarted:
        assert restarted.get(path + '/flujo', headers=AUTH).json() == flow


def test_conflict_is_compared_locally_and_never_sent_as_identity_values(service):
    settings, state = service
    with TestClient(create_app(settings)) as client:
        path, before = prepared(client, dni_receipt='22222222')
        result = client.post(path + '/auditoria/ia', headers=AUTH, json={'revision': 1})
        assert result.status_code == 201, result.text
        flow = result.json()
        assert flow['validation']['habilitado_enrutamiento'] is False
        assert flow['validation']['auditoria_ia']['cruce_local']['requiere_revision'] is True
        assert flow['validation']['inconsistencias_cruzadas'] == before['validation']['inconsistencias_cruzadas']
        assert '22222222' not in json.dumps(state['requests'])
        assert client.post(path + '/enrutamiento', headers=AUTH, json={'revision': 2}).status_code == 409


def test_ai_cannot_invent_compliance_or_references_and_failures_preserve_flow(service):
    settings, state = service
    with TestClient(create_app(settings)) as client:
        path, before = prepared(client)
        def mutate(data):
            data['hallazgos'][0]['hallazgo'] = 'CONFORME'
            data['hallazgos'][0]['documentos'] = [999]
            return data
        state['mutate'] = mutate
        result = client.post(path + '/auditoria/ia', headers=AUTH, json={'revision': 1})
        assert result.status_code == 503
        assert client.get(path + '/flujo', headers=AUTH).json() == before
        state['status'] = 429
        assert client.post(path + '/auditoria/ia', headers=AUTH, json={'revision': 1}).status_code == 503
        assert client.get(path + '/flujo', headers=AUTH).json() == before


def test_authentication_prevalidation_and_request_limits(service):
    settings, state = service
    with TestClient(create_app(settings)) as client:
        data = client.post('/api/expedientes', headers=AUTH,
            files={'archivo': ('ficticio.pdf', content(), 'application/pdf')}).json()
        path = '/api/expedientes/' + data['id']
        assert client.post(path + '/auditoria/ia', json={'revision': 0}).status_code == 401
        assert client.post(path + '/auditoria/ia', headers=AUTH, json={'revision': 0}).status_code == 409
        assert client.post(path + '/auditoria/ia', headers=AUTH, json={'revision': 0, 'texto': 'no permitido'}).status_code == 422
        assert not state['requests']
    settings.gemini_enabled = False
    with TestClient(create_app(settings)) as client:
        path, before = prepared(client)
        assert client.get('/api/capacidades').json()['ia_generativa']['auditoria_tupa'] is False
        assert client.post(path + '/auditoria/ia', headers=AUTH, json={'revision': 1}).status_code == 503
        assert client.get(path + '/flujo', headers=AUTH).json() == before


def domain_facts(unknown=False):
    procedure = Procedure('PILOTO', 'Procedimiento público', 'Gerencia', 5,
        (Requirement('pago', 'Recibo', ('RECIBO_PAGO',)),
         Requirement('condicional', 'Condición a revisar', ('FUT',), True)),
        'https://example.invalid/publico', (1,), '2025')
    documents = [Document('DESCONOCIDO' if unknown else 'DNI', [1],
                          'Texto privado no etiquetado Persona No Etiquetada', {'dni': '11111111'}, 1)]
    return evidence_facts(procedure, documents, {'alertas': [], 'campos_comparados': []})


def test_missing_category_unknown_and_conditional_are_not_legal_conclusions():
    facts = domain_facts()
    assert facts['requisitos'][0]['hallazgo_local'] == 'SIN_EVIDENCIA'
    assert facts['requisitos'][1]['hallazgo_local'] == 'REVISION_HUMANA'
    assert domain_facts(True)['requisitos'][0]['hallazgo_local'] == 'REVISION_HUMANA'
    assert 'Persona No Etiquetada' not in json.dumps(facts)
    assert '11111111' not in json.dumps(facts)


def test_payment_receipt_is_optional_evidence_and_identity_does_not_require_a_copy():
    procedure = Procedure('PILOTO', 'Procedimiento público', 'Gerencia', 5,
        (Requirement('pago', 'Acreditación del pago'),
         Requirement('identidad', 'Exhibir DNI, no exigir copia', ('DNI',))),
        'https://example.invalid/publico', (1,), '2025')
    documents = [Document('FUT', [1], 'Texto no transmitido', {}, 1)]
    empty = evidence_facts(procedure, documents, {'alertas': [], 'campos_comparados': []})
    assert all(r['hallazgo_local'] == 'REVISION_HUMANA' for r in empty['requisitos'])
    documents.append(Document('RECIBO_PAGO', [2], 'Contenido no transmitido', {}, 1))
    with_receipt = evidence_facts(procedure, documents, {'alertas': [], 'campos_comparados': []})
    assert with_receipt['requisitos'][0]['documentos_candidatos'] == [1]
    assert with_receipt['requisitos'][0]['hallazgo_local'] == 'EVIDENCIA_CANDIDATA'


@pytest.mark.parametrize('mutation', [
    lambda data: data.pop(),
    lambda data: data.append(deepcopy(data[0])),
    lambda data: data[0].update(requisito='INVENTADO'),
    lambda data: data[0].update(hallazgo='CONFORME'),
    lambda data: data[0].update(documentos=[0]),
    lambda data: data[0].update(documentos=[True]),
    lambda data: data[0].update(explicacion=''),
    lambda data: data[0].update(extra='no admitido'),
])
def test_strict_audit_references_and_schema(mutation):
    facts = domain_facts()
    data = findings(facts)
    mutation(data)
    with pytest.raises(DependencyUnavailable):
        validate_ai_audit({'hallazgos': data}, facts)
