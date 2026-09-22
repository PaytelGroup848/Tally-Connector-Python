"""
CtrlBooks - SQLAlchemy Declarative Base & Mixins
------------------------------------------------------------
Provides unified DeclarativeBase and mixins for timezone-aware UTC timestamps,
soft-deletion support, and UUID primary keys.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import DateTime, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class Base(DeclarativeBase):
    """Base declarative class for all SQLAlchemy ORM models."""
    pass

class UUIDPrimaryKeyMixin:
    """Mixin for UUID primary key generation as string."""
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )

class TimestampMixin:
    """Mixin adding timezone-aware created_at and updated_at UTC timestamps."""
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
        nullable=False
    )

class SoftDeleteMixin:
    """Mixin adding soft-delete support."""
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None
    )
    deleted_by: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        default=None
    )
