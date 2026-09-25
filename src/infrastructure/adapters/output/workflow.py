import json
from dataclasses import asdict
from pathlib import Path
from sqlalchemy import JSON, Column, Integer, MetaData, String, Table, select
from sqlalchemy.exc import IntegrityError
from src.domain.workflow import Conflict, DependencyUnavailable, Procedure, Requirement, Workflow


class JSONProcedureCatalog:
    def __init__(self, path):
        self.metadata = json.loads(Path(path).read_text(encoding="utf-8"))
        self.procedures = {}
        for item in self.metadata["procedures"]:
            requirements = tuple(Requirement(r["id"], r["description"],
                                             tuple(r.get("document_types", [])),
                                             r.get("conditional", False)) for r in item["requirements"])
            procedure = Procedure(item["code"], item["name"], item["department"],
                                  item["published_days"], requirements, self.metadata["source_url"],
                                  tuple(item["pdf_pages"]), self.metadata["source_version"])
            if procedure.code in self.procedures:
                raise ValueError("Código TUPA duplicado en catálogo.")
            self.procedures[procedure.code] = procedure

    def list(self):
        return list(self.procedures.values())

    def get(self, code):
        return self.procedures.get(code)


class SQLWorkflowRepository:
    def __init__(self, engine):
        self.engine = engine
        metadata = MetaData()
        self.table = Table("flujos_municipales", metadata,
                           Column("dossier_id", String(36), primary_key=True),
                           Column("revision", Integer, nullable=False),
                           Column("payload", JSON, nullable=False))
        metadata.create_all(engine)

    def get(self, dossier_id):
        with self.engine.connect() as connection:
            payload = connection.execute(select(self.table.c.payload).where(
                self.table.c.dossier_id == dossier_id)).scalar_one_or_none()
        return Workflow(**payload) if payload is not None else None

    def save(self, workflow, expected_revision):
        payload = asdict(workflow)
        payload["revision"] = expected_revision + 1
        try:
            with self.engine.begin() as connection:
                if expected_revision == 0:
                    connection.execute(self.table.insert().values(dossier_id=workflow.dossier_id,
                                       revision=1, payload=payload))
                else:
                    result = connection.execute(self.table.update().where(
                        (self.table.c.dossier_id == workflow.dossier_id) &
                        (self.table.c.revision == expected_revision)).values(
                            revision=expected_revision + 1, payload=payload))
                    if result.rowcount != 1:
                        raise Conflict("Actualización concurrente; vuelva a consultar el flujo.")
        except IntegrityError as error:
            raise Conflict("El flujo ya fue creado; vuelva a consultarlo.") from error
        workflow.revision = expected_revision + 1


class UnavailableRoutingModel:
    def predict(self, dossier):
        raise DependencyUnavailable("No hay un modelo local validado con datos de Huancayo.")


class UnavailableAdministrativeGateway:
    def require_available(self):
        raise DependencyUnavailable("Firma, SISGEDOC y notificaciones no configurados. No se realizó ninguna emisión.")
