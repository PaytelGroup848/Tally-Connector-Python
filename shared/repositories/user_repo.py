"""
CtrlBooks - UserRepository & RoleRepository
------------------------------------------------------
Data access layer for User, Role, and UserRole management.
"""

from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import select, func, or_
from shared.db.models.user import User, Role, UserRole
from shared.repositories.base import BaseRepository

class UserRepository(BaseRepository[User]):
    def __init__(self):
        super().__init__(User)

    def get_by_username(self, db: Session, username: str) -> Optional[User]:
        """Fetch user by username (trimmed, case-insensitive match)."""
        clean_username = username.strip().lower()
        stmt = select(User).where(func.lower(User.username) == clean_username)
        return db.scalar(stmt)

    def get_by_email(self, db: Session, email: str) -> Optional[User]:
        """Fetch user by email address."""
        stmt = select(User).where(func.lower(User.email) == email.strip().lower())
        return db.scalar(stmt)

    def get_by_mobile(self, db: Session, mobile: str) -> Optional[User]:
        """Fetch user by mobile number."""
        stmt = select(User).where(User.mobile == mobile.strip())
        return db.scalar(stmt)

    def list_users(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 20,
        search: Optional[str] = None,
        role_code: Optional[str] = None,
        status: Optional[str] = None
    ) -> List[User]:
        """List users with search, role code filter, status filter, and pagination."""
        stmt = select(User)

        if search:
            s_term = f"%{search.strip().lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(User.username).like(s_term),
                    func.lower(User.full_name).like(s_term),
                    func.lower(User.email).like(s_term)
                )
            )

        if status:
            stmt = stmt.where(User.status == status.upper())

        if role_code:
            stmt = (
                stmt.join(UserRole, UserRole.user_id == User.id)
                .join(Role, Role.id == UserRole.role_id)
                .where(func.upper(Role.code) == role_code.upper())
            )

        stmt = stmt.order_by(User.created_at.desc()).offset(skip).limit(limit)
        return list(db.scalars(stmt).all())

    def count_users(
        self,
        db: Session,
        search: Optional[str] = None,
        role_code: Optional[str] = None,
        status: Optional[str] = None
    ) -> int:
        """Count total matching users."""
        stmt = select(func.count()).select_from(User)

        if search:
            s_term = f"%{search.strip().lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(User.username).like(s_term),
                    func.lower(User.full_name).like(s_term),
                    func.lower(User.email).like(s_term)
                )
            )

        if status:
            stmt = stmt.where(User.status == status.upper())

        if role_code:
            stmt = (
                stmt.join(UserRole, UserRole.user_id == User.id)
                .join(Role, Role.id == UserRole.role_id)
                .where(func.upper(Role.code) == role_code.upper())
            )

        return db.scalar(stmt) or 0

    def count_active_admins(self, db: Session) -> int:
        """Count total ACTIVE users with the 'ADMIN' role code."""
        stmt = (
            select(func.count())
            .select_from(User)
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .where(User.status == "ACTIVE", func.upper(Role.code) == "ADMIN")
        )
        return db.scalar(stmt) or 0

class RoleRepository(BaseRepository[Role]):
    def __init__(self):
        super().__init__(Role)

    def get_by_name(self, db: Session, name: str) -> Optional[Role]:
        """Fetch role by name."""
        stmt = select(Role).where(func.lower(Role.name) == name.strip().lower())
        return db.scalar(stmt)

    def get_by_code(self, db: Session, code: str) -> Optional[Role]:
        """Fetch role by code (ADMIN, OPERATOR, VIEWER)."""
        stmt = select(Role).where(func.upper(Role.code) == code.strip().upper())
        return db.scalar(stmt)

    def assign_role_to_user(self, db: Session, user_id: str, role_id: str) -> UserRole:
        """Assign role to user, replacing any existing user role."""
        db.query(UserRole).filter(UserRole.user_id == user_id).delete(synchronize_session=False)
        db.flush()

        ur = UserRole(user_id=user_id, role_id=role_id)
        db.add(ur)
        db.flush()
        return ur

    def count_users_with_role(self, db: Session, role_id: str) -> int:
        """Count total users assigned to a specific role."""
        stmt = select(func.count()).select_from(UserRole).where(UserRole.role_id == role_id)
        return db.scalar(stmt) or 0
