

from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import String, Integer, DateTime, Text, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from shared.db.base import Base, UUIDPrimaryKeyMixin, TimestampMixin, utc_now

if TYPE_CHECKING:
    from shared.db.models.connector import Connector

class SyncJobV2(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "sync_jobs_v2"

    connector_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("connectors.id", ondelete="SET NULL"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(50), default="PENDING", nullable=False, index=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    records_read: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_processed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_success: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    connector: Mapped[Optional["Connector"]] = relationship("Connector", back_populates="sync_jobs")
    sync_errors: Mapped[List["SyncError"]] = relationship("SyncError", back_populates="sync_job", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_sync_jobs_connector_status", "connector_id", "status"),
        Index("idx_sync_jobs_created_at", "created_at"),
    )

class SyncError(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "sync_errors"

    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("sync_jobs_v2.id", ondelete="CASCADE"), nullable=False, index=True)
    record_reference: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    error_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    sync_job: Mapped["SyncJobV2"] = relationship("SyncJobV2", back_populates="sync_errors")

class SyncCheckpoint(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "sync_checkpoints"

    connector_id: Mapped[str] = mapped_column(String(36), ForeignKey("connectors.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_name: Mapped[str] = mapped_column(String(150), nullable=False)
    checkpoint_value: Mapped[str] = mapped_column(Text, nullable=False)
    last_processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    connector: Mapped["Connector"] = relationship("Connector", back_populates="checkpoints")

    __table_args__ = (
        Index("idx_checkpoint_connector_entity", "connector_id", "entity_name", unique=True),
    )

class SyncQueue(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Local Database Queue table for storing extracted/transformed payloads
    prior to pushing to central Cloud Server. Prevents data loss during network outages.
    """
    __tablename__ = "sync_queue"

    payload_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="PENDING", nullable=False, index=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_msg: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("idx_sync_queue_status_created", "status", "created_at"),
    )

