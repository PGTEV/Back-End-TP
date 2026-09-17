from pydantic import BaseModel


class DocumentResponse(BaseModel):
    tipo: str
    paginas: list[int]
    texto: str
    campos: dict[str, str]
    confianza_ocr: float
    metodo_extraccion: str
    dpi_efectivo: float | None
    requiere_revision: bool


class DossierResponse(BaseModel):
    id: str
    nombre_archivo: str
    sha256: str
    estado: str
    creado_en: str
    error: str | None
    documentos: list[DocumentResponse]
