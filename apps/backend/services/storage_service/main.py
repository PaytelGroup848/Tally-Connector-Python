

from fastapi import FastAPI
from contextlib import asynccontextmanager
from typing import Optional
from datetime import datetime
from shared.config import get_settings
from shared.logging_config import setup_logging, get_logger
from shared.exceptions import register_exception_handlers
from shared.middleware import add_request_id_middleware
from shared.models import NormalizedRecord
from shared.db.mongo_client import get_mongo_db, get_collection, serialize_mongo_doc

setup_logging("storage_service")
logger = get_logger("app.storage_service")
settings = get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    get_mongo_db()
    yield

app = FastAPI(
    title="CtrlBooks Storage Service",
    description="Manages MongoDB Atlas persistence for canonical records from Tally and BUSY",
    lifespan=lifespan
)

add_request_id_middleware(app)
register_exception_handlers(app)

@app.get("/health")
async def health():
    return {"service": "storage_service", "status": "ok", "database": "mongodb"}

@app.post("/records")
async def upsert_record(record: NormalizedRecord):
    """Upsert a canonical record into MongoDB database."""
    col = get_collection("normalized_records")
    
    filter_query = {
        "source": record.source.value,
        "record_type": record.record_type.value,
        "external_id": record.external_id,
        "company_name": record.company_name,
    }
    
    doc_data = {
        "source": record.source.value,
        "record_type": record.record_type.value,
        "external_id": record.external_id,
        "company_name": record.company_name,
        "canonical": record.canonical,
        "fingerprint": record.fingerprint,
        "normalized_at": record.normalized_at.isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }
    
    col.update_one(filter_query, {"$set": doc_data}, upsert=True)
    
    rec_type = record.record_type.value.lower()
    if "voucher" in rec_type:
        get_collection("vouchers").update_one(
            {"voucher_number": record.external_id, "company_name": record.company_name},
            {"$set": {"data": record.canonical, "company_name": record.company_name, "updated_at": datetime.utcnow().isoformat()}},
            upsert=True
        )
    elif "ledger" in rec_type:
        canon = record.canonical if isinstance(record.canonical, dict) else {}
        get_collection("ledgers").update_one(
            {"name": record.external_id, "company_name": record.company_name},
            {"$set": {
                "tallyExternalId": str(canon.get("tallyExternalId") or canon.get("guid") or record.external_id),
                "name": str(canon.get("name") or record.external_id),
                "parent": str(canon.get("parent") or canon.get("group") or ""),
                "group": str(canon.get("group") or canon.get("parent") or ""),
                "ledgerType": str(canon.get("ledgerType") or "GENERAL"),
                "openingBalance": float(canon.get("openingBalance") if canon.get("openingBalance") is not None else (canon.get("opening_balance") or 0.0)),
                "closingBalance": float(canon.get("closingBalance") if canon.get("closingBalance") is not None else (canon.get("closing_balance") or 0.0)),
                "gstin": str(canon.get("gstin")) if canon.get("gstin") else None,
                "data": record.canonical,
                "company_name": record.company_name,
                "updated_at": datetime.utcnow().isoformat()
            }},
            upsert=True
        )
    elif "stock" in rec_type or "item" in rec_type:
        get_collection("stock_items").update_one(
            {"name": record.external_id, "company_name": record.company_name},
            {"$set": {"data": record.canonical, "company_name": record.company_name, "updated_at": datetime.utcnow().isoformat()}},
            upsert=True
        )
        
    logger.info(f"Upserted MongoDB record: {record.source.value}/{record.record_type.value}/{record.external_id} ({record.company_name})")
    return {"stored": True, "external_id": record.external_id, "source": record.source.value}

@app.get("/records")
async def list_records(company_name: Optional[str] = None, source: Optional[str] = None, record_type: Optional[str] = None):
    """Retrieve list of normalized stored records with optional filtering."""
    query = {}
    if company_name:
        query["company_name"] = company_name
    if source:
        query["source"] = source
    if record_type:
        query["record_type"] = record_type

    col = get_collection("normalized_records")
    docs = list(col.find(query).sort("normalized_at", -1).limit(500))
    return [serialize_mongo_doc(d) for d in docs]

@app.get("/stats")
async def storage_stats():
    """Returns database record counts grouped by source software."""
    col = get_collection("normalized_records")
    pipeline = [
        {"$group": {"_id": {"source": "$source", "record_type": "$record_type"}, "count": {"$sum": 1}}}
    ]
    cursor = col.aggregate(pipeline)
    return [{"source": doc["_id"]["source"], "record_type": doc["_id"]["record_type"], "count": doc["count"]} for doc in cursor]
