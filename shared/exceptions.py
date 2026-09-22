"""
CtrlBooks - Global Exception Handling & Standardized Error Schema
-----------------------------------------------------------------------------
Defines standard domain exceptions and FastAPI exception handlers to prevent raw tracebacks
from being exposed to end users in production.
"""

from typing import Any, Dict, Optional
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from shared.constants import ErrorCode
from shared.config import get_settings
from shared.logging_config import get_logger

logger = get_logger("app.exceptions")

class AppException(Exception):
    """Base domain exception for CtrlBooks."""
    def __init__(
        self,
        message: str,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        error_code: ErrorCode = ErrorCode.INTERNAL_SERVER_ERROR,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.details = details or {}

class ValidationError(AppException):
    def __init__(self, message: str = "Invalid request data", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status.HTTP_400_BAD_REQUEST, ErrorCode.VALIDATION_ERROR, details)

class ConfigurationError(AppException):
    def __init__(self, message: str = "Configuration error", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status.HTTP_500_INTERNAL_SERVER_ERROR, ErrorCode.CONFIGURATION_ERROR, details)

class NotFoundException(AppException):
    def __init__(self, message: str = "Resource not found", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status.HTTP_404_NOT_FOUND, ErrorCode.NOT_FOUND, details)

class ConflictException(AppException):
    def __init__(self, message: str = "Resource conflict", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status.HTTP_409_CONFLICT, ErrorCode.CONFLICT, details)

class AuthenticationError(AppException):
    def __init__(self, message: str = "Authentication failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status.HTTP_401_UNAUTHORIZED, ErrorCode.AUTHENTICATION_ERROR, details)

class AuthorizationError(AppException):
    def __init__(self, message: str = "Permission denied", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status.HTTP_403_FORBIDDEN, ErrorCode.AUTHORIZATION_ERROR, details)

class ExternalServiceError(AppException):
    def __init__(self, message: str = "External service error", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status.HTTP_502_BAD_GATEWAY, ErrorCode.EXTERNAL_SERVICE_ERROR, details)

class ServiceUnavailableException(AppException):
    def __init__(self, message: str = "Service unavailable", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, status.HTTP_503_SERVICE_UNAVAILABLE, ErrorCode.SERVICE_UNAVAILABLE, details)

def create_error_payload(code: str, message: str, request_id: Optional[str] = None, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Builds standard error response dictionary."""
    payload = {
        "success": False,
        "error": {
            "code": code,
            "message": message,
        },
        "request_id": request_id or ""
    }
    if details and get_settings().debug:
        payload["error"]["details"] = details
    return payload

def register_exception_handlers(app: FastAPI) -> None:
    """Registers global exception handlers on a FastAPI application instance."""

    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException):
        req_id = getattr(request.state, "request_id", "")
        logger.warning(f"Domain exception: [{exc.error_code.value}] {exc.message} (RequestID={req_id})")
        return JSONResponse(
            status_code=exc.status_code,
            content=create_error_payload(exc.error_code.value, exc.message, req_id, exc.details)
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        req_id = getattr(request.state, "request_id", "")
        logger.warning(f"Request validation error: {exc.errors()} (RequestID={req_id})")
        msg = "The provided request data is invalid"
        details = {"errors": exc.errors()} if get_settings().debug else None
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=create_error_payload(ErrorCode.VALIDATION_ERROR.value, msg, req_id, details)
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        req_id = getattr(request.state, "request_id", "")
        logger.warning(f"HTTP exception {exc.status_code}: {exc.detail} (RequestID={req_id})")
        code = ErrorCode.NOT_FOUND.value if exc.status_code == 404 else ErrorCode.INTERNAL_SERVER_ERROR.value
        return JSONResponse(
            status_code=exc.status_code,
            content=create_error_payload(code, str(exc.detail), req_id)
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        req_id = getattr(request.state, "request_id", "")
        logger.error(f"Unhandled exception: {exc} (RequestID={req_id})", exc_info=True)
        settings = get_settings()
        msg = str(exc) if settings.debug else "An unexpected internal server error occurred"
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=create_error_payload(ErrorCode.INTERNAL_SERVER_ERROR.value, msg, req_id)
        )
