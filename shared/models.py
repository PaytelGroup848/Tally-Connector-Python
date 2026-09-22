from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
from datetime import datetime, timezone

def utc_now():
    """Helper function to get current UTC timestamp."""
    return datetime.now(timezone.utc)

class SourceType(str, Enum):
    TALLY = "tally"

class RecordType(str, Enum):
    COMPANY = "company"
    LEDGER = "ledger"
    GROUP = "group"
    VOUCHER = "voucher"
    VOUCHER_ENTRY = "voucher_entry"
    STOCK_ITEM = "stock_item"
    STOCK_GROUP = "stock_group"
    UNIT = "unit"
    PARTY = "party"
    GST = "gst"
    INVENTORY_BATCH = "inventory_batch"

class ConnectionState(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"

class CompanyCreate(BaseModel):
    source: SourceType = Field(..., description="Source accounting software: 'tally' or 'busy'")
    name: str = Field(..., description="Name of the company in Tally/BUSY")
    data_path: Optional[str] = Field(None, description="Local folder path for BUSY/Tally data")
    host: Optional[str] = Field(None, description="Host IP/Name for Tally HTTP server (e.g. 127.0.0.1)")
    port: Optional[int] = Field(None, description="Port for Tally HTTP server (e.g. 9000)")

class Company(BaseModel):
    id: Optional[int] = None
    source: SourceType
    name: str
    data_path: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    created_at: datetime = Field(default_factory=utc_now)

class ConnectionStatus(BaseModel):
    source: SourceType
    state: ConnectionState
    message: str
    details: Dict[str, Any] = Field(default_factory=dict)
    checked_at: datetime = Field(default_factory=utc_now)

class SourceRecord(BaseModel):
    source: SourceType
    record_type: RecordType
    external_id: str = Field(..., description="Unique ID / GUID / Master ID from source software")
    company_name: str
    data: Dict[str, Any] = Field(..., description="Raw dict extracted from Tally XML or BUSY DB/API")
    modified_at: Optional[datetime] = None

class NormalizedRecord(BaseModel):
    source: SourceType
    record_type: RecordType
    external_id: str
    company_name: str
    canonical: Dict[str, Any] = Field(..., description="Normalized LR format record")
    fingerprint: str = Field(..., description="SHA-256 hash of canonical content for diffing")
    normalized_at: datetime = Field(default_factory=utc_now)

class ChangeEvent(BaseModel):
    event_type: str = Field(..., description="'created', 'updated', or 'unchanged'")
    source: SourceType
    record_type: RecordType
    external_id: str
    fingerprint: str
    previous_fingerprint: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)

class SyncRequest(BaseModel):
    source: SourceType
    company_name: str
    full_sync: bool = False

class SyncJob(BaseModel):
    job_id: str
    source: SourceType
    company_name: str
    state: str = Field(..., description="'queued', 'syncing', 'completed', 'failed'")
    progress: int = Field(0, description="Percentage 0-100")
    message: str
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    stats: Dict[str, int] = Field(default_factory=dict)

class AuditEvent(BaseModel):
    level: str = Field("INFO", description="'INFO', 'WARNING', 'ERROR'")
    service: str
    action: str
    message: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)

