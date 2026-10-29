"""Mide latencia de la API desplegada (BD + inferencia OCR).

Uso:
    python -m scripts.latency_check https://TU-BACKEND.onrender.com 10
"""
import statistics
import sys
import time
import httpx
import pymupdf


def scanned_pdf():
    with pymupdf.open() as source:
        source.new_page().insert_text((45, 80), "FORMULARIO UNICO DE TRAMITE\nDNI: 00000009\nPRUEBA LATENCIA", fontsize=16)
        pix = source[0].get_pixmap(dpi=200)
    with pymupdf.open() as doc:
        page = doc.new_page()
        page.insert_image(page.rect, stream=pix.tobytes("png"))
        return doc.tobytes()


def measure(client, n, method, path, **kwargs):
    times, errors = [], 0
    for _ in range(n):
        start = time.perf_counter()
        try:
            response = client.request(method, path, **kwargs)
            ok = response.status_code < 400
        except httpx.HTTPError:
            ok = False
        elapsed = (time.perf_counter() - start) * 1000
        times.append(elapsed) if ok else None
        errors += 0 if ok else 1
    return times, errors


def row(name, times, errors):
    if not times:
        return f"| {name} | - | - | - | - | {errors} |"
    ordered = sorted(times)
    p95 = ordered[min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))]
    return (f"| {name} | {min(ordered):.0f} | {statistics.median(ordered):.0f} | {p95:.0f} | "
            f"{max(ordered):.0f} | {errors} |")


def main():
    base = sys.argv[1].rstrip("/")
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    with httpx.Client(base_url=base, timeout=120) as client:
        print("Calentando (Render free puede tardar ~50 s en despertar)...")
        client.get("/health")
        print("Respuesta /health/db:", client.get("/health/db").json())
        print("Respuesta /health/ia:", client.get("/health/ia").json())
        content = scanned_pdf()
        results = [
            ("GET /health", *measure(client, n, "GET", "/health")),
            ("GET /health/db (SELECT a Supabase)", *measure(client, n, "GET", "/health/db")),
            ("GET /health/ia (inferencia OCR)", *measure(client, n, "GET", "/health/ia")),
            ("POST /api/expedientes (OCR + BD)", *measure(
                client, max(1, n // 2), "POST", "/api/expedientes",
                files={"archivo": ("LATENCIA_FICTICIO.pdf", content, "application/pdf")})),
        ]
    print(f"\nLatencia extremo a extremo (ms), n={n}, destino={base}\n")
    print("| Endpoint | min | p50 | p95 | max | errores |")
    print("| --- | --- | --- | --- | --- | --- |")
    for name, times, errors in results:
        print(row(name, times, errors))


if __name__ == "__main__":
    main()
