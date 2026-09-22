
from fastapi import FastAPI
from contextlib import asynccontextmanager
from shared.config import get_settings
from shared.logging_config import setup_logging, get_logger
from shared.exceptions import register_exception_handlers
from shared.middleware import add_request_id_middleware
from shared.models import NormalizedRecord, ChangeEvent
from shared.db.mongo_client import get_collection
from shared.database import initialize_database

setup_logging("change_detection_service")
logger = get_logger("app.change_detection_service")
settings = get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_database()
    yield

app = FastAPI(
    title="CtrlBooks Change Detection Service",
    description="Identifies created, updated, and unchanged records using fingerprint diffing",
    lifespan=lifespan
)

add_request_id_middleware(app)
register_exception_handlers(app)

@app.get("/health")
async def health():
    return {"service": "change_detection_service", "status": "ok"}

@app.post("/detect")
async def detect(record: NormalizedRecord):
    """
    Compares normalized record fingerprint with previously saved database state in MongoDB.
    Returns ChangeEvent object tagged with 'created', 'updated', or 'unchanged'.
    """
    rec_col = get_collection("normalized_records")
    evt_col = get_collection("change_events")

    query = {
        "source": record.source.value,
        "record_type": record.record_type.value,
        "external_id": record.external_id,
        "company_name": record.company_name
    }

    row = rec_col.find_one(query)

    if row is None:
        event_type = "created"
        previous = None
    elif row.get("fingerprint") != record.fingerprint:
        event_type = "updated"
        previous = row.get("fingerprint")
    else:
        event_type = "unchanged"
        previous = row.get("fingerprint")

    rec_col.update_one(
        query,
        {
            "$set": {
                "source": record.source.value,
                "record_type": record.record_type.value,
                "external_id": record.external_id,
                "company_name": record.company_name,
                "fingerprint": record.fingerprint,
                "updated_at": record.normalized_at.isoformat()
            }
        },
        upsert=True
    )

    evt_doc = {
        "event_type": event_type,
        "source": record.source.value,
        "record_type": record.record_type.value,
        "external_id": record.external_id,
        "fingerprint": record.fingerprint,
        "previous_fingerprint": previous,
        "created_at": record.normalized_at.isoformat()
    }
    evt_col.insert_one(evt_doc)

    event = ChangeEvent(
        event_type=event_type,
        source=record.source,
        record_type=record.record_type,
        external_id=record.external_id,
        fingerprint=record.fingerprint,
        previous_fingerprint=previous
    )
    return event.model_dump(mode="json")
