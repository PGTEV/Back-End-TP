import ast
from pathlib import Path
from uuid import uuid4
import pymupdf
import pytest
from fastapi.testclient import TestClient
from src.infrastructure.main import create_app
from src.infrastructure.settings import Settings
from src.infrastructure.adapters.output.ocr import PDFReader
from src.domain.errors import InvalidPDF, IllegibleDocument


def pdf_bytes(texts, scan_dpi=None):
    source = pymupdf.open()
    for text in texts:
        page = source.new_page()
        page.insert_text((45, 80), text, fontsize=18)
    if scan_dpi:
        scanned = pymupdf.open()
        for page in source:
            output = scanned.new_page(width=page.rect.width, height=page.rect.height)
            output.insert_image(output.rect, stream=page.get_pixmap(dpi=scan_dpi).tobytes("png"))
        result = scanned.tobytes(deflate=True)
        scanned.close()
    else:
        result = source.tobytes()
    source.close()
    return result


@pytest.fixture
def settings(tmp_path):
    return Settings(database_url=f"sqlite:///{tmp_path / 'test.db'}",
                    storage_dir=str(tmp_path / "originals"), max_file_mb=1)


def send(client, content, name="expediente.pdf"):
    return client.post("/api/expedientes", files={"archivo": (name, content, "application/pdf")})


def test_success_and_persistence_after_app_restart(settings):
    content = pdf_bytes(["FORMULARIO UNICO DE TRAMITE\nSOLICITO: Licencia\nDNI: 12345678",
                         "DOCUMENTO NACIONAL DE IDENTIDAD\nRENIEC\nDNI: 12345678",
                         "PLANO DE UBICACION\nESCALA: 1:100\nLAMINA: A01"])
    with TestClient(create_app(settings)) as client:
        response = send(client, content)
        assert response.status_code == 201, response.text
        data = response.json()
        assert data["estado"] == "PROCESADO"
        assert [d["tipo"] for d in data["documentos"]] == ["FUT", "DNI", "PLANO"]
        assert data["documentos"][1]["campos"]["dni"] == "12345678"
        assert [d["paginas"] for d in data["documentos"]] == [[1], [2], [3]]
        assert (Path(settings.storage_dir) / f"{data['id']}.pdf").read_bytes() == content
    with TestClient(create_app(settings)) as client:
        assert client.get(f"/api/expedientes/{data['id']}").json() == data


def test_illegible_stops_and_persists_failure(settings):
    with TestClient(create_app(settings)) as client:
        response = send(client, pdf_bytes(["FORMULARIO UNICO DE TRAMITE", ""]))
        assert response.status_code == 422, response.text
        detail = response.json()["detail"]
        assert detail["mensaje"] == IllegibleDocument.message
        assert detail["pagina"] == 2
        dossier = client.get(f"/api/expedientes/{detail['id']}").json()
        assert dossier["estado"] == "ILEGIBLE"
        assert dossier["documentos"] == []


def test_low_resolution_rejected(settings):
    with TestClient(create_app(settings)) as client:
        response = send(client, pdf_bytes(["DOCUMENTO NACIONAL DE IDENTIDAD\nRENIEC"], 72))
        assert response.status_code == 422
        assert response.json()["detail"]["codigo"] == "DOCUMENTO_ILEGIBLE"


def test_real_ocr_on_scan(settings):
    with TestClient(create_app(settings)) as client:
        response = send(client, pdf_bytes(["DOCUMENTO NACIONAL DE IDENTIDAD\nRENIEC\nDNI: 12345678"], 200))
        assert response.status_code == 201, response.text
        document = response.json()["documentos"][0]
        assert document["tipo"] == "DNI"
        assert document["metodo_extraccion"] == "PP_OCR_ONNX"
        assert "12345678" in document["texto"]


@pytest.mark.parametrize("content,name", [(b"hello", "documento.pdf"), (b"%PDF-corrupt", "documento.pdf"),
                                           (b"%PDF-1.7", "documento.exe")])
def test_invalid_files(settings, content, name):
    with TestClient(create_app(settings)) as client:
        assert send(client, content, name).status_code == 400


def test_unknown_class_is_not_invented(settings):
    with TestClient(create_app(settings)) as client:
        response = send(client, pdf_bytes(["Contenido sin categoria documental reconocible."]))
        doc = response.json()["documentos"][0]
        assert doc["tipo"] == "DESCONOCIDO"
        assert doc["requiere_revision"] is True


def test_limits_and_missing_id(settings):
    with TestClient(create_app(settings)) as client:
        home = client.get("/")
        assert home.status_code == 200
        assert "Expedientes Municipales" in home.text
        assert client.get("/assets/styles.css").status_code == 200
        assert client.get("/assets/app.js").status_code == 200
        assert send(client, b"%PDF-" + b"x" * (1024 * 1024)).status_code == 413
        assert client.get(f"/api/expedientes/{uuid4()}").status_code == 404
        assert client.get("/api/expedientes/not-a-uuid").status_code == 422
        assert client.get("/health").json() == {"estado": "ok"}


def test_page_limit():
    with pytest.raises(InvalidPDF):
        PDFReader(max_pages=1).extract(pdf_bytes(["Page one", "Page two"]))


def test_ocr_failure_is_not_reported_as_illegibility(settings):
    class UnavailableReader:
        def extract(self, content):
            raise RuntimeError("Fallo interno del motor")

    with TestClient(create_app(settings, reader=UnavailableReader())) as client:
        response = send(client, pdf_bytes(["DOCUMENTO NACIONAL DE IDENTIDAD"]))
        assert response.status_code == 503
        dossier_id = next(Path(settings.storage_dir).glob("*.pdf")).stem
        result = client.get(f"/api/expedientes/{dossier_id}").json()
        assert result["estado"] == "ERROR"
        assert result["documentos"] == []


def test_heavily_blurred_scan(settings):
    import cv2
    import numpy as np
    with pymupdf.open(stream=pdf_bytes(["DOCUMENTO NACIONAL DE IDENTIDAD\nRENIEC\nDNI: 12345678"]), filetype="pdf") as source:
        pix = source[0].get_pixmap(dpi=200, colorspace=pymupdf.csRGB, alpha=False)
        pixels = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
        blurred = cv2.GaussianBlur(pixels, (101, 101), 35)
        _, encoded = cv2.imencode(".png", blurred)
        with pymupdf.open() as output:
            page = output.new_page()
            page.insert_image(page.rect, stream=encoded.tobytes())
            content = output.tobytes(deflate=True)
    with TestClient(create_app(settings)) as client:
        assert send(client, content).status_code == 422


def test_core_has_no_framework_or_infrastructure_imports():
    root = Path(__file__).parents[1] / "src"
    forbidden = ("fastapi", "pydantic", "sqlalchemy", "pymupdf", "rapidocr", "src.infrastructure")
    for layer in ("domain", "application"):
        for file in (root / layer).rglob("*.py"):
            tree = ast.parse(file.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                names = ([node.module or ""] if isinstance(node, ast.ImportFrom)
                         else [n.name for n in node.names] if isinstance(node, ast.Import) else [])
                assert not any(name.startswith(forbidden) for name in names), file
