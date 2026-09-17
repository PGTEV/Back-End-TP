"""Clasificación conservadora por reglas; no inventa campos ni categorías."""
import re
import unicodedata
from src.domain.entities import Document
from src.domain.valueObjects import Page


def normalize(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text.upper())
                   if unicodedata.category(c) != "Mn")


def classify(page: Page) -> Document:
    text = normalize(page.text)
    # Un título técnico y etiquetas del formato evitan clasificar referencias
    # narrativas al Plano de Desarrollo como si fueran planos adjuntos.
    plan_title = re.search(
        r"(?m)^\s*(?:PLANO\s+DE\s+(?:UBICACION|LOCALIZACION|ARQUITECTURA|DISTRIBUCION|"
        r"ESTRUCTURAS|INSTALACIONES|LOTIZACION)|ESQUEMA\s+DE\s+LOCALIZACION)\b", text)
    plan_layout = re.search(r"(?m)^\s*(?:ESCALA|LAMINA|CUADRO\s+DE\s+AREAS)\b", text)
    scores = {
        "FUT": sum(phrase in text for phrase in (
            "FORMULARIO UNICO DE TRAMITE", "FORMATO UNICO DE TRAMITE", "SOLICITO:")),
        "DNI": sum(phrase in text for phrase in (
            "DOCUMENTO NACIONAL DE IDENTIDAD", "REGISTRO NACIONAL DE IDENTIFICACION", "RENIEC")),
        "PLANO": 1 if plan_title and plan_layout else 0,
    }
    best = max(scores.values())
    winners = [kind for kind, score in scores.items() if score == best]
    kind = winners[0] if best and len(winners) == 1 else "DESCONOCIDO"
    fields = {}
    for key, pattern in {
        "dni": r"\bDNI\s*[:.\-]?\s*(\d{8})\b",
        "ruc": r"\bRUC\s*[:.\-]?\s*(\d{11})\b",
        "escala": r"\bESCALA\s*:?\s*(1\s*[:/]\s*[1-9]\d*)(?![\d.,])\b",
    }.items():
        match = re.search(pattern, text)
        if match:
            value = match.group(1)
            fields[key] = re.sub(r"\s+", "", value).replace("/", ":") if key == "escala" else value
    # Una unidad por página evita unir dos DNI o FUT distintos sin evidencia.
    return Document(kind, [page.number], page.text, fields, page.confidence, page.method, page.dpi)
