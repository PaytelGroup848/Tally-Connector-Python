
from typing import Optional, List
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from shared.db.session import get_db
from shared.db.models.user import User
from shared.auth.rbac import require_permission
from shared.auth.permissions import Permissions
from apps.backend.services.role_service import role_service
from shared.response import success_response

router = APIRouter(prefix="/api/roles", tags=["Role & Permission Management"])
permission_router = APIRouter(prefix="/api/permissions", tags=["Permissions"])

class CreateRoleRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100, description="Display name for custom role")
    code: str = Field(..., min_length=2, max_length=50, description="Unique machine-readable role code")
    description: Optional[str] = Field(default=None, description="Optional role description")
    permissions: Optional[List[str]] = Field(default_factory=list, description="Assigned permission code strings")

class UpdateRoleRequest(BaseModel):
    name: Optional[str] = Field(default=None, description="Updated role display name")
    description: Optional[str] = Field(default=None, description="Updated role description")
    permissions: Optional[List[str]] = Field(default=None, description="Updated list of permission code strings")

@router.get("")
async def list_roles_endpoint(
    request: Request,
    current_user: User = Depends(require_permission(Permissions.ROLES_VIEW)),
    db: Session = Depends(get_db)
):
    """List all system and custom roles with assigned permissions."""
    req_id = getattr(request.state, "request_id", "")
    roles = role_service.list_roles(db=db)
    return success_response(data=roles, message="Roles retrieved successfully", request_id=req_id)

@router.get("/{role_id}")
async def get_role_endpoint(
    role_id: str,
    request: Request,
    current_user: User = Depends(require_permission(Permissions.ROLES_VIEW)),
    db: Session = Depends(get_db)
):
    """Get single role details and permission assignments."""
    req_id = getattr(request.state, "request_id", "")
    data = role_service.get_role_by_id(db=db, role_id=role_id)
    return success_response(data=data, message="Role retrieved successfully", request_id=req_id)

@router.post("")
async def create_role_endpoint(
    request: Request,
    body: CreateRoleRequest,
    current_user: User = Depends(require_permission(Permissions.ROLES_CREATE)),
    db: Session = Depends(get_db)
):
    """Create a new custom role with assigned permission codes."""
    req_id = getattr(request.state, "request_id", "")
    data = role_service.create_role(
        db=db,
        name=body.name,
        code=body.code,
        description=body.description,
        permission_codes=body.permissions,
        acting_user_id=current_user.id,
        request_id=req_id
    )
    return success_response(data=data, message="Role created successfully", request_id=req_id)

@router.put("/{role_id}")
async def update_role_endpoint(
    role_id: str,
    request: Request,
    body: UpdateRoleRequest,
    current_user: User = Depends(require_permission(Permissions.ROLES_UPDATE)),
    db: Session = Depends(get_db)
):
    """Update role details or assigned permission codes."""
    req_id = getattr(request.state, "request_id", "")
    data = role_service.update_role(
        db=db,
        role_id=role_id,
        name=body.name,
        description=body.description,
        permission_codes=body.permissions,
        acting_user_id=current_user.id,
        request_id=req_id
    )
    return success_response(data=data, message="Role updated successfully", request_id=req_id)

@router.delete("/{role_id}")
async def delete_role_endpoint(
    role_id: str,
    request: Request,
    current_user: User = Depends(require_permission(Permissions.ROLES_DELETE)),
    db: Session = Depends(get_db)
):
    """Delete a custom role (system roles and assigned roles are protected)."""
    req_id = getattr(request.state, "request_id", "")
    role_service.delete_role(db=db, role_id=role_id, acting_user_id=current_user.id, request_id=req_id)
    return success_response(data={"deleted": True}, message="Role deleted successfully", request_id=req_id)

@permission_router.get("")
async def list_permissions_endpoint(
    request: Request,
    current_user: User = Depends(require_permission(Permissions.ROLES_VIEW)),
    db: Session = Depends(get_db)
):
    """List all available system permissions."""
    req_id = getattr(request.state, "request_id", "")
    perms = role_service.list_permissions(db=db)
    return success_response(data=perms, message="Permissions retrieved successfully", request_id=req_id)
