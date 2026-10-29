"""Carga de datos iniciales (seeding) con expedientes FICTICIOS.

Uso (usa DATABASE_URL de .env o del entorno):
    python -m scripts.seed

Procesa PDFs sintéticos por el flujo real (OCR + clasificación + persistencia), de modo que
los datos sembrados tienen exactamente el formato que produce la API. Es idempotente: si ya
existen expedientes sembrados (mismo nombre SEED_*) no se duplican.
"""
import json
from sqlalchemy import create_engine, text
import pymupdf
from fastapi.testclient import TestClient
from src.infrastructure.adapters.output.database import normalize_database_url
from src.infrastructure.main import create_app
from src.infrastructure.settings import Settings

CASOS = {
    "SEED_FUT_licencia.pdf": ["FORMULARIO UNICO DE TRAMITE\nNombres y apellidos: Persona Ficticia Uno\nDNI: 00000001\n"
                              "Asunto: Licencia de edificacion modalidad A"],
    "SEED_FUT_DNI.pdf": ["FORMULARIO UNICO DE TRAMITE\nNombres y apellidos: Persona Ficticia Dos\nDNI: 00000002",
                         "DOCUMENTO NACIONAL DE IDENTIDAD\nREPUBLICA DEL PERU\nDNI 00000002"],
    "SEED_plano.pdf": ["FORMULARIO UNICO DE TRAMITE\nRazon social: Empresa Ficticia SAC\nRUC: 20000000001",
                       "PLANO DE UBICACION\nESCALA: 1:500\nLAMINA: A01\nCUADRO DE AREAS"],
}


def pdf(pages):
    with pymupdf.open() as document:
        for content in pages:
            document.new_page().insert_text((45, 80), content, fontsize=14)
        return document.tobytes()


def main():
    settings = Settings()
    engine = create_engine(normalize_database_url(settings.database_url))
    app = create_app(settings)  # crea las tablas si no existen
    with engine.connect() as connection:
        hashes = set()
        for payload in connection.execute(text("SELECT payload FROM expedientes")).scalars():
            data = payload if isinstance(payload, dict) else json.loads(payload)
            hashes.add(data.get("filename"))
    creados = 0
    with TestClient(app) as client:
        for nombre, paginas in CASOS.items():
            content = pdf(paginas)
            if nombre in hashes:
                print(f"= {nombre}: ya existe, se omite")
                continue
            response = client.post("/api/expedientes", files={"archivo": (nombre, content, "application/pdf")})
            response.raise_for_status()
            body = response.json()
            creados += 1
            print(f"+ {nombre}: id={body['id']} estado={body['estado']} "
                  f"tipos={[d['tipo'] for d in body['documentos']]}")
    print(f"Motor: {engine.dialect.name} | expedientes nuevos: {creados}")
    engine.dispose()


if __name__ == "__main__":
    main()
