"""Bearer identities and dossier authorization for the isolated academic mode."""

from dataclasses import dataclass
from secrets import compare_digest
from uuid import UUID

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.infrastructure.adapters.input.security import reviewer_dependency


ACTIONS = {
    "administrador": frozenset({"consultar", "asignar"}),
    "evaluador": frozenset({"consultar", "cargar", "evaluar", "enrutar", "asignar"}),
    "responsable": frozenset({"consultar", "aprobar"}),
}


@dataclass(frozen=True)
class Actor:
    id: str
    role: str | None = None
    department: str | None = None


class AcademicAccess:
    def __init__(self, settings, dossiers, workflows, catalog):
        self.accounts = settings.academic_accounts
        self.protected = settings.protect_dossier_routes
        self.dossiers, self.workflows = dossiers, workflows
        self.responsibles = {account.department: account.id for account in self.accounts
                             if account.role == "responsable"}
        self._validate(settings, {procedure.department for procedure in catalog.list()})
        bearer = HTTPBearer(auto_error=False)
        legacy = reviewer_dependency(settings)
        legacy_configured = len(settings.reviewer_token.get_secret_value()) >= 32 and bool(settings.reviewer_id.strip())

        def authenticate(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
            if credentials is not None:
                token = credentials.credentials.encode()
                for account in self.accounts:
                    if compare_digest(account.token.get_secret_value().encode(), token):
                        return Actor(account.id, account.role, account.department)
            if self.accounts and not legacy_configured:
                raise HTTPException(401, "Credencial de evaluador inválida.",
                                    headers={"WWW-Authenticate": "Bearer"})
            return Actor(legacy(credentials))

        self.authenticate = authenticate

    def _validate(self, settings, departments):
        if not self.accounts:
            return
        if not (settings.academic_demo and self.protected):
            raise ValueError("Las cuentas académicas requieren modo académico y protección de expedientes.")
        ids = {settings.reviewer_id.strip()}
        tokens = {settings.reviewer_token.get_secret_value()}
        assigned_departments = set()
        for account in self.accounts:
            token = account.token.get_secret_value()
            if account.id in ids or token in tokens or len(token) < 32 or any(c.isspace() for c in token):
                raise ValueError("Las cuentas académicas requieren identificadores y tokens únicos y válidos.")
            ids.add(account.id)
            tokens.add(token)
            if account.role == "responsable":
                if account.department not in departments or account.department in assigned_departments:
                    raise ValueError("Cada responsable debe tener un área válida y única.")
                assigned_departments.add(account.department)
            elif account.department is not None:
                raise ValueError("Solo las cuentas responsables pueden indicar un área.")

    @staticmethod
    def _require(actor, action):
        if actor.role is not None and action not in ACTIONS[actor.role]:
            raise HTTPException(403, "Acción no autorizada para el rol académico.")

    def upload(self):
        authenticate = self.authenticate
        if not self.protected:
            return lambda: Actor("")

        def permit(actor: Actor = Depends(authenticate)):
            self._require(actor, "cargar")
            return actor

        return permit

    def read_actor(self):
        return self.authenticate if self.protected else lambda: Actor("")

    def authorize_dossier(self, actor, record):
        owner = record.academic_owner if record is not None else None
        if actor.role is None and owner is None:
            return  # Preserve the legacy route's missing-dossier response.
        if owner is not None:
            if actor.role == "administrador" or (actor.role == "evaluador" and owner == actor.id):
                return
            if actor.role == "responsable":
                flow = self.workflows.get(record.id)
                if flow and flow.routing.get("responsable_id") == actor.id:
                    return
        raise HTTPException(404, "Expediente no encontrado.")

    def for_dossier(self, action, *, public=False):
        authenticate = (lambda: Actor("")) if public else self.authenticate

        def permit(dossier_id: UUID, actor: Actor = Depends(authenticate)):
            self._require(actor, action)
            self.authorize_dossier(actor, self.dossiers.get(str(dossier_id)))
            return actor

        return permit

    def describe(self, actor):
        return {"id": actor.id, "rol": actor.role, "area": actor.department,
                "acciones": sorted(ACTIONS.get(actor.role, ())),
                "areas_asignables": sorted(self.responsibles) if actor.role in {"evaluador", "administrador"} else []}
