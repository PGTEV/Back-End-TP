"""Cruce determinista de datos declarados. Una contradicción no acredita fraude."""
import re
from src.domain.classification import normalize
from src.domain.privacy import LocalPrivacyFilter


def protect_and_compare(documents):
    privacy = LocalPrivacyFilter().project(documents)
    alerts = []
    compared = []
    for field in ('dni', 'ruc'):
        sources = [(index, doc) for index, doc in enumerate(documents) if doc.fields.get(field)]
        if len(sources) < 2:
            continue
        compared.append(field)
        if len({doc.fields[field].strip() for _, doc in sources}) > 1:
            alerts.append({'codigo': field.upper() + '_DIFIERE_ENTRE_ANEXOS', 'campo': field,
                'mensaje': 'Se detectaron valores distintos de ' + field.upper() + ' entre anexos. Revisar titular, representante y posibles errores OCR.',
                'fuentes': [{'documento': index, 'tipo': doc.type, 'paginas': doc.pages,
                             'valor_protegido': privacy['documentos'][index]['campos'][field]} for index, doc in sources]})
    for index, document in enumerate(documents):
        values = set(re.findall(r'\bDNI\s*[:.\-]?\s*(\d{8})\b', document.text, flags=re.I))
        if len(values) > 1:
            alerts.append({'codigo': 'MULTIPLES_DNI_EN_UN_ANEXO', 'campo': 'dni',
                'mensaje': 'El anexo contiene varios DNI etiquetados. Revisar los roles antes de atribuirlos al solicitante.',
                'fuentes': [{'documento': index, 'tipo': document.type, 'paginas': document.pages}]})
    consistency = {'estado': 'REQUIERE_REVISION' if alerts else 'SIN_CONTRADICCIONES_DETECTADAS' if compared else 'DATOS_INSUFICIENTES',
                   'requiere_revision_humana': bool(alerts), 'campos_comparados': compared, 'alertas': alerts,
                   'fraude_determinado': False,
                   'advertencia': 'Se comparan DNI/RUC explícitos. Una diferencia puede deberse a un representante, pagador u OCR; no constituye prueba de fraude.'}
    return privacy, consistency


def is_fictional(documents):
    # RapidOCR may join the two words in the marker on scanned pages.
    return bool(documents) and all(
        re.search(r"\bEXPEDIENTE\s*FICTICIO\b", normalize(document.text)) for document in documents
    )
