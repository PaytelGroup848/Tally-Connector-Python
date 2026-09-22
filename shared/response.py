"""
CtrlBooks - Standardized API Response Models & Helpers
------------------------------------------------------------------
Provides consistent response envelopes for external application API responses.
"""

from typing import Any, Dict, Optional, Generic, TypeVar
from pydantic import BaseModel, Field

T = TypeVar("T")

class ErrorDetail(BaseModel):
    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Safe user-facing error message")
    details: Optional[Dict[str, Any]] = Field(None, description="Optional diagnostic details (Dev mode only)")

class StandardResponse(BaseModel, Generic[T]):
    success: bool = True
    data: Optional[T] = None
    message: str = "Operation completed successfully"
    request_id: str = ""

class StandardErrorResponse(BaseModel):
    success: bool = False
    error: ErrorDetail
    request_id: str = ""

def success_response(
    data: Any = None,
    message: str = "Operation completed successfully",
    request_id: str = ""
) -> Dict[str, Any]:
    """Helper to return standardized success dictionary."""
    return {
        "success": True,
        "data": data if data is not None else {},
        "message": message,
        "request_id": request_id
    }

def error_response(
    code: str,
    message: str,
    request_id: str = "",
    details: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Helper to return standardized error dictionary."""
    err_obj = {"code": code, "message": message}
    if details:
        err_obj["details"] = details
    return {
        "success": False,
        "error": err_obj,
        "request_id": request_id
    }
