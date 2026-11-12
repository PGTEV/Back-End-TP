"""Start an isolated, loopback-only demonstration with generated credentials."""

import argparse
from pathlib import Path
from secrets import token_hex
from tempfile import TemporaryDirectory

import uvicorn

from scripts.academic_examples import ROOT, write_examples
from src.infrastructure.adapters.output.workflow import JSONProcedureCatalog
from src.infrastructure.main import create_app
from src.infrastructure.settings import Settings


def isolated_settings(folder: Path, origin: str):
    catalog = JSONProcedureCatalog(ROOT / "config/tupa_huancayo.json")
    departments = sorted({procedure.department for procedure in catalog.list()})
    accounts = [
        {"id": "admin-demo", "role": "administrador"},
        {"id": "evaluador-demo", "role": "evaluador"},
        {"id": "evaluador-control", "role": "evaluador"},
        *({"id": f"responsable-{index}", "role": "responsable", "department": area}
          for index, area in enumerate(departments, 1)),
    ]
    return Settings(_env_file=None, academic_demo=True, protect_dossier_routes=True,
                    database_url=f"sqlite:///{folder / 'demo.sqlite'}",
                    storage_dir=str(folder / "originales"), cors_origins=[origin], ai_provider="none",
                    reviewer_id="revisor-legado", reviewer_token=token_hex(32),
                    academic_accounts=[{**account, "token": token_hex(32)} for account in accounts])


def main():
    parser = argparse.ArgumentParser(description="Demostración local aislada, con datos y credenciales ficticios.")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--frontend-origin", default="http://localhost:5173")
    args = parser.parse_args()
    with TemporaryDirectory(prefix="gobexpedientes-demo-") as temporary:
        folder = Path(temporary)
        settings = isolated_settings(folder, args.frontend_origin)
        fixtures = folder / "ejemplos"
        write_examples(fixtures)
        print(f"Demostración académica sin validez legal · PDFs ficticios: {fixtures}", flush=True)
        print("Credenciales efímeras de esta sesión local:", flush=True)
        for account in settings.academic_accounts:
            area = f" · {account.department}" if account.department else ""
            print(f"{account.id} · {account.role}{area} · {account.token.get_secret_value()}", flush=True)
        print(f"{settings.reviewer_id} · compatibilidad · {settings.reviewer_token.get_secret_value()}", flush=True)
        uvicorn.run(create_app(settings), host="127.0.0.1", port=args.port, access_log=False)


if __name__ == "__main__":
    main()
