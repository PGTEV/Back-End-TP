"""Vista local de seudonimización. No autoriza transmisión de texto libre."""
import re


class LocalPrivacyFilter:
    def preview(self, text, known_names):
        counts = {}
        replacements = {}

        def token(kind, value):
            key = (kind, value.casefold())
            if key not in replacements:
                counts[kind] = counts.get(kind, 0) + 1
                replacements[key] = f"[{kind}_{counts[kind]}]"
            return replacements[key]

        # Nombres declarados por el revisor y nombres en líneas etiquetadas.
        names = list(known_names)
        names.extend(re.findall(
            r"(?im)^(?:nombres?\s+y\s+apellidos|apellidos\s+y\s+nombres|nombre\s+completo)\s*:\s*([^\r\n]+)", text))
        for name in sorted({n.strip() for n in names if n.strip()}, key=len, reverse=True):
            text = re.sub(re.escape(name), lambda m: token("NOMBRE", m.group()), text, flags=re.I)
        text = re.sub(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b", lambda m: token("CORREO", m.group()), text)
        text = re.sub(r"(?<!\d)\d{11}(?!\d)", lambda m: token("RUC", m.group()), text)
        text = re.sub(r"(?<!\d)9\d{8}(?!\d)", lambda m: token("TELEFONO", m.group()), text)
        text = re.sub(r"(?<!\d)\d{8}(?!\d)", lambda m: token("DNI", m.group()), text)
        return {"texto_enmascarado": text, "reemplazos_por_tipo": counts,
                "transmision_externa_habilitada": False,
                "advertencia": "Vista previa local. Puede omitir nombres no etiquetados, direcciones u otros datos; no garantiza anonimización. No se envía a ningún LLM."}
