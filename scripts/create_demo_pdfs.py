"""Genera ejemplos ficticios, nunca expedientes reales de ciudadanos."""
from pathlib import Path
import pymupdf


def main():
    target = Path(__file__).resolve().parents[1] / "data" / "ejemplos"
    target.mkdir(parents=True, exist_ok=True)
    with pymupdf.open() as digital:
        for text in (
            "FORMULARIO UNICO DE TRAMITE\nSOLICITO: Licencia de ejemplo\nDNI: 12345678\nDATOS FICTICIOS PARA PRUEBA",
            "DOCUMENTO NACIONAL DE IDENTIDAD\nRENIEC\nDNI: 12345678\nDATOS FICTICIOS PARA PRUEBA",
            "PLANO DE UBICACION\nESCALA: 1:100\nLAMINA A01\nPLANO FICTICIO PARA PRUEBA",
        ):
            page = digital.new_page()
            page.insert_text((45, 80), text, fontsize=18)
        digital.save(target / "01_expediente_digital.pdf")
        for dpi, name in ((200, "02_expediente_escaneado.pdf"), (72, "03_baja_resolucion.pdf")):
            with pymupdf.open() as scanned:
                for page in digital:
                    output = scanned.new_page(width=page.rect.width, height=page.rect.height)
                    output.insert_image(output.rect, stream=page.get_pixmap(dpi=dpi).tobytes("png"))
                scanned.save(target / name, deflate=True)
    with pymupdf.open() as blank:
        blank.new_page()
        blank.save(target / "04_ilegible_sin_texto.pdf")
    print(f"Ejemplos ficticios disponibles en: {target}")


if __name__ == "__main__":
    main()
