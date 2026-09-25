"""Demo reproducible: python -m scripts.demo_huancayo. Solo datos ficticios."""
from pathlib import Path
from secrets import token_urlsafe
from tempfile import TemporaryDirectory
import json
import pymupdf
from fastapi.testclient import TestClient
from src.infrastructure.main import create_app
from src.infrastructure.settings import Settings


def main():
    with TemporaryDirectory(prefix="huancayo-demo-") as folder:
        token = token_urlsafe(32)
        settings = Settings(database_url=f"sqlite:///{Path(folder) / 'demo.db'}",
                            storage_dir=str(Path(folder) / "originales"),
                            reviewer_token=token, reviewer_id="evaluador-ficticio-demo")
        with pymupdf.open() as pdf:
            for content in ["FORMULARIO UNICO DE TRAMITE\nNombres y apellidos: Persona Ficticia\nDNI: 00000000",
                            "PLANO DE UBICACION\nESCALA: 1:500\nLAMINA: A01"]:
                pdf.new_page().insert_text((45, 80), content, fontsize=14)
            content = pdf.tobytes()
        headers = {"Authorization": "Bearer " + token}
        with TestClient(create_app(settings)) as client:
            response = client.post("/api/expedientes", files={"archivo": ("FICTICIO.pdf", content, "application/pdf")})
            response.raise_for_status()
            dossier_id = response.json()["id"]
            base = f"/api/expedientes/{dossier_id}"
            result = client.post(base + "/validacion", headers=headers, json={
                "revision": 0, "codigo_tupa": "PA12115285",
                "verificaciones": {"pago": {"estado": "FALTA", "nota": "Caso ficticio: pago no acreditado."}}})
            result.raise_for_status()
            observed = result.json()
            edited = client.post(base + "/borradores", headers=headers, json={
                "revision": observed["revision"], "contenido": "BORRADOR DE PRUEBA: verificar pago. Sin validez legal."})
            edited.raise_for_status()
            signature = client.post(base + "/aprobar-firmar", headers=headers,
                                    json={"revision": edited.json()["revision"]})
            assert signature.status_code == 503
            checks = {key: {"estado": "CUMPLE", "nota": "Verificación ficticia exclusiva de esta demo."}
                      for key in ["solicitud", "identidad", "plano_firmado", "pago"]}
            verified = client.post(base + "/validacion", headers=headers, json={
                "revision": edited.json()["revision"], "codigo_tupa": "PA12115285", "verificaciones": checks})
            verified.raise_for_status()
            routed = client.post(base + "/enrutamiento", headers=headers, json={"revision": verified.json()["revision"]})
            routed.raise_for_status()
            indicators = client.get(base + "/indicadores", headers=headers)
            indicators.raise_for_status()
            privacy = client.post(base + "/privacidad/vista-previa", headers=headers, json={})
            privacy.raise_for_status()
            result = {"datos": "FICTICIOS; base temporal, sin transmisión externa",
                      "extraccion": response.json()["estado"], "validacion_inicial": observed["validation"]["estado"],
                      "versiones_borrador": len(edited.json()["drafts"]), "firma_http": signature.status_code,
                      "enrutamiento": routed.json()["routing"], "indicadores": indicators.json(),
                      "privacidad": privacy.json()}
            print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
