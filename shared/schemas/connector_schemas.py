"""
CtrlBooks - Connector Pydantic Validation & Serialization Schemas
-----------------------------------------------------------------------------
Type-specific schemas for validating connector inputs, network parameters,
file paths, allowed connection modes, and masking secrets.
"""

from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator

ALLOWED_CONNECTOR_TYPES = ["TALLY", "REST_API", "DATABASE", "FILE"]
PRIMARY_CONNECTOR_TYPES = ["TALLY"]

class TallyConfigurationSchema(BaseModel):
    host: str = Field(default="127.0.0.1", description="Tally Prime host IP address or hostname")
    port: int = Field(default=9000, ge=1, le=65535, description="Tally Prime HTTP/XML port number")
    company_name: Optional[str] = Field(default=None, description="Optional target Tally company name")
    connection_mode: str = Field(default="HTTP_XML", description="Tally connection protocol mode (HTTP_XML, ODBC, NATIVE)")

    @field_validator("connection_mode")
    @classmethod
    def validate_mode(cls, v: str) -> str:
        clean = v.strip().upper()
        if clean not in ("HTTP_XML", "ODBC", "NATIVE"):
            raise ValueError(f"Invalid Tally connection mode '{v}'. Allowed: HTTP_XML, ODBC, NATIVE.")
        return clean

    @field_validator("host")
    @classmethod
    def validate_host(cls, v: str) -> str:
        clean = v.strip()
        if not clean:
            raise ValueError("Host cannot be empty.")
        if len(clean) > 255:
            raise ValueError("Host string length exceeds limit (255 chars).")
        return clean

class CreateConnectorRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=150, description="Unique display name for data connector")
    connector_type: str = Field(..., description="Connector type identifier (TALLY)")
    description: Optional[str] = Field(default=None, max_length=255, description="Optional connector summary description")
    configuration: Dict[str, Any] = Field(default_factory=dict, description="Type-specific connection configuration")

    @field_validator("connector_type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        clean = v.strip().upper()
        if clean not in ALLOWED_CONNECTOR_TYPES:
            raise ValueError(f"Unsupported connector type '{v}'. Allowed types: {', '.join(ALLOWED_CONNECTOR_TYPES)}")
        return clean

class UpdateConnectorRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=150, description="Updated connector display name")
    description: Optional[str] = Field(default=None, max_length=255, description="Updated connector summary description")
    configuration: Optional[Dict[str, Any]] = Field(default=None, description="Updated type-specific configuration")
    is_active: Optional[bool] = Field(default=None, description="Updated activation status flag")

class ConnectorResponse(BaseModel):
    id: str
    name: str
    connector_type: str
    description: Optional[str] = None
    configuration_status: str
    connection_status: str
    is_active: bool
    configuration: Dict[str, Any]
    last_tested_at: Optional[str] = None
    last_connected_at: Optional[str] = None
    last_sync_at: Optional[str] = None
    last_error_message: Optional[str] = None
    created_at: str
    updated_at: str
