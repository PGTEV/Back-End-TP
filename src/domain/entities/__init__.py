from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class Document:
    type: str
    pages: list[int]
    text: str
    fields: dict[str, str]
    confidence: float
    method: str = ""
    dpi: float | None = None


@dataclass
class Dossier:
    id: str
    filename: str
    sha256: str
    status: str = "PROCESANDO"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    documents: list[Document] = field(default_factory=list)
    error: str | None = None
