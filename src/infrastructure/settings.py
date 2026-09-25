from pydantic import Field, SecretStr
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
