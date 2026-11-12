from contextlib import closing
from datetime import datetime, timezone
import json
import sqlite3

import pytest

from scripts.inspect_processing import inspect_processing


NOW = datetime(2026, 11, 12, 12, tzinfo=timezone.utc)


def test_counts_pending_rows_and_preserves_snapshot(tmp_path):
    snapshot = tmp_path / "copia sintética.sqlite"
    rows = [
        ("PROCESANDO", "2026-11-12T10:00:00+00:00"),
        ("PROCESANDO", "2026-11-12T06:00:00-05:00"),
        ("PROCESANDO", "2026-11-12T11:30:00+00:00"),
        ("PROCESANDO", "2026-11-12T07:30:00"),
        ("PROCESANDO", None),
        ("PROCESADO", "2026-11-11T06:00:00+00:00"),
        ("ERROR", "2026-11-11T06:00:00+00:00"),
    ]
    with closing(sqlite3.connect(snapshot)) as connection:
        connection.execute("CREATE TABLE expedientes (id TEXT PRIMARY KEY, payload JSON NOT NULL)")
        connection.executemany("INSERT INTO expedientes VALUES (?, ?)", [
            (str(index), json.dumps({"status": status, "created_at": value}))
            for index, (status, value) in enumerate(rows)
        ])
        connection.commit()

    original = snapshot.read_bytes()
    assert inspect_processing(snapshot, 60, NOW) == {
        "estancados": 2,
        "recientes": 1,
        "sin_fecha_valida": 2,
    }
    assert snapshot.read_bytes() == original


def test_missing_snapshot_is_never_created(tmp_path):
    snapshot = tmp_path / "ausente.sqlite"
    with pytest.raises(sqlite3.OperationalError):
        inspect_processing(snapshot, 60, NOW)
    assert not snapshot.exists()
