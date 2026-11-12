from pathlib import Path

from src.domain.entities import Document, Dossier
from src.infrastructure.adapters.output.academic import AcademicRequirementAuditor, SyntheticRoutingModel
from src.infrastructure.adapters.output.academic_indicators import (
    ROUTING_HOLDOUT, SyntheticAcademicIndicators, assess_routing,
)
from src.infrastructure.adapters.output.workflow import JSONProcedureCatalog


def test_synthetic_models_pass_independent_metrics_and_decline_out_of_range():
    model = SyntheticAcademicIndicators()
    assert model.metrics["entrenamiento"] == 1200
    assert model.metrics["evaluacion"] == 400
    assert model.metrics["eta_mae_dias"] <= 2
    assert model.metrics["riesgo_brier"] <= 0.20
    assert model.metrics["riesgo_exactitud_balanceada"] >= 0.65
    low = model.predict(10, 3, 0, 0, False)
    high = model.predict(10, 3, 5, 0, True)
    assert high["dias_estimados"] > low["dias_estimados"]
    assert high["probabilidad_rechazo"] > low["probabilidad_rechazo"]
    outside = model.predict(10, 31, 5, 0, True)
    assert outside["dias_estimados"] is outside["probabilidad_rechazo"] is None
    assert outside["revision_humana"]


def test_existing_route_model_is_evaluated_on_distinct_synthetic_texts():
    path = Path(__file__).resolve().parents[1] / "config" / "tupa_huancayo.json"
    catalog = JSONProcedureCatalog(path)
    model = SyntheticRoutingModel(catalog)
    training = {row["texto"] for row in model.training_rows}
    holdout = {sentence for texts in ROUTING_HOLDOUT.values() for sentence in texts}
    assert training.isdisjoint(holdout)
    result = assess_routing(model, catalog)
    assert result["muestras"] == 9
    assert result["aprobada"] == (result["exactitud"] >= 0.75 and result["cobertura"] >= 0.5
                                  and result["precision_sobre_umbral"] >= 0.8)


def test_academic_markers_accept_ocr_whitespace_joining():
    path = Path(__file__).resolve().parents[1] / "config/tupa_huancayo.json"
    procedure = JSONProcedureCatalog(path).get("PA12115285")
    dossier = Dossier("ejemplo", "ficticio.pdf", "", documents=[
        Document("FUT", [1], "EXPEDIENTEFICTICIO\nEVIDENCIADEMO:solicitud", {}, 0.99),
    ])
    checks = AcademicRequirementAuditor().checks(procedure, dossier)
    assert checks["solicitud"]["estado"] == "CUMPLE"
