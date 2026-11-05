import json
import httpx
import pytest
from fastapi.testclient import TestClient
from src.domain.workflow import DependencyUnavailable
from src.infrastructure.adapters.output.gemini_drafts import GeminiDraftGenerator
from src.infrastructure.main import create_app
from src.infrastructure.settings import Settings


def completed(text=None):
    return {'responseId': 'gemini-response-test', 'modelVersion': 'gemini-test', 'candidates': [
        {'finishReason': 'STOP', 'content': {'parts': [
            {'text': text if text is not None else json.dumps({'contenido': 'Proyecto para revisión.'})}]}}]}


def generator(handler, model='gemini-test'):
    return GeminiDraftGenerator('clave-ficticia', model, transport=httpx.MockTransport(handler))


def test_generate_content_contract_and_thoughts_are_excluded():
    def handler(request):
        assert str(request.url) == 'https://generativelanguage.googleapis.com/v1beta/models/gemini-test:generateContent'
        assert not request.url.query and request.headers['x-goog-api-key'] == 'clave-ficticia'
        body = json.loads(request.content)
        assert body['generationConfig']['responseMimeType'] == 'application/json'
        assert body['generationConfig']['responseJsonSchema']['required'] == ['contenido']
        assert body['generationConfig']['maxOutputTokens'] == 4096
        assert 'tools' not in body and 'cachedContent' not in body
        assert body['contents'][0]['role'] == 'user'
        data = completed()
        data['candidates'][0]['content']['parts'].insert(0, {'thought': True, 'text': 'razonamiento no mostrar'})
        return httpx.Response(200, json=data)
    result = generator(handler).generate({'resultado_documental': 'CONFORME'})
    assert result['proveedor'] == 'GEMINI' and result['modelo'] == 'gemini-test'
    assert 'razonamiento' not in result['contenido']


@pytest.mark.parametrize('status', [400, 401, 403, 404, 429, 500, 302])
def test_provider_errors_do_not_disclose_secrets(status):
    with pytest.raises(DependencyUnavailable) as error:
        generator(lambda r: httpx.Response(status, text='SECRET clave-ficticia')).generate({})
    assert 'SECRET' not in str(error.value) and 'clave-ficticia' not in str(error.value)


@pytest.mark.parametrize('data', [
    {}, {'promptFeedback': {'blockReason': 'SAFETY'}},
    {'candidates': [{'finishReason': 'MAX_TOKENS'}]},
    {'candidates': [{'finishReason': 'SAFETY'}]},
    completed('not-json'), completed('{"contenido":""}'),
    completed(json.dumps({'contenido': 'x' * 20001})),
    completed('{"contenido":"válido", "extra":1}'),
    {**completed(), 'responseId': ''},
])
def test_incomplete_blocked_or_invalid_output_is_not_accepted(data):
    with pytest.raises(DependencyUnavailable):
        generator(lambda r: httpx.Response(200, json=data)).generate({})


def test_timeout_busy_and_invalid_model_do_not_retry_or_change_host():
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
    finally:
        adapter._slot.release()
    with pytest.raises(DependencyUnavailable, match='modelo Gemini'):
        generator(handler, model='gemini-test/../../?key=SECRET').generate({})
    assert len(calls) == 1


@pytest.mark.parametrize('provider,key,protected,expected', [
    ('gemini', 'clave-ficticia', True, 'GEMINI'),
    ('openai', 'clave-ficticia', True, 'OPENAI'),
    ('none', 'clave-ficticia', True, None),
    ('gemini', '', True, None),
    ('gemini', 'clave-ficticia', False, None),
])
def test_selection_has_no_fallback_to_openai_and_does_not_probe_provider(tmp_path, provider, key, protected, expected):
    settings = Settings(_env_file=None, database_url=f'sqlite:///{tmp_path / "db.sqlite"}',
                        storage_dir=str(tmp_path / 'pdf'), ai_provider=provider,
                        gemini_enabled=True, gemini_api_key=key, gemini_model='gemini-test',
                        openai_enabled=True, openai_api_key='otra-clave-ficticia', openai_model='modelo-test',
                        protect_dossier_routes=protected)
    with TestClient(create_app(settings)) as client:
        response = client.get('/api/capacidades')
        capability = response.json()['ia_generativa']
        assert capability['configurada'] is (expected is not None)
        assert capability['proveedor'] == expected
        assert 'clave-ficticia' not in response.text
