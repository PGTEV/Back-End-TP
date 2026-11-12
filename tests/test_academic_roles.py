from secrets import token_hex

import pymupdf
import pytest
from fastapi.testclient import TestClient

from scripts.academic_examples import demo_pdf
from src.infrastructure.main import create_app
from src.infrastructure.settings import Settings


AREA = "Gerencia de Desarrollo Urbano"
OTHER_AREA = "Gerencia de Promoción Económica y Turismo"
CODE = "PA12115285"


@pytest.fixture
def demo_settings(tmp_path):
    accounts = [
        dict(id="evaluador-uno", role="evaluador"),
        dict(id="evaluador-dos", role="evaluador"),
        dict(id="admin-demo", role="administrador"),
        dict(id="responsable-uno", role="responsable", department=AREA),
        dict(id="responsable-dos", role="responsable", department=OTHER_AREA),
    ]
    return Settings(_env_file=None, database_url=f"sqlite:///{tmp_path / 'demo.sqlite'}",
                    storage_dir=str(tmp_path / "pdf"), academic_demo=True,
                    protect_dossier_routes=True, reviewer_id="revisor-compatibilidad", reviewer_token=token_hex(32),
                    academic_accounts=[{**account, "token": token_hex(32)} for account in accounts],
                    ai_provider="none")


def auth(settings, actor):
    return {"Authorization": "Bearer " + next(a.token.get_secret_value()
            for a in settings.academic_accounts if a.id == actor)}


def upload(client, headers, content=None):
    return client.post("/api/expedientes", headers=headers,
                       files={"archivo": ("ficticio.pdf", content if content is not None else demo_pdf(), "application/pdf")})


def test_roles_isolate_dossiers_and_close_only_with_assigned_responsible(demo_settings):
    eval1, eval2, admin, lead, other = [auth(demo_settings, name) for name in
        ("evaluador-uno", "evaluador-dos", "admin-demo", "responsable-uno", "responsable-dos")]
    legacy = {"Authorization": "Bearer " + demo_settings.reviewer_token.get_secret_value()}
    with TestClient(create_app(demo_settings)) as client:
        assert client.get("/api/academico/sesion").status_code == 401
        for headers, role in ((eval1, "evaluador"), (admin, "administrador"), (lead, "responsable"), (legacy, None)):
            session = client.get("/api/academico/sesion", headers=headers)
            assert session.status_code == 200 and session.json()["rol"] == role
            assert session.headers["cache-control"] == "no-store" and "token" not in session.json()
        assert upload(client, admin).status_code == 403
        assert upload(client, lead).status_code == 403
        created = upload(client, eval1)
        assert created.status_code == 201
        path = "/api/expedientes/" + created.json()["id"]
        assert "academic_owner" not in created.json()
        for denied in (eval2, lead, other, legacy):
            for suffix in ("", "/flujo", "/documentos/0/pdf", "/indicadores"):
                assert client.get(path + suffix, headers=denied).status_code == 404
        assert client.get(path, headers=admin).status_code == 200

        validated = client.post(path + "/validacion", headers=eval1, json={"codigo_tupa": CODE, "revision": 0}).json()
        assert validated["validation"]["estado"] == "CONFORME"
        indicators = client.get(path + "/indicadores", headers=eval1).json()
        assert indicators["eta"]["dias_habiles_predichos"] is None  # The legacy contract stays unavailable.
        predicted = indicators["academico"]
        assert predicted["origen"] == "SINTETICO" and predicted["revision_humana"]
        assert predicted["dias_estimados"] > 0 and 0 < predicted["probabilidad_rechazo"] < 1
        proposed = client.post(path + "/enrutamiento", headers=eval1, json={"revision": validated["revision"]}).json()
        assert proposed["routing"]["destino"] is None
        assert client.get(path, headers=lead).status_code == 404
        assigned = client.post(path + "/asignacion", headers=admin,
                               json={"destino": AREA, "revision": proposed["revision"]})
        assert assigned.status_code == 200 and assigned.json()["routing"]["responsable_id"] == "responsable-uno"
        assert client.get(path + "/documentos/0/pdf", headers=lead).status_code == 200
        assert client.get(path, headers=other).status_code == 404
        payload = {"revision": assigned.json()["revision"]}
        for denied in (eval1, admin, other):
            expected = 404 if denied == other else 403
            assert client.post(path + "/aprobar-firmar", headers=denied, json=payload).status_code == expected
        assert client.post(path + "/borradores", headers=lead, json={**payload, "contenido": "Ficticio"}).status_code == 403
        closed = client.post(path + "/aprobar-firmar", headers=lead, json=payload)
        assert closed.status_code == 200
        flow = closed.json()
        receipt = flow["drafts"][-1]
        assert receipt["firma"]["validez_legal"] is False
        assert receipt["sisgedoc"]["transmision_externa"] is False
        assert receipt["notificacion"]["envio_real"] is False
        assert receipt["firma"]["firmante"] == "responsable-uno"
        assert [event["actor"] for event in flow["audit"]] == [
            "evaluador-uno", "evaluador-uno", "admin-demo", "responsable-uno",
        ]
        assert client.post(path + "/aprobar-firmar", headers=lead, json={"revision": flow["revision"]}).json() == flow
        original = upload(client, legacy)
        original_path = "/api/expedientes/" + original.json()["id"]
        assert client.get(original_path, headers=legacy).status_code == 200
        assert "academico" not in client.get(original_path + "/indicadores", headers=legacy).json()
        assert client.get(original_path, headers=admin).status_code == 404

    reverted = demo_settings.model_copy(update={"academic_accounts": []})
    with TestClient(create_app(reverted)) as client:
        assert client.get(path, headers=legacy).status_code == 404
        assert client.get(original_path, headers=legacy).status_code == 200
        assert "roles_academicos" not in client.get("/api/capacidades").json()["seguridad"]


def test_unmarked_upload_leaves_no_record_or_original(demo_settings, tmp_path):
    with pymupdf.open() as pdf:
        pdf.new_page().insert_text((50, 60), "FORMULARIO UNICO DE TRAMITE\nDOCUMENTO DE CONTROL SIN MARCA")
        content = pdf.tobytes()
    with TestClient(create_app(demo_settings)) as client:
        assert upload(client, auth(demo_settings, "evaluador-uno"), content).status_code == 400
        assert client.get("/health/db").json()["expedientes"] == 0
        assert not list((tmp_path / "pdf").glob("*.pdf"))


@pytest.mark.parametrize("flags", [{"academic_demo": False}, {"protect_dossier_routes": False}])
def test_accounts_require_explicit_protected_demo_mode(demo_settings, flags):
    with pytest.raises(ValueError, match="requieren modo académico"):
        create_app(demo_settings.model_copy(update=flags))
