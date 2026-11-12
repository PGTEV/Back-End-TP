import json
from uuid import uuid4

from fastapi.testclient import TestClient

from src.infrastructure.adapters.input.metrics import logger
from src.infrastructure.main import create_app
from src.infrastructure.settings import Settings


def configured_app(tmp_path, **overrides):
    return create_app(Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'test.sqlite'}",
        storage_dir=str(tmp_path / "pdf"),
        protect_dossier_routes=True,
        reviewer_id="evaluador-sintetico",
        reviewer_token="t" * 32,
        **overrides,
    ))


def events(caplog):
    return [json.loads(record.getMessage().removeprefix("furps_request "))
            for record in caplog.records if record.name == logger.name]


def test_request_metrics_are_disabled_by_default(tmp_path, caplog):
    caplog.set_level("INFO", logger=logger.name)
    with TestClient(configured_app(tmp_path)) as client:
        assert client.get("/health").json() == {"estado": "ok"}
    assert events(caplog) == []


def test_request_metrics_use_templates_and_skip_unmatched_paths(tmp_path, caplog):
    caplog.set_level("INFO", logger=logger.name)
    dossier_id = str(uuid4())
    with TestClient(configured_app(tmp_path, request_metrics_enabled=True)) as client:
        assert client.get("/health").status_code == 200
        assert client.get(f"/api/expedientes/{dossier_id}?dni=12345678").status_code == 401
        assert client.get("/api/dato-sintetico-no-enrutado").status_code == 404

    observed = events(caplog)
    assert [(item["route"], item["method"], item["status"]) for item in observed] == [
        ("/health", "GET", 200),
        ("/api/expedientes/{dossier_id}", "GET", 401),
    ]
    assert all(set(item) == {"route", "method", "status", "duration_ms"} and item["duration_ms"] >= 0
               for item in observed)


def test_request_metrics_report_server_error_without_exception_text(tmp_path, caplog):
    caplog.set_level("INFO", logger=logger.name)
    app = configured_app(tmp_path, request_metrics_enabled=True)

    @app.get("/api/test-error")
    def fail():
        raise RuntimeError("dato sintético que no debe entrar en las métricas")

    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get("/api/test-error").status_code == 500
    assert events(caplog)[0]["status"] == 500
    assert "dato sintético" not in caplog.text
