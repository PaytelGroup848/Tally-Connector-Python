"""
CtrlBooks - Persistent Extracted Record ORM Model
--------------------------------------------------------------
Stores normalized canonical and mapped accounting data records (Ledgers, Stock Items, Vouchers, Account Groups)
extracted from source accounting systems (Tally / BUSY) into persistent database storage for website consumption.
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, DateTime, Text, Boolean, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column
from shared.db.base import Base, UUIDPrimaryKeyMixin, TimestampMixin

class ExtractedRecord(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "extracted_records"

    connector_id: Mapped[str] = mapped_column(String(36), ForeignKey("connectors.id", ondelete="CASCADE"), nullable=False, index=True)
    company_identifier: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    record_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    
    canonical_data_json: Mapped[str] = mapped_column(Text, nullable=False)
    mapped_data_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    extracted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_extracted_records_connector_company_entity", "connector_id", "company_identifier", "entity_type"),
        Index("ix_extracted_records_external_lookup", "connector_id", "company_identifier", "entity_type", "external_id", unique=True),
    )
