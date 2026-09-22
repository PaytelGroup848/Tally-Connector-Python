"""
CtrlBooks - Data Extraction Run ORM Model
------------------------------------------------------
Tracks source data reading operations, extraction parameters, pagination metrics,
record counts, normalization status, and error diagnostics.
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, DateTime, Text, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column
from shared.db.base import Base, UUIDPrimaryKeyMixin, TimestampMixin

class DataExtractionRun(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "data_extraction_runs"

    connector_id: Mapped[str] = mapped_column(String(36), ForeignKey("connectors.id", ondelete="CASCADE"), nullable=False, index=True)
    company_identifier: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    filters_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    mapping_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("mapping_definitions.id", ondelete="SET NULL"), nullable=True, index=True)
    
    mode: Mapped[str] = mapped_column(String(50), default="CANONICAL", nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(50), default="PENDING", nullable=False, index=True)
    
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    records_requested: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_returned: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_normalized: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    error_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    __table_args__ = (
        Index("ix_extraction_runs_connector_entity", "connector_id", "entity_type"),
        Index("ix_extraction_runs_status_created", "status", "created_at"),
    )
