
import os
from pathlib import Path
from typing import Any, Dict, Optional, Set
from pydantic import BaseModel, Field
from shared.constants import APP_NAME, APP_VERSION, Environment

SENSITIVE_KEYS: Set[str] = {
    "JWT_SECRET",
    "OTP_PROVIDER_KEY",
    "RESEND_API_KEY",
    "DATABASE_URL",
    "SECRET_KEY",
    "PASSWORD",
    "API_KEY",
    "TOKEN",
}

def parse_bool(val: Any, default: bool = False) -> bool:
    if isinstance(val, bool):
        return val
    if val is None:
        return default
    return str(val).strip().lower() in ("true", "1", "t", "yes", "y")

def load_env_file(filepath: Path) -> None:
    """Reads simple .env file into os.environ if file exists and env var is not already set."""
    if not filepath.exists():
        return
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip("'").strip('"')
            if key and key not in os.environ:
                os.environ[key] = val

class Settings(BaseModel):
    app_name: str = Field(default=APP_NAME)
    app_version: str = Field(default=APP_VERSION)
    app_environment: Environment = Field(default=Environment.DEVELOPMENT)
    debug: bool = Field(default=True)
    log_level: str = Field(default="INFO")
    host: str = Field(default="127.0.0.1")
    port: int = Field(default=8000)

    db_path: str = Field(default="data/ctrlbooks.db")
    database_url: Optional[str] = Field(default=None)
    mongo_db_url: Optional[str] = Field(default=None)
    mongo_db_name: str = Field(default="test")
    database_pool_size: int = Field(default=5)
    database_max_overflow: int = Field(default=10)
    database_pool_timeout: int = Field(default=30)

    log_dir: str = Field(default="logs")
    log_max_bytes: int = Field(default=10 * 1024 * 1024)
    log_backup_count: int = Field(default=5)

    tally_host: str = Field(default="127.0.0.1")
    tally_port: int = Field(default=9000)

    cloud_api_base_url: str = Field(default="https://connector.cloudata.in/api/connector")
    gateway_url: str = Field(default="http://127.0.0.1:8000")
    web_portal_url: str = Field(default="https://ctrlbooks.com")

    jwt_secret: Optional[str] = None
    otp_provider_key: Optional[str] = None
    resend_api_key: Optional[str] = Field(default=None)
    sync_worker_count: int = Field(default=2)

    @property
    def effective_mongo_url(self) -> str:
        """Returns valid MongoDB connection URI, strictly from config or environment variables."""
        if self.mongo_db_url and self.mongo_db_url.strip():
            return self.mongo_db_url.strip()
        return os.getenv("CTRLBOOKS_DB_URL", os.getenv("MONGODB_URI", os.getenv("MONGO_URL", ""))).strip()

    @property
    def effective_database_url(self) -> str:
        """Returns valid database URL for SQLAlchemy, falling back to SQLite db_path."""
        if self.database_url and self.database_url.strip():
            return self.database_url.strip()
        clean_path = self.db_path.replace("\\", "/")
        return f"sqlite:///{clean_path}"

    @classmethod
    def load_from_env(cls, env_path: Optional[Path] = None) -> "Settings":
        """Loads configuration from environment variables and optional .env file."""
        if env_path is None:
            env_path = Path(__file__).resolve().parents[1] / ".env"
        load_env_file(env_path)

        app_env_str = os.getenv("APP_ENVIRONMENT", Environment.DEVELOPMENT.value).lower()
        try:
            env_mode = Environment(app_env_str)
        except ValueError:
            env_mode = Environment.DEVELOPMENT

        debug_val = parse_bool(os.getenv("DEBUG"), default=(env_mode == Environment.DEVELOPMENT))
        if env_mode == Environment.PRODUCTION:
            debug_val = False

        log_lvl = os.getenv("LOG_LEVEL", "INFO" if env_mode == Environment.DEVELOPMENT else "WARNING").upper()

        db_path_val = os.getenv("CTRLBOOKS_DB_PATH", "data/ctrlbooks.db")
        db_url_val = os.getenv("DATABASE_URL", os.getenv("CTRLBOOKS_DATABASE_URL"))
        mongo_url_val = os.getenv("CTRLBOOKS_DB_URL", os.getenv("MONGODB_URI", os.getenv("MONGO_URL")))
        mongo_db_name_val = os.getenv("CTRLBOOKS_DB_NAME", "ctrlbooks")

        return cls(
            app_name=os.getenv("APP_NAME", APP_NAME),
            app_version=os.getenv("APP_VERSION", APP_VERSION),
            app_environment=env_mode,
            debug=debug_val,
            log_level=log_lvl,
            host=os.getenv("HOST", os.getenv("CTRLBOOKS_HOST", "127.0.0.1")),
            port=int(os.getenv("PORT", os.getenv("CTRLBOOKS_GATEWAY_PORT", "8000"))),
            db_path=db_path_val,
            database_url=db_url_val,
            mongo_db_url=mongo_url_val,
            mongo_db_name=mongo_db_name_val,
            database_pool_size=int(os.getenv("DATABASE_POOL_SIZE", "5")),
            database_max_overflow=int(os.getenv("DATABASE_MAX_OVERFLOW", "10")),
            database_pool_timeout=int(os.getenv("DATABASE_POOL_TIMEOUT", "30")),
            log_dir=os.getenv("LOG_DIR", "logs"),
            log_max_bytes=int(os.getenv("LOG_MAX_BYTES", "10485760")),
            log_backup_count=int(os.getenv("LOG_BACKUP_COUNT", "5")),
            tally_host=os.getenv("CTRLBOOKS_TALLY_HOST", "127.0.0.1"),
            tally_port=int(os.getenv("CTRLBOOKS_TALLY_PORT", "9000")),
            cloud_api_base_url=os.getenv("CLOUD_API_BASE_URL", os.getenv("CTRLBOOKS_CLOUD_API_URL", "https://connector.cloudata.in/api/connector")),
            gateway_url=os.getenv("CTRLBOOKS_GATEWAY_URL", f"http://{os.getenv('HOST', '127.0.0.1')}:{os.getenv('PORT', '8000')}"),
            web_portal_url=os.getenv("CTRLBOOKS_WEB_PORTAL_URL", "https://ctrlbooks.com"),
            jwt_secret=os.getenv("JWT_SECRET"),
            otp_provider_key=os.getenv("OTP_PROVIDER_KEY"),
            sync_worker_count=int(os.getenv("SYNC_WORKER_COUNT", "2")),
        )

    def validate_required(self) -> None:
        """Validates that required settings exist and are valid."""
        if not self.app_name:
            raise ValueError("APP_NAME configuration must not be empty.")
        if not self.db_path and not self.database_url:
            raise ValueError("Database configuration (CTRLBOOKS_DB_PATH or DATABASE_URL) must not be empty.")
        if self.port < 1 or self.port > 65535:
            raise ValueError(f"Invalid PORT value: {self.port}")

    def get_masked_dict(self) -> Dict[str, Any]:
        """Returns a copy of the settings dictionary with sensitive values masked."""
        raw = self.model_dump(mode="json")
        masked = {}
        for key, val in raw.items():
            if any(s.lower() in key.lower() for s in SENSITIVE_KEYS) and val is not None:
                masked[key] = "****"
            else:
                masked[key] = val
        return masked

_settings: Optional[Settings] = None

def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings.load_from_env()
        _settings.validate_required()
    return _settings

def reset_settings() -> None:
    """Resets the singleton instance (useful for unit testing)."""
    global _settings
    _settings = None
    
