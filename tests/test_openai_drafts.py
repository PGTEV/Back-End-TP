import json
import httpx
import pytest
from fastapi.testclient import TestClient
from src.domain.workflow import DependencyUnavailable
from src.infrastructure.adapters.output.openai_drafts import OpenAIDraftGenerator
from src.infrastructure.main import create_app
from src.infrastructure.settings import Settings
from test_municipal import Reader, complete_checks

TOKEN = 'solo-tests-' + 'x' * 40
AUTH = {'Authorization': 'Bearer ' + TOKEN}


def completed(content='Proyecto sujeto a revisión técnica.'):
    return {'id': 'resp_test', 'model': 'modelo-test', 'status': 'completed',
            'output': [{'type': 'message', 'content': [
                {'type': 'output_text', 'text': json.dumps({'contenido': content})}]}]}


def generator(handler):
    return OpenAIDraftGenerator('clave-ficticia', 'modelo-test', transport=httpx.MockTransport(handler))


def test_responses_contract():
    def handler(request):
        assert str(request.url) == 'https://api.openai.com/v1/responses'
        assert request.headers['authorization'] == 'Bearer clave-ficticia'
        body = json.loads(request.content)
        assert body['store'] is False and body['max_output_tokens'] == 2500
        assert body['text']['format']['strict'] is True
        assert 'tools' not in body and 'previous_response_id' not in body
        return httpx.Response(200, json=completed())
    assert generator(handler).generate({'tipo_borrador': 'PROYECTO'})['respuesta_id'] == 'resp_test'


@pytest.mark.parametrize('status', [401, 403, 429, 500, 302])
def test_provider_errors_never_disclose_body_or_key(status):
    adapter = generator(lambda r: httpx.Response(status, text='clave-ficticia SECRET provider body'))
    with pytest.raises(DependencyUnavailable) as error:
        adapter.generate({})
    assert 'SECRET' not in str(error.value) and 'clave-ficticia' not in str(error.value)


@pytest.mark.parametrize('data', [
    {'status': 'incomplete'},
    {'status': 'completed', 'output': [{'type': 'message', 'content': [{'type': 'refusal'}]}]},
    completed(''), completed('x' * 20001), {'status': 'completed', 'output': []},
])
def test_invalid_output_is_not_saved(data):
    with pytest.raises(DependencyUnavailable):
        generator(lambda r: httpx.Response(200, json=data)).generate({})


def test_timeout_and_busy_fail_without_retry():
    calls = []
    def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout('SECRET', request=request)
    adapter = generator(handler)
    with pytest.raises(DependencyUnavailable, match='tardó demasiado'):
        adapter.generate({})
    assert len(calls) == 1
    adapter._slot.acquire()
    try:
        with pytest.raises(DependencyUnavailable, match='ocupada'):
            adapter.generate({})
        assert len(calls) == 1
    finally:
        adapter._slot.release()


@pytest.mark.parametrize('missing_payment', [False, True])
def test_authenticated_generation_minimizes_data_versions_and_persists(tmp_path, monkeypatch, missing_payment):
    captured = []
    def handler(request):
        captured.append(json.loads(request.content))
        return httpx.Response(200, json=completed())
    adapter = generator(handler)
    monkeypatch.setattr('src.infrastructure.main.OpenAIDraftGenerator', lambda *args: adapter)
    settings = Settings(_env_file=None, database_url=f'sqlite:///{tmp_path / "db.sqlite"}',
                        storage_dir=str(tmp_path / 'pdf'), reviewer_token=TOKEN, reviewer_id='revisor',
                        protect_dossier_routes=True, openai_enabled=True, openai_api_key='clave-ficticia',
                        openai_model='modelo-test')
    with TestClient(create_app(settings, Reader())) as client:
        dossier_id = client.post('/api/expedientes', headers=AUTH,
            files={'archivo': ('privado.pdf', b'%PDF-FAKE', 'application/pdf')}).json()['id']
        path = f'/api/expedientes/{dossier_id}'
        assert client.post(path + '/borradores/ia', json={'revision': 0}).status_code == 401
        assert client.post(path + '/borradores/ia', headers=AUTH, json={'revision': 0}).status_code == 409
        checks = complete_checks()
        checks['pago']['nota'] = 'Persona Ficticia DNI 12345678 teléfono 987654321'
        if missing_payment:
            checks['pago']['estado'] = 'FALTA'
        before = client.post(path + '/validacion', headers=AUTH,
            json={'revision': 0, 'codigo_tupa': 'PA12115285', 'verificaciones': checks}).json()
        result = client.post(path + '/borradores/ia', headers=AUTH, json={'revision': 1})
        assert result.status_code == 201, result.text
        flow = result.json()
        assert flow['validation'] == before['validation'] and flow['routing'] == before['routing']
        assert flow['drafts'][-1]['origen'] == 'OPENAI'
        assert flow['drafts'][-1]['ia']['respuesta_id'] == 'resp_test'
        assert flow['audit'][-1]['action'] == 'BORRADOR_IA'
        assert flow['revision'] == 2
        assert client.post(path + '/borradores/ia', headers=AUTH, json={'revision': 1}).status_code == 409
        assert len(captured) == 1
        outbound = json.dumps(captured[0])
        for secret in ['Persona Ficticia', '12345678', '987654321', 'privado.pdf', dossier_id, 'SOLICITO', 'revisor']:
            assert secret not in outbound
        facts = json.loads(captured[0]['input'])
        assert facts['resultado_documental'] == ('OBSERVADO' if missing_payment else 'CONFORME')
        assert facts['tipo_borrador'] == ('OBSERVACION' if missing_payment else 'PROYECTO')
        assert flow['drafts'][-1]['tipo'] == facts['tipo_borrador']
        assert all(set(r) == {'descripcion', 'estado'} for r in facts['requisitos'])
        adapter._transport = httpx.MockTransport(lambda r: httpx.Response(429))
        assert client.post(path + '/borradores/ia', headers=AUTH, json={'revision': 2}).status_code == 503
        assert client.get(path + '/flujo', headers=AUTH).json() == flow
    with TestClient(create_app(settings, Reader())) as restarted:
        assert restarted.get(path + '/flujo', headers=AUTH).json() == flow


def test_unconfigured_ai_is_explicit(tmp_path):
    settings = Settings(_env_file=None, database_url=f'sqlite:///{tmp_path / "db.sqlite"}',
                        storage_dir=str(tmp_path / 'pdf'), reviewer_token=TOKEN, reviewer_id='revisor',
                        openai_enabled=True, openai_api_key='ficticia', openai_model='modelo-test',
                        protect_dossier_routes=False)
    with TestClient(create_app(settings, Reader())) as client:
        assert client.get('/api/capacidades').json()['ia_generativa']['configurada'] is False
        dossier_id = client.post('/api/expedientes',
            files={'archivo': ('ficticio.pdf', b'%PDF-FAKE', 'application/pdf')}).json()['id']
        path = f'/api/expedientes/{dossier_id}'
        client.post(path + '/validacion', headers=AUTH,
            json={'revision': 0, 'codigo_tupa': 'PA12115285', 'verificaciones': complete_checks()})
        assert client.post(path + '/borradores/ia', headers=AUTH, json={'revision': 1}).status_code == 503
