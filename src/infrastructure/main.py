from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from src.application.useCases import GetDossier, ProcessDossier
from src.infrastructure.adapters.input.controllers import build_router
from src.infrastructure.adapters.output.database import SQLDossierRepository
from src.infrastructure.adapters.output.ocr import PDFReader
from src.infrastructure.adapters.output.storage import LocalFileStorage
from src.infrastructure.settings import Settings
from src.application.workflow import MunicipalWorkflow
from src.domain.privacy import LocalPrivacyFilter
from src.infrastructure.adapters.input.municipal import build_municipal_router
from src.infrastructure.adapters.output.workflow import (
    JSONProcedureCatalog, SQLWorkflowRepository, UnavailableAdministrativeGateway,
    UnavailableRoutingModel,
)


def create_app(settings=None, reader=None):
    settings = settings or Settings()
    repository = SQLDossierRepository(settings.database_url)
    storage = LocalFileStorage(settings.storage_dir)
    reader = reader or PDFReader(settings.max_pages, settings.min_dpi, settings.min_ocr_confidence)
    catalog = JSONProcedureCatalog(Path(__file__).resolve().parents[2] / "config" / "tupa_huancayo.json")
    workflow = MunicipalWorkflow(repository, SQLWorkflowRepository(repository.engine), catalog,
                                 UnavailableRoutingModel(), UnavailableAdministrativeGateway(),
                                 LocalPrivacyFilter())

    @asynccontextmanager
    async def lifespan(app):
        yield
        repository.engine.dispose()

    app = FastAPI(title="Huancayo · Backend de expedientes", version="0.2.0", lifespan=lifespan,
                  description="Prototipo académico hexagonal. HU01 y base local HU02-HU07. Consulte /api/capacidades: no emite actos administrativos ni inventa predicciones.")
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                       allow_methods=["GET", "POST"], allow_headers=["Content-Type", "Authorization"])
    web_dir = Path(__file__).parent / "adapters" / "input" / "web"
    app.mount("/assets", StaticFiles(directory=web_dir / "assets"), name="assets")
    app.include_router(build_router(ProcessDossier(reader, repository, storage), GetDossier(repository), settings.max_file_mb))
    app.include_router(build_municipal_router(workflow, settings))

    @app.get("/", include_in_schema=False)
    def home():
        return FileResponse(web_dir / "index.html")

    @app.get("/health", tags=["Servicio"])
    def health():
        return {"estado": "ok"}

    return app
