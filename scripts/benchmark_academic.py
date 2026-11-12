"""Measure existing SQLite queries and local ASGI reads on synthetic data."""

import argparse
from dataclasses import asdict
import json
from math import ceil
from pathlib import Path
from secrets import token_hex
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter, process_time
import tracemalloc
from uuid import UUID

from fastapi.testclient import TestClient

from src.domain.entities import Dossier
from src.infrastructure.adapters.output.database import SQLDossierRepository
from src.infrastructure.main import create_app
from src.infrastructure.settings import Settings


def quantiles(values):
    ordered = sorted(values)
    return {"p50_ms": round(median(values), 3), "p95_ms": round(ordered[ceil(len(values) * .95) - 1], 3)}


def measure(folder, rows, requests, roles):
    db = folder / "benchmark.sqlite"
    token = token_hex(32)
    options = {"academic_demo": True, "academic_accounts": [
        {"id": "evaluador-banco", "role": "evaluador", "token": token}]} if roles else {}
    settings = Settings(_env_file=None, database_url=f"sqlite:///{db}", storage_dir=str(folder / "pdf"),
                        protect_dossier_routes=True, reviewer_id="revisor-banco",
                        reviewer_token=token_hex(32) if roles else token, ai_provider="none", **options)
    repository = SQLDossierRepository(settings.database_url)
    ids = [str(UUID(int=index)) for index in range(1, rows + 1)]
    with repository.engine.begin() as connection:
        payloads = []
        for dossier_id in ids:
            row = asdict(Dossier(dossier_id, "sintetico.pdf", "ficticio", status="PROCESADO"))
            if roles:
                row["academic_owner"] = "evaluador-banco"
            else:
                row.pop("academic_owner", None)
            payloads.append({"id": dossier_id, "payload": row})
        connection.execute(repository.table.insert(), payloads)
    status_query = "SELECT COUNT(*) FROM expedientes WHERE json_extract(payload, '$.status') = 'PROCESADO'"
    lookup_query = "SELECT payload FROM expedientes WHERE id = ?"
    with repository.engine.connect() as connection:
        lookup_plan = connection.exec_driver_sql("EXPLAIN QUERY PLAN " + lookup_query, (ids[0],)).one()[-1]
        status_plan = connection.exec_driver_sql("EXPLAIN QUERY PLAN " + status_query).one()[-1]
        status_times = []
        for _ in range(12):
            start = perf_counter()
            assert connection.exec_driver_sql(status_query).scalar_one() == rows
            status_times.append((perf_counter() - start) * 1000)
    repository.engine.dispose()

    headers = {"Authorization": "Bearer " + token}
    times = []
    with TestClient(create_app(settings)) as client:
        assert client.get(f"/api/expedientes/{ids[0]}", headers=headers).status_code == 200
        cpu_start = process_time()
        for index in range(requests):
            start = perf_counter()
            response = client.get(f"/api/expedientes/{ids[(index * 73) % rows]}", headers=headers)
            times.append((perf_counter() - start) * 1000)
            assert response.status_code == 200
        cpu_ms = (process_time() - cpu_start) * 1000
        tracemalloc.start()
        for dossier_id in ids[:min(30, rows)]:
            assert client.get(f"/api/expedientes/{dossier_id}", headers=headers).status_code == 200
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
    return {"filas": rows, "consultas_asgi": requests, "roles": roles, "consulta_uuid": quantiles(times),
            "conteo_estado_sql": quantiles(status_times), "plan_uuid": lookup_plan, "plan_estado": status_plan,
            "cpu_lote_ms": round(cpu_ms, 2), "pico_memoria_python_kib": round(peak / 1024, 1),
            "sqlite_kib": round(db.stat().st_size / 1024, 1)}


def main():
    parser = argparse.ArgumentParser(description="Medición local sobre SQLite y expedientes sintéticos.")
    parser.add_argument("--rows", type=int, nargs="+", default=[1000, 10000])
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--roles", action="store_true")
    args = parser.parse_args()
    if min(args.rows) < 1 or args.requests < 1:
        parser.error("Los volúmenes y las solicitudes deben ser positivos.")
    for rows in args.rows:
        with TemporaryDirectory(prefix="gobexpedientes-benchmark-") as directory:
            print(json.dumps(measure(Path(directory), rows, args.requests, args.roles), ensure_ascii=False))


if __name__ == "__main__":
    main()
