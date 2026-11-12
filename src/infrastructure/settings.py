from pydantic import Field, SecretStr
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "sqlite:///./data/expedientes.db"
    storage_dir: str = "./data/originales"
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]
    max_file_mb: int = Field(default=20, ge=1, le=100)
    max_pages: int = Field(default=30, ge=1, le=100)
    min_dpi: int = Field(default=150, ge=72, le=600)
    min_ocr_confidence: float = Field(default=0.65, ge=0, le=1)
    reviewer_token: SecretStr = SecretStr("")
    reviewer_id: str = ""
    # False conserva el contrato público local; activar en Render para el cliente React.
    protect_dossier_routes: bool = False
    request_metrics_enabled: bool = False
    academic_demo: bool = False
    openai_enabled: bool = False
    openai_api_key: SecretStr = SecretStr("")
    openai_model: str = ""
    openai_timeout_seconds: int = Field(default=60, ge=5, le=120)
    # openai conserva los despliegues previos; no hay conmutación automática ni llamadas dobles.
    ai_provider: Literal['openai', 'gemini', 'none'] = 'openai'
    gemini_enabled: bool = False
    gemini_api_key: SecretStr = SecretStr('')
    gemini_model: str = 'gemini-3.8-flash'
    gemini_timeout_seconds: int = Field(default=60, ge=5, le=120)
