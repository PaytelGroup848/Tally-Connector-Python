

from datetime import datetime
from typing import Optional, TYPE_CHECKING
from sqlalchemy import String, DateTime, Text, Integer, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from shared.db.base import Base, UUIDPrimaryKeyMixin, TimestampMixin

if TYPE_CHECKING:
    from shared.db.models.connector import Connector

class UnifiedSourceMetadata(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "unified_source_metadata"

    connector_id: Mapped[str] = mapped_column(String(36), ForeignKey("connectors.id", ondelete="CASCADE"), nullable=False, index=True)
    company_identifier: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    
    source_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    source_entity_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    canonical_entity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    
    source_identifier: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    
    parent_source_identifier: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    parent_display_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    status: Mapped[str] = mapped_column(String(50), default="ACTIVE", nullable=False, index=True)
    source_metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    connector: Mapped["Connector"] = relationship("Connector", backref="unified_metadata")

    __table_args__ = (
        Index("idx_meta_conn_comp_canon", "connector_id", "company_identifier", "canonical_entity_type"),
        Index("idx_meta_conn_canon_srcid", "connector_id", "canonical_entity_type", "source_identifier", unique=True),
        Index("idx_meta_src_canon", "source_type", "canonical_entity_type"),
    )

class MetadataDiscoveryRun(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "metadata_discovery_runs"

    connector_id: Mapped[str] = mapped_column(String(36), ForeignKey("connectors.id", ondelete="CASCADE"), nullable=False, index=True)
    company_identifier: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    requested_entity_types_json: Mapped[str] = mapped_column(Text, nullable=False)
    
    status: Mapped[str] = mapped_column(String(50), default="RUNNING", nullable=False, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    records_discovered: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_updated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_marked_stale: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    
    error_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    connector: Mapped["Connector"] = relationship("Connector", backref="discovery_runs")
