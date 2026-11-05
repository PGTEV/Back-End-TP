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
            'generationConfig': {'maxOutputTokens': 4096,
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
            if response.status_code == 400:
                try:
                    precondition = response.json().get('error', {}).get('status') == 'FAILED_PRECONDITION'
                except (ValueError, TypeError, AttributeError):
                    precondition = False
                if precondition:
                    raise self._failure('HTTP_400_PRECONDICION', 'Google exige revisar los requisitos de acceso del proyecto (región, verificación o nivel de servicio) en AI Studio.')
                raise self._failure('HTTP_400', 'Google rechazó los parámetros de generación. Compruebe que está desplegada la última corrección del backend y que el modelo admite salida JSON estructurada.')
            if response.status_code == 402:
                raise self._failure('HTTP_402', 'El proyecto de Google requiere revisar su facturación o saldo. Compruebe el nivel del proyecto en AI Studio.')
            if 500 <= response.status_code <= 599:
                raise self._failure('HTTP_5XX', 'Google no pudo atender la solicitud. Espere antes de intentar otra generación.')
            response.raise_for_status()
            try:
                data = response.json()
            except ValueError:
                raise self._failure('RESPUESTA_NO_JSON', 'Google no devolvió una respuesta JSON válida.') from None
            if data.get('promptFeedback', {}).get('blockReason'):
                raise self._failure('SOLICITUD_BLOQUEADA', 'Google bloqueó la solicitud. Revise el contenido público usado para redactar; no se desactivaron los filtros del proveedor.')
            candidates = data.get('candidates', [])
            if len(candidates) != 1:
                raise self._failure('SIN_CANDIDATO_UNICO', 'Google no devolvió un único borrador para revisar.')
            finish = candidates[0].get('finishReason')
            if finish == 'MAX_TOKENS':
                raise self._failure('MAX_TOKENS', 'La generación llegó al límite de tokens antes de terminar. No se aceptó el texto incompleto.')
            if finish != 'STOP':
                raise self._failure('GENERACION_NO_COMPLETADA', 'Google interrumpió o bloqueó la generación antes de completarla.')
            parts = candidates[0].get('content', {}).get('parts', [])
            try:
                parsed = json.loads(''.join(part['text'] for part in parts
                                            if 'text' in part and not part.get('thought', False)))
            except ValueError:
                raise self._failure('BORRADOR_NO_JSON', 'El texto generado no tiene el formato JSON solicitado.') from None
            if not isinstance(parsed, dict):
                raise self._failure('ESQUEMA_INVALIDO', 'La respuesta no respeta el esquema del borrador.')
            content = parsed.get('contenido')
            if set(parsed) != {'contenido'} or not isinstance(content, str) or not 1 <= len(content.strip()) <= 20000:
                raise self._failure('ESQUEMA_INVALIDO', 'El contenido está vacío, supera el límite o no respeta el esquema del borrador.')
            response_id, model = data.get('responseId'), data.get('modelVersion')
            if (not isinstance(response_id, str) or not 1 <= len(response_id) <= 200
                    or not isinstance(model, str) or not 1 <= len(model) <= 200):
                raise self._failure('METADATOS_INCOMPLETOS', 'Google no devolvió el identificador y modelo necesarios para registrar la procedencia.')
            return {'contenido': content.strip(), 'proveedor': self.provider, 'modelo': model,
                    'respuesta_id': response_id, 'version_prompt': 'BORRADOR_MINIMIZADO_V1'}
        except httpx.TimeoutException:
            raise DependencyUnavailable('Gemini tardó demasiado. No se guardó un borrador nuevo.') from None
        except httpx.RequestError:
            raise self._failure('CONEXION', 'No se pudo completar la conexión HTTPS con Google. Intente de nuevo cuando el servicio esté disponible.') from None
        except httpx.HTTPStatusError:
            raise self._failure('HTTP_INESPERADO', 'Google devolvió un estado HTTP inesperado.') from None
        except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError):
            raise self._failure('ESTRUCTURA_INVALIDA', 'La respuesta de Google no tiene la estructura esperada por el adaptador.') from None

    @staticmethod
    def _failure(code, message):
        # Solo códigos/mensajes locales: nunca copiar cuerpos, claves ni errores libres de Google.
        return DependencyUnavailable(f'Gemini [{code}]: {message} El borrador anterior se conserva.')
