from contextlib import asynccontextmanager
from pathlib import Path
from time import perf_counter
import pymupdf
from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text
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
from src.infrastructure.adapters.input.security import reviewer_dependency
from src.infrastructure.adapters.output.academic import AcademicAdministrativeGateway, AcademicRequirementAuditor, SyntheticRoutingModel
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
                                 SyntheticRoutingModel(catalog) if settings.academic_demo else UnavailableRoutingModel(),
                                 AcademicAdministrativeGateway() if settings.academic_demo else UnavailableAdministrativeGateway(),
                                 LocalPrivacyFilter(), AcademicRequirementAuditor() if settings.academic_demo else None)

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
    dossier_dependencies = [Depends(reviewer_dependency(settings))] if settings.protect_dossier_routes else []
    app.include_router(build_router(ProcessDossier(reader, repository, storage), GetDossier(repository), settings.max_file_mb),
                       dependencies=dossier_dependencies)
    app.include_router(build_municipal_router(workflow, settings))

    @app.get("/", include_in_schema=False)
    def home():
        return FileResponse(web_dir / "index.html")

    @app.get("/health", tags=["Servicio"])
    def health():
        return {"estado": "ok"}

    @app.get("/health/db", tags=["Servicio"])
    def health_db():
        start = perf_counter()
        try:
            with repository.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
                total = connection.execute(text("SELECT COUNT(*) FROM expedientes")).scalar_one()
        except Exception as error:
            return JSONResponse(status_code=503, content={"estado": "error", "detalle": type(error).__name__})
        return {"estado": "ok", "motor": repository.engine.dialect.name, "expedientes": total,
                "latencia_ms": round((perf_counter() - start) * 1000, 1)}

    @app.get("/health/ia", tags=["Servicio"])
    def health_ia():
        """Inferencia real del OCR (RapidOCR/PP-OCR ONNX) sobre un PDF escaneado sintético."""
        with pymupdf.open() as source:
            source.new_page().insert_text((45, 80), "FORMULARIO UNICO DE TRAMITE\nPRUEBA DE OCR 12345", fontsize=18)
            pix = source[0].get_pixmap(dpi=200)
        with pymupdf.open() as scanned:
            page = scanned.new_page()
            page.insert_image(page.rect, stream=pix.tobytes("png"))
            content = scanned.tobytes()
        start = perf_counter()
        try:
            pages = reader.extract(content)
        except Exception as error:
            return JSONResponse(status_code=503, content={"estado": "error", "detalle": type(error).__name__})
        return {"estado": "ok", "modelo": pages[0].method, "confianza": pages[0].confidence,
                "latencia_inferencia_ms": round((perf_counter() - start) * 1000, 1),
                "texto": pages[0].text[:80]}

    return app
