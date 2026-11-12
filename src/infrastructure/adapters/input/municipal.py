from dataclasses import asdict
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Response
from src.infrastructure.adapters.input.academic_access import Actor
from pydantic import BaseModel, ConfigDict, Field
from src.domain.workflow import Conflict, DependencyUnavailable, NotFound, WorkflowError


class RevisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=0, description="Versión del flujo obtenido mediante GET; inicialmente 0.")


class RequirementCheck(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    estado: Literal["CUMPLE", "FALTA", "NO_APLICA", "PENDIENTE"]
    nota: str = Field(min_length=1, max_length=2000)
    paginas: list[int] = Field(default_factory=list, max_length=100)


class ValidationRequest(RevisionRequest):
    codigo_tupa: str = Field(min_length=1, max_length=40)
    verificaciones: dict[str, RequirementCheck] = Field(default_factory=dict, max_length=50)


class DraftRequest(RevisionRequest):
    contenido: str = Field(min_length=1, max_length=100000)


class AssignmentRequest(RevisionRequest):
    destino: str = Field(min_length=1, max_length=200)


class PrivacyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nombres_conocidos: list[str] = Field(default_factory=list, max_length=100)


def build_municipal_router(service, settings, access):
    router = APIRouter(prefix="/api")
    reviewer = access.authenticate
    read = access.for_dossier("consultar")
    evaluate = access.for_dossier("evaluar")
    route_dossier = access.for_dossier("enrutar")
    assign_dossier = access.for_dossier("asignar")
    approve_dossier = access.for_dossier("aprobar")
    external = access.for_dossier("asistencia_externa")

    def invoke(function, *args):
        try:
            result = function(*args)
            return asdict(result) if hasattr(result, "__dataclass_fields__") else result
        except NotFound as error:
            raise HTTPException(404, detail=str(error)) from error
        except Conflict as error:
            raise HTTPException(409, detail=str(error)) from error
        except DependencyUnavailable as error:
            raise HTTPException(503, detail={"codigo": "INTEGRACION_NO_DISPONIBLE", "mensaje": str(error)}) from error
        except WorkflowError as error:
            raise HTTPException(422, detail=str(error)) from error

    @router.get("/capacidades", tags=["Servicio"], summary="Alcance real del prototipo Huancayo")
    def capabilities():
        result = {"municipalidad": "Municipalidad Provincial de Huancayo",
                "modo": "DEMO_UNIVERSITARIA" if settings.academic_demo else "ACADEMICO_LOCAL",
                "demo": settings.academic_demo,
                "ia_generativa": {"configurada": service.draft_generator is not None,
                                  "auditoria_tupa": service.evidence_assistant is not None,
                                  "proveedor": service.draft_generator.provider if service.draft_generator is not None else None,
                                  "modelo": service.draft_generator.model if service.draft_generator is not None else None,
                                  "alcance": "BORRADORES_Y_AUDITORIA_DE_METADATOS" if service.evidence_assistant is not None else "BORRADORES_CON_HECHOS_MINIMIZADOS",
                                  "envia_ocr_o_pdf": False},
                "ingreso_documental": {"extraccion": "OCR_LOCAL", "segmentacion": "POR_PAGINA",
                    "privacidad": "SEUDONIMIZACION_LOCAL_PARCIAL", "envio_a_ia_externa": False,
                    "cruce_de_anexos": ["dni", "ruc"], "requiere_api_key": False},
                "seguridad": {"expedientes_protegidos": settings.protect_dossier_routes,
                              "autenticacion": "TOKEN_REVISOR_PROTOTIPO"},
                "integraciones": {"firma_electronica": False, "sisgedoc": False,
                                  "notificaciones": False, "enrutamiento_predictivo": False},
                "simulaciones": {"habilitadas": settings.academic_demo,
                                 "firma_sisgedoc_notificacion": settings.academic_demo,
                                 "modelo_datos_sinteticos": settings.academic_demo},
                "HU01": "OCR_Y_CLASIFICACION_LOCAL",
                "HU02": "AUDITORIA_AUTOMATICA_EVIDENCIAS_FICTICIAS" if settings.academic_demo else "PREVALIDACION_TUPA_PILOTO_CON_REVISION_HUMANA",
                "HU03": "EMISION_SIMULADA_UNIVERSITARIA" if settings.academic_demo else "BORRADORES_VERSIONADOS_Y_AUDITORIA; EMISION_NO_DISPONIBLE",
                "HU04": "MODELO_SINTETICO_Y_DERIVACION_LOCAL_DEMO" if settings.academic_demo else "BANDEJA_MANUAL; MODELO_PREDICTIVO_NO_CONFIGURADO",
                "HU05": "PLAZO_TUPA_REFERENCIAL; ETA_PREDICTIVO_NO_DISPONIBLE",
                "HU06": "FALTANTES_DOCUMENTALES; PROBABILIDAD_NO_DISPONIBLE",
                "HU07": "ENMASCARAMIENTO_LOCAL_PARCIAL; TRANSMISION_EXTERNA_BLOQUEADA"}
        if access.accounts:
            result["seguridad"]["roles_academicos"] = True
            result["predicciones_academicas"] = True
        return result

    if access.accounts:
        @router.get("/academico/sesion", tags=["Demostración"])
        def session(response: Response, actor: Actor = Depends(reviewer)):
            response.headers["Cache-Control"] = "no-store"
            return access.describe(actor)

    @router.get("/tupa/procedimientos", tags=["HU02"], summary="Catálogo piloto oficial de Huancayo",
                dependencies=[Depends(reviewer)] if settings.protect_dossier_routes else [])
    def procedures():
        return {"municipalidad": "Municipalidad Provincial de Huancayo", "catalogo_completo": False,
                "demo": settings.academic_demo,
                "fuente": {"sha256": service.catalog.metadata['source_sha256'],
                           "archivo_pdf_paginas": 605, "ordenanza": "790-MPH/CM",
                           "paginas_pdf_verificadas": [75, 76, 80, 81, 524]},
                "vigencia_normativa_2026_certificada": False,
                "procedimientos": [asdict(p) for p in service.catalog.list()]}

    @router.get("/expedientes/{dossier_id}/flujo", tags=["HU03"])
    def get_flow(dossier_id: UUID, _actor: Actor = Depends(read)):
        return invoke(service.get, str(dossier_id))

    @router.post("/expedientes/{dossier_id}/validacion", tags=["HU02"],
                 summary="Prevalidar con TUPA y registrar verificaciones del evaluador")
    def validate(dossier_id: UUID, request: ValidationRequest, actor: Actor = Depends(evaluate)):
        return invoke(service.validate, str(dossier_id), request.codigo_tupa,
                      {key: value.model_dump() for key, value in request.verificaciones.items()},
                      request.revision, actor.id)

    @router.post("/expedientes/{dossier_id}/borradores", tags=["HU03"], status_code=201)
    def draft(dossier_id: UUID, request: DraftRequest, actor: Actor = Depends(evaluate)):
        return invoke(service.edit_draft, str(dossier_id), request.contenido, request.revision, actor.id)

    @router.post("/expedientes/{dossier_id}/aprobar-firmar", tags=["HU03"],
                 summary="No disponible sin integración real de firma y SISGEDOC")
    def approve(dossier_id: UUID, request: RevisionRequest, actor: Actor = Depends(approve_dossier)):
        return invoke(service.approve_and_sign, str(dossier_id), request.revision, actor.id,
                      actor.id if actor.role == "responsable" else None)

    @router.post("/expedientes/{dossier_id}/borradores/ia", tags=["HU03"], status_code=201)
    def generate_draft(dossier_id: UUID, request: RevisionRequest, response: Response, actor: Actor = Depends(external)):
        response.headers['Cache-Control'] = 'no-store'
        return invoke(service.generate_draft, str(dossier_id), request.revision, actor.id)

    @router.post('/expedientes/{dossier_id}/auditoria/ia', tags=['HU02'], status_code=201)
    def audit_ai(dossier_id: UUID, request: RevisionRequest, response: Response, actor: Actor = Depends(external)):
        response.headers['Cache-Control'] = 'no-store'
        return invoke(service.audit_with_ai, str(dossier_id), request.revision, actor.id)

    @router.post("/expedientes/{dossier_id}/enrutamiento", tags=["HU04"])
    def route(dossier_id: UUID, request: RevisionRequest, actor: Actor = Depends(route_dossier)):
        return invoke(service.route, str(dossier_id), request.revision, actor.id)

    @router.post("/expedientes/{dossier_id}/asignacion", tags=["HU04"])
    def assign(dossier_id: UUID, request: AssignmentRequest, actor: Actor = Depends(assign_dossier)):
        responsible = access.responsibles.get(request.destino) if actor.role else None
        if actor.role and responsible is None:
            raise HTTPException(422, "El área no tiene un responsable académico configurado.")
        return invoke(service.assign, str(dossier_id), request.destino, request.revision, actor.id, responsible)

    @router.get("/expedientes/{dossier_id}/indicadores", tags=["HU05", "HU06"])
    def indicators(dossier_id: UUID, _actor: Actor = Depends(read)):
        return invoke(service.indicators, str(dossier_id))

    @router.post("/expedientes/{dossier_id}/privacidad/vista-previa", tags=["HU07"])
    def privacy(dossier_id: UUID, request: PrivacyRequest, _actor: Actor = Depends(read)):
        if any(not name.strip() or len(name) > 200 for name in request.nombres_conocidos):
            raise HTTPException(422, detail="Cada nombre debe contener entre 1 y 200 caracteres.")
        return invoke(service.privacy_preview, str(dossier_id), request.nombres_conocidos)

    return router
