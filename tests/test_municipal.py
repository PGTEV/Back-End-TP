from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from src.domain.privacy import LocalPrivacyFilter
from src.domain.valueObjects import Page
from src.domain.workflow import (Conflict, RoutingPrediction, Workflow, WorkflowError,
                                 decide_route, evaluate_requirements)
from src.infrastructure.adapters.output.database import SQLDossierRepository
from src.infrastructure.adapters.output.workflow import JSONProcedureCatalog, SQLWorkflowRepository
from src.infrastructure.main import create_app
from src.infrastructure.settings import Settings

TOKEN = "solo-pruebas-" + "a" * 40
HEADERS = {"Authorization": "Bearer " + TOKEN}
ROOT = Path(__file__).parents[1]


class Reader:
    def extract(self, content):
        return [Page(1, "FORMULARIO UNICO DE TRAMITE\nDNI: 12345678\n"
                     "Nombres y apellidos: Persona Ficticia\nSOLICITO: certificado", 1.0, "TEXTO_PDF"),
                Page(2, "PLANO DE UBICACION\nESCALA: 1:500\nLAMINA: A01", 1.0, "TEXTO_PDF")]


@pytest.fixture
def settings(tmp_path):
    return Settings(database_url=f"sqlite:///{tmp_path / 'db.sqlite'}", storage_dir=str(tmp_path / "pdf"),
                    reviewer_token=TOKEN, reviewer_id="evaluador-pruebas")


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings, reader=Reader())) as client:
        yield client


def upload(client):
    response = client.post("/api/expedientes", files={"archivo": ("prueba.pdf", b"%PDF-FAKE", "application/pdf")})
    assert response.status_code == 201
    return response.json()["id"]


def validate(client, dossier_id, revision=0, checks=None, code="PA12115285"):
    return client.post(f"/api/expedientes/{dossier_id}/validacion", headers=HEADERS,
                       json={"revision": revision, "codigo_tupa": code, "verificaciones": checks or {}})


def complete_checks():
    return {key: {"estado": "CUMPLE", "nota": "Verificado por evaluador ficticio para test.", "paginas": []}
            for key in ["solicitud", "identidad", "plano_firmado", "pago"]}


def test_catalog_sources_and_capabilities(client):
    data = client.get("/api/tupa/procedimientos").json()
    assert data["catalogo_completo"] is False
    assert data["vigencia_normativa_2026_certificada"] is False
    assert {p["code"] for p in data["procedimientos"]} == {"PA12115285", "PA121121B0", "PE1027344C1"}
    assert all("8019739" in p["source_url"] for p in data["procedimientos"])
    assert "NO_DISPONIBLE" in client.get("/api/capacidades").json()["HU05"]


def test_candidate_document_never_means_compliant_signature(client):
    dossier_id = upload(client)
    response = validate(client, dossier_id)
    assert response.status_code == 200, response.text
    flow = response.json()
    assert flow["revision"] == 1
    assert flow["validation"]["estado"] == "PENDIENTE_REVISION"
    plan = next(r for r in flow["validation"]["requisitos"] if r["id"] == "plano_firmado")
    assert plan["paginas_candidatas"] == [2]
    assert plan["estado"] == "PENDIENTE"
    assert client.post(f"/api/expedientes/{dossier_id}/enrutamiento", headers=HEADERS,
                       json={"revision": 1}).status_code == 409


def test_missing_payment_creates_observation_and_retains_versions(client, settings):
    dossier_id = upload(client)
    checks = complete_checks()
    checks["pago"] = {"estado": "FALTA", "nota": "No hay acreditación de pago."}
    flow = validate(client, dossier_id, checks=checks).json()
    assert flow["validation"]["estado"] == "OBSERVADO"
    assert flow["drafts"][0]["origen"] == "PLANTILLA_LOCAL"
    original = flow["drafts"][0]["contenido"]
    response = client.post(f"/api/expedientes/{dossier_id}/borradores", headers=HEADERS,
                           json={"revision": 1, "contenido": "Corrección técnica de prueba"})
    assert response.status_code == 201, response.text
    flow = response.json()
    assert flow["drafts"][0]["contenido"] == original
    assert flow["drafts"][0]["vigente"] is False
    assert flow["drafts"][1]["version"] == 2
    assert flow["audit"][-1]["actor"] == "evaluador-pruebas"
    with TestClient(create_app(settings, reader=Reader())) as restarted:
        assert restarted.get(f"/api/expedientes/{dossier_id}/flujo", headers=HEADERS).json() == flow


def test_no_fake_signature_or_side_effect(client):
    dossier_id = upload(client)
    validate(client, dossier_id)
    client.post(f"/api/expedientes/{dossier_id}/borradores", headers=HEADERS,
                json={"revision": 1, "contenido": "Proyecto de prueba"})
    before = client.get(f"/api/expedientes/{dossier_id}/flujo", headers=HEADERS).json()
    response = client.post(f"/api/expedientes/{dossier_id}/aprobar-firmar", headers=HEADERS,
                           json={"revision": 2})
    assert response.status_code == 503
    assert before == client.get(f"/api/expedientes/{dossier_id}/flujo", headers=HEADERS).json()
    assert before["drafts"][-1]["firma"] is None


def test_conforme_manual_route_and_honest_predictions(client):
    dossier_id = upload(client)
    assert validate(client, dossier_id, checks=complete_checks()).json()["validation"]["estado"] == "CONFORME"
    response = client.post(f"/api/expedientes/{dossier_id}/enrutamiento", headers=HEADERS,
                           json={"revision": 1})
    assert response.status_code == 200, response.text
    route = response.json()["routing"]
    assert route["estado"] == "CLASIFICACION_MANUAL"
    assert route["confianza"] is None
    assert route["sugerencia"] == "Gerencia de Desarrollo Urbano"
    response = client.post(f"/api/expedientes/{dossier_id}/asignacion", headers=HEADERS,
                           json={"revision": 2, "destino": "Gerencia de Desarrollo Urbano"})
    assert response.json()["routing"]["estado"] == "DERIVADO_LOCAL"
    indicators = client.get(f"/api/expedientes/{dossier_id}/indicadores", headers=HEADERS).json()
    assert indicators["eta"]["dias_habiles_predichos"] is None
    assert indicators["eta"]["plazo_tupa_referencial_dias_habiles"] == 5
    assert indicators["riesgo"]["probabilidad_rechazo"] is None
    flow = validate(client, dossier_id, revision=3).json()
    assert flow["routing"] == {}


@pytest.mark.parametrize("confidence,expected", [(0.86, "DERIVADO_LOCAL"), (0.85, "CLASIFICACION_MANUAL"),
                                                 (0.84, "CLASIFICACION_MANUAL")])
def test_predictive_threshold_domain_contract(confidence, expected):
    assert decide_route(RoutingPrediction("GDU", confidence, "fake-test-model"), {"GDU"})["estado"] == expected


@pytest.mark.parametrize("confidence", [float("nan"), float("inf"), -0.1, 1.1])
def test_model_invalid_probabilities(confidence):
    with pytest.raises(WorkflowError):
        RoutingPrediction("GDU", confidence, "test")


def test_unknown_model_destination_rejected():
    with pytest.raises(WorkflowError):
        decide_route(RoutingPrediction("INVENTADA", 0.99, "test"), {"GDU"})


def test_privacy_no_transmission_or_original_mutation(client):
    dossier_id = upload(client)
    original = client.get(f"/api/expedientes/{dossier_id}").json()
    result = client.post(f"/api/expedientes/{dossier_id}/privacidad/vista-previa", headers=HEADERS,
                         json={}).json()
    assert "12345678" not in result["texto_enmascarado"]
    assert "Persona Ficticia" not in result["texto_enmascarado"]
    assert "[DNI_1]" in result["texto_enmascarado"]
    assert "[NOMBRE_1]" in result["texto_enmascarado"]
    assert result["transmision_externa_habilitada"] is False
    assert original == client.get(f"/api/expedientes/{dossier_id}").json()


def test_privacy_repeated_tokens_and_case():
    result = LocalPrivacyFilter().preview("Persona Ficticia PERSONA FICTICIA 12345678 12345678", ["Persona Ficticia"])
    assert result["texto_enmascarado"] == "[NOMBRE_1] [NOMBRE_1] [DNI_1] [DNI_1]"


def test_review_authentication_and_optimistic_lock(client):
    dossier_id = upload(client)
    url = f"/api/expedientes/{dossier_id}/validacion"
    body = {"revision": 0, "codigo_tupa": "PA12115285"}
    assert client.post(url, json=body).status_code == 401
    assert client.post(url, json=body, headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.post(url, json={**body, "actor": "alcalde"}, headers=HEADERS).status_code == 422
    assert validate(client, dossier_id).status_code == 200
    assert validate(client, dossier_id).status_code == 409


def test_unconfigured_reviewer_fails_closed(settings):
    settings = Settings(**{**settings.model_dump(), "reviewer_token": ""})
    with TestClient(create_app(settings, reader=Reader())) as client:
        dossier_id = upload(client)
        assert validate(client, dossier_id).status_code == 503


@pytest.mark.parametrize("checks", [
    {"inventado": {"estado": "CUMPLE", "nota": "prueba"}},
    {"pago": {"estado": "NO_APLICA", "nota": "prueba"}},
    {"plano_firmado": {"estado": "CUMPLE", "nota": "prueba", "paginas": [999]}},
    {"pago": {"estado": "CUMPLE", "nota": "   "}},
])
def test_invalid_requirement_verifications(client, checks):
    assert validate(client, upload(client), checks=checks).status_code == 422


def test_unknown_procedure_and_dossier(client):
    assert validate(client, upload(client), code="NO_EXISTE").status_code == 404
    assert client.get(f"/api/expedientes/{uuid4()}/flujo", headers=HEADERS).status_code == 404


def test_conditional_requirement_may_not_apply():
    catalog = JSONProcedureCatalog(ROOT / "config/tupa_huancayo.json")
    result = evaluate_requirements(catalog.get("PE1027344C1"), [],
                                   {"salud": {"estado": "NO_APLICA", "nota": "No presta servicios de salud."}})
    assert next(r for r in result["requisitos"] if r["id"] == "salud")["estado"] == "NO_APLICA"
    assert result["estado"] == "PENDIENTE_REVISION"


def test_concurrent_writes_one_winner(settings):
    dossiers = SQLDossierRepository(settings.database_url)
    repository = SQLWorkflowRepository(dossiers.engine)
    dossier_id = str(uuid4())
    repository.save(Workflow(dossier_id), 0)
    first, second = repository.get(dossier_id), repository.get(dossier_id)
    first.record("uno", "PRUEBA", {})
    second.record("dos", "PRUEBA", {})

    def save(flow):
        try:
            repository.save(flow, 1)
            return "ok"
        except Conflict:
            return "conflict"

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(save, [first, second])) == ["conflict", "ok"]
        assert len(repository.get(dossier_id).audit) == 1
        assert repository.get(dossier_id).revision == 2
    finally:
        dossiers.engine.dispose()
