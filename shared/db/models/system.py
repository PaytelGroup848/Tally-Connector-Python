"""
CtrlBooks - ActivityLog, Notification, ApplicationSetting & HealthHistory ORM Models
--------------------------------------------------------------------------------------------------
Core system entities for audit logs, user notifications, application settings, and health probes.
"""

from datetime import datetime
from typing import Optional, TYPE_CHECKING
from sqlalchemy import String, Boolean, Integer, DateTime, Text, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from shared.db.base import Base, UUIDPrimaryKeyMixin, TimestampMixin, utc_now

if TYPE_CHECKING:
    from shared.db.models.user import User
    from shared.db.models.connector import Connector

class ActivityLog(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "activity_logs"

    user_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    connector_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("connectors.id", ondelete="SET NULL"), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    request_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)

    user: Mapped[Optional["User"]] = relationship("User", back_populates="activity_logs")
    connector: Mapped[Optional["Connector"]] = relationship("Connector", back_populates="activity_logs")

class Notification(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "notifications"

    user_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    severity: Mapped[str] = mapped_column(String(50), default="INFO", nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[Optional["User"]] = relationship("User", back_populates="notifications")

class ApplicationSetting(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "application_settings"

    scope: Mapped[str] = mapped_column(String(50), default="GLOBAL", nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    value_json: Mapped[str] = mapped_column(Text, nullable=False)
    updated_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    __table_args__ = (
        Index("idx_settings_scope_key", "scope", "key", unique=True),
    )

class HealthHistory(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "health_history"

    component: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    details_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
