"""
CtrlBooks - PermissionRepository & RolePermissionRepository
-------------------------------------------------------------------------
Data access layer for system permissions and role permission assignments.
"""

from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import select
from shared.db.models.user import Permission, RolePermission
from shared.repositories.base import BaseRepository

class PermissionRepository(BaseRepository[Permission]):
    def __init__(self):
        super().__init__(Permission)

    def get_by_code(self, db: Session, code: str) -> Optional[Permission]:
        """Fetch permission entity by machine-readable code."""
        stmt = select(Permission).where(Permission.code == code.strip())
        return db.scalar(stmt)

    def list_by_module(self, db: Session, module: str) -> List[Permission]:
        """List permissions filtered by module name."""
        stmt = select(Permission).where(Permission.module == module.upper()).order_by(Permission.code)
        return list(db.scalars(stmt).all())

class RolePermissionRepository(BaseRepository[RolePermission]):
    def __init__(self):
        super().__init__(RolePermission)

    def list_permissions_by_role(self, db: Session, role_id: str) -> List[Permission]:
        """Fetch list of Permission objects assigned to a role ID."""
        stmt = (
            select(Permission)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id == role_id)
        )
        return list(db.scalars(stmt).all())

    def get_permission_codes_by_role(self, db: Session, role_id: str) -> List[str]:
        """Fetch string permission codes assigned to a role ID."""
        permissions = self.list_permissions_by_role(db, role_id)
        return [p.code for p in permissions]

    def set_role_permissions(self, db: Session, role_id: str, permission_ids: List[str]) -> None:
        """Replace all permission assignments for a role with specified permission IDs."""
        db.query(RolePermission).filter(RolePermission.role_id == role_id).delete(synchronize_session=False)
        db.flush()

        for pid in set(permission_ids):
            rp = RolePermission(role_id=role_id, permission_id=pid)
            db.add(rp)
        db.flush()
