
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, Request, Query, Body
from sqlalchemy.orm import Session
from shared.db.session import get_db
from shared.db.models.user import User
from shared.auth.rbac import require_permission
from shared.auth.permissions import Permissions
from apps.backend.services.mapping_service import mapping_service
from shared.response import success_response

router = APIRouter(tags=["Data Mapping & Field Mapping Engine"])

@router.post("/api/mappings")
async def create_mapping_endpoint(
    request: Request,
    payload: Dict[str, Any] = Body(...),
    current_user: User = Depends(require_permission(Permissions.MAPPING_CREATE)),
    db: Session = Depends(get_db)
):
    """Creates a new mapping definition for a source/target scope and canonical entity type."""
    req_id = getattr(request.state, "request_id", "")
    data = mapping_service.create_mapping(
        db=db,
        payload=payload,
        acting_user_id=current_user.id,
        request_id=req_id
    )
    return success_response(data=data, message="Mapping definition created successfully", request_id=req_id)

@router.get("/api/mappings")
async def list_mappings_endpoint(
    request: Request,
    source_connector_id: Optional[str] = Query(None),
    target_connector_id: Optional[str] = Query(None),
    canonical_entity_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None, description="DRAFT, ACTIVE, INACTIVE, ARCHIVED"),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: User = Depends(require_permission(Permissions.MAPPING_VIEW)),
    db: Session = Depends(get_db)
):
    """Lists mapping definitions with optional filters and pagination."""
    req_id = getattr(request.state, "request_id", "")
    data = mapping_service.list_mappings(
        db=db,
        source_connector_id=source_connector_id,
        target_connector_id=target_connector_id,
        canonical_entity_type=canonical_entity_type,
        status=status,
        search=search,
        page=page,
        page_size=page_size
    )
    return success_response(data=data, message="Mapping definitions retrieved successfully", request_id=req_id)

@router.get("/api/mappings/{id}")
async def get_mapping_endpoint(
    id: str,
    request: Request,
    current_user: User = Depends(require_permission(Permissions.MAPPING_VIEW)),
    db: Session = Depends(get_db)
):
    """Gets details of a specific mapping definition including field rules and versions."""
    req_id = getattr(request.state, "request_id", "")
    data = mapping_service.get_mapping(db=db, mapping_id=id)
    return success_response(data=data, message="Mapping definition retrieved successfully", request_id=req_id)

@router.put("/api/mappings/{id}")
async def update_mapping_endpoint(
    id: str,
    request: Request,
    payload: Dict[str, Any] = Body(...),
    current_user: User = Depends(require_permission(Permissions.MAPPING_EDIT)),
    db: Session = Depends(get_db)
):
    """Updates mapping definition metadata. Increments version if active."""
    req_id = getattr(request.state, "request_id", "")
    data = mapping_service.update_mapping(
        db=db,
        mapping_id=id,
        payload=payload,
        acting_user_id=current_user.id,
        request_id=req_id
    )
    return success_response(data=data, message="Mapping definition updated successfully", request_id=req_id)

@router.delete("/api/mappings/{id}")
async def archive_mapping_endpoint(
    id: str,
    request: Request,
    current_user: User = Depends(require_permission(Permissions.MAPPING_DELETE)),
    db: Session = Depends(get_db)
):
    """Archives a mapping definition."""
    req_id = getattr(request.state, "request_id", "")
    data = mapping_service.archive_mapping(
        db=db,
        mapping_id=id,
        acting_user_id=current_user.id,
        request_id=req_id
    )
    return success_response(data=data, message="Mapping definition archived successfully", request_id=req_id)

@router.post("/api/mappings/{id}/fields")
async def add_field_rule_endpoint(
    id: str,
    request: Request,
    payload: Dict[str, Any] = Body(...),
    current_user: User = Depends(require_permission(Permissions.MAPPING_EDIT)),
    db: Session = Depends(get_db)
):
    """Adds a field transformation rule to a mapping definition."""
    req_id = getattr(request.state, "request_id", "")
    data = mapping_service.add_field_rule(
        db=db,
        mapping_id=id,
        payload=payload,
        acting_user_id=current_user.id,
        request_id=req_id
    )
    return success_response(data=data, message="Field mapping rule created successfully", request_id=req_id)

@router.get("/api/mappings/{id}/fields")
async def list_field_rules_endpoint(
    id: str,
    request: Request,
    current_user: User = Depends(require_permission(Permissions.MAPPING_VIEW)),
    db: Session = Depends(get_db)
):
    """Lists field transformation rules for a mapping definition."""
    req_id = getattr(request.state, "request_id", "")
    mapping = mapping_service.get_mapping(db=db, mapping_id=id)
    return success_response(data=mapping.get("field_rules", []), message="Field mapping rules retrieved successfully", request_id=req_id)

@router.put("/api/mappings/{id}/fields/{field_mapping_id}")
async def update_field_rule_endpoint(
    id: str,
    field_mapping_id: str,
    request: Request,
    payload: Dict[str, Any] = Body(...),
    current_user: User = Depends(require_permission(Permissions.MAPPING_EDIT)),
    db: Session = Depends(get_db)
):
    """Updates a specific field mapping rule."""
    req_id = getattr(request.state, "request_id", "")
    data = mapping_service.update_field_rule(
        db=db,
        mapping_id=id,
        field_rule_id=field_mapping_id,
        payload=payload,
        acting_user_id=current_user.id,
        request_id=req_id
    )
    return success_response(data=data, message="Field mapping rule updated successfully", request_id=req_id)

@router.delete("/api/mappings/{id}/fields/{field_mapping_id}")
async def delete_field_rule_endpoint(
    id: str,
    field_mapping_id: str,
    request: Request,
    current_user: User = Depends(require_permission(Permissions.MAPPING_EDIT)),
    db: Session = Depends(get_db)
):
    """Deletes a specific field mapping rule."""
    req_id = getattr(request.state, "request_id", "")
    data = mapping_service.delete_field_rule(
        db=db,
        mapping_id=id,
        field_rule_id=field_mapping_id,
        acting_user_id=current_user.id,
        request_id=req_id
    )
    return success_response(data=data, message="Field mapping rule deleted successfully", request_id=req_id)

@router.get("/api/mappings/{id}/field-suggestions")
async def get_field_suggestions_endpoint(
    id: str,
    request: Request,
    current_user: User = Depends(require_permission(Permissions.MAPPING_VIEW)),
    db: Session = Depends(get_db)
):
    """Generates automatic field matching suggestions based on canonical field definitions and aliases."""
    req_id = getattr(request.state, "request_id", "")
    data = mapping_service.get_field_suggestions(db=db, mapping_id=id)
    return success_response(data=data, message="Field mapping suggestions generated successfully", request_id=req_id)

@router.post("/api/mappings/{id}/validate")
async def validate_mapping_endpoint(
    id: str,
    request: Request,
    current_user: User = Depends(require_permission(Permissions.MAPPING_VALIDATE)),
    db: Session = Depends(get_db)
):
    """Executes validation against mapping rules, connector status, required fields, and type compatibility."""
    req_id = getattr(request.state, "request_id", "")
    data = mapping_service.validate_mapping(
        db=db,
        mapping_id=id,
        acting_user_id=current_user.id,
        request_id=req_id
    )
    return success_response(data=data, message="Mapping validation completed", request_id=req_id)

@router.post("/api/mappings/{id}/preview")
async def preview_mapping_endpoint(
    id: str,
    request: Request,
    payload: Dict[str, Any] = Body(...),
    current_user: User = Depends(require_permission(Permissions.MAPPING_PREVIEW)),
    db: Session = Depends(get_db)
):
    """Executes transformation preview on a sample source record. ZERO target writes."""
    req_id = getattr(request.state, "request_id", "")
    source_record = payload.get("source_record") or payload
    data = mapping_service.preview_mapping(
        db=db,
        mapping_id=id,
        source_record=source_record
    )
    return success_response(data=data, message="Mapping preview generated successfully", request_id=req_id)

@router.post("/api/mappings/{id}/activate")
async def activate_mapping_endpoint(
    id: str,
    request: Request,
    current_user: User = Depends(require_permission(Permissions.MAPPING_ACTIVATE)),
    db: Session = Depends(get_db)
):
    """Validates and activates a mapping definition."""
    req_id = getattr(request.state, "request_id", "")
    data = mapping_service.activate_mapping(
        db=db,
        mapping_id=id,
        acting_user_id=current_user.id,
        request_id=req_id
    )
    return success_response(data=data, message="Mapping definition activated successfully", request_id=req_id)

@router.post("/api/mappings/{id}/deactivate")
async def deactivate_mapping_endpoint(
    id: str,
    request: Request,
    current_user: User = Depends(require_permission(Permissions.MAPPING_DEACTIVATE)),
    db: Session = Depends(get_db)
):
    """Deactivates an active mapping definition."""
    req_id = getattr(request.state, "request_id", "")
    data = mapping_service.deactivate_mapping(
        db=db,
        mapping_id=id,
        acting_user_id=current_user.id,
        request_id=req_id
    )
    return success_response(data=data, message="Mapping definition deactivated successfully", request_id=req_id)
