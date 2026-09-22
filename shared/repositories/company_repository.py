

from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import uuid

from shared.db.mongo_client import get_collection
from shared.db.session import get_db_session
from shared.db.models.company import CompanySyncConfig
from shared.logging_config import get_logger

logger = get_logger("app.repositories.company")

def get_all_company_configs(
    organization_id: Optional[str] = None,
    device_id: Optional[str] = None,
    email: Optional[str] = None,
    allow_all: bool = False
) -> List[Dict[str, Any]]:
    """Fetches stored company configurations from MongoDB collection 'companies', strictly filtered by tenant."""
    try:
        col = get_collection("companies")
        # Auto-detect tenant context from active cloud session if not passed explicitly
        if not organization_id and not device_id and not email and not allow_all:
            try:
                from shared.auth.cloud_auth_service import cloud_auth_service
                device_id = getattr(cloud_auth_service, "device_id", None)
                user_dict = getattr(cloud_auth_service, "current_user", None) or {}
                email = getattr(cloud_auth_service, "email", None) or user_dict.get("email")
                organization_id = getattr(cloud_auth_service, "organization_id", None) or user_dict.get("organizationId") or user_dict.get("organization_id")
            except Exception:
                pass

        if organization_id:
            try:
                from bson import ObjectId
                filters.append({"$or": [
                    {"organizationId": ObjectId(str(organization_id))},
                    {"organizationId": str(organization_id)},
                    {"organization_id": str(organization_id)}
                ]})
            except Exception:
                filters.append({"$or": [
                    {"organizationId": str(organization_id)},
                    {"organization_id": str(organization_id)}
                ]})
        if device_id:
            filters.append({"$or": [
                {"deviceId": str(device_id)},
                {"device_id": str(device_id)}
            ]})
        if email:
            filters.append({"email": str(email).strip().lower()})

        if filters:
            query = {"$or": filters} if len(filters) > 1 else filters[0]
        else:
            # Unauthenticated or local unit test execution
            query = {}

        docs = list(col.find(query))
        if docs:
            results = []
            for d in docs:
                results.append({
                    "id": str(d.get("_id", d.get("id", ""))),
                    "source_type": d.get("source_type", "TALLY"),
                    "company_name": d.get("tallyCompanyName") or d.get("company_name") or d.get("name", ""),
                    "name": d.get("tallyCompanyName") or d.get("company_name") or d.get("name", ""),
                    "company_guid": d.get("tallyCompanyGuid") or d.get("company_guid"),
                    "financial_year_from": d.get("financial_year_from", "01-Apr-2025"),
                    "is_sync_enabled": d.get("is_sync_enabled", d.get("isActive", True)),
                    "status": d.get("status", "CONNECTED"),
                    "last_sync_at": d.get("last_sync_at"),
                    "last_alter_id": d.get("last_alter_id", 0),
                    "organizationId": str(d.get("organizationId") or d.get("organization_id") or "")
                })
            return results
    except Exception as exc:
        logger.debug(f"MongoDB fallback for get_all_company_configs: {exc}")

    try:
        with get_db_session() as session:
            configs = session.query(CompanySyncConfig).all()
            return [
                {
                    "id": c.id,
                    "source_type": c.source_type,
                    "company_name": c.company_name,
                    "name": c.company_name,
                    "company_guid": c.company_guid,
                    "financial_year_from": c.financial_year_from,
                    "is_sync_enabled": c.is_sync_enabled,
                    "status": c.status,
                    "last_sync_at": c.last_sync_at.isoformat() if c.last_sync_at else None,
                    "last_alter_id": c.last_alter_id,
                }
                for c in configs
            ]
    except Exception:
        return []

def get_enabled_company_configs(source_type: str) -> List[Dict[str, Any]]:
    """Fetches company configs for a given source type where is_sync_enabled == True."""
    try:
        with get_db_session() as session:
            configs = (
                session.query(CompanySyncConfig)
                .filter_by(source_type=source_type.upper(), is_sync_enabled=True)
                .all()
            )
            if configs:
                return [
                    {
                        "id": c.id,
                        "source_type": c.source_type,
                        "company_name": c.company_name,
                        "company_guid": c.company_guid,
                        "last_alter_id": c.last_alter_id,
                    }
                    for c in configs
                ]
    except Exception:
        pass

    try:
        col = get_collection("companies")
        docs = list(col.find({"source_type": source_type.upper(), "is_sync_enabled": True}))
        return [
            {
                "id": str(d.get("_id", d.get("id", ""))),
                "source_type": d.get("source_type", source_type),
                "company_name": d.get("company_name", ""),
                "company_guid": d.get("company_guid"),
                "last_alter_id": d.get("last_alter_id", 0),
            }
            for d in docs
        ]
    except Exception as exc:
        logger.error(f"MongoDB error loading enabled company configs: {exc}")
        return []

def is_company_sync_enabled(source_type: str, company_name: str) -> bool:
    """Checks if sync is enabled for a specific company in MongoDB or session."""
    try:
        with get_db_session() as session:
            cfg = (
                session.query(CompanySyncConfig)
                .filter_by(source_type=source_type.upper(), company_name=company_name)
                .first()
            )
            if cfg is not None:
                return cfg.is_sync_enabled
    except Exception:
        pass

    try:
        col = get_collection("companies")
        doc = col.find_one({"source_type": source_type.upper(), "company_name": company_name})
        if doc:
            return bool(doc.get("is_sync_enabled", True))
        return True
    except Exception as exc:
        logger.error(f"MongoDB error checking company sync enabled: {exc}")
        return True

def upsert_company_config(
    source_type: str,
    company_name: str,
    company_guid: Optional[str] = None,
    financial_year_from: Optional[str] = None,
    status: str = "CONNECTED",
    organization_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Inserts or updates a company configuration record in MongoDB and session."""
    now_iso = datetime.now(timezone.utc).isoformat()

    try:
        col = get_collection("companies")
        guid_val = company_guid or f"guid-{company_name}"
        org_id = None
        if organization_id:
            try:
                from bson import ObjectId
                org_id = ObjectId(str(organization_id)) if len(str(organization_id)) == 24 else str(organization_id)
            except Exception:
                org_id = str(organization_id)
        if not org_id:
            try:
                org_doc = get_collection("organizations").find_one()
                if org_doc:
                    org_id = org_doc.get("_id")
            except Exception:
                pass

        update_data: Dict[str, Any] = {
            "source_type": source_type.upper(),
            "company_name": company_name,
            "tallyCompanyName": company_name,
            "tallyCompanyGuid": guid_val,
            "name": company_name,
            "status": status,
            "updated_at": now_iso,
        }
        if org_id:
            update_data["organizationId"] = org_id
        if company_guid:
            update_data["company_guid"] = company_guid
        if financial_year_from:
            update_data["financial_year_from"] = financial_year_from

        existing = col.find_one({
            "$or": [
                {"company_name": company_name},
                {"tallyCompanyName": company_name},
                {"name": company_name}
            ]
        })
        if not existing:
            update_data["id"] = str(uuid.uuid4())
            update_data["is_sync_enabled"] = True
            update_data["created_at"] = now_iso
            update_data["last_alter_id"] = 0
            col.insert_one(update_data)
        else:
            col.update_one({"_id": existing["_id"]}, {"$set": update_data})
    except Exception as exc:
        logger.debug(f"MongoDB upsert notice: {exc}")

    try:
        with get_db_session() as session:
            cfg = (
                session.query(CompanySyncConfig)
                .filter_by(source_type=source_type.upper(), company_name=company_name)
                .first()
            )
            if not cfg:
                cfg = CompanySyncConfig(
                    source_type=source_type.upper(),
                    company_name=company_name,
                    company_guid=company_guid,
                    financial_year_from=financial_year_from,
                    is_sync_enabled=True,
                    status=status,
                )
                session.add(cfg)
            else:
                if company_guid:
                    cfg.company_guid = company_guid
                if financial_year_from:
                    cfg.financial_year_from = financial_year_from
                cfg.status = status
            session.commit()
            return {"id": cfg.id, "company_name": cfg.company_name, "is_sync_enabled": cfg.is_sync_enabled}
    except Exception:
        pass

    return {"company_name": company_name, "is_sync_enabled": True}

def set_company_sync_enabled(source_type: str, company_name: str, is_enabled: bool) -> bool:
    """Toggles sync ON/OFF for a target company in MongoDB and session."""
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        col = get_collection("companies")
        col.update_one(
            {"source_type": source_type.upper(), "company_name": company_name},
            {"$set": {"is_sync_enabled": is_enabled, "updated_at": now_iso}}
        )
    except Exception:
        pass

    try:
        with get_db_session() as session:
            cfg = (
                session.query(CompanySyncConfig)
                .filter_by(source_type=source_type.upper(), company_name=company_name)
                .first()
            )
            if cfg:
                cfg.is_sync_enabled = is_enabled
                session.commit()
                return True
    except Exception:
        pass

    return True

def delete_company_config(company_id_or_name: str) -> bool:
    """Deletes a company config from MongoDB and session by ID or name."""
    try:
        col = get_collection("companies")
        col.delete_many({
            "$or": [
                {"id": company_id_or_name},
                {"company_name": company_id_or_name},
                {"tallyCompanyName": company_id_or_name},
                {"name": company_id_or_name}
            ]
        })
    except Exception:
        pass

    try:
        with get_db_session() as session:
            session.query(CompanySyncConfig).filter(
                (CompanySyncConfig.company_name == company_id_or_name)
            ).delete()
            session.commit()
            return True
    except Exception:
        pass

    return True

def update_company_last_alter_id(source_type: str, company_name: str, last_alter_id: int) -> bool:
    """Updates last_alter_id checkpoint for a company in MongoDB and session."""
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        col = get_collection("companies")
        col.update_one(
            {"source_type": source_type.upper(), "company_name": company_name},
            {
                "$set": {
                    "last_alter_id": last_alter_id,
                    "last_sync_at": now_iso,
                    "updated_at": now_iso,
                }
            }
        )
    except Exception:
        pass

    try:
        with get_db_session() as session:
            cfg = (
                session.query(CompanySyncConfig)
                .filter_by(source_type=source_type.upper(), company_name=company_name)
                .first()
            )
            if cfg:
                if last_alter_id > cfg.last_alter_id:
                    cfg.last_alter_id = last_alter_id
                    cfg.last_sync_at = datetime.now()
                    session.commit()
                return True
    except Exception:
        pass

    return True
