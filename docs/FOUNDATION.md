# CtrlBooks — Foundation Architecture Guide (Module 1)

This document describes the production foundation created in **Module 1** for the **CtrlBooks** desktop & microservices platform.

---

## 1. Core Architecture Principles

1. **Centralized Configuration**: All system settings and environment variables are loaded, validated, and managed via `shared/config.py`.
2. **Structured Logging & Masking**: All components use standard structured logging with UTF-8 log rotation (`logs/app.log`) and automatic secret masking for API keys, passwords, and tokens.
3. **Correlation ID Tracking**: Every HTTP request receives a unique `X-Request-ID` header (or propagates an incoming one) for end-to-end tracing across gateway, microservices, and desktop client.
4. **Standardized Responses**: External API endpoints return consistent JSON envelopes:
   - **Success**: `{"success": true, "data": ..., "message": "...", "request_id": "..."}`
   - **Error**: `{"success": false, "error": {"code": "...", "message": "..."}, "request_id": "..."}`
5. **Global Error Handling**: Domain exceptions (`AppException`, `ValidationError`, `NotFoundException`, `ServiceUnavailableException`) prevent raw Python stack traces from exposing internal details in production.
6. **Real Health Monitoring**: Health endpoints reflect actual component state (Config, Logging, Database) without returning fake business data.

---

## 2. Shared Foundation Components (`shared/`)

| Module | File | Purpose |
|---|---|---|
| **Constants** | `shared/constants.py` | Defines error codes (`VALIDATION_ERROR`, `NOT_FOUND`, etc.), environments, and default service ports (8000–8009). |
| **Config** | `shared/config.py` | Environment loader (`Settings`) supporting `.env`, validation, default fallbacks, and secret masking (`get_masked_dict()`). |
| **Logging** | `shared/logging_config.py` | Structured logger setup with `RotatingFileHandler` (UTF-8, 10MB limit), console handler, and `SecretMaskingFilter`. |
| **Exceptions** | `shared/exceptions.py` | Base domain exception classes and FastAPI global exception handlers. |
| **Response** | `shared/response.py` | Standardized success and error response payload builders. |
| **Middleware** | `shared/middleware.py` | `RequestIDMiddleware` for generating/propagating `X-Request-ID`. |
| **Lifecycle** | `shared/lifecycle.py` | Standardized application startup/shutdown sequence logger & manager. |
| **Health** | `shared/health.py` | Real component health status (`/api/health`) and app metadata (`/api/app/info`). |

---

## 3. Environment & Configuration Variables

Configure settings via environment variables or a `.env` file in the project root:

```ini
APP_NAME="CtrlBooks"
APP_VERSION="1.0.0"
APP_ENVIRONMENT=development  # 'development' or 'production'
DEBUG=true                   # Forced to false in production mode
LOG_LEVEL=INFO               # Log level: DEBUG, INFO, WARNING, ERROR

HOST=127.0.0.1
PORT=8000
CTRLBOOKS_DB_PATH=data/ctrlbooks.db

LOG_DIR=logs
LOG_MAX_BYTES=10485760
LOG_BACKUP_COUNT=5

CTRLBOOKS_TALLY_HOST=127.0.0.1
CTRLBOOKS_TALLY_PORT=9000
BUSY_DATA_PATH=C:\BUSYWIN\DATA
```

---

## 4. How to Run & Test

### Run Unit & Integration Tests
```powershell
python -m unittest discover -s tests -p "test_*.py"
```

### Run Full Verification Suite
Runs unit tests, boots all 10 microservices, tests health check, app info, request ID propagation, and pipeline execution:
```powershell
python scripts/verify_all.py
```

### Run Backend Microservices
```powershell
python scripts/run_all.py
```

---

## 5. Standard Endpoints Added in Module 1

- **GET `/api/app/info`**: Returns real application name, version, environment mode, and masked configuration settings.
- **GET `/api/health`** / **GET `/health`**: Returns real foundation health status (Config, Logging, Database) and downstream microservice status.

---

## 6. Integration Rules for Future Modules

When building future business modules (Authentication, Tally/BUSY extractors, Sync Engine, Notifications):
1. **Never hardcode settings**: Always obtain configuration via `from shared.config import get_settings`.
2. **Use category loggers**: Obtain loggers using `from shared.logging_config import get_logger; logger = get_logger("app.modulename")`.
3. **Throw domain exceptions**: Raise exceptions from `shared.exceptions` (e.g. `raise ValidationError(...)` or `raise NotFoundException(...)`).
4. **Pass Request ID**: Include `request_id` or `X-Request-ID` header when making inter-service HTTP requests.
5. **No dummy health returns**: Only report health status for systems that are actually connected and verified.
