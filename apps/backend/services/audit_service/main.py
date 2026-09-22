

from fastapi import FastAPI
from contextlib import asynccontextmanager
from typing import Optional
from datetime import datetime, timezone
from shared.config import get_settings
from shared.logging_config import setup_logging, get_logger
from shared.exceptions import register_exception_handlers
from shared.middleware import add_request_id_middleware
from shared.models import AuditEvent
from shared.db.mongo_client import get_collection, serialize_mongo_doc
from shared.database import initialize_database

setup_logging("audit_service")
logger = get_logger("app.audit_service")
settings = get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database()
    yield

app = FastAPI(
    title="CtrlBooks Audit Service",
    description="Centralized audit logging and event tracking microservice",
    lifespan=lifespan
)

add_request_id_middleware(app)
register_exception_handlers(app)

@app.get("/health")
async def health():
    return {"service": "audit_service", "status": "ok"}

@app.post("/events")
async def log_event(event: AuditEvent):
    """Log an audit event to MongoDB Atlas."""
    try:
        col = get_collection("audit_events")
        doc = {
            "level": event.level,
            "service": event.service,
            "action": event.action,
            "message": event.message,
            "metadata": event.metadata,
            "created_at": event.created_at.isoformat() if hasattr(event.created_at, "isoformat") else str(event.created_at)
        }
        col.insert_one(doc)
    except Exception as exc:
        logger.warning(f"MongoDB audit log notice: {exc}")
    logger.info(f"Audit event logged from service '{event.service}': {event.action}")
    return {"logged": True}

@app.get("/events")
async def events(level: Optional[str] = None, service: Optional[str] = None, limit: int = 100):
    """Retrieve audit events from MongoDB with optional filtering by log level or service name."""
    query = {}
    if level:
        query["level"] = level
    if service:
        query["service"] = service

    col = get_collection("audit_events")
    cursor = col.find(query).sort("_id", -1).limit(limit)
    return [serialize_mongo_doc(doc) for doc in cursor]
