"""Reglas del flujo documental. Sin HTTP, SQL, OCR ni proveedores externos."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from math import isfinite


class WorkflowError(Exception):
    pass


class NotFound(WorkflowError):
    pass


class Conflict(WorkflowError):
    pass


class DependencyUnavailable(WorkflowError):
    pass


@dataclass(frozen=True)
class Requirement:
    id: str
    description: str
    document_types: tuple[str, ...] = ()
    conditional: bool = False


@dataclass(frozen=True)
class Procedure:
    code: str
    name: str
    department: str
    published_days: int
    requirements: tuple[Requirement, ...]
    source_url: str
    pdf_pages: tuple[int, ...]
    source_version: str


@dataclass(frozen=True)
class RoutingPrediction:
    department: str
    confidence: float
    model_version: str

    def __post_init__(self):
        if not isfinite(self.confidence) or not 0 <= self.confidence <= 1:
            raise WorkflowError("Confianza inválida del modelo.")
        if not self.department.strip() or not self.model_version.strip():
            raise WorkflowError("Predicción sin destino o versión del modelo.")


@dataclass
class Workflow:
    dossier_id: str
    revision: int = 0
    procedure_code: str | None = None
    validation: dict = field(default_factory=dict)
    routing: dict = field(default_factory=dict)
    drafts: list[dict] = field(default_factory=list)
    audit: list[dict] = field(default_factory=list)

    def record(self, actor: str, action: str, detail: dict):
        if not actor.strip():
            raise WorkflowError("Se requiere un evaluador identificado.")
        self.audit.append({"actor": actor, "action": action, "detail": detail,
                           "at": datetime.now(timezone.utc).isoformat()})


def evaluate_requirements(procedure, documents, checks):
    expected = {r.id for r in procedure.requirements}
    if set(checks) - expected:
        raise WorkflowError("Se enviaron requisitos que no pertenecen al trámite.")
    pages = {page for document in documents for page in document.pages}
    results = []
    for requirement in procedure.requirements:
        evidence = sorted({p for d in documents if d.type in requirement.document_types for p in d.pages})
        check = checks.get(requirement.id)
        state, note, reviewed_pages = "PENDIENTE", "", []
        if check:
            state, note = check["estado"], check["nota"].strip()
            reviewed_pages = check.get("paginas", [])
            if state not in {"CUMPLE", "FALTA", "NO_APLICA", "PENDIENTE"}:
                raise WorkflowError("Estado de requisito inválido.")
            if not note:
                raise WorkflowError("Cada verificación debe incluir su fundamento.")
            if state == "NO_APLICA" and not requirement.conditional:
                raise WorkflowError("Un requisito obligatorio no puede marcarse NO_APLICA.")
            if not set(reviewed_pages).issubset(pages):
                raise WorkflowError("La evidencia cita páginas que no existen en el expediente.")
        results.append({"id": requirement.id, "descripcion": requirement.description,
                        "condicional": requirement.conditional, "estado": state,
                        "paginas_candidatas": evidence, "paginas_revisadas": reviewed_pages,
                        "nota": note})
    states = {r["estado"] for r in results}
    status = "OBSERVADO" if "FALTA" in states else "PENDIENTE_REVISION" if "PENDIENTE" in states else "CONFORME"
    return {"estado": status, "alcance": "PREVALIDACION_DOCUMENTAL_ACADEMICA",
            "habilitado_enrutamiento": status == "CONFORME", "requisitos": results,
            "fuente": procedure.source_url, "version_fuente": procedure.source_version,
            "paginas_fuente": list(procedure.pdf_pages),
            "advertencia": "La clasificación OCR no verifica firmas, pagos ni validez legal. Requiere revisión humana; no emite actos administrativos."}


def decide_route(prediction, allowed_departments):
    if prediction.department not in allowed_departments:
        raise WorkflowError("El modelo devolvió una unidad desconocida para el catálogo.")
    automatic = prediction.confidence > 0.85
    return {"estado": "DERIVADO_LOCAL" if automatic else "CLASIFICACION_MANUAL",
            "destino": prediction.department if automatic else None,
            "sugerencia": prediction.department, "confianza": prediction.confidence,
            "modelo": prediction.model_version, "alerta": not automatic,
            "alcance": "BANDEJA_LOCAL_NO_SISGEDOC"}
