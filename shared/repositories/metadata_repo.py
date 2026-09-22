"""
CtrlBooks - Metadata & Discovery Run Repositories
--------------------------------------------------------------
Database repositories for persisting unified source metadata, batched upsert,
stale record reconciliation, search, and tracking discovery run execution history.
"""

import json
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import or_
from shared.db.models.metadata import UnifiedSourceMetadata, MetadataDiscoveryRun
from shared.exceptions import NotFoundException
from shared.logging_config import get_logger

logger = get_logger("app.repositories.metadata")

class MetadataRepository:
    def upsert_metadata_batch(
        self,
        db: Session,
        records: List[Dict[str, Any]]
    ) -> Tuple[int, int]:
        """
        Upserts a batch of normalized metadata records.
        Returns tuple (created_count, updated_count).
        """
        if not records:
            return 0, 0

        created_count = 0
        updated_count = 0

        for r in records:
            existing = db.query(UnifiedSourceMetadata).filter(
                UnifiedSourceMetadata.connector_id == r["connector_id"],
                UnifiedSourceMetadata.canonical_entity_type == r["canonical_entity_type"],
                UnifiedSourceMetadata.source_identifier == r["source_identifier"]
            ).first()

            if existing:
                existing.company_identifier = r["company_identifier"]
                existing.source_name = r["source_name"]
                existing.display_name = r["display_name"]
                existing.parent_source_identifier = r.get("parent_source_identifier")
                existing.parent_display_name = r.get("parent_display_name")
                existing.status = "ACTIVE"
                existing.source_metadata_json = r.get("source_metadata_json")
                existing.updated_at = datetime.now(timezone.utc)
                updated_count += 1
            else:
                new_meta = UnifiedSourceMetadata(
                    connector_id=r["connector_id"],
                    company_identifier=r["company_identifier"],
                    source_type=r["source_type"],
                    source_entity_type=r["source_entity_type"],
                    canonical_entity_type=r["canonical_entity_type"],
                    source_identifier=r["source_identifier"],
                    source_name=r["source_name"],
                    display_name=r["display_name"],
                    parent_source_identifier=r.get("parent_source_identifier"),
                    parent_display_name=r.get("parent_display_name"),
                    status="ACTIVE",
                    source_metadata_json=r.get("source_metadata_json"),
                    discovered_at=datetime.now(timezone.utc)
                )
                db.add(new_meta)
                created_count += 1

        db.commit()
        return created_count, updated_count

    def mark_stale_records(
        self,
        db: Session,
        connector_id: str,
        company_identifier: str,
        canonical_entity_type: str,
        current_source_ids: List[str]
    ) -> int:
        """
        Marks active metadata records not present in current_source_ids as STALE.
        Only executed after a successful full discovery run for that category.
        """
        query = db.query(UnifiedSourceMetadata).filter(
            UnifiedSourceMetadata.connector_id == connector_id,
            UnifiedSourceMetadata.company_identifier == company_identifier,
            UnifiedSourceMetadata.canonical_entity_type == canonical_entity_type,
            UnifiedSourceMetadata.status == "ACTIVE"
        )
        if current_source_ids:
            query = query.filter(UnifiedSourceMetadata.source_identifier.notin_(current_source_ids))

        stale_records = query.all()
        for r in stale_records:
            r.status = "STALE"
            r.updated_at = datetime.now(timezone.utc)

        db.commit()
        return len(stale_records)

    def list_metadata(
        self,
        db: Session,
        connector_id: str,
        canonical_entity_type: Optional[str] = None,
        search: Optional[str] = None,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 50
    ) -> Dict[str, Any]:
        """Paginated listing of unified metadata for a connector."""
        query = db.query(UnifiedSourceMetadata).filter(UnifiedSourceMetadata.connector_id == connector_id)

        if canonical_entity_type:
            query = query.filter(UnifiedSourceMetadata.canonical_entity_type == canonical_entity_type.upper())
        if status:
            query = query.filter(UnifiedSourceMetadata.status == status.upper())
        if search and search.strip():
            s = f"%{search.strip()}%"
            query = query.filter(
                or_(
                    UnifiedSourceMetadata.display_name.ilike(s),
                    UnifiedSourceMetadata.source_name.ilike(s),
                    UnifiedSourceMetadata.parent_display_name.ilike(s)
                )
            )

        total_count = query.count()
        offset = (page - 1) * page_size
        items = query.order_by(UnifiedSourceMetadata.display_name.asc()).offset(offset).limit(page_size).all()

        return {
            "items": [self._to_dict(i) for i in items],
            "total_count": total_count,
            "page": page,
            "page_size": page_size,
            "total_pages": (total_count + page_size - 1) // page_size if page_size > 0 else 1
        }

    def get_by_id_or_raise(self, db: Session, metadata_id: str) -> UnifiedSourceMetadata:
        meta = db.query(UnifiedSourceMetadata).filter(UnifiedSourceMetadata.id == metadata_id).first()
        if not meta:
            raise NotFoundException(f"Unified source metadata record '{metadata_id}' not found.")
        return meta

    def search_metadata(
        self,
        db: Session,
        query_str: str,
        connector_id: Optional[str] = None,
        company_identifier: Optional[str] = None,
        canonical_entity_type: Optional[str] = None,
        page: int = 1,
        page_size: int = 50
    ) -> Dict[str, Any]:
        """Unified search across connectors and company metadata."""
        q = db.query(UnifiedSourceMetadata)

        if connector_id:
            q = q.filter(UnifiedSourceMetadata.connector_id == connector_id)
        if company_identifier:
            q = q.filter(UnifiedSourceMetadata.company_identifier == company_identifier)
        if canonical_entity_type:
            q = q.filter(UnifiedSourceMetadata.canonical_entity_type == canonical_entity_type.upper())

        if query_str and query_str.strip():
            s = f"%{query_str.strip()}%"
            q = q.filter(
                or_(
                    UnifiedSourceMetadata.display_name.ilike(s),
                    UnifiedSourceMetadata.source_name.ilike(s),
                    UnifiedSourceMetadata.parent_display_name.ilike(s)
                )
            )

        total_count = q.count()
        offset = (page - 1) * page_size
        items = q.order_by(UnifiedSourceMetadata.display_name.asc()).offset(offset).limit(page_size).all()

        return {
            "items": [self._to_dict(i) for i in items],
            "total_count": total_count,
            "page": page,
            "page_size": page_size,
            "total_pages": (total_count + page_size - 1) // page_size if page_size > 0 else 1
        }

    def _to_dict(self, m: UnifiedSourceMetadata) -> Dict[str, Any]:
        extra = {}
        if m.source_metadata_json:
            try:
                extra = json.loads(m.source_metadata_json)
            except Exception:
                extra = {}

        return {
            "id": m.id,
            "connector_id": m.connector_id,
            "company_identifier": m.company_identifier,
            "source_type": m.source_type,
            "source_entity_type": m.source_entity_type,
            "canonical_entity_type": m.canonical_entity_type,
            "source_identifier": m.source_identifier,
            "source_name": m.source_name,
            "display_name": m.display_name,
            "parent_source_identifier": m.parent_source_identifier,
            "parent_display_name": m.parent_display_name,
            "status": m.status,
            "source_metadata": extra,
            "discovered_at": m.discovered_at.isoformat() if m.discovered_at else None,
            "updated_at": m.updated_at.isoformat() if m.updated_at else None
        }

class MetadataDiscoveryRunRepository:
    def create_run(
        self,
        db: Session,
        connector_id: str,
        company_identifier: str,
        requested_types: List[str]
    ) -> MetadataDiscoveryRun:
        run = MetadataDiscoveryRun(
            connector_id=connector_id,
            company_identifier=company_identifier,
            requested_entity_types_json=json.dumps(requested_types),
            status="RUNNING",
            started_at=datetime.now(timezone.utc)
        )
        db.add(run)
        db.commit()
        db.refresh(run)
        return run

    def complete_run(
        self,
        db: Session,
        run_id: str,
        status: str,
        discovered: int,
        created: int,
        updated: int,
        stale: int,
        failed: int,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None
    ) -> MetadataDiscoveryRun:
        run = db.query(MetadataDiscoveryRun).filter(MetadataDiscoveryRun.id == run_id).first()
        if run:
            run.status = status
            run.completed_at = datetime.now(timezone.utc)
            run.records_discovered = discovered
            run.records_created = created
            run.records_updated = updated
            run.records_marked_stale = stale
            run.records_failed = failed
            run.error_code = error_code
            run.error_message = error_message
            db.commit()
            db.refresh(run)
        return run
