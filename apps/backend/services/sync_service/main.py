

from fastapi import FastAPI, HTTPException
from contextlib import asynccontextmanager
import httpx, asyncio, uuid, json
from datetime import datetime, timezone
from shared.config import get_settings
from shared.logging_config import setup_logging, get_logger
from shared.exceptions import register_exception_handlers
from shared.middleware import add_request_id_middleware
from shared.models import SyncRequest, SyncJob, SourceType
from shared.db.mongo_client import get_collection
from shared.database import initialize_database

setup_logging("sync_service")
logger = get_logger("app.sync_service")
settings = get_settings()

URLS = {
    "connection": "http://127.0.0.1:8001",
    "tally": "http://127.0.0.1:8002",
    "normalization": "http://127.0.0.1:8004",
    "change": "http://127.0.0.1:8006",
    "storage": "http://127.0.0.1:8007",
    "audit": "http://127.0.0.1:8008"
}

jobs = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database()
    yield

app = FastAPI(
    title="CtrlBooks Sync Orchestrator Service",
    description="Orchestrates sync pipeline execution across microservices for Tally",
    lifespan=lifespan
)

add_request_id_middleware(app)
register_exception_handlers(app)

async def update_job_status(job_id: str, state: str, progress: int, message: str, stats: dict = None):
    job = jobs.get(job_id)
    if not job:
        return
    updated_stats = stats if stats is not None else job.stats
    now = datetime.now(timezone.utc)
    jobs[job_id] = job.model_copy(update={
        "state": state,
        "progress": progress,
        "message": message,
        "updated_at": now,
        "stats": updated_stats
    })
    try:
        col = get_collection("sync_jobs")
        col.update_one(
            {"job_id": job_id},
            {
                "$set": {
                    "state": state,
                    "progress": progress,
                    "message": message,
                    "stats": updated_stats,
                    "updated_at": now.isoformat()
                }
            },
            upsert=True
        )
    except Exception as exc:
        logger.warning(f"MongoDB sync job update notice: {exc}")

async def run_sync_pipeline(job_id: str, source: SourceType, company_name: str):
    """Executes the microservice pipeline for Tally company data."""
    try:
        logger.info(f"Starting sync job {job_id} for company '{company_name}' ({source.value.upper()})")
        await update_job_status(job_id, "syncing", 10, f"Checking connectivity for {source.value.upper()}")
        async with httpx.AsyncClient(timeout=10) as client:
            status_res = await client.get(f"{URLS['connection']}/status/{source.value}")
            status_res.json()

        await update_job_status(job_id, "syncing", 30, f"Extracting ledgers from {source.value.upper()} Adapter")
        adapter_service = URLS["tally"]
        async with httpx.AsyncClient(timeout=15) as client:
            records_res = await client.get(f"{adapter_service}/extract/ledgers?company_name={company_name}")
            raw_records = records_res.json()

        if not isinstance(raw_records, list):
            raw_records = []

        processed_count = 0
        created_count = 0
        updated_count = 0
        unchanged_count = 0
        enqueuable_payloads = []

        async with httpx.AsyncClient(timeout=15) as client:
            for idx, rec in enumerate(raw_records):
                norm_res = await client.post(f"{URLS['normalization']}/normalize", json=rec)
                normalized = norm_res.json()

                change_res = await client.post(f"{URLS['change']}/detect", json=normalized)
                change = change_res.json()

                evt_type = change.get("event_type", "created")
                if evt_type == "created":
                    created_count += 1
                elif evt_type == "updated":
                    updated_count += 1
                else:
                    unchanged_count += 1

                if evt_type in ("created", "updated"):
                    await client.post(f"{URLS['storage']}/records", json=normalized)
                    enqueuable_payloads.append(normalized)

                processed_count += 1
                pct = 60 + int((idx + 1) / max(len(raw_records), 1) * 30)
                await update_job_status(job_id, "syncing", pct, f"Processed {processed_count}/{len(raw_records)} records")

        if enqueuable_payloads:
            try:
                from shared.db.session import get_db_session
                from apps.backend.services.queue_service import queue_service
                with get_db_session() as db_session:
                    for payload in enqueuable_payloads:
                        queue_service.enqueue_payload(
                            db_session=db_session,
                            payload_type="MASTERS",
                            payload=payload,
                            company_identifier=company_name
                        )
                logger.info(f"Enqueued {len(enqueuable_payloads)} sync records to queue_service.")
            except Exception as e:
                logger.error(f"Failed to enqueue synced records: {e}")

        stats = {
            "total_extracted": len(raw_records),
            "created": created_count,
            "updated": updated_count,
            "unchanged": unchanged_count
        }
        await update_job_status(
            job_id, "completed", 100,
            f"Sync completed successfully for {company_name} ({source.value.upper()})",
            stats
        )
        logger.info(f"Sync job {job_id} completed successfully.")

    except Exception as exc:
        logger.error(f"Sync job {job_id} failed: {exc}", exc_info=True)
        await update_job_status(job_id, "failed", 0, f"Sync error: {str(exc)}")

@app.get("/health")
async def health():
    return {"service": "sync_service", "status": "ok"}

@app.post("/jobs")
async def create_job(request: SyncRequest):
    """Creates and starts a background sync job for Tally or BUSY."""
    job_id = uuid.uuid4().hex
    job = SyncJob(
        job_id=job_id,
        source=request.source,
        company_name=request.company_name,
        state="queued",
        progress=0,
        message="Job queued for processing"
    )
    jobs[job_id] = job
    try:
        col = get_collection("sync_jobs")
        doc = {
            "job_id": job.job_id,
            "source": job.source.value,
            "company_name": job.company_name,
            "state": job.state,
            "progress": job.progress,
            "message": job.message,
            "stats": job.stats,
            "created_at": job.created_at.isoformat(),
            "updated_at": job.updated_at.isoformat()
        }
        col.insert_one(doc)
    except Exception as exc:
        logger.warning(f"MongoDB sync job creation notice: {exc}")

    asyncio.create_task(run_sync_pipeline(job_id, request.source, request.company_name))
    return job.model_dump(mode="json")

@app.get("/jobs/{job_id}")
async def get_job(job_id: str):
    """Get status of a specific sync job."""
    if job_id in jobs:
        return jobs[job_id].model_dump(mode="json")
    
    col = get_collection("sync_jobs")
    row = col.find_one({"job_id": job_id})
    if not row:
        raise HTTPException(404, f"Sync job {job_id} not found")
    return serialize_mongo_doc(row)

@app.get("/jobs")
async def list_jobs():
    """List all recent sync jobs from MongoDB."""
    col = get_collection("sync_jobs")
    cursor = col.find().sort("_id", -1).limit(50)
    return [serialize_mongo_doc(r) for r in cursor]
