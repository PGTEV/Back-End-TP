"""Demostración universitaria local. No firma, registra ni notifica a servicios externos."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
from hashlib import sha256
from math import exp, log
import re
from src.domain.classification import normalize
from src.domain.intake import is_fictional
from src.domain.workflow import RoutingPrediction, WorkflowError

def require_fictional(dossier):
    if not is_fictional(dossier.documents):
        raise WorkflowError('El modo académico solo audita expedientes marcados EXPEDIENTE FICTICIO en todas sus páginas.')


class AcademicRequirementAuditor:
    """Verifica evidencias de práctica explícitas, no firmas/pagos reales."""
    def checks(self, procedure, dossier):
        require_fictional(dossier)
        result = {}
        for requirement in procedure.requirements:
            marker = re.compile(r'(?m)^EVIDENCIA[ \t]*DEMO:\s*' + re.escape(requirement.id.upper()) + r'\s*$')
            pages = [p for d in dossier.documents if marker.search(normalize(d.text)) for p in d.pages]
            not_applicable = requirement.conditional and any(
                re.search(r'(?m)^NO[ \t]*APLICA[ \t]*DEMO:\s*' + re.escape(requirement.id.upper()) + r'\s*$', normalize(d.text))
                for d in dossier.documents)
            if requirement.id == 'plano_firmado':
                pages = [p for d in dossier.documents if marker.search(normalize(d.text))
                         and re.search(r'FIRMA[ \t]*DEMO:\s*PROFESIONAL[ \t]*FICTICIO\b', normalize(d.text)) for p in d.pages]
            state = 'NO_APLICA' if not_applicable else 'CUMPLE' if pages else 'FALTA'
            result[requirement.id] = {'estado': state, 'paginas': pages,
                'nota': 'AUDITORIA AUTOMATICA DEMO: ' + ('evidencia ficticia detectada.' if pages else
                         'condición ficticia no aplicable.' if not_applicable else 'evidencia ficticia ausente.')}
        return result


class SyntheticRoutingModel:
    """Naive Bayes multinomial entrenado localmente con textos sintéticos identificados.

    La salida es una probabilidad del modelo didáctico, no una confianza calibrada municipal.
    """
    def __init__(self, catalog):
        topics = {
            'PA12115285': ['certificado parametros urbanisticos edificatorios', 'parametros edificacion altura retiros terreno',
                          'certificado urbanistico edificatorio predio', 'solicitud parametros urbanisticos certificado'],
            'PA121121B0': ['modificacion zonificacion especifica', 'cambio zonificacion planes territoriales',
                          'propuesta zonificacion impacto predios vecinos', 'modificacion uso suelo zonificacion'],
            'PE1027344C1': ['licencia funcionamiento comercio riesgo bajo', 'apertura establecimiento comercial negocio',
                           'licencia funcionamiento tienda restaurante', 'autorizacion actividad economica comercio'],
        }
        self.counts = defaultdict(Counter)
        self.samples = Counter()
        self.vocabulary = set()
        self.training_rows = []
        for code, texts in topics.items():
            procedure = catalog.get(code)
            if procedure is None:
                continue
            for text in texts:
                words = self.tokens(text)
                self.counts[procedure.department].update(words)
                self.samples[procedure.department] += 1
                self.vocabulary.update(words)
                self.training_rows.append({'texto': text, 'destino': procedure.department, 'origen': 'SINTETICO'})
        self.version = 'NAIVE_BAYES_SINTETICO_DEMO_V1'

    @staticmethod
    def tokens(text):
        stopwords = {'DE', 'DEL', 'LA', 'EL', 'LOS', 'LAS', 'UN', 'UNA', 'PARA', 'POR', 'Y', 'EN', 'SOLICITO', 'SOLICITUD'}
        return [word for word in re.findall(r'[A-Z]+', normalize(text)) if len(word) > 2 and word not in stopwords]

    def predict(self, dossier):
        require_fictional(dossier)
        text = ' '.join(d.fields.get('asunto', '') + ' ' + d.fields.get('solicito', '')
                        for d in dossier.documents if d.type == 'FUT')
        words = [word for word in self.tokens(text) if word in self.vocabulary]
        scores = {}
        for department, counts in self.counts.items():
            total = sum(counts.values()) + len(self.vocabulary)
            scores[department] = log(self.samples[department] / sum(self.samples.values())) + sum(
                log((counts[word] + 1) / total) for word in words)
        top = max(scores, key=scores.get)
        maximum = scores[top]
        probability = 1 / sum(exp(value - maximum) for value in scores.values())
        return RoutingPrediction(top, probability, self.version)


class AcademicAdministrativeGateway:
    def require_available(self):
        return None

    def issue(self, dossier_id, draft, actor):
        fingerprint = sha256((dossier_id + ':' + str(draft['version']) + ':' + draft['contenido']).encode()).hexdigest()
        timestamp = datetime.now(timezone.utc).isoformat()
        return {
            'estado': 'EMITIDO_DEMO', 'validez_legal': False,
            'firma': {'tipo': 'FIRMA_SIMULADA', 'firmante': actor, 'sha256_borrador': fingerprint,
                      'fecha': timestamp, 'validez_legal': False},
            'sisgedoc': {'tipo': 'SISGEDOC_SIMULADO', 'registro': 'DEMO-' + fingerprint[:16],
                         'estado': 'REGISTRADO_SIMULADO', 'fecha': timestamp, 'transmision_externa': False},
            'notificacion': {'tipo': 'NOTIFICACION_SIMULADA', 'estado': 'ENTREGADA_BUZON_DEMO',
                             'destinatario': 'ciudadano-demo@example.invalid', 'fecha': timestamp,
                             'envio_real': False},
        }
