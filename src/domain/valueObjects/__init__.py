from dataclasses import dataclass


@dataclass(frozen=True)
class Page:
    """Evidencia de extracción de una página; sin identidad independiente."""
    number: int
    text: str
    confidence: float
    method: str
    dpi: float | None = None
