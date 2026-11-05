"""GenerateContent vía HTTPS. Clave en cabecera, nunca en URL ni en el cliente React."""
import json
import re
from threading import BoundedSemaphore
import httpx
from src.domain.workflow import DependencyUnavailable
from .draft_contract import DRAFT_INSTRUCTIONS, DRAFT_SCHEMA


class GeminiDraftGenerator:
    provider = 'GEMINI'

    def __init__(self, key, model, timeout=60, transport=None):
        self._key, self.model, self.timeout = key, model, timeout
        self._transport = transport
        self._slot = BoundedSemaphore(1)

    def generate(self, facts):
        if not re.fullmatch(r'gemini-[A-Za-z0-9._-]{1,100}', self.model):
            raise DependencyUnavailable('El modelo Gemini configurado no es válido. Use su identificador en GEMINI_MODEL.')
        if not self._slot.acquire(blocking=False):
            raise DependencyUnavailable('La IA está ocupada. Espere a que termine la solicitud actual.')
        try:
            return self._generate(facts)
        finally:
            self._slot.release()

    def _generate(self, facts):
        body = {
            'systemInstruction': {'parts': [{'text': DRAFT_INSTRUCTIONS}]},
            'contents': [{'role': 'user', 'parts': [{'text': json.dumps(facts, ensure_ascii=False)}]}],
            'generationConfig': {'candidateCount': 1, 'maxOutputTokens': 4096,
                                 'responseMimeType': 'application/json', 'responseJsonSchema': DRAFT_SCHEMA},
        }
        try:
            with httpx.Client(timeout=self.timeout, transport=self._transport, follow_redirects=False) as client:
                response = client.post(
                    f'https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent',
                    headers={'x-goog-api-key': self._key, 'Content-Type': 'application/json'}, json=body)
            if response.status_code == 429:
                raise DependencyUnavailable('Gemini alcanzó su cuota o límite de solicitudes. Revise los límites del proyecto en Google AI Studio antes de reintentar.')
            if response.status_code in (401, 403):
                raise DependencyUnavailable('Gemini rechazó el acceso. Revise GEMINI_API_KEY y los permisos del proyecto en Render.')
            if response.status_code == 404:
                raise DependencyUnavailable('El modelo Gemini no está disponible. Revise GEMINI_MODEL y los modelos habilitados en su proyecto.')
            response.raise_for_status()
            data = response.json()
            if data.get('promptFeedback', {}).get('blockReason'):
                raise ValueError('Solicitud bloqueada')
            candidates = data.get('candidates', [])
            if len(candidates) != 1 or candidates[0].get('finishReason') != 'STOP':
                raise ValueError('Respuesta incompleta o bloqueada')
            parts = candidates[0].get('content', {}).get('parts', [])
            parsed = json.loads(''.join(part['text'] for part in parts
                                        if 'text' in part and not part.get('thought', False)))
            content = parsed.get('contenido')
            if set(parsed) != {'contenido'} or not isinstance(content, str) or not 1 <= len(content.strip()) <= 20000:
                raise ValueError('Contenido inválido')
            response_id, model = data.get('responseId'), data.get('modelVersion')
            if (not isinstance(response_id, str) or not 1 <= len(response_id) <= 200
                    or not isinstance(model, str) or not 1 <= len(model) <= 200):
                raise ValueError('Metadatos inválidos')
            return {'contenido': content.strip(), 'proveedor': self.provider, 'modelo': model,
                    'respuesta_id': response_id, 'version_prompt': 'BORRADOR_MINIMIZADO_V1'}
        except httpx.TimeoutException:
            raise DependencyUnavailable('Gemini tardó demasiado. No se guardó un borrador nuevo.') from None
        except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError):
            raise DependencyUnavailable('No se obtuvo un borrador válido de Gemini. Revise el modelo y la configuración; el borrador anterior se conserva.') from None
