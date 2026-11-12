from pathlib import PureWindowsPath
from uuid import UUID
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from src.domain.errors import DocumentNotFound, IllegibleDocument, InvalidPDF, ProcessingUnavailable
from src.infrastructure.adapters.input.schemas import DossierResponse
from src.infrastructure.adapters.input.academic_access import Actor


def build_router(process, query, max_file_mb: int, access, document_pdf=None):
    router = APIRouter(prefix="/api/expedientes", tags=["HU01"])
    upload_access = access.upload()
    read_access = access.for_dossier("consultar", public=not access.protected)
    read_actor = access.read_actor()

    @router.post("", status_code=201, response_model=DossierResponse,
                 summary="Extraer y clasificar un expediente PDF",
                 responses={400: {"description": "PDF inválido"},
                            413: {"description": "Archivo demasiado grande"},
                            422: {"description": "Documento ilegible o entrada inválida"},
                            503: {"description": "Procesamiento no disponible"}})
    def upload(response: Response, archivo: UploadFile = File(...), actor: Actor = Depends(upload_access)):
        response.headers['Cache-Control'] = 'no-store'
        try:
            content = archivo.file.read(max_file_mb * 1024 * 1024 + 1)
        finally:
            archivo.file.close()
        if len(content) > max_file_mb * 1024 * 1024:
            raise HTTPException(413, detail={"codigo": "ARCHIVO_GRANDE", "mensaje": f"Máximo {max_file_mb} MB."})
        try:
            dossier = process.execute(PureWindowsPath(archivo.filename or "").name, content,
                                      academic_owner=actor.id if actor.role else None)
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
    def get(dossier_id: UUID, response: Response, actor: Actor = Depends(read_actor)):
        response.headers['Cache-Control'] = 'no-store'
        dossier = query.execute(str(dossier_id))
        access.authorize_dossier(actor, dossier)
        if dossier is None:
            raise HTTPException(404, detail={"codigo": "NO_ENCONTRADO", "mensaje": "Expediente no encontrado."})
        return serialize(dossier)

    if document_pdf is not None:
        @router.get('/{dossier_id}/documentos/{index}/pdf', summary='Descargar un segmento real del PDF original')
        def get_document_pdf(dossier_id: UUID, index: int, _actor: Actor = Depends(read_access)):
            try:
                content = document_pdf.execute(str(dossier_id), index)
            except DocumentNotFound as error:
                raise HTTPException(404, detail=str(error)) from error
            except ProcessingUnavailable as error:
                raise HTTPException(503, detail=str(error)) from error
            return Response(content, media_type='application/pdf', headers={
                'Content-Disposition': f'attachment; filename="segmento-{index + 1}.pdf"',
                'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
            })
    return router


def serialize(dossier):
    return {"id": dossier.id, "nombre_archivo": dossier.filename, "sha256": dossier.sha256,
            "estado": dossier.status, "creado_en": dossier.created_at, "error": dossier.error,
            "privacidad": dossier.privacy, "consistencia": dossier.consistency,
            "segmentacion": {"metodo": "UNA_UNIDAD_POR_PAGINA", "agrupacion_semantica": False,
                             "total_segmentos": len(dossier.documents)},
            "documentos": [{"tipo": d.type, "paginas": d.pages, "texto": d.text,
                            "campos": d.fields, "confianza_ocr": d.confidence,
                            "metodo_extraccion": d.method, "dpi_efectivo": d.dpi,
                            "requiere_revision": d.type == "DESCONOCIDO"} for d in dossier.documents]}
