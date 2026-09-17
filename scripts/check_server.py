"""Comprueba el servidor HTTP real y lo detiene al terminar."""
import socket
import subprocess
import sys
import time
from pathlib import Path
import httpx


def main():
    root = Path(__file__).resolve().parents[1]
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "src.infrastructure.main:create_app", "--factory",
         "--host", "127.0.0.1", "--port", str(port)], cwd=root,
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    base = f"http://127.0.0.1:{port}"
    try:
        with httpx.Client(timeout=60, trust_env=False) as client:
            for _ in range(40):
                if process.poll() is not None:
                    raise RuntimeError(process.stderr.read().decode(errors="replace"))
                try:
                    response = client.get(base + "/health")
                    response.raise_for_status()
                    break
                except httpx.ConnectError:
                    time.sleep(0.25)
            else:
                raise RuntimeError("El servidor no inició en 10 segundos.")
            assert client.get(base + "/docs").status_code == 200
            for filename, status in (("01_expediente_digital.pdf", 201),
                                     ("02_expediente_escaneado.pdf", 201),
                                     ("03_baja_resolucion.pdf", 422),
                                     ("04_ilegible_sin_texto.pdf", 422)):
                with (root / "data" / "ejemplos" / filename).open("rb") as pdf:
                    response = client.post(base + "/api/expedientes", files={"archivo": (filename, pdf, "application/pdf")})
                assert response.status_code == status, response.text
                if status == 201:
                    data = response.json()
                    assert [d["tipo"] for d in data["documentos"]] == ["FUT", "DNI", "PLANO"], data
                    assert client.get(base + "/api/expedientes/" + data["id"]).json() == data
                print(f"{filename}: HTTP {status} OK")
            print("Servidor HTTP, Swagger, carga y consulta: OK")
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        if process.stderr:
            process.stderr.close()


if __name__ == "__main__":
    main()
