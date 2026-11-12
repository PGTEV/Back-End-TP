"""Fit and evaluate local demonstration models using generated data only."""

import numpy as np

from src.domain.entities import Document, Dossier
from src.domain.workflow import ROUTING_THRESHOLD


ROUTING_HOLDOUT = {
    "PA12115285": (
        "certificado edificatorio del terreno para altura y retiros",
        "parametros urbanisticos y retiros del predio",
        "altura permitida en certificado de edificacion urbanistica",
    ),
    "PA121121B0": (
        "modificacion de la zonificacion del suelo para predios vecinos",
        "propuesta de cambio territorial y uso del suelo",
        "zonificacion especifica y su impacto territorial",
    ),
    "PE1027344C1": (
        "apertura de tienda con licencia de funcionamiento comercial",
        "licencia para restaurante de riesgo bajo",
        "autorizacion economica para funcionamiento de establecimiento",
    ),
}


def assess_routing(model, catalog):
    correct = confident = confident_correct = total = 0
    for code, texts in ROUTING_HOLDOUT.items():
        procedure = catalog.get(code)
        if procedure is None:
            continue
        for text in texts:
            document = Document("FUT", [1], "EXPEDIENTE FICTICIO", {"asunto": text}, 1.0)
            prediction = model.predict(Dossier("evaluacion", "ficticio.pdf", "", documents=[document]))
            matches = prediction.department == procedure.department
            total += 1
            correct += matches
            if prediction.confidence > ROUTING_THRESHOLD:
                confident += 1
                confident_correct += matches
    accuracy = correct / total if total else 0
    coverage = confident / total if total else 0
    precision = confident_correct / confident if confident else 0
    return {"muestras": total, "exactitud": round(accuracy, 3), "cobertura": round(coverage, 3),
            "precision_sobre_umbral": round(precision, 3), "umbral": ROUTING_THRESHOLD,
            "aprobada": total == 9 and accuracy >= 0.75 and coverage >= 0.5 and precision >= 0.8}


def sigmoid(value):
    return 1.0 / (1.0 + np.exp(-np.clip(value, -30, 30)))


def synthetic_samples(seed, size):
    rng = np.random.default_rng(seed)
    days = rng.integers(1, 61, size)
    pages = rng.integers(1, 31, size)
    missing = rng.integers(0, 9, size)
    pending = rng.integers(0, 9 - missing)
    conflict = rng.binomial(1, 0.2, size)
    features = np.column_stack((days, pages, missing, pending, conflict))
    eta = 1.5 + 0.48 * days + 0.17 * pages + 0.7 * missing + 0.4 * pending + 1.2 * conflict
    eta = eta + rng.normal(0, 1.35, size)
    risk = sigmoid(-3.2 + 0.65 * missing + 0.24 * pending + 1.35 * conflict + 0.03 * pages)
    return features, eta, rng.binomial(1, risk)


class SyntheticAcademicIndicators:
    version = "ETA_LINEAL_RIESGO_LOGISTICO_SINTETICO_V1"

    def __init__(self):
        train, train_eta, train_risk = synthetic_samples(1704, 1200)
        holdout, holdout_eta, holdout_risk = synthetic_samples(9127, 400)
        self.mean, self.scale = train.mean(axis=0), train.std(axis=0)
        x, validation = self._matrix(train), self._matrix(holdout)
        self.eta = np.linalg.lstsq(x, train_eta, rcond=None)[0]
        self.risk = np.zeros(x.shape[1])
        for _ in range(500):
            self.risk -= 0.25 * (x.T @ (sigmoid(x @ self.risk) - train_risk)) / len(train)
        estimated = sigmoid(validation @ self.risk)
        classified = estimated >= 0.5
        positives = holdout_risk == 1
        mae = float(np.mean(np.abs(validation @ self.eta - holdout_eta)))
        brier = float(np.mean((estimated - holdout_risk) ** 2))
        balanced = float((classified[positives].mean() + (~classified[~positives]).mean()) / 2)
        self.eta_approved = mae <= 2.0
        self.risk_approved = brier <= 0.20 and balanced >= 0.65
        self.metrics = {"entrenamiento": len(train), "evaluacion": len(holdout),
                        "eta_mae_dias": round(mae, 3), "riesgo_brier": round(brier, 3),
                        "riesgo_exactitud_balanceada": round(balanced, 3),
                        "eta_aprobada": self.eta_approved, "riesgo_aprobado": self.risk_approved}

    def _matrix(self, features):
        return np.column_stack((np.ones(len(features)), (features - self.mean) / self.scale))

    def predict(self, published_days, pages, missing, pending, conflict):
        result = {"origen": "SINTETICO", "modelo": self.version, "revision_humana": True,
                  "dias_estimados": None, "probabilidad_rechazo": None, "metricas": self.metrics}
        if not (1 <= published_days <= 60 and 1 <= pages <= 30 and missing >= 0 and pending >= 0
                and missing + pending <= 8):
            return {**result, "motivo": "CARACTERISTICAS_FUERA_DEL_RANGO_SINTETICO"}
        x = self._matrix(np.array([[published_days, pages, missing, pending, int(conflict)]]))[0]
        if self.eta_approved:
            result["dias_estimados"] = round(max(1.0, float(x @ self.eta)), 1)
        if self.risk_approved:
            result["probabilidad_rechazo"] = round(float(sigmoid(x @ self.risk)), 4)
        return result
