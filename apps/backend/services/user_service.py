"""
CtrlBooks - User Management Service
-----------------------------------------------
Business logic for User CRUD, role assignment, status management, password reset,
audit trail logging, and administrative safety guards (preventing self-deactivation and lockout).
"""

from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from shared.db.models.user import User
from shared.repositories.user_repo import UserRepository, RoleRepository
from shared.repositories.system_repo import ActivityLogRepository
from shared.auth.password import hash_password
from shared.exceptions import ValidationError, ConflictException
from shared.logging_config import get_logger

logger = get_logger("app.services.user")

class UserService:
    def __init__(self):
        self.user_repo = UserRepository()
        self.role_repo = RoleRepository()
        self.audit_repo = ActivityLogRepository()

    def list_users(
        self,
        db: Session,
        page: int = 1,
        page_size: int = 20,
        search: Optional[str] = None,
        role_code: Optional[str] = None,
        status: Optional[str] = None
    ) -> Dict[str, Any]:
        """List users with pagination, search, role, and status filtering."""
        page = max(1, page)
        page_size = max(1, min(100, page_size))
        skip = (page - 1) * page_size

        users = self.user_repo.list_users(db, skip=skip, limit=page_size, search=search, role_code=role_code, status=status)
        total = self.user_repo.count_users(db, search=search, role_code=role_code, status=status)
        total_pages = (total + page_size - 1) // page_size if total > 0 else 0

        items = [self._format_user_dict(u) for u in users]
        return {
            "items": items,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "total_pages": total_pages
            }
        }

    def get_user_by_id(self, db: Session, user_id: str) -> Dict[str, Any]:
        """Fetch user by ID and return safe representation."""
        user = self.user_repo.get_by_id_or_raise(db, user_id)
        return self._format_user_dict(user)

    def create_user(
        self,
        db: Session,
        username: str,
        full_name: str,
        password: str,
        role_code: str = "OPERATOR",
        email: Optional[str] = None,
        mobile: Optional[str] = None,
        acting_user_id: Optional[str] = None,
        request_id: str = ""
    ) -> Dict[str, Any]:
        """Creates a new user with secure password hash and role assignment."""
        clean_username = username.strip().lower()
        if not clean_username or len(clean_username) < 3 or len(clean_username) > 50:
            raise ValidationError("Username must be between 3 and 50 characters long.")

        if not password or len(password) < 6:
            raise ValidationError("Password must be at least 6 characters long.")

        if self.user_repo.get_by_username(db, clean_username):
            raise ConflictException(f"Username '{clean_username}' is already taken.")

        if email and email.strip() and self.user_repo.get_by_email(db, email):
            raise ConflictException(f"Email address '{email.strip()}' is already registered.")

        role = self.role_repo.get_by_code(db, role_code) or self.role_repo.get_by_name(db, role_code)
        if not role:
            raise ValidationError(f"Specified role '{role_code}' does not exist.")

        hashed = hash_password(password)

        new_user = User(
            username=clean_username,
            full_name=full_name.strip(),
            email=email.strip().lower() if email else None,
            mobile=mobile.strip() if mobile else None,
            password_hash=hashed,
            status="ACTIVE"
        )
        created_user = self.user_repo.create(db, new_user)
        self.role_repo.assign_role_to_user(db, created_user.id, role.id)

        self._log_audit(db, acting_user_id, created_user.id, "USER_CREATED", f"Created user '{clean_username}' with role '{role.name}'", request_id)

        logger.info(f"User '{clean_username}' created successfully with role '{role.code}'")
        return self._format_user_dict(created_user)

    def update_user(
        self,
        db: Session,
        user_id: str,
        full_name: Optional[str] = None,
        role_code: Optional[str] = None,
        status: Optional[str] = None,
        acting_user_id: Optional[str] = None,
        request_id: str = ""
    ) -> Dict[str, Any]:
        """Updates user details, role assignment, or status with administrative safety guards."""
        user = self.user_repo.get_by_id_or_raise(db, user_id)

        if acting_user_id and acting_user_id == user.id and status and status.upper() != "ACTIVE":
            raise ValidationError("You cannot deactivate or disable your own account.")

        if status and status.upper() != "ACTIVE":
            self._guard_last_admin_lockout(db, user)

        update_fields = {}
        if full_name and full_name.strip():
            update_fields["full_name"] = full_name.strip()
        if status and status.upper() in ("ACTIVE", "INACTIVE", "LOCKED", "DISABLED"):
            update_fields["status"] = status.upper()

        if update_fields:
            user = self.user_repo.update(db, user, update_fields)

        if role_code:
            role = self.role_repo.get_by_code(db, role_code) or self.role_repo.get_by_name(db, role_code)
            if not role:
                raise ValidationError(f"Role '{role_code}' does not exist.")
            self.role_repo.assign_role_to_user(db, user.id, role.id)

        self._log_audit(db, acting_user_id, user.id, "USER_UPDATED", f"Updated user profile/status for '{user.username}'", request_id)
        return self._format_user_dict(user)

    def set_user_status(self, db: Session, user_id: str, new_status: str, acting_user_id: Optional[str] = None, request_id: str = "") -> Dict[str, Any]:
        """Activates or deactivates a user account."""
        target_status = new_status.upper()
        if target_status not in ("ACTIVE", "INACTIVE", "LOCKED", "DISABLED"):
            raise ValidationError(f"Invalid status value '{new_status}'.")
        return self.update_user(db=db, user_id=user_id, status=target_status, acting_user_id=acting_user_id, request_id=request_id)

    def reset_password(
        self,
        db: Session,
        user_id: str,
        new_password: str,
        acting_user_id: Optional[str] = None,
        request_id: str = ""
    ) -> Dict[str, Any]:
        """Resets user password, hashes new secret, and invalidates existing sessions."""
        if not new_password or len(new_password) < 6:
            raise ValidationError("New password must be at least 6 characters long.")

        user = self.user_repo.get_by_id_or_raise(db, user_id)
        hashed = hash_password(new_password)

        self.user_repo.update(db, user, {"password_hash": hashed})
        self._log_audit(db, acting_user_id, user.id, "USER_PASSWORD_RESET", f"Reset password for user '{user.username}'", request_id)

        logger.info(f"Password reset completed for user '{user.username}'")
        return {"user_id": user.id, "username": user.username, "password_reset": True}

    def _guard_last_admin_lockout(self, db: Session, target_user: User) -> None:
        """Verifies that deactivating target_user will not lock out the system by leaving 0 active admins."""
        is_admin = False
        if target_user.user_roles:
            r = target_user.user_roles[0].role
            if r and r.code.upper() == "ADMIN":
                is_admin = True
        elif "admin" in target_user.username.lower():
            is_admin = True

        if is_admin:
            active_admins = self.user_repo.count_active_admins(db)
            if active_admins <= 1:
                raise ValidationError("Action blocked: Cannot deactivate or disable the last active Administrator account.")

    def _format_user_dict(self, user: User) -> Dict[str, Any]:
        role_name = "User"
        role_code = "VIEWER"
        if user.user_roles:
            r = user.user_roles[0].role
            if r:
                role_name = r.name
                role_code = r.code

        return {
            "id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "email": user.email,
            "mobile": user.mobile,
            "status": user.status,
            "role": role_name,
            "role_code": role_code,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "updated_at": user.updated_at.isoformat() if user.updated_at else None,
            "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
        }

    def _log_audit(self, db: Session, acting_user_id: Optional[str], target_user_id: str, event_type: str, message: str, request_id: str) -> None:
        try:
            self.audit_repo.log_activity(
                db=db,
                event_type=event_type,
                status="SUCCESS",
                message=message,
                user_id=acting_user_id or target_user_id,
                request_id=request_id
            )
        except Exception as exc:
            logger.error(f"Failed to record user audit event: {exc}")

user_service = UserService()
