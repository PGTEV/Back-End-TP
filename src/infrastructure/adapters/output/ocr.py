"""OCR local real. RapidOCR ejecuta modelos PP-OCR mediante ONNX en CPU."""
from threading import Lock
import pymupdf
import numpy as np
from src.domain.valueObjects import Page
from src.domain.errors import IllegibleDocument, InvalidPDF


class PDFReader:
    def __init__(self, max_pages=30, min_dpi=150, min_confidence=0.65):
        self.max_pages = max_pages
        self.min_dpi = min_dpi
        self.min_confidence = min_confidence
        self._engine = None
        self._lock = Lock()

    def extract(self, content: bytes) -> list[Page]:
        try:
            pdf = pymupdf.open(stream=content, filetype="pdf")
        except Exception as error:
            raise InvalidPDF("El PDF está corrupto o no puede abrirse.") from error
        with pdf:
            if pdf.needs_pass:
                raise InvalidPDF("No se admiten PDF protegidos con contraseña.")
            if not 1 <= len(pdf) <= self.max_pages:
                raise InvalidPDF(f"El PDF debe tener entre 1 y {self.max_pages} páginas.")
            return [self._page(page, index + 1) for index, page in enumerate(pdf)]

    def _page(self, page, number):
        if max(page.rect.width, page.rect.height) > 1800:
            raise InvalidPDF("Página demasiado grande; exporte el plano a un formato PDF reducido.")
        # Resolución efectiva de imágenes grandes según su tamaño colocado en la página.
        dpis = []
        for info in page.get_image_info():
            rect = pymupdf.Rect(info["bbox"])
            if rect.width > 0 and rect.height > 0 and rect.get_area() >= page.rect.get_area() * 0.4:
                dpis.append(min(info["width"] * 72 / rect.width, info["height"] * 72 / rect.height))
        dpi = min(dpis) if dpis else None
        if dpi is not None and dpi + 0.5 < self.min_dpi:
            raise IllegibleDocument(number)
        text = page.get_text().strip()
        # Un PDF escaneado con capa OCR previa debe volver a verificarse visualmente.
        if len(text) >= 20 and not dpis:
            return Page(number, text, 1.0, "TEXTO_PDF", dpi)
        pix = page.get_pixmap(dpi=180, colorspace=pymupdf.csRGB, alpha=False)
        pixels = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
        with self._lock:
            if self._engine is None:
                from rapidocr_onnxruntime import RapidOCR
                self._engine = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=2)
            result, _ = self._engine(pixels)
        if not result:
            raise IllegibleDocument(number)
        text = "\n".join(item[1] for item in result)
        confidence = sum(float(item[2]) for item in result) / len(result)
        if sum(c.isalnum() for c in text) < 12 or confidence < self.min_confidence:
            raise IllegibleDocument(number)
        return Page(number, text, round(confidence, 4), "PP_OCR_ONNX", dpi)
