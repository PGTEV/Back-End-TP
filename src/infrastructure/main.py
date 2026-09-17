from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.application.useCases import GetDossier, ProcessDossier
from src.infrastructure.adapters.input.controllers import build_router
from src.infrastructure.adapters.output.database import SQLDossierRepository
from src.infrastructure.adapters.output.ocr import PDFReader
from src.infrastructure.adapters.output.storage import LocalFileStorage
from src.infrastructure.settings import Settings


def create_app(settings=None, reader=None):
    settings = settings or Settings()
    repository = SQLDossierRepository(settings.database_url)
    storage = LocalFileStorage(settings.storage_dir)
    reader = reader or PDFReader(settings.max_pages, settings.min_dpi, settings.min_ocr_confidence)

    @asynccontextmanager
    async def lifespan(app):
        yield
        repository.engine.dispose()

    app = FastAPI(title="PMV1 · Extracción de expedientes", version="0.1.0", lifespan=lifespan,
                  description="HU01. Prototipo académico local, sin decisiones administrativas.")
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                       allow_methods=["GET", "POST"], allow_headers=["Content-Type"])
    app.include_router(build_router(ProcessDossier(reader, repository, storage), GetDossier(repository), settings.max_file_mb))

    @app.get("/health", tags=["Servicio"])
    def health():
        return {"estado": "ok"}

    return app
