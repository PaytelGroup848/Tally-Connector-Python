 

from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, Query, Path
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from shared.db.session import get_db
from shared.db.models.user import User
from shared.auth.rbac import require_permission
from shared.auth.permissions import Permissions
from apps.backend.services.extraction_service import extraction_service

extraction_router = APIRouter(prefix="", tags=["Data Extraction Engine"])

class ExtractEntityRequestSchema(BaseModel):
    company_identifier: str = Field(..., description="Target company name or code context")
    entity_type: str = Field(..., description="Canonical entity type (e.g. LEDGER, STOCK_ITEM, VOUCHER)")
    filters: Optional[Dict[str, Any]] = Field(None, description="Optional entity-specific filters")
    page_size: int = Field(100, ge=1, le=500, description="Page size limit")
    cursor: Optional[str] = Field(None, description="Pagination cursor for next page")
    mapping_id: Optional[str] = Field(None, description="Optional Module 9 mapping definition ID for transformation preview")

class PreviewExtractionRequestSchema(BaseModel):
    company_identifier: str = Field(..., description="Target company name or code context")
    entity_type: str = Field(..., description="Canonical entity type")
    mapping_id: Optional[str] = Field(None, description="Optional Module 9 mapping definition ID")
    limit: int = Field(10, ge=1, le=50, description="Small preview limit")

@extraction_router.post(
    "/api/connectors/{connector_id}/extract",
    summary="Extract Source Data (Paginated)",
    description="Reads and normalizes accounting data from target source connector with optional Module 9 mapping preview. Zero target write."
)
def extract_entity_data(
    connector_id: str = Path(..., description="Data Connector UUID"),
    body: ExtractEntityRequestSchema = ...,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.DATA_EXTRACT))
):
    res = extraction_service.extract_entity(
        db=db,
        connector_id=connector_id,
        company_identifier=body.company_identifier,
        entity_type=body.entity_type,
        filters=body.filters,
        page_size=body.page_size,
        cursor=body.cursor,
        mapping_id=body.mapping_id,
        user_id=getattr(current_user, "id", None)
    )
    return res

@extraction_router.post(
    "/api/connectors/{connector_id}/extract/preview",
    summary="Preview Source Data Extraction (Safe Read-Only)",
    description="Executes a safe read-only preview extraction bounded by small limits (max 50) with zero target mutations."
)
def preview_extraction_data(
    connector_id: str = Path(..., description="Data Connector UUID"),
    body: PreviewExtractionRequestSchema = ...,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.DATA_EXTRACT_PREVIEW))
):
    res = extraction_service.preview_extraction(
        db=db,
        connector_id=connector_id,
        company_identifier=body.company_identifier,
        entity_type=body.entity_type,
        mapping_id=body.mapping_id,
        limit=body.limit,
        user_id=getattr(current_user, "id", None)
    )
    return res

@extraction_router.get(
    "/api/connectors/{connector_id}/extract/{entity_type}/{source_identifier}",
    summary="Get Single Source Record",
    description="Reads a single normalized source record by primary identifier."
)
def get_single_source_record(
    connector_id: str = Path(..., description="Data Connector UUID"),
    entity_type: str = Path(..., description="Canonical entity type"),
    source_identifier: str = Path(..., description="Primary source name or code"),
    company_identifier: str = Query(..., description="Target company name or code context"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.DATA_EXTRACT_SINGLE))
):
    res = extraction_service.get_single_record(
        db=db,
        connector_id=connector_id,
        company_identifier=company_identifier,
        entity_type=entity_type,
        source_identifier=source_identifier
    )
    return res

@extraction_router.get(
    "/api/extractions",
    summary="List Extraction Run History",
    description="Queries paginated extraction run execution history logs."
)
def list_extraction_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    connector_id: Optional[str] = Query(None),
    company_identifier: Optional[str] = Query(None),
    entity_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.DATA_EXTRACTION_HISTORY))
):
    res = extraction_service.list_history(
        db=db,
        page=page,
        page_size=page_size,
        connector_id=connector_id,
        company_identifier=company_identifier,
        entity_type=entity_type,
        status=status
    )
    return {
        "success": True,
        "data": res
    }

@extraction_router.get(
    "/api/extractions/{run_id}",
    summary="Get Extraction Run Details",
    description="Retrieves detailed diagnostic metrics and status of a specific extraction run."
)
def get_extraction_run_details(
    run_id: str = Path(..., description="DataExtractionRun UUID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission(Permissions.DATA_EXTRACTION_HISTORY))
):
    res = extraction_service.get_run_details(db, run_id)
    return {
        "success": True,
        "data": res
    }
