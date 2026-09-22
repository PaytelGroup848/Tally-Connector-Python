"""
CtrlBooks - User, Role, UserRole, Permission & RolePermission ORM Models
-------------------------------------------------------------------------------------
Core entities for user identity, security, role-based access control (RBAC), and permissions.
"""

from datetime import datetime
from typing import Optional, List, TYPE_CHECKING
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from shared.db.base import Base, UUIDPrimaryKeyMixin, TimestampMixin, utc_now

if TYPE_CHECKING:
    from shared.db.models.system import ActivityLog, Notification

class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    mobile: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), unique=True, index=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="ACTIVE", nullable=False, index=True)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    user_roles: Mapped[List["UserRole"]] = relationship("UserRole", back_populates="user", cascade="all, delete-orphan")
    activity_logs: Mapped[List["ActivityLog"]] = relationship("ActivityLog", back_populates="user")
    notifications: Mapped[List["Notification"]] = relationship("Notification", back_populates="user")

class Role(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "roles"

    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_system_role: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    user_roles: Mapped[List["UserRole"]] = relationship("UserRole", back_populates="role", cascade="all, delete-orphan")
    role_permissions: Mapped[List["RolePermission"]] = relationship("RolePermission", back_populates="role", cascade="all, delete-orphan")

class UserRole(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "user_roles"

    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role_id: Mapped[str] = mapped_column(String(36), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="user_roles")
    role: Mapped["Role"] = relationship("Role", back_populates="user_roles")

    __table_args__ = (
        Index("idx_user_role_unique", "user_id", "role_id", unique=True),
    )

class Permission(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "permissions"

    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    module: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    role_permissions: Mapped[List["RolePermission"]] = relationship("RolePermission", back_populates="permission", cascade="all, delete-orphan")

class RolePermission(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "role_permissions"

    role_id: Mapped[str] = mapped_column(String(36), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True)
    permission_id: Mapped[str] = mapped_column(String(36), ForeignKey("permissions.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    role: Mapped["Role"] = relationship("Role", back_populates="role_permissions")
    permission: Mapped["Permission"] = relationship("Permission", back_populates="role_permissions")

    __table_args__ = (
        Index("idx_role_permission_unique", "role_id", "permission_id", unique=True),
    )
