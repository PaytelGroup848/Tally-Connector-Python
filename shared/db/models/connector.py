

from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import String, Boolean, DateTime, Text, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from shared.db.base import Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin

if TYPE_CHECKING:
    from shared.db.models.sync import SyncJobV2, SyncCheckpoint
    from shared.db.models.system import ActivityLog

class DataSource(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "data_sources"

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(50), default="ACTIVE", nullable=False, index=True)
    configuration_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    connectors: Mapped[List["Connector"]] = relationship("Connector", back_populates="source")

class Destination(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "destinations"

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    destination_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(50), default="ACTIVE", nullable=False, index=True)
    configuration_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    connectors: Mapped[List["Connector"]] = relationship("Connector", back_populates="destination")

class Connector(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "connectors"

    name: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    connector_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    configuration_status: Mapped[str] = mapped_column(String(50), default="DRAFT", nullable=False, index=True)
    connection_status: Mapped[str] = mapped_column(String(50), default="UNKNOWN", nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(50), default="DRAFT", nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)

    configuration_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    source_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("data_sources.id", ondelete="SET NULL"), nullable=True, index=True)
    destination_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("destinations.id", ondelete="SET NULL"), nullable=True, index=True)
    
    last_tested_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_connected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_by: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    source: Mapped[Optional["DataSource"]] = relationship("DataSource", back_populates="connectors")
    destination: Mapped[Optional["Destination"]] = relationship("Destination", back_populates="connectors")
    field_mappings: Mapped[List["FieldMapping"]] = relationship("FieldMapping", back_populates="connector", cascade="all, delete-orphan")
    sync_jobs: Mapped[List["SyncJobV2"]] = relationship("SyncJobV2", back_populates="connector")
    checkpoints: Mapped[List["SyncCheckpoint"]] = relationship("SyncCheckpoint", back_populates="connector")
    activity_logs: Mapped[List["ActivityLog"]] = relationship("ActivityLog", back_populates="connector")

    __table_args__ = (
        Index("idx_connectors_status_type", "status", "connector_type"),
        Index("idx_connectors_active_conn", "is_active", "connection_status"),
    )

class FieldMapping(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "field_mappings"

    connector_id: Mapped[str] = mapped_column(String(36), ForeignKey("connectors.id", ondelete="CASCADE"), nullable=False, index=True)
    source_field: Mapped[str] = mapped_column(String(150), nullable=False)
    destination_field: Mapped[str] = mapped_column(String(150), nullable=False)
    transform_rule: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    connector: Mapped["Connector"] = relationship("Connector", back_populates="field_mappings")
