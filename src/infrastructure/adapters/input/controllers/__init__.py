from pathlib import PureWindowsPath
from uuid import UUID
from fastapi import APIRouter, File, HTTPException, UploadFile
from src.domain.errors import IllegibleDocument, InvalidPDF, ProcessingUnavailable
from src.infrastructure.adapters.input.schemas import DossierResponse


def build_router(process, query, max_file_mb: int):
    router = APIRouter(prefix="/api/expedientes", tags=["HU01"])

    @router.post("", status_code=201, response_model=DossierResponse,
                 summary="Extraer y clasificar un expediente PDF",
                 responses={400: {"description": "PDF inválido"},
                            413: {"description": "Archivo demasiado grande"},
                            422: {"description": "Documento ilegible o entrada inválida"},
                            503: {"description": "Procesamiento no disponible"}})
    def upload(archivo: UploadFile = File(...)):
        try:
            content = archivo.file.read(max_file_mb * 1024 * 1024 + 1)
        finally:
            archivo.file.close()
        if len(content) > max_file_mb * 1024 * 1024:
            raise HTTPException(413, detail={"codigo": "ARCHIVO_GRANDE", "mensaje": f"Máximo {max_file_mb} MB."})
        try:
            dossier = process.execute(PureWindowsPath(archivo.filename or "").name, content)
        except IllegibleDocument as error:
            raise HTTPException(422, detail={"codigo": "DOCUMENTO_ILEGIBLE", "mensaje": error.message,
                                            "pagina": error.page, "id": error.dossier_id}) from error
        except InvalidPDF as error:
            raise HTTPException(400, detail={"codigo": "PDF_INVALIDO", "mensaje": str(error)}) from error
        except ProcessingUnavailable as error:
            raise HTTPException(503, detail={"codigo": "PROCESAMIENTO_NO_DISPONIBLE", "mensaje": str(error)}) from error
        return serialize(dossier)

    @router.get("/{dossier_id}", response_model=DossierResponse,
                summary="Consultar un expediente persistido",
                responses={404: {"description": "Expediente no encontrado"}})
    def get(dossier_id: UUID):
        dossier = query.execute(str(dossier_id))
        if dossier is None:
            raise HTTPException(404, detail={"codigo": "NO_ENCONTRADO", "mensaje": "Expediente no encontrado."})
        return serialize(dossier)

    return router


def serialize(dossier):
    return {"id": dossier.id, "nombre_archivo": dossier.filename, "sha256": dossier.sha256,
            "estado": dossier.status, "creado_en": dossier.created_at, "error": dossier.error,
            "documentos": [{"tipo": d.type, "paginas": d.pages, "texto": d.text,
                            "campos": d.fields, "confianza_ocr": d.confidence,
                            "metodo_extraccion": d.method, "dpi_efectivo": d.dpi,
                            "requiere_revision": d.type == "DESCONOCIDO"} for d in dossier.documents]}
