from typing import Protocol
from src.domain.entities import Dossier
from src.domain.workflow import Procedure, RoutingPrediction, Workflow


class ProcedureCatalog(Protocol):
    def list(self) -> list[Procedure]: ...
    def get(self, code: str) -> Procedure | None: ...


class WorkflowRepository(Protocol):
    def get(self, dossier_id: str) -> Workflow | None: ...
    def save(self, workflow: Workflow, expected_revision: int) -> None: ...


class LocalRoutingModel(Protocol):
    """El adaptador debe ejecutarse localmente; no recibe permiso de transmitir PII."""
    def predict(self, dossier: Dossier) -> RoutingPrediction: ...


class AcademicIndicatorEstimator(Protocol):
    def predict(self, published_days: int, pages: int, missing: int, pending: int, conflict: bool) -> dict: ...


class AdministrativeGateway(Protocol):
    def require_available(self) -> None: ...
    def issue(self, dossier_id: str, draft: dict, actor: str) -> dict: ...


class RequirementAuditor(Protocol):
    def checks(self, procedure: Procedure, dossier: Dossier) -> dict: ...


class PrivacyFilter(Protocol):
    def preview(self, text: str, known_names: list[str]) -> dict: ...


class DraftGenerator(Protocol):
    def generate(self, facts: dict) -> dict: ...


class EvidenceAuditAssistant(Protocol):
    def analyze(self, facts: dict) -> dict: ...
