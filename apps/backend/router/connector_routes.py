

from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, Request, Query, Body
from sqlalchemy.orm import Session
from shared.db.session import get_db
from shared.db.models.user import User
from shared.auth.rbac import require_permission
from shared.auth.permissions import Permissions
from shared.schemas.connector_schemas import CreateConnectorRequest, UpdateConnectorRequest
from apps.backend.services.connector_service import connector_service
from apps.backend.services.tally_service import tally_service
from apps.backend.adapters.registry import connector_registry
from shared.repositories.connector_repo import ConnectorRepository
from shared.response import success_response

router = APIRouter(prefix="/api/connectors", tags=["Connector Management & Tally Integration"])
connector_repo = ConnectorRepository()

@router.get("")
async def list_connectors_endpoint(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    connector_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    is_active: Optional[bool] = Query(None),
    current_user: User = Depends(require_permission(Permissions.CONNECTORS_VIEW)),
    db: Session = Depends(get_db)
):
    """List connectors with pagination, search, connector_type filter, and status filter."""
    req_id = getattr(request.state, "request_id", "")
    data = connector_service.list_connectors(
        db=db,
        page=page,
        page_size=page_size,
        search=search,
        connector_type=connector_type,
        status=status,
        is_active=is_active
    )
    return success_response(data=data, message="Connectors retrieved successfully", request_id=req_id)

@router.get("/{connector_id}")
async def get_connector_endpoint(
    connector_id: str,
    request: Request,
    current_user: User = Depends(require_permission(Permissions.CONNECTORS_VIEW)),
    db: Session = Depends(get_db)
):
    """Get single connector details (sensitive secrets masked)."""
    req_id = getattr(request.state, "request_id", "")
    data = connector_service.get_connector_by_id(db=db, connector_id=connector_id)
    return success_response(data=data, message="Connector retrieved successfully", request_id=req_id)

@router.get("/{connector_id}/health")
async def get_connector_health_endpoint(
    connector_id: str,
    request: Request,
    current_user: User = Depends(require_permission(Permissions.CONNECTORS_VIEW)),
    db: Session = Depends(get_db)
):
    """Executes real lightweight health check against connector software/port/path."""
    req_id = getattr(request.state, "request_id", "")
    connector = connector_repo.get_by_id_or_raise(db, connector_id)
    adapter = connector_registry.get_adapter(connector.connector_type)
    raw_config = connector_repo.get_configuration(connector, mask_secrets=False)

    health_data = adapter.get_health(raw_config)
    return success_response(data=health_data, message="Connector health check completed", request_id=req_id)

@router.post("")
async def create_connector_endpoint(
    request: Request,
    body: CreateConnectorRequest,
    current_user: User = Depends(require_permission(Permissions.CONNECTORS_CREATE)),
    db: Session = Depends(get_db)
):
    """Create a new connector with configuration validation via registered adapter."""
    req_id = getattr(request.state, "request_id", "")
    data = connector_service.create_connector(
        db=db,
        name=body.name,
        connector_type=body.connector_type,
        configuration=body.configuration,
        description=body.description,
        acting_user_id=current_user.id,
        request_id=req_id
    )
    return success_response(data=data, message="Connector created successfully", request_id=req_id)

@router.put("/{connector_id}")
async def update_connector_endpoint(
    connector_id: str,
    request: Request,
    body: UpdateConnectorRequest,
    current_user: User = Depends(require_permission(Permissions.CONNECTORS_UPDATE)),
    db: Session = Depends(get_db)
):
    """Update connector details or configuration (resets connection_status if config changes)."""
    req_id = getattr(request.state, "request_id", "")
    data = connector_service.update_connector(
        db=db,
        connector_id=connector_id,
        name=body.name,
        description=body.description,
        configuration=body.configuration,
        is_active=body.is_active,
        acting_user_id=current_user.id,
        request_id=req_id
    )
    return success_response(data=data, message="Connector updated successfully", request_id=req_id)

@router.post("/{connector_id}/activate")
async def activate_connector_endpoint(
    connector_id: str,
    request: Request,
    current_user: User = Depends(require_permission(Permissions.CONNECTORS_ACTIVATE)),
    db: Session = Depends(get_db)
):
    """Activate data connector pipeline."""
    req_id = getattr(request.state, "request_id", "")
    data = connector_service.set_connector_activation(db=db, connector_id=connector_id, active=True, acting_user_id=current_user.id, request_id=req_id)
    return success_response(data=data, message="Connector activated successfully", request_id=req_id)

@router.post("/{connector_id}/deactivate")
async def deactivate_connector_endpoint(
    connector_id: str,
    request: Request,
    current_user: User = Depends(require_permission(Permissions.CONNECTORS_DEACTIVATE)),
    db: Session = Depends(get_db)
):
    """Deactivate data connector pipeline."""
    req_id = getattr(request.state, "request_id", "")
    data = connector_service.set_connector_activation(db=db, connector_id=connector_id, active=False, acting_user_id=current_user.id, request_id=req_id)
    return success_response(data=data, message="Connector deactivated successfully", request_id=req_id)

@router.post("/{connector_id}/test")
async def test_connector_endpoint(
    connector_id: str,
    request: Request,
    current_user: User = Depends(require_permission(Permissions.CONNECTORS_TEST)),
    db: Session = Depends(get_db)
):
    """Execute truthful connection test against target connector software/port/path."""
    req_id = getattr(request.state, "request_id", "")
    data = connector_service.test_connector_connection(db=db, connector_id=connector_id, acting_user_id=current_user.id, request_id=req_id)
    return success_response(data=data, message="Connection test completed", request_id=req_id)

@router.delete("/{connector_id}")
async def delete_connector_endpoint(
    connector_id: str,
    request: Request,
    current_user: User = Depends(require_permission(Permissions.CONNECTORS_DELETE)),
    db: Session = Depends(get_db)
):
    """Soft delete connector pipeline."""
    req_id = getattr(request.state, "request_id", "")
    connector_service.delete_connector(db=db, connector_id=connector_id, acting_user_id=current_user.id, request_id=req_id)
    return success_response(data={"deleted": True}, message="Connector deleted successfully", request_id=req_id)

@router.get("/{connector_id}/tally/companies")
async def get_tally_companies_endpoint(
    connector_id: str,
    request: Request,
    current_user: User = Depends(require_permission(Permissions.TALLY_VIEW_COMPANIES)),
    db: Session = Depends(get_db)
):
    """Discover list of open companies from target running Tally Prime instance."""
    req_id = getattr(request.state, "request_id", "")
    companies = await tally_service.get_tally_companies(db=db, connector_id=connector_id, acting_user_id=current_user.id, request_id=req_id)
    return success_response(data={"connector_id": connector_id, "companies": companies}, message="Tally open companies discovered successfully", request_id=req_id)

@router.post("/{connector_id}/tally/company")
async def select_tally_company_endpoint(
    connector_id: str,
    request: Request,
    payload: Dict[str, Any] = Body(...),
    current_user: User = Depends(require_permission(Permissions.TALLY_SELECT_COMPANY)),
    db: Session = Depends(get_db)
):
    """Re-validates selected company_name against real Tally response and binds company to connector configuration."""
    req_id = getattr(request.state, "request_id", "")
    company_name = payload.get("company_name", "")
    data = await tally_service.select_tally_company(db=db, connector_id=connector_id, company_name=company_name, acting_user_id=current_user.id, request_id=req_id)
    return success_response(data=data, message="Tally target company selected and validated successfully", request_id=req_id)

@router.get("/{connector_id}/tally/metadata")
async def get_tally_metadata_endpoint(
    connector_id: str,
    request: Request,
    type: str = Query("ledgers", description="Metadata collection type (companies, groups, ledgers, voucher_types, cost_centres, godowns, stock_groups, stock_categories, units)"),
    current_user: User = Depends(require_permission(Permissions.TALLY_VIEW_METADATA)),
    db: Session = Depends(get_db)
):
    """Discover metadata (Ledgers, Groups, VoucherTypes) from Tally instance for allowed metadata type."""
    req_id = getattr(request.state, "request_id", "")
    data = await tally_service.get_tally_metadata(db=db, connector_id=connector_id, metadata_type=type, acting_user_id=current_user.id, request_id=req_id)
    return success_response(data=data, message=f"Tally metadata '{type}' retrieved successfully", request_id=req_id)
