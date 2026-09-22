"""
CtrlBooks - Persistent Extracted Record Repository
----------------------------------------------------------------
Provides database persistence, upsert operations, querying, filtering, and summary statistics
for accounting records stored from Tally / BUSY extractions for external website API consumption.
"""

import json
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import Session
from shared.db.models.storage import ExtractedRecord
from shared.logging_config import get_logger

logger = get_logger("app.repositories.storage")

class ExtractedRecordRepository:
    def upsert_batch(
        self,
        db: Session,
        connector_id: str,
        company_identifier: str,
        entity_type: str,
        records: List[Dict[str, Any]],
        extracted_at: Optional[datetime] = None
    ) -> Tuple[int, int]:
        """
        Atomically upserts a batch of extracted records for a company and entity type.
        Returns tuple (inserted_count, updated_count).
        """
        if not records:
            return 0, 0

        ts = extracted_at or datetime.now(timezone.utc)
        entity = entity_type.strip().upper()
        inserted = 0
        updated = 0

        for r in records:
            ext_id = str(r.get("record_id") or r.get("external_id") or r.get("name") or r.get("account_name") or r.get("item_name") or f"rec_{inserted+updated+1}").strip()
            name = str(r.get("name") or r.get("account_name") or r.get("item_name") or r.get("voucher_number") or ext_id).strip()
            
            canonical_json = json.dumps(r.get("data") if "data" in r else r, default=str)
            mapped_json = json.dumps(r.get("mapped_data"), default=str) if r.get("mapped_data") else None

            existing = db.execute(
                select(ExtractedRecord).where(
                    and_(
                        ExtractedRecord.connector_id == connector_id,
                        ExtractedRecord.company_identifier == company_identifier,
                        ExtractedRecord.entity_type == entity,
                        ExtractedRecord.external_id == ext_id
                    )
                )
            ).scalar_one_or_none()

            if existing:
                existing.record_name = name
                existing.canonical_data_json = canonical_json
                existing.mapped_data_json = mapped_json
                existing.version += 1
                existing.is_active = True
                existing.extracted_at = ts
                updated += 1
            else:
                new_rec = ExtractedRecord(
                    connector_id=connector_id,
                    company_identifier=company_identifier,
                    entity_type=entity,
                    external_id=ext_id,
                    record_name=name,
                    canonical_data_json=canonical_json,
                    mapped_data_json=mapped_json,
                    version=1,
                    is_active=True,
                    extracted_at=ts
                )
                db.add(new_rec)
                inserted += 1

        db.flush()
        logger.info(f"Upserted {inserted} new, {updated} updated {entity} records for company '{company_identifier}'")
        return inserted, updated

    def query_records(
        self,
        db: Session,
        entity_type: Optional[str] = None,
        company_identifier: Optional[str] = None,
        connector_id: Optional[str] = None,
        search_query: Optional[str] = None,
        page: int = 1,
        page_size: int = 50
    ) -> Dict[str, Any]:
        """
        Query stored records with pagination, filtering, and search capability.
        """
        stmt = select(ExtractedRecord).where(ExtractedRecord.is_active == True)

        if connector_id:
            stmt = stmt.where(ExtractedRecord.connector_id == connector_id)
        if company_identifier:
            stmt = stmt.where(ExtractedRecord.company_identifier == company_identifier)
        if entity_type:
            stmt = stmt.where(ExtractedRecord.entity_type == entity_type.strip().upper())
        if search_query:
            pattern = f"%{search_query.strip()}%"
            stmt = stmt.where(
                or_(
                    ExtractedRecord.record_name.ilike(pattern),
                    ExtractedRecord.external_id.ilike(pattern),
                    ExtractedRecord.canonical_data_json.ilike(pattern)
                )
            )

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_count = db.execute(count_stmt).scalar() or 0

        clean_page = max(1, page)
        clean_page_size = min(500, max(1, page_size))
        offset = (clean_page - 1) * clean_page_size

        records = db.execute(
            stmt.order_by(ExtractedRecord.record_name.asc()).offset(offset).limit(clean_page_size)
        ).scalars().all()

        formatted_items = []
        for r in records:
            try:
                c_data = json.loads(r.canonical_data_json)
            except Exception:
                c_data = {}

            try:
                m_data = json.loads(r.mapped_data_json) if r.mapped_data_json else None
            except Exception:
                m_data = None

            formatted_items.append({
                "id": r.id,
                "connector_id": r.connector_id,
                "company_identifier": r.company_identifier,
                "entity_type": r.entity_type,
                "external_id": r.external_id,
                "record_name": r.record_name,
                "canonical_data": c_data,
                "mapped_data": m_data,
                "version": r.version,
                "extracted_at": r.extracted_at.isoformat() if r.extracted_at else None
            })

        total_pages = (total_count + clean_page_size - 1) // clean_page_size if total_count > 0 else 1

        return {
            "items": formatted_items,
            "total_count": total_count,
            "page": clean_page,
            "page_size": clean_page_size,
            "total_pages": total_pages
        }

    def get_by_id(self, db: Session, record_id: str) -> Optional[Dict[str, Any]]:
        r = db.execute(
            select(ExtractedRecord).where(ExtractedRecord.id == record_id)
        ).scalar_one_or_none()

        if not r:
            return None

        try:
            c_data = json.loads(r.canonical_data_json)
        except Exception:
            c_data = {}

        try:
            m_data = json.loads(r.mapped_data_json) if r.mapped_data_json else None
        except Exception:
            m_data = None

        return {
            "id": r.id,
            "connector_id": r.connector_id,
            "company_identifier": r.company_identifier,
            "entity_type": r.entity_type,
            "external_id": r.external_id,
            "record_name": r.record_name,
            "canonical_data": c_data,
            "mapped_data": m_data,
            "version": r.version,
            "extracted_at": r.extracted_at.isoformat() if r.extracted_at else None
        }

    def get_company_summaries(self, db: Session) -> List[Dict[str, Any]]:
        """Returns list of all companies with record breakdown by entity type."""
        stmt = select(
            ExtractedRecord.company_identifier,
            ExtractedRecord.connector_id,
            ExtractedRecord.entity_type,
            func.count(ExtractedRecord.id).label("record_count"),
            func.max(ExtractedRecord.extracted_at).label("last_extracted")
        ).where(ExtractedRecord.is_active == True).group_by(
            ExtractedRecord.company_identifier,
            ExtractedRecord.connector_id,
            ExtractedRecord.entity_type
        )

        rows = db.execute(stmt).all()
        companies_map = {}

        for row in rows:
            comp_name, conn_id, entity_type, cnt, last_ext = row
            if comp_name not in companies_map:
                companies_map[comp_name] = {
                    "company_name": comp_name,
                    "connector_id": conn_id,
                    "total_records": 0,
                    "entities": {},
                    "last_synced_at": None
                }
            
            companies_map[comp_name]["total_records"] += cnt
            companies_map[comp_name]["entities"][entity_type] = cnt
            
            if last_ext:
                iso_time = last_ext.isoformat()
                if not companies_map[comp_name]["last_synced_at"] or iso_time > companies_map[comp_name]["last_synced_at"]:
                    companies_map[comp_name]["last_synced_at"] = iso_time

        return list(companies_map.values())

    def get_dashboard_summary(self, db: Session) -> Dict[str, Any]:
        """Returns high-level statistics for external web dashboard widgets."""
        total_records = db.execute(
            select(func.count(ExtractedRecord.id)).where(ExtractedRecord.is_active == True)
        ).scalar() or 0

        companies_count = db.execute(
            select(func.count(func.distinct(ExtractedRecord.company_identifier))).where(ExtractedRecord.is_active == True)
        ).scalar() or 0

        ledgers_count = db.execute(
            select(func.count(ExtractedRecord.id)).where(
                and_(ExtractedRecord.is_active == True, ExtractedRecord.entity_type == "LEDGER")
            )
        ).scalar() or 0

        stock_items_count = db.execute(
            select(func.count(ExtractedRecord.id)).where(
                and_(ExtractedRecord.is_active == True, ExtractedRecord.entity_type == "STOCK_ITEM")
            )
        ).scalar() or 0

        vouchers_count = db.execute(
            select(func.count(ExtractedRecord.id)).where(
                and_(ExtractedRecord.is_active == True, ExtractedRecord.entity_type == "VOUCHER")
            )
        ).scalar() or 0

        last_extraction = db.execute(
            select(func.max(ExtractedRecord.extracted_at)).where(ExtractedRecord.is_active == True)
        ).scalar()

        return {
            "total_records": total_records,
            "total_companies": companies_count,
            "total_ledgers": ledgers_count,
            "total_stock_items": stock_items_count,
            "total_vouchers": vouchers_count,
            "last_synced_at": last_extraction.isoformat() if last_extraction else None
        }

extracted_record_repository = ExtractedRecordRepository()
