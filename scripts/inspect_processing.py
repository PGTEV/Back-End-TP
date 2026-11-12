"""Count pending dossiers in an isolated, read-only SQLite snapshot."""

import argparse
from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3


def inspect_processing(snapshot: Path, minutes: int, now: datetime) -> dict[str, int]:
    if minutes <= 0:
        raise ValueError("El umbral debe ser mayor que cero.")
    cutoff = now - timedelta(minutes=minutes)
    counts = {"estancados": 0, "recientes": 0, "sin_fecha_valida": 0}

    uri = f"{snapshot.resolve().as_uri()}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        rows = connection.execute("""
            SELECT json_extract(payload, '$.created_at')
            FROM expedientes
            WHERE json_extract(payload, '$.status') = 'PROCESANDO'
        """)
        for (value,) in rows:
            created_at = None
            if isinstance(value, str):
                try:
                    created_at = datetime.fromisoformat(value)
                except ValueError:
                    pass
            if created_at is None or created_at.utcoffset() is None:
                counts["sin_fecha_valida"] += 1
            elif created_at <= cutoff:
                counts["estancados"] += 1
            else:
                counts["recientes"] += 1

    return counts


def main():
    parser = argparse.ArgumentParser(description="Cuenta estados PROCESANDO en una copia SQLite aislada.")
    parser.add_argument("snapshot", type=Path, help="Copia consistente obtenida con la API de respaldo de SQLite.")
    parser.add_argument("--minutos", required=True, type=int, help="Umbral de antigüedad elegido para la inspección.")
    args = parser.parse_args()
    try:
        counts = inspect_processing(args.snapshot, args.minutos, datetime.now(timezone.utc))
    except (sqlite3.Error, ValueError, OverflowError) as error:
        parser.exit(1, f"No se pudo inspeccionar la copia: {error}\n")
    print(json.dumps(counts))


if __name__ == "__main__":
    main()
