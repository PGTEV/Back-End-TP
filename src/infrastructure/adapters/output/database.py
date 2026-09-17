from dataclasses import asdict
from pathlib import Path
from sqlalchemy import JSON, Column, MetaData, String, Table, create_engine, select
from sqlalchemy.engine import make_url
from src.domain.entities import Document, Dossier


class SQLDossierRepository:
    def __init__(self, url: str):
        parsed = make_url(url)
        if parsed.drivername.startswith("sqlite") and parsed.database not in (None, ":memory:"):
            Path(parsed.database).parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(url, pool_pre_ping=True)
        metadata = MetaData()
        self.table = Table("expedientes", metadata,
                           Column("id", String(36), primary_key=True),
                           Column("payload", JSON, nullable=False))
        metadata.create_all(self.engine)

    def save(self, dossier: Dossier) -> None:
        with self.engine.begin() as connection:
            exists = connection.execute(select(self.table.c.id).where(self.table.c.id == dossier.id)).first()
            if exists:
                connection.execute(self.table.update().where(self.table.c.id == dossier.id)
                                   .values(payload=asdict(dossier)))
            else:
                connection.execute(self.table.insert().values(id=dossier.id, payload=asdict(dossier)))

    def get(self, dossier_id: str) -> Dossier | None:
        with self.engine.connect() as connection:
            data = connection.execute(select(self.table.c.payload)
                                      .where(self.table.c.id == dossier_id)).scalar_one_or_none()
        if data is None:
            return None
        data["documents"] = [Document(**document) for document in data["documents"]]
        return Dossier(**data)
