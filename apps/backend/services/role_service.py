"""
CtrlBooks - Role & Permission Management Service
--------------------------------------------------------------
Business logic for creating, updating, listing, and deleting custom roles,
assigning permission codes, and protecting system roles from deletion.
"""

from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from shared.db.models.user import Role
from shared.repositories.user_repo import RoleRepository
from shared.repositories.permission_repo import PermissionRepository, RolePermissionRepository
from shared.repositories.system_repo import ActivityLogRepository
from shared.exceptions import ValidationError, ConflictException
from shared.logging_config import get_logger

logger = get_logger("app.services.role")

class RoleService:
    def __init__(self):
        self.role_repo = RoleRepository()
        self.perm_repo = PermissionRepository()
        self.role_perm_repo = RolePermissionRepository()
        self.audit_repo = ActivityLogRepository()

    def list_roles(self, db: Session) -> List[Dict[str, Any]]:
        """List all system and custom roles with assigned permissions."""
        roles = self.role_repo.list_all(db)
        result = []
        for r in roles:
            perm_codes = self.role_perm_repo.get_permission_codes_by_role(db, r.id)
            user_count = self.role_repo.count_users_with_role(db, r.id)
            result.append({
                "id": r.id,
                "name": r.name,
                "code": r.code,
                "description": r.description,
                "is_system_role": r.is_system_role,
                "permissions": perm_codes,
                "user_count": user_count,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            })
        return result

    def get_role_by_id(self, db: Session, role_id: str) -> Dict[str, Any]:
        """Fetch role by ID and return details with permission codes."""
        role = self.role_repo.get_by_id_or_raise(db, role_id)
        perm_codes = self.role_perm_repo.get_permission_codes_by_role(db, role.id)
        user_count = self.role_repo.count_users_with_role(db, role.id)
        return {
            "id": role.id,
            "name": role.name,
            "code": role.code,
            "description": role.description,
            "is_system_role": role.is_system_role,
            "permissions": perm_codes,
            "user_count": user_count,
            "created_at": role.created_at.isoformat() if role.created_at else None,
            "updated_at": role.updated_at.isoformat() if role.updated_at else None,
        }

    def create_role(
        self,
        db: Session,
        name: str,
        code: str,
        description: Optional[str] = None,
        permission_codes: Optional[List[str]] = None,
        acting_user_id: Optional[str] = None,
        request_id: str = ""
    ) -> Dict[str, Any]:
        """Creates a custom role and assigns permission codes."""
        clean_name = name.strip()
        clean_code = code.strip().upper()

        if not clean_name or len(clean_name) < 2 or len(clean_name) > 100:
            raise ValidationError("Role name must be between 2 and 100 characters long.")

        if not clean_code or len(clean_code) < 2 or len(clean_code) > 50:
            raise ValidationError("Role code must be between 2 and 50 characters long.")

        if self.role_repo.get_by_code(db, clean_code):
            raise ConflictException(f"Role code '{clean_code}' already exists.")

        if self.role_repo.get_by_name(db, clean_name):
            raise ConflictException(f"Role name '{clean_name}' already exists.")

        new_role = Role(
            name=clean_name,
            code=clean_code,
            description=description.strip() if description else None,
            is_system_role=False
        )
        created_role = self.role_repo.create(db, new_role)

        if permission_codes:
            perm_ids = self._resolve_permission_ids(db, permission_codes)
            self.role_perm_repo.set_role_permissions(db, created_role.id, perm_ids)

        self._log_audit(db, acting_user_id, "ROLE_CREATED", f"Created custom role '{clean_name}' ({clean_code})", request_id)
        logger.info(f"Custom role '{clean_code}' created successfully")
        return self.get_role_by_id(db, created_role.id)

    def update_role(
        self,
        db: Session,
        role_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        permission_codes: Optional[List[str]] = None,
        acting_user_id: Optional[str] = None,
        request_id: str = ""
    ) -> Dict[str, Any]:
        """Updates role metadata or assigned permission list."""
        role = self.role_repo.get_by_id_or_raise(db, role_id)

        update_fields = {}
        if name and name.strip():
            update_fields["name"] = name.strip()
        if description is not None:
            update_fields["description"] = description.strip()

        if update_fields:
            role = self.role_repo.update(db, role, update_fields)

        if permission_codes is not None:
            perm_ids = self._resolve_permission_ids(db, permission_codes)
            self.role_perm_repo.set_role_permissions(db, role.id, perm_ids)

        self._log_audit(db, acting_user_id, "ROLE_UPDATED", f"Updated role permissions/details for '{role.name}'", request_id)
        return self.get_role_by_id(db, role.id)

    def delete_role(self, db: Session, role_id: str, acting_user_id: Optional[str] = None, request_id: str = "") -> bool:
        """Deletes a custom role after verifying it is not a system role or assigned to active users."""
        role = self.role_repo.get_by_id_or_raise(db, role_id)

        if role.is_system_role:
            raise ValidationError(f"System role '{role.name}' ({role.code}) is protected and cannot be deleted.")

        assigned_count = self.role_repo.count_users_with_role(db, role.id)
        if assigned_count > 0:
            raise ValidationError(f"Cannot delete role '{role.name}' because it is currently assigned to {assigned_count} user(s). Reassign users first.")

        role_name = role.name
        self.role_repo.delete(db, role.id, hard=True)
        self._log_audit(db, acting_user_id, "ROLE_DELETED", f"Deleted custom role '{role_name}'", request_id)
        logger.info(f"Role '{role_name}' deleted successfully")
        return True

    def list_permissions(self, db: Session) -> List[Dict[str, Any]]:
        """List all system permissions grouped by module."""
        perms = self.perm_repo.list_all(db)
        return [
            {
                "id": p.id,
                "code": p.code,
                "name": p.name,
                "description": p.description,
                "module": p.module,
            }
            for p in perms
        ]

    def _resolve_permission_ids(self, db: Session, permission_codes: List[str]) -> List[str]:
        perm_ids = []
        for code in permission_codes:
            p = self.perm_repo.get_by_code(db, code)
            if p:
                perm_ids.append(p.id)
        return perm_ids

    def _log_audit(self, db: Session, acting_user_id: Optional[str], event_type: str, message: str, request_id: str) -> None:
        try:
            self.audit_repo.log_activity(
                db=db,
                event_type=event_type,
                status="SUCCESS",
                message=message,
                user_id=acting_user_id,
                request_id=request_id
            )
        except Exception as exc:
            logger.error(f"Failed to record role audit event: {exc}")

role_service = RoleService()
