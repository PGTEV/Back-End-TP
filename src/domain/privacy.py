"""Seudonimización local determinista por expediente; nunca autoriza envíos externos."""
import re
import unicodedata

SENSITIVE_FIELDS = {
    'dni': 'DNI', 'ruc': 'RUC', 'nombres': 'NOMBRE', 'nombre': 'NOMBRE', 'apellidos': 'NOMBRE',
    'domicilio': 'DIRECCION', 'direccion': 'DIRECCION', 'telefono': 'TELEFONO', 'correo': 'CORREO',
    'fecha_nacimiento': 'FECHA_NACIMIENTO', 'ce': 'IDENTIDAD',
}
WARNING = ('Seudonimización local parcial, no anonimización garantizada. Los datos no etiquetados pueden '
           'permanecer. Originales disponibles solo en el circuito autorizado; transmisión externa bloqueada.')


def identity(value):
    return ' '.join(''.join(c for c in unicodedata.normalize('NFD', value.casefold())
                           if unicodedata.category(c) != 'Mn').split())


class _Redactor:
    def __init__(self, texts, fields, known_names):
        self.counts = {}
        self.replacements = {}
        sensitive = [('NOMBRE', name.strip()) for name in known_names if name.strip()]
        labels = {
            'NOMBRE': r'nombres?(?:\s+y\s+apellidos)?|apellidos(?:\s+y\s+nombres)?|nombre\s+completo|administrado|solicitante|representante',
            'DIRECCION': r'domicilio(?:\s+legal)?|direcci[oó]n(?:\s+legal)?',
            'TELEFONO': r'tel[eé]fono(?:\s+de\s+contacto)?|celular',
            'FECHA_NACIMIENTO': r'fecha\s+de\s+nacimiento',
        }
        for text in texts:
            for kind, label in labels.items():
                sensitive.extend((kind, match) for match in re.findall(
                    r'(?im)^\s*(?:' + label + r')\s*:\s*([^\r\n]+)', text))
        for record in fields:
            sensitive.extend((SENSITIVE_FIELDS[key], str(value)) for key, value in record.items()
                             if key in SENSITIVE_FIELDS and str(value).strip())
        # Números se procesan con reglas específicas; mantener identidad entre texto y campos.
        self.named_values = sorted({(kind, value.strip()) for kind, value in sensitive
                                    if value.strip() and kind not in {'DNI', 'RUC', 'CORREO'}},
                                   key=lambda item: (-len(item[1]), item[0], item[1]))

    def token(self, kind, value):
        key = (kind, identity(value))
        if key not in self.replacements:
            self.counts[kind] = self.counts.get(kind, 0) + 1
            self.replacements[key] = f'[{kind}_{self.counts[kind]}]'
        return self.replacements[key]

    def redact(self, text):
        for kind, value in self.named_values:
            text = re.sub(re.escape(value), lambda m: self.token(kind, m.group()), text, flags=re.I)
        text = re.sub(r'\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b', lambda m: self.token('CORREO', m.group()), text)
        text = re.sub(r'(?<!\d)\d{11}(?!\d)', lambda m: self.token('RUC', m.group()), text)
        text = re.sub(r'(?<!\d)(?:\+?51[ -]?)?9\d{8}(?!\d)', lambda m: self.token('TELEFONO', m.group()), text)
        text = re.sub(r'(?<!\d)\d{8}(?!\d)', lambda m: self.token('DNI', m.group()), text)
        return text


class LocalPrivacyFilter:
    def preview(self, text, known_names):
        redactor = _Redactor([text], [], known_names)
        protected = redactor.redact(text)
        return {'texto_enmascarado': protected, 'reemplazos_por_tipo': redactor.counts,
                'transmision_externa_habilitada': False, 'advertencia': WARNING}

    def project(self, documents):
        redactor = _Redactor([d.text for d in documents], [d.fields for d in documents], [])
        protected = []
        for index, document in enumerate(documents):
            text = redactor.redact(document.text)
            fields = {key: redactor.token(SENSITIVE_FIELDS[key], str(value))
                      if key in SENSITIVE_FIELDS else redactor.redact(str(value))
                      for key, value in document.fields.items()}
            protected.append({'documento': index, 'tipo': document.type, 'paginas': document.pages,
                              'texto': text, 'campos': fields})
        return {'tecnica': 'SEUDONIMIZACION_LOCAL_PARCIAL', 'anonimizacion_garantizada': False,
                'documentos': protected, 'reemplazos_por_tipo': redactor.counts,
                'transmision_externa_habilitada': False, 'advertencia': WARNING}
