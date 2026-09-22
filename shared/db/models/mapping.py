

from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import String, Boolean, DateTime, Text, Integer, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from shared.db.base import Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin

if TYPE_CHECKING:
    from shared.db.models.connector import Connector

class MappingDefinition(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "mapping_definitions"

    name: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    
    source_connector_id: Mapped[str] = mapped_column(String(36), ForeignKey("connectors.id", ondelete="CASCADE"), nullable=False, index=True)
    source_company_identifier: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    
    target_connector_id: Mapped[str] = mapped_column(String(36), ForeignKey("connectors.id", ondelete="CASCADE"), nullable=False, index=True)
    target_company_identifier: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    
    canonical_entity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    
    status: Mapped[str] = mapped_column(String(50), default="DRAFT", nullable=False, index=True)
    current_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_by: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    source_connector: Mapped["Connector"] = relationship("Connector", foreign_keys=[source_connector_id], backref="source_mappings")
    target_connector: Mapped["Connector"] = relationship("Connector", foreign_keys=[target_connector_id], backref="target_mappings")
    
    versions: Mapped[List["MappingVersion"]] = relationship("MappingVersion", back_populates="mapping", cascade="all, delete-orphan")
    field_rules: Mapped[List["MappingFieldRule"]] = relationship("MappingFieldRule", back_populates="mapping", cascade="all, delete-orphan")
    validation_logs: Mapped[List["MappingValidationLog"]] = relationship("MappingValidationLog", back_populates="mapping", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_mapping_scope", "source_connector_id", "source_company_identifier", "target_connector_id", "target_company_identifier", "canonical_entity_type"),
        Index("idx_mapping_status", "status", "canonical_entity_type"),
    )

class MappingVersion(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "mapping_versions"

    mapping_id: Mapped[str] = mapped_column(String(36), ForeignKey("mapping_definitions.id", ondelete="CASCADE"), nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="DRAFT", nullable=False)
    change_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    snapshot_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_by: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    mapping: Mapped["MappingDefinition"] = relationship("MappingDefinition", back_populates="versions")
    field_rules: Mapped[List["MappingFieldRule"]] = relationship("MappingFieldRule", back_populates="mapping_version", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_mapping_version_uniq", "mapping_id", "version_number", unique=True),
    )

class MappingFieldRule(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "mapping_field_rules"

    mapping_id: Mapped[str] = mapped_column(String(36), ForeignKey("mapping_definitions.id", ondelete="CASCADE"), nullable=False, index=True)
    mapping_version_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("mapping_versions.id", ondelete="CASCADE"), nullable=True, index=True)
    
    source_field: Mapped[str] = mapped_column(String(150), nullable=False)
    target_field: Mapped[str] = mapped_column(String(150), nullable=False)
    
    source_data_type: Mapped[str] = mapped_column(String(50), default="STRING", nullable=False)
    target_data_type: Mapped[str] = mapped_column(String(50), default="STRING", nullable=False)
    
    is_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    default_value: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    
    transformation_type: Mapped[str] = mapped_column(String(50), default="NONE", nullable=False)
    transformation_config_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    mapping: Mapped["MappingDefinition"] = relationship("MappingDefinition", back_populates="field_rules")
    mapping_version: Mapped[Optional["MappingVersion"]] = relationship("MappingVersion", back_populates="field_rules")

    __table_args__ = (
        Index("idx_rule_mapping_target", "mapping_id", "target_field"),
    )

class MappingValidationLog(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "mapping_validation_logs"

    mapping_id: Mapped[str] = mapped_column(String(36), ForeignKey("mapping_definitions.id", ondelete="CASCADE"), nullable=False, index=True)
    overall_status: Mapped[str] = mapped_column(String(50), nullable=False)
    errors_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    warnings_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    mapped_fields_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unmapped_required_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unmapped_optional_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    validated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    mapping: Mapped["MappingDefinition"] = relationship("MappingDefinition", back_populates="validation_logs")
