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


class AdministrativeGateway(Protocol):
    def require_available(self) -> None: ...


class PrivacyFilter(Protocol):
    def preview(self, text: str, known_names: list[str]) -> dict: ...
