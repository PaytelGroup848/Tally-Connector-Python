"""
CtrlBooks - Data Extraction Run Repository
-------------------------------------------------------
Data access layer for tracking data extraction run executions, status updates, and history queries.
"""

import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from shared.db.models.extraction import DataExtractionRun
from shared.repositories.base import BaseRepository

class ExtractionRunRepository(BaseRepository[DataExtractionRun]):
    def __init__(self):
        super().__init__(DataExtractionRun)

    def create_run(
        self,
        db: Session,
        connector_id: str,
        company_identifier: str,
        entity_type: str,
        filters: Optional[Dict[str, Any]] = None,
        mapping_id: Optional[str] = None,
        mode: str = "CANONICAL",
        created_by: Optional[str] = None
    ) -> DataExtractionRun:
        """Creates a new DataExtractionRun entry in RUNNING state."""
        run = DataExtractionRun(
            connector_id=connector_id,
            company_identifier=company_identifier,
            entity_type=entity_type.upper(),
            filters_json=json.dumps(filters) if filters else None,
            mapping_id=mapping_id,
            mode=mode.upper(),
            status="RUNNING",
            started_at=datetime.now(timezone.utc),
            created_by=created_by
        )
        return self.create(db, run)

    def update_run_status(
        self,
        db: Session,
        run_id: str,
        status: str,
        records_requested: int = 0,
        records_returned: int = 0,
        records_normalized: int = 0,
        records_failed: int = 0,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None
    ) -> DataExtractionRun:
        """Updates status, record count metrics, and completion timestamp of an extraction run."""
        run = self.get_by_id_or_raise(db, run_id)
        run.status = status.upper()
        run.completed_at = datetime.now(timezone.utc)
        run.records_requested = records_requested
        run.records_returned = records_returned
        run.records_normalized = records_normalized
        run.records_failed = records_failed
        run.error_code = error_code
        run.error_message = error_message
        db.flush()
        return run

    def find_active_run(
        self,
        db: Session,
        connector_id: str,
        company_identifier: str,
        entity_type: str
    ) -> Optional[DataExtractionRun]:
        """Checks if a matching extraction run is currently in RUNNING state for concurrency control."""
        stmt = select(DataExtractionRun).where(
            DataExtractionRun.connector_id == connector_id,
            func.lower(DataExtractionRun.company_identifier) == company_identifier.strip().lower(),
            func.upper(DataExtractionRun.entity_type) == entity_type.strip().upper(),
            DataExtractionRun.status == "RUNNING"
        )
        return db.scalar(stmt)

    def list_runs(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 20,
        connector_id: Optional[str] = None,
        company_identifier: Optional[str] = None,
        entity_type: Optional[str] = None,
        status: Optional[str] = None
    ) -> List[DataExtractionRun]:
        """Lists extraction run history with optional filters and pagination."""
        stmt = select(DataExtractionRun)
        if connector_id:
            stmt = stmt.where(DataExtractionRun.connector_id == connector_id)
        if company_identifier:
            stmt = stmt.where(func.lower(DataExtractionRun.company_identifier) == company_identifier.strip().lower())
        if entity_type:
            stmt = stmt.where(func.upper(DataExtractionRun.entity_type) == entity_type.strip().upper())
        if status:
            stmt = stmt.where(func.upper(DataExtractionRun.status) == status.strip().upper())

        stmt = stmt.order_by(DataExtractionRun.started_at.desc()).offset(skip).limit(limit)
        return list(db.scalars(stmt).all())

    def count_runs(
        self,
        db: Session,
        connector_id: Optional[str] = None,
        company_identifier: Optional[str] = None,
        entity_type: Optional[str] = None,
        status: Optional[str] = None
    ) -> int:
        """Counts matching extraction run entries."""
        stmt = select(func.count()).select_from(DataExtractionRun)
        if connector_id:
            stmt = stmt.where(DataExtractionRun.connector_id == connector_id)
        if company_identifier:
            stmt = stmt.where(func.lower(DataExtractionRun.company_identifier) == company_identifier.strip().lower())
        if entity_type:
            stmt = stmt.where(func.upper(DataExtractionRun.entity_type) == entity_type.strip().upper())
        if status:
            stmt = stmt.where(func.upper(DataExtractionRun.status) == status.strip().upper())

        return db.scalar(stmt) or 0

extraction_run_repository = ExtractionRunRepository()
