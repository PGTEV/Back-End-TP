from pydantic import AwareDatetime, BaseModel, Field, SecretStr, model_validator
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict


class AcademicAccount(BaseModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{2,39}$")
    role: Literal["administrador", "evaluador", "responsable"]
    token: SecretStr
    department: str | None = None
    expires_at: AwareDatetime | None = None


class ReviewerCredential(BaseModel):
    token: SecretStr
    expires_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def validate_token(self):
        value = self.token.get_secret_value()
        if len(value) < 32 or any(c.isspace() for c in value):
            raise ValueError("El token debe tener al menos 32 caracteres y no contener espacios.")
        return self


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)
    database_url: str = "sqlite:///./data/expedientes.db"
    storage_dir: str = "./data/originales"
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]
    max_file_mb: int = Field(default=20, ge=1, le=100)
    max_pages: int = Field(default=30, ge=1, le=100)
    min_dpi: int = Field(default=150, ge=72, le=600)
    min_ocr_confidence: float = Field(default=0.65, ge=0, le=1)
    reviewer_token: SecretStr = SecretStr("")
    reviewer_id: str = ""
    reviewer_token_expires_at: AwareDatetime | None = None
    reviewer_tokens: list[ReviewerCredential] = Field(default_factory=list, repr=False)
    # Las cuentas nominales son opt-in; el modo académico conserva su contrato.
    individual_accounts_enabled: bool = False
    # False conserva el contrato público local; activar en Render para el cliente React.
    protect_dossier_routes: bool = False
    request_metrics_enabled: bool = False
    academic_demo: bool = False
    academic_accounts: list[AcademicAccount] = Field(default_factory=list, repr=False)
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
    app_environment: Literal['development', 'staging', 'production'] = 'development'
    security_events_enabled: bool = False
    auth_rate_limit_enabled: bool = False
    auth_failures_per_window: int = Field(default=30, ge=1, le=10000)
    security_window_seconds: int = Field(default=60, ge=1, le=3600)
    security_max_origins: int = Field(default=10000, ge=1, le=100000)
    ocr_limits_enabled: bool = False
    ocr_requests_per_window: int = Field(default=20, ge=1, le=10000)
    ocr_max_concurrent: int = Field(default=2, ge=1, le=32)
    protect_diagnostics: bool = False
    diagnostic_cache_seconds: int = Field(default=120, ge=0, le=3600)
    disable_api_docs: bool = False
    security_headers_enabled: bool = False
    hsts_enabled: bool = False
    storage_encryption_enabled: bool = False
    storage_encryption_keys: list[SecretStr] = Field(default_factory=list, repr=False)

    @model_validator(mode='after')
    def production_guard(self):
        if self.app_environment in {'production', 'staging'}:
            if not self.protect_dossier_routes:
                raise ValueError('Producción/staging requiere PROTECT_DOSSIER_ROUTES=true.')
            if not (self.academic_accounts or self.reviewer_tokens or
                    (len(self.reviewer_token.get_secret_value()) >= 32 and self.reviewer_id.strip())):
                raise ValueError('Producción/staging requiere credenciales válidas.')
        if self.reviewer_tokens and not self.reviewer_id.strip():
            raise ValueError('REVIEWER_TOKENS requiere REVIEWER_ID.')
        if self.individual_accounts_enabled and (not self.protect_dossier_routes or not self.academic_accounts):
            raise ValueError('Las cuentas individuales requieren protección y cuentas configuradas.')
        if self.storage_encryption_enabled and not self.storage_encryption_keys:
            raise ValueError('El cifrado requiere STORAGE_ENCRYPTION_KEYS fuera del repositorio.')
        return self
