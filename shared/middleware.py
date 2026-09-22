"""
CtrlBooks - Request ID / Correlation ID Middleware
--------------------------------------------------------------
Generates or propagates unique correlation IDs (`X-Request-ID`) across incoming API requests
to enable end-to-end tracing across gateway, microservices, and desktop logs.
"""

import uuid
from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware
from shared.logging_config import get_logger

logger = get_logger("app.api")

class RequestIDMiddleware(BaseHTTPMiddleware):
    """Middleware that assigns a unique request_id to each incoming HTTP request."""
    async def dispatch(self, request: Request, call_next):
        request_id = (
            request.headers.get("X-Request-ID")
            or request.headers.get("X-Correlation-ID")
            or f"req-{uuid.uuid4().hex[:12]}"
        )
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

def add_request_id_middleware(app: FastAPI) -> None:
    """Registers RequestIDMiddleware on a FastAPI application instance."""
    app.add_middleware(RequestIDMiddleware)
