

from fastapi import FastAPI
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any
from datetime import datetime, timezone
import uuid

from shared.config import get_settings
from shared.logging_config import setup_logging, get_logger
from shared.exceptions import register_exception_handlers, NotFoundException
from shared.middleware import add_request_id_middleware
from shared.models import CompanyCreate
from shared.db.mongo_client import get_mongo_db, get_collection, serialize_mongo_doc

setup_logging("company_service")
logger = get_logger("app.company_service")
settings = get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    get_mongo_db()
    yield

app = FastAPI(
    title="CtrlBooks Company Service",
    description="Registers and manages Tally companies in MongoDB Atlas",
    lifespan=lifespan
)

add_request_id_middleware(app)
register_exception_handlers(app)

@app.get("/health")
async def health():
    return {"service": "company_service", "status": "ok", "database": "mongodb"}

@app.post("/companies")
async def create_company(data: CompanyCreate):
    """Registers a new Tally company in MongoDB."""
    col = get_collection("companies")
    created = datetime.now(timezone.utc)
    cid_str = str(uuid.uuid4())
    
    doc = {
        "id": cid_str,
        "source": data.source.value,
        "source_type": data.source.value.upper(),
        "name": data.name,
        "company_name": data.name,
        "data_path": data.data_path,
        "host": data.host,
        "port": data.port,
        "is_sync_enabled": True,
        "status": "CONNECTED",
        "created_at": created.isoformat(),
        "updated_at": created.isoformat(),
    }
    
    existing = col.find_one({"name": data.name, "source_type": data.source.value.upper()})
    if not existing:
        col.insert_one(doc)
    else:
        cid_str = str(existing.get("id", existing.get("_id")))
        col.update_one({"_id": existing["_id"]}, {"$set": doc})

    logger.info(f"Registered new company '{data.name}' ({data.source.value.upper()}) in MongoDB Atlas.")
    return {
        "id": cid_str,
        "name": data.name,
        "company_name": data.name,
        "source": data.source.value,
        "data_path": data.data_path,
        "host": data.host,
        "port": data.port,
        "created_at": created.isoformat()
    }

@app.get("/companies")
async def list_companies(source: Optional[str] = None, organization_id: Optional[str] = None):
    """Lists registered companies from MongoDB Atlas optionally filtered by organization_id."""
    col = get_collection("companies")
    query: Dict[str, Any] = {}
    if source:
        query["$or"] = [{"source": source.lower()}, {"source_type": source.upper()}]
    if organization_id:
        try:
            from bson import ObjectId
            org_match = [
                {"organizationId": ObjectId(str(organization_id))},
                {"organizationId": str(organization_id)},
                {"organization_id": str(organization_id)}
            ]
        except Exception:
            org_match = [
                {"organizationId": str(organization_id)},
                {"organization_id": str(organization_id)}
            ]
        if "$or" in query:
            query = {"$and": [{"$or": query["$or"]}, {"$or": org_match}]}
        else:
            query["$or"] = org_match
        
    docs = list(col.find(query).sort("created_at", -1))
    return [serialize_mongo_doc(d) for d in docs]

@app.delete("/companies/{company_id}")
async def delete_company(company_id: str):
    """Deletes a registered company by ID or Name from MongoDB."""
    col = get_collection("companies")
    res = col.delete_many({
        "$or": [
            {"id": company_id},
            {"name": company_id},
            {"company_name": company_id}
        ]
    })
    if res.deleted_count == 0:
        raise NotFoundException(f"Company '{company_id}' not found")
    logger.info(f"Deleted company '{company_id}' from MongoDB Atlas.")
    return {"deleted": True, "id": company_id}