

from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, Request, Query, Body
from sqlalchemy.orm import Session
from shared.db.session import get_db
from shared.db.models.user import User
from shared.auth.rbac import require_permission
from shared.auth.permissions import Permissions
from apps.backend.services.metadata_discovery_service import metadata_discovery_service
from shared.response import success_response

router = APIRouter(tags=["Data Discovery & Unified Source Metadata"])

@router.post("/api/connectors/{connector_id}/metadata/discover")
async def discover_metadata_endpoint(
    connector_id: str,
    request: Request,
    payload: Dict[str, Any] = Body(...),
    current_user: User = Depends(require_permission(Permissions.METADATA_DISCOVER)),
    db: Session = Depends(get_db)
):
    """Executes data discovery for requested canonical entity types over target connector."""
    req_id = getattr(request.state, "request_id", "")
    entity_types = payload.get("entity_types") or payload.get("entity_type")
    if isinstance(entity_types, str):
        entity_types = [entity_types]

    data = await metadata_discovery_service.discover_metadata(
        db=db,
        connector_id=connector_id,
        entity_types=entity_types,
        acting_user_id=current_user.id,
        request_id=req_id
    )
    return success_response(data=data, message="Data discovery completed successfully", request_id=req_id)

@router.post("/api/connectors/{connector_id}/metadata/refresh")
async def refresh_metadata_endpoint(
    connector_id: str,
    request: Request,
    payload: Dict[str, Any] = Body(default={}),
    current_user: User = Depends(require_permission(Permissions.METADATA_REFRESH)),
    db: Session = Depends(get_db)
):
    """Re-discovers and refreshes unified source metadata for target connector."""
    req_id = getattr(request.state, "request_id", "")
    entity_types = payload.get("entity_types") or payload.get("entity_type")
    if isinstance(entity_types, str):
        entity_types = [entity_types]

    data = await metadata_discovery_service.refresh_metadata(
        db=db,
        connector_id=connector_id,
        entity_types=entity_types,
        acting_user_id=current_user.id,
        request_id=req_id
    )
    return success_response(data=data, message="Source metadata refreshed successfully", request_id=req_id)

@router.get("/api/connectors/{connector_id}/metadata")
async def list_connector_metadata_endpoint(
    connector_id: str,
    request: Request,
    entity_type: Optional[str] = Query(None, description="Filter by canonical entity type (LEDGER, STOCK_ITEM, VOUCHER_TYPE, etc.)"),
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None, description="ACTIVE or STALE"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: User = Depends(require_permission(Permissions.METADATA_VIEW)),
    db: Session = Depends(get_db)
):
    """Lists unified source metadata records for a connector with pagination and filters."""
    req_id = getattr(request.state, "request_id", "")
    data = metadata_discovery_service.get_metadata_records(
        db=db,
        connector_id=connector_id,
        canonical_entity_type=entity_type,
        search=search,
        status=status,
        page=page,
        page_size=page_size
    )
    return success_response(data=data, message="Connector metadata retrieved successfully", request_id=req_id)

@router.get("/api/connectors/{connector_id}/metadata/{metadata_id}")
async def get_metadata_detail_endpoint(
    connector_id: str,
    metadata_id: str,
    request: Request,
    current_user: User = Depends(require_permission(Permissions.METADATA_VIEW)),
    db: Session = Depends(get_db)
):
    """Returns single unified metadata record detail."""
    req_id = getattr(request.state, "request_id", "")
    data = metadata_discovery_service.get_metadata_by_id(db=db, metadata_id=metadata_id)
    return success_response(data=data, message="Metadata record retrieved successfully", request_id=req_id)

@router.get("/api/metadata/search")
async def search_metadata_endpoint(
    request: Request,
    query: str = Query(..., min_length=1),
    connector_id: Optional[str] = Query(None),
    company_identifier: Optional[str] = Query(None),
    entity_type: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: User = Depends(require_permission(Permissions.METADATA_SEARCH)),
    db: Session = Depends(get_db)
):
    """Global search across unified source metadata."""
    req_id = getattr(request.state, "request_id", "")
    data = metadata_discovery_service.search_metadata(
        db=db,
        query_str=query,
        connector_id=connector_id,
        company_identifier=company_identifier,
        canonical_entity_type=entity_type,
        page=page,
        page_size=page_size
    )
    return success_response(data=data, message="Metadata search completed successfully", request_id=req_id)
