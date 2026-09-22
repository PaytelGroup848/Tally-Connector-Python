"""
CtrlBooks - Structured Logging & Rotation System
------------------------------------------------------------
Provides production-ready centralized structured logging with UTF-8 log rotation,
secret masking filter, correlation ID contextual formatting, and category loggers.
"""

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path
from shared.config import get_settings, SENSITIVE_KEYS

SECRET_PATTERNS = [
    re.compile(rf"({key})\s*[:=]\s*['\"]?([^\s'\";,]+)['\"]?", re.IGNORECASE)
    for key in SENSITIVE_KEYS
] + [
    re.compile(r"(bearer\s+)[A-Za-z0-9\-\._~\+\/]+=*", re.IGNORECASE),
    re.compile(r"(otp\s*[:=]\s*)[0-9]{4,8}", re.IGNORECASE),
]

class SecretMaskingFilter(logging.Filter):
    """Filters log records to mask passwords, tokens, API keys, and OTPs."""
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            masked_msg = record.msg
            for pat in SECRET_PATTERNS:
                masked_msg = pat.sub(r"\1=****", masked_msg)
            record.msg = masked_msg
        return True

class ContextFormatter(logging.Formatter):
    """Formats logs with timestamp, level, logger name, message, and request ID."""
    def format(self, record: logging.LogRecord) -> str:
        req_id = getattr(record, "request_id", None)
        req_suffix = f" | RequestID={req_id}" if req_id else ""
        record.message = record.getMessage()
        record.asctime = self.formatTime(record, self.datefmt)
        s = f"{record.asctime} | {record.levelname:<7} | {record.name} | {record.message}{req_suffix}"
        if record.exc_info:
            if not record.exc_text:
                record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
            if s[-1:] != "\n":
                s += "\n"
            s += record.exc_text
        return s

_initialized = False

def get_writable_log_dir(configured_dir: str = "logs") -> Path:
    """Returns a directory that is guaranteed to be writable across all environments."""
    primary = Path(configured_dir)
    try:
        primary.mkdir(parents=True, exist_ok=True)
        test_file = primary / ".perm_check"
        test_file.touch(exist_ok=True)
        test_file.unlink(missing_ok=True)
        return primary
    except Exception:
        pass

    import os
    local_app_data = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    fallback = Path(local_app_data) / "CtrlBooks" / "logs"
    try:
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback
    except Exception:
        import tempfile
        tmp = Path(tempfile.gettempdir()) / "CtrlBooks" / "logs"
        tmp.mkdir(parents=True, exist_ok=True)
        return tmp

def setup_logging(service_name: str = "app") -> logging.Logger:
    """Configures root structured logger with rotating file handler and console handler."""
    global _initialized
    settings = get_settings()

    log_dir = get_writable_log_dir(settings.log_dir)
    log_file = log_dir / f"{service_name}.log"

    root_logger = logging.getLogger()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    root_logger.setLevel(level)

    if not _initialized or len(root_logger.handlers) == 0:
        formatter = ContextFormatter(datefmt="%Y-%m-%d %H:%M:%S")

        try:
            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=settings.log_max_bytes,
                backupCount=settings.log_backup_count,
                encoding="utf-8"
            )
            file_handler.setFormatter(formatter)
            file_handler.addFilter(SecretMaskingFilter())
            file_handler.setLevel(level)
            root_logger.addHandler(file_handler)
        except Exception:
            pass

        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        stream_handler.addFilter(SecretMaskingFilter())
        stream_handler.setLevel(level)
        root_logger.addHandler(stream_handler)

        for noisy_logger in ["httpx", "httpcore", "urllib3", "uvicorn", "uvicorn.access", "uvicorn.error"]:
            logging.getLogger(noisy_logger).setLevel(logging.WARNING)

        _initialized = True

    return logging.getLogger(service_name)

def get_logger(category: str) -> logging.Logger:
    """Retrieves a logger for a specific category (e.g. app.lifecycle, app.api, app.security, app.connector, app.sync)."""
    if not _initialized:
        setup_logging()
    return logging.getLogger(category)
