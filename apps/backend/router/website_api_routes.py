from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from shared.db.session import get_db
from shared.repositories.storage_repo import extracted_record_repository
from shared.repositories.connector_repo import ConnectorRepository
from apps.backend.services.extraction_service import ExtractionService
from shared.exceptions import ValidationError, NotFoundException
from shared.logging_config import get_logger

logger = get_logger("app.router.website_api")

website_api_router = APIRouter(prefix="/api/v1/website", tags=["External Website REST API"])

connector_repo = ConnectorRepository()
extraction_service = ExtractionService()

@website_api_router.get(
    "/companies",
    summary="List Synced Companies",
    description="Returns all companies registered and stored in database with record count summaries."
)
async def list_website_companies(db: Session = Depends(get_db)):
    try:
        companies = extracted_record_repository.get_company_summaries(db)
        return {
            "success": True,
            "data": {
                "total_companies": len(companies),
                "companies": companies
            }
        }
    except Exception as exc:
        logger.error(f"Error fetching website companies: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))

@website_api_router.get(
    "/dashboard/summary",
    summary="Get Website Dashboard Statistics",
    description="Returns high-level statistics (Total Companies, Total Ledgers, Total Stock Items, Total Vouchers, Last Sync) for web dashboard widgets."
)
async def get_website_dashboard_summary(db: Session = Depends(get_db)):
    try:
        summary = extracted_record_repository.get_dashboard_summary(db)
        return {
            "success": True,
            "data": summary
        }
    except Exception as exc:
        logger.error(f"Error fetching dashboard summary: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))

@website_api_router.get(
    "/entities/{entity_type}",
    summary="Query Stored Accounting Records",
    description="Returns paginated stored records (LEDGER, STOCK_ITEM, VOUCHER, ACCOUNT_GROUP) with search and company filter capability."
)
async def query_website_records(
    entity_type: str,
    company_name: Optional[str] = Query(None, description="Filter by Company Name"),
    search: Optional[str] = Query(None, description="Search query for name, external_id, or JSON data"),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(50, ge=1, le=500, description="Page size limit (1 to 500)"),
    db: Session = Depends(get_db)
):
    try:
        clean_entity = entity_type.strip().upper()
        res = extracted_record_repository.query_records(
            db=db,
            entity_type=clean_entity,
            company_identifier=company_name,
            search_query=search,
            page=page,
            page_size=page_size
        )
        return {
            "success": True,
            "data": res
        }
    except Exception as exc:
        logger.error(f"Error querying website records for entity '{entity_type}': {exc}")
        raise HTTPException(status_code=500, detail=str(exc))

@website_api_router.get(
    "/records/{record_id}",
    summary="Get Detailed Stored Record",
    description="Fetch single detailed accounting record by record ID."
)
async def get_website_record(record_id: str, db: Session = Depends(get_db)):
    try:
        rec = extracted_record_repository.get_by_id(db, record_id)
        if not rec:
            raise HTTPException(status_code=404, detail=f"ExtractedRecord with ID '{record_id}' not found.")
        return {
            "success": True,
            "data": rec
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Error fetching record '{record_id}': {exc}")
        raise HTTPException(status_code=500, detail=str(exc))

@website_api_router.post(
    "/sync-and-store",
    summary="Extract from Source & Store in DB for Website",
    description="Triggers live extraction from source accounting software (Tally / BUSY), persists records to database storage, and returns stored payload."
)
async def sync_and_store(payload: Dict[str, Any], db: Session = Depends(get_db)):
    try:
        connector_id = payload.get("connector_id")
        company_identifier = payload.get("company_identifier")
        entity_type = payload.get("entity_type", "LEDGER")
        filters = payload.get("filters")
        page_size = payload.get("page_size", 100)

        if not connector_id or not company_identifier:
            raise HTTPException(status_code=400, detail="'connector_id' and 'company_identifier' are required.")

        res = extraction_service.extract_entity(
            db=db,
            connector_id=connector_id,
            company_identifier=company_identifier,
            entity_type=entity_type,
            filters=filters,
            page_size=page_size,
            store_in_db=True
        )

        return res
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except NotFoundException as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.error(f"Error in sync-and-store endpoint: {exc}")
@website_api_router.post(
    "/sync/start",
    summary="Start Cloud Sync Session",
    description="Initiates a cloud sync session with the configured Cloud Server (/sync/start)."
)
async def website_sync_start(payload: Dict[str, Any]):
    from shared.auth.cloud_auth_service import cloud_auth_service
    company_name = payload.get("companyName") or payload.get("company_name") or ""
    company_guid = payload.get("companyGuid") or payload.get("company_guid") or ""
    sync_type = payload.get("syncType") or payload.get("sync_type") or "FULL"
    total_records = payload.get("totalRecords") or payload.get("total_records") or 0
    metadata = payload.get("metadata") or {}

    if not company_name:
        raise HTTPException(status_code=400, detail="'companyName' is required.")

    ok, msg, data = cloud_auth_service.sync_start(
        company_name=company_name,
        company_guid=company_guid,
        sync_type=sync_type,
        total_records=total_records,
        metadata=metadata
    )
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"success": True, "message": msg, "data": data}


@website_api_router.post(
    "/sync/batch",
    summary="Push Cloud Sync Batch",
    description="Pushes a chunk batch of extracted records to the Cloud Server (/sync/batch)."
)
async def website_sync_batch(payload: Dict[str, Any]):
    from shared.auth.cloud_auth_service import cloud_auth_service
    sync_id = payload.get("syncId") or payload.get("sync_id") or ""
    company_name = payload.get("companyName") or payload.get("company_name") or ""
    entity_type = payload.get("entityType") or payload.get("entity_type") or "LEDGERS"
    items = payload.get("data") or payload.get("items") or []
    batch_number = payload.get("batchNumber") or payload.get("batch_number") or 1
    is_last_batch = payload.get("isLastBatch") or payload.get("is_last_batch") or False

    if not sync_id or not company_name:
        raise HTTPException(status_code=400, detail="'syncId' and 'companyName' are required.")

    ok, msg, data = cloud_auth_service.sync_batch(
        sync_id=sync_id,
        company_name=company_name,
        entity_type=entity_type,
        items=items,
        batch_number=batch_number,
        is_last_batch=is_last_batch
    )
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"success": True, "message": msg, "data": data}


@website_api_router.post(
    "/sync/complete",
    summary="Complete Cloud Sync Session",
    description="Marks cloud sync session completed with the Cloud Server (/sync/complete)."
)
async def website_sync_complete(payload: Dict[str, Any]):

    from shared.auth.cloud_auth_service import cloud_auth_service
    sync_id = payload.get("syncId") or payload.get("sync_id") or ""
    company_name = payload.get("companyName") or payload.get("company_name") or ""
    status_str = payload.get("status", "COMPLETED")
    total_synced = payload.get("totalSynced") or payload.get("total_synced") or 0
    last_alter_id = payload.get("lastAlterId") or payload.get("last_alter_id") or 0
    summary = payload.get("summary") or {}

    if not sync_id or not company_name:
        raise HTTPException(status_code=400, detail="'syncId' and 'companyName' are required.")

    ok, msg, data = cloud_auth_service.sync_complete(
        sync_id=sync_id,
        company_name=company_name,
        status=status_str,
        total_synced=total_synced,
        last_alter_id=last_alter_id,
        summary=summary
    )
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"success": True, "message": msg, "data": data}

@website_api_router.get(
    "/commands",
    summary="Get Cloud Sync Commands",
    description="Fetches pending 2-way sync commands from the Cloud Server (/commands)."
)
async def website_sync_commands(sync_id: Optional[str] = Query(None, description="Optional Sync Session ID")):
    from shared.auth.cloud_auth_service import cloud_auth_service
    ok, msg, data = cloud_auth_service.get_pending_commands()
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"success": True, "message": msg, "data": {"commands": data}}


@website_api_router.post(
    "/commands/{command_id}/result",
    summary="Submit Cloud Sync Command Result",
    description="Submits the result of a command executed in Tally to the Cloud Server (/commands/:commandId/result)."
)
async def website_sync_command_result(
    command_id: str,
    payload: Dict[str, Any]
):
    from shared.auth.cloud_auth_service import cloud_auth_service
    status_str = payload.get("status", "DONE")
    result_data = payload.get("result") or {}
    err_msg = payload.get("errorMessage") or payload.get("error_message")

    ok, msg, data = cloud_auth_service.send_command_result(
        command_id=command_id,
        status=status_str,
        result=result_data,
        error_message=err_msg
    )
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"success": True, "message": msg, "data": data}


@website_api_router.get(
    "/config",
    summary="Get Website Configuration",
    description="Returns configuration settings for the website API and cloud flags."
)
async def get_website_config():
    try:
        from shared.auth.cloud_auth_service import cloud_auth_service
        ok, msg, remote_cfg = cloud_auth_service.get_remote_config()
        config = {
            "api_version": "1.0",
            "supported_entities": ["LEDGER", "STOCK_ITEM", "VOUCHER", "ACCOUNT_GROUP"],
            "max_page_size": 500,
            "default_page_size": 50,
            "sync_endpoints": {
                "start": "/api/v1/website/sync/start",
                "batch": "/api/v1/website/sync/batch",
                "complete": "/api/v1/website/sync/complete",
                "commands": "/api/v1/website/commands"
            },
            "remote": remote_cfg if ok else {}
        }
        return {
            "success": True,
            "data": config
        }
    except Exception as exc:
        logger.error(f"Error fetching website configuration: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@website_api_router.get(
    "/version",
    summary="Get Website API Version",
    description="Returns the current version of the website API."
)
async def get_website_version():
    try:
        from shared.auth.cloud_auth_service import cloud_auth_service
        ok, msg, ver_data = cloud_auth_service.get_connector_version()
        version_info = {
            "version": ver_data.get("latestVersion", "1.0.0") if ok else "1.0.0",
            "release_date": "2026-09-03",
            "downloadUrl": ver_data.get("downloadUrl") if ok else None,
            "description": "Website API for external access to accounting records and sync operations."
        }
        return {
            "success": True,
            "data": version_info
        }
    except Exception as exc:
        logger.error(f"Error fetching website API version: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


