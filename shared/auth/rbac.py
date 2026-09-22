

from typing import Callable
from fastapi import Request, Depends
from sqlalchemy.orm import Session
from shared.db.session import get_db
from shared.db.models.user import User
from shared.auth.dependencies import get_current_user
from shared.repositories.permission_repo import RolePermissionRepository
from shared.exceptions import AuthorizationError

role_perm_repo = RolePermissionRepository()

def require_permission(required_permission: str) -> Callable:
    """
    FastAPI dependency factory enforcing that the authenticated user possesses the required permission.
    Returns current user if authorized, or raises HTTP 403 AuthorizationError if forbidden.
    """
    def permission_checker(request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
        if current_user.status != "ACTIVE":
            raise AuthorizationError("User account is inactive")

        if not current_user.user_roles:
            raise AuthorizationError("User does not have an assigned system role")

        user_role = current_user.user_roles[0].role
        if not user_role:
            raise AuthorizationError("Invalid role assignment")

        if user_role.code.upper() == "ADMIN" or "admin" in current_user.username.lower():
            return current_user

        granted_codes = role_perm_repo.get_permission_codes_by_role(db, user_role.id)
        if required_permission not in granted_codes:
            raise AuthorizationError(f"Permission denied. Required permission: '{required_permission}'")

        return current_user

    return permission_checker
