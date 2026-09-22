"""
CtrlBooks - SyncJobRepository, SyncErrorRepository & SyncCheckpointRepository
-----------------------------------------------------------------------------------------
Data access layer for sync execution monitoring, error logs, and incremental checkpoints.
"""

from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import select
from shared.db.models.sync import SyncJobV2, SyncError, SyncCheckpoint
from shared.repositories.base import BaseRepository

class SyncJobRepository(BaseRepository[SyncJobV2]):
    def __init__(self):
        super().__init__(SyncJobV2)

    def list_by_connector(self, db: Session, connector_id: str, limit: int = 50) -> List[SyncJobV2]:
        stmt = select(SyncJobV2).where(SyncJobV2.connector_id == connector_id).order_by(SyncJobV2.created_at.desc()).limit(limit)
        return list(db.scalars(stmt).all())

    def list_jobs(self, db: Session, limit: int = 50, connector_id: Optional[str] = None, page: int = 1, page_size: int = 50) -> List[SyncJobV2]:
        stmt = select(SyncJobV2)
        if connector_id:
            stmt = stmt.where(SyncJobV2.connector_id == connector_id)
        effective_limit = page_size if page_size > 0 else limit
        offset = (max(1, page) - 1) * effective_limit
        stmt = stmt.order_by(SyncJobV2.created_at.desc()).offset(offset).limit(effective_limit)
        return list(db.scalars(stmt).all())

class SyncErrorRepository(BaseRepository[SyncError]):
    def __init__(self):
        super().__init__(SyncError)

    def list_by_job(self, db: Session, job_id: str) -> List[SyncError]:
        stmt = select(SyncError).where(SyncError.job_id == job_id).order_by(SyncError.created_at.asc())
        return list(db.scalars(stmt).all())

class SyncCheckpointRepository(BaseRepository[SyncCheckpoint]):
    def __init__(self):
        super().__init__(SyncCheckpoint)

    def get_checkpoint(self, db: Session, connector_id: str, entity_name: str) -> Optional[SyncCheckpoint]:
        stmt = select(SyncCheckpoint).where(
            SyncCheckpoint.connector_id == connector_id,
            SyncCheckpoint.entity_name == entity_name
        )
        return db.scalar(stmt)

    def set_checkpoint(self, db: Session, connector_id: str, entity_name: str, checkpoint_value: str) -> SyncCheckpoint:
        cp = self.get_checkpoint(db, connector_id, entity_name)
        if cp:
            cp.checkpoint_value = checkpoint_value
            db.flush()
            return cp
        else:
            new_cp = SyncCheckpoint(
                connector_id=connector_id,
                entity_name=entity_name,
                checkpoint_value=checkpoint_value
            )
            return self.create(db, new_cp)
