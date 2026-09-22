"""
CtrlBooks - Company Sync Configuration ORM Model
-------------------------------------------------------------
Persists per-company multi-company sync toggles (is_sync_enabled),
last sync timestamps, GUIDs, and status badges in SQLite cache.
Must strictly stay under 150 lines of code.
"""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Boolean, DateTime, Index, Integer
from sqlalchemy.orm import Mapped, mapped_column
from shared.db.base import Base, UUIDPrimaryKeyMixin, TimestampMixin

class CompanySyncConfig(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "company_sync_configs"

    source_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    company_name: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    company_guid: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    financial_year_from: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    is_sync_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(50), default="CONNECTED", nullable=False)
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_alter_id: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        Index("idx_company_source_name", "source_type", "company_name", unique=True),
    )
