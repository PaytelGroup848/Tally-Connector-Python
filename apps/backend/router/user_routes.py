

from typing import Optional
from fastapi import APIRouter, Depends, Request, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from shared.db.session import get_db
from shared.db.models.user import User
from shared.auth.rbac import require_permission
from shared.auth.permissions import Permissions
from apps.backend.services.user_service import user_service
from shared.response import success_response

router = APIRouter(prefix="/api/users", tags=["User Management"])

class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, description="Unique login username")
    full_name: str = Field(..., min_length=1, max_length=150, description="User full name")
    password: str = Field(..., min_length=6, max_length=255, description="Initial login password")
    role: str = Field(default="OPERATOR", description="Assigned role code (e.g. ADMIN, OPERATOR, VIEWER)")
    email: Optional[str] = Field(default=None, description="Optional email address")
    mobile: Optional[str] = Field(default=None, description="Optional mobile number")

class UpdateUserRequest(BaseModel):
    full_name: Optional[str] = Field(default=None, description="Updated full name")
    role: Optional[str] = Field(default=None, description="Updated role code")
    status: Optional[str] = Field(default=None, description="Updated status (ACTIVE, INACTIVE, LOCKED, DISABLED)")

class ResetPasswordRequest(BaseModel):
    new_password: str = Field(..., min_length=6, max_length=255, description="New secret password")

@router.get("")
async def list_users_endpoint(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    role: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    current_user: User = Depends(require_permission(Permissions.USERS_VIEW)),
    db: Session = Depends(get_db)
):
    """List paginated users with optional search, role, and status filtering."""
    req_id = getattr(request.state, "request_id", "")
    data = user_service.list_users(
        db=db,
        page=page,
        page_size=page_size,
        search=search,
        role_code=role,
        status=status
    )
    return success_response(data=data, message="Users retrieved successfully", request_id=req_id)

@router.get("/{user_id}")
async def get_user_endpoint(
    user_id: str,
    request: Request,
    current_user: User = Depends(require_permission(Permissions.USERS_VIEW)),
    db: Session = Depends(get_db)
):
    """Get single user profile by ID."""
    req_id = getattr(request.state, "request_id", "")
    data = user_service.get_user_by_id(db=db, user_id=user_id)
    return success_response(data=data, message="User retrieved successfully", request_id=req_id)

@router.post("")
async def create_user_endpoint(
    request: Request,
    body: CreateUserRequest,
    current_user: User = Depends(require_permission(Permissions.USERS_CREATE)),
    db: Session = Depends(get_db)
):
    """Create a new user account with hashed password and role assignment."""
    req_id = getattr(request.state, "request_id", "")
    data = user_service.create_user(
        db=db,
        username=body.username,
        full_name=body.full_name,
        password=body.password,
        role_code=body.role,
        email=body.email,
        mobile=body.mobile,
        acting_user_id=current_user.id,
        request_id=req_id
    )
    return success_response(data=data, message="User created successfully", request_id=req_id)

@router.put("/{user_id}")
async def update_user_endpoint(
    user_id: str,
    request: Request,
    body: UpdateUserRequest,
    current_user: User = Depends(require_permission(Permissions.USERS_UPDATE)),
    db: Session = Depends(get_db)
):
    """Update user full name, assigned role, or status."""
    req_id = getattr(request.state, "request_id", "")
    data = user_service.update_user(
        db=db,
        user_id=user_id,
        full_name=body.full_name,
        role_code=body.role,
        status=body.status,
        acting_user_id=current_user.id,
        request_id=req_id
    )
    return success_response(data=data, message="User updated successfully", request_id=req_id)

@router.post("/{user_id}/activate")
async def activate_user_endpoint(
    user_id: str,
    request: Request,
    current_user: User = Depends(require_permission(Permissions.USERS_UPDATE)),
    db: Session = Depends(get_db)
):
    """Activate user account."""
    req_id = getattr(request.state, "request_id", "")
    data = user_service.set_user_status(db=db, user_id=user_id, new_status="ACTIVE", acting_user_id=current_user.id, request_id=req_id)
    return success_response(data=data, message="User activated successfully", request_id=req_id)

@router.post("/{user_id}/deactivate")
async def deactivate_user_endpoint(
    user_id: str,
    request: Request,
    current_user: User = Depends(require_permission(Permissions.USERS_UPDATE)),
    db: Session = Depends(get_db)
):
    """Deactivate user account (with self-deactivation and last-admin guards)."""
    req_id = getattr(request.state, "request_id", "")
    data = user_service.set_user_status(db=db, user_id=user_id, new_status="INACTIVE", acting_user_id=current_user.id, request_id=req_id)
    return success_response(data=data, message="User deactivated successfully", request_id=req_id)

@router.post("/{user_id}/reset-password")
async def reset_password_endpoint(
    user_id: str,
    request: Request,
    body: ResetPasswordRequest,
    current_user: User = Depends(require_permission(Permissions.USERS_UPDATE)),
    db: Session = Depends(get_db)
):
    """Reset user password and invalidate active user sessions."""
    req_id = getattr(request.state, "request_id", "")
    data = user_service.reset_password(
        db=db,
        user_id=user_id,
        new_password=body.new_password,
        acting_user_id=current_user.id,
        request_id=req_id
    )
    return success_response(data=data, message="Password reset successfully", request_id=req_id)
