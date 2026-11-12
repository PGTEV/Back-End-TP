from dataclasses import asdict
from pathlib import Path
from sqlalchemy import JSON, Column, MetaData, String, Table, create_engine, select
from sqlalchemy.engine import make_url
from src.domain.entities import Document, Dossier


def normalize_database_url(url: str):
    """Adapta URLs de proveedores cloud (Supabase/Render) al driver psycopg v3 instalado."""
    url = url.strip()
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    parsed = make_url(url)
    if parsed.drivername == "postgresql":
        parsed = parsed.set(drivername="postgresql+psycopg")
    if parsed.drivername.startswith("postgresql") and parsed.host not in (None, "localhost", "127.0.0.1"):
        if "sslmode" not in parsed.query:
            parsed = parsed.update_query_dict({"sslmode": "require"})
    return parsed


class SQLDossierRepository:
    def __init__(self, url: str):
        parsed = normalize_database_url(url)
        if parsed.drivername.startswith("sqlite") and parsed.database not in (None, ":memory:"):
            Path(parsed.database).parent.mkdir(parents=True, exist_ok=True)
        connect_args = {}
        if parsed.drivername.startswith("postgresql"):
            # Compatible con el pooler de Supabase (PgBouncer) en modo transacción.
            connect_args["prepare_threshold"] = None
        self.engine = create_engine(parsed, pool_pre_ping=True, pool_recycle=300,
                                    connect_args=connect_args)
        metadata = MetaData()
        self.table = Table("expedientes", metadata,
                           Column("id", String(36), primary_key=True),
                           Column("payload", JSON, nullable=False))
        metadata.create_all(self.engine)

    def save(self, dossier: Dossier) -> None:
        payload = asdict(dossier)
        if dossier.academic_owner is None:
            payload.pop("academic_owner")
        with self.engine.begin() as connection:
            exists = connection.execute(select(self.table.c.id).where(self.table.c.id == dossier.id)).first()
            if exists:
                connection.execute(self.table.update().where(self.table.c.id == dossier.id)
                                   .values(payload=payload))
            else:
                connection.execute(self.table.insert().values(id=dossier.id, payload=payload))

    def get(self, dossier_id: str) -> Dossier | None:
        with self.engine.connect() as connection:
            data = connection.execute(select(self.table.c.payload)
                                      .where(self.table.c.id == dossier_id)).scalar_one_or_none()
        if data is None:
            return None
        data["documents"] = [Document(**document) for document in data["documents"]]
        return Dossier(**data)
