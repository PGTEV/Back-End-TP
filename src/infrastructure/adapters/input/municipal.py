from dataclasses import asdict
from secrets import compare_digest
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
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


def build_municipal_router(service, settings):
    router = APIRouter(prefix="/api")
    bearer = HTTPBearer(auto_error=False)

    def reviewer(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
        token = settings.reviewer_token.get_secret_value()
        if len(token) < 32 or not settings.reviewer_id.strip():
            raise HTTPException(503, detail={"codigo": "REVISOR_NO_CONFIGURADO",
                                "mensaje": "Configure REVIEWER_TOKEN (mínimo 32 caracteres) y REVIEWER_ID en .env para usar el flujo local."})
        if credentials is None or not compare_digest(credentials.credentials.encode(), token.encode()):
            raise HTTPException(401, detail="Credencial de evaluador inválida.",
                                headers={"WWW-Authenticate": "Bearer"})
        return settings.reviewer_id

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
        return {"municipalidad": "Municipalidad Provincial de Huancayo", "modo": "ACADEMICO_LOCAL",
                "HU01": "OCR_Y_CLASIFICACION_LOCAL",
                "HU02": "PREVALIDACION_TUPA_PILOTO_CON_REVISION_HUMANA",
                "HU03": "BORRADORES_VERSIONADOS_Y_AUDITORIA; EMISION_NO_DISPONIBLE",
                "HU04": "BANDEJA_MANUAL; MODELO_PREDICTIVO_NO_CONFIGURADO",
                "HU05": "PLAZO_TUPA_REFERENCIAL; ETA_PREDICTIVO_NO_DISPONIBLE",
                "HU06": "FALTANTES_DOCUMENTALES; PROBABILIDAD_NO_DISPONIBLE",
                "HU07": "ENMASCARAMIENTO_LOCAL_PARCIAL; TRANSMISION_EXTERNA_BLOQUEADA"}

    @router.get("/tupa/procedimientos", tags=["HU02"], summary="Catálogo piloto oficial de Huancayo")
    def procedures():
        return {"municipalidad": "Municipalidad Provincial de Huancayo", "catalogo_completo": False,
                "vigencia_normativa_2026_certificada": False,
                "procedimientos": [asdict(p) for p in service.catalog.list()]}

    @router.get("/expedientes/{dossier_id}/flujo", tags=["HU03"])
    def get_flow(dossier_id: UUID, actor: str = Depends(reviewer)):
        return invoke(service.get, str(dossier_id))

    @router.post("/expedientes/{dossier_id}/validacion", tags=["HU02"],
                 summary="Prevalidar con TUPA y registrar verificaciones del evaluador")
    def validate(dossier_id: UUID, request: ValidationRequest, actor: str = Depends(reviewer)):
        return invoke(service.validate, str(dossier_id), request.codigo_tupa,
                      {key: value.model_dump() for key, value in request.verificaciones.items()},
                      request.revision, actor)

    @router.post("/expedientes/{dossier_id}/borradores", tags=["HU03"], status_code=201)
    def draft(dossier_id: UUID, request: DraftRequest, actor: str = Depends(reviewer)):
        return invoke(service.edit_draft, str(dossier_id), request.contenido, request.revision, actor)

    @router.post("/expedientes/{dossier_id}/aprobar-firmar", tags=["HU03"],
                 summary="No disponible sin integración real de firma y SISGEDOC")
    def approve(dossier_id: UUID, request: RevisionRequest, actor: str = Depends(reviewer)):
        return invoke(service.approve_and_sign, str(dossier_id), request.revision, actor)

    @router.post("/expedientes/{dossier_id}/enrutamiento", tags=["HU04"])
    def route(dossier_id: UUID, request: RevisionRequest, actor: str = Depends(reviewer)):
        return invoke(service.route, str(dossier_id), request.revision, actor)

    @router.post("/expedientes/{dossier_id}/asignacion", tags=["HU04"])
    def assign(dossier_id: UUID, request: AssignmentRequest, actor: str = Depends(reviewer)):
        return invoke(service.assign, str(dossier_id), request.destino, request.revision, actor)

    @router.get("/expedientes/{dossier_id}/indicadores", tags=["HU05", "HU06"])
    def indicators(dossier_id: UUID, actor: str = Depends(reviewer)):
        return invoke(service.indicators, str(dossier_id))

    @router.post("/expedientes/{dossier_id}/privacidad/vista-previa", tags=["HU07"])
    def privacy(dossier_id: UUID, request: PrivacyRequest, actor: str = Depends(reviewer)):
        if any(not name.strip() or len(name) > 200 for name in request.nombres_conocidos):
            raise HTTPException(422, detail="Cada nombre debe contener entre 1 y 200 caracteres.")
        return invoke(service.privacy_preview, str(dossier_id), request.nombres_conocidos)

    return router
