"""
CtrlBooks - Connector, DataSource & Destination Repositories
-------------------------------------------------------------------------
Data access layer for connectors, sources, destinations, and field mappings with secret protection.
"""

import json
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import select, func, or_
from shared.db.models.connector import Connector, DataSource, Destination, FieldMapping
from shared.repositories.base import BaseRepository
from shared.config import SENSITIVE_KEYS

def mask_config_dict(config_data: Dict[str, Any]) -> Dict[str, Any]:
    """Masks sensitive values in configuration dictionary before returning to API."""
    if not config_data:
        return {}
    masked = {}
    for key, val in config_data.items():
        if any(s.lower() in key.lower() for s in SENSITIVE_KEYS) and val is not None:
            masked[key] = "****"
        else:
            masked[key] = val
    return masked

class DataSourceRepository(BaseRepository[DataSource]):
    def __init__(self):
        super().__init__(DataSource)

    def create_source(self, db: Session, name: str, source_type: str, config: Dict[str, Any]) -> DataSource:
        ds = DataSource(
            name=name,
            source_type=source_type,
            configuration_json=json.dumps(config)
        )
        return self.create(db, ds)

    def get_configuration(self, ds: DataSource, mask_secrets: bool = True) -> Dict[str, Any]:
        if not ds.configuration_json:
            return {}
        try:
            raw = json.loads(ds.configuration_json)
            return mask_config_dict(raw) if mask_secrets else raw
        except Exception:
            return {}

class DestinationRepository(BaseRepository[Destination]):
    def __init__(self):
        super().__init__(Destination)

    def create_destination(self, db: Session, name: str, destination_type: str, config: Dict[str, Any]) -> Destination:
        dest = Destination(
            name=name,
            destination_type=destination_type,
            configuration_json=json.dumps(config)
        )
        return self.create(db, dest)

    def get_configuration(self, dest: Destination, mask_secrets: bool = True) -> Dict[str, Any]:
        if not dest.configuration_json:
            return {}
        try:
            raw = json.loads(dest.configuration_json)
            return mask_config_dict(raw) if mask_secrets else raw
        except Exception:
            return {}

class ConnectorRepository(BaseRepository[Connector]):
    def __init__(self):
        super().__init__(Connector)

    def get_by_name(self, db: Session, name: str) -> Optional[Connector]:
        """Fetch connector by name (trimmed, case-insensitive, excluding soft deleted)."""
        clean = name.strip().lower()
        stmt = select(Connector).where(
            func.lower(Connector.name) == clean,
            Connector.deleted_at.is_(None)
        )
        return db.scalar(stmt)

    def list_connectors(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 20,
        page: Optional[int] = None,
        page_size: Optional[int] = None,
        search: Optional[str] = None,
        connector_type: Optional[str] = None,
        status: Optional[str] = None,
        is_active: Optional[bool] = None
    ) -> List[Connector]:
        """List connectors with pagination, search, connector_type filter, status filter, and active filter."""
        if page is not None:
            p = max(1, page)
            psize = page_size if page_size is not None else limit
            skip = (p - 1) * psize
            limit = psize

        stmt = select(Connector).where(Connector.deleted_at.is_(None))

        if search:
            s_term = f"%{search.strip().lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(Connector.name).like(s_term),
                    func.lower(Connector.description).like(s_term)
                )
            )

        if connector_type:
            stmt = stmt.where(func.upper(Connector.connector_type) == connector_type.strip().upper())

        if status:
            stmt = stmt.where(
                or_(
                    func.upper(Connector.status) == status.strip().upper(),
                    func.upper(Connector.connection_status) == status.strip().upper()
                )
            )

        if is_active is not None:
            stmt = stmt.where(Connector.is_active == is_active)

        stmt = stmt.order_by(Connector.created_at.desc()).offset(skip).limit(limit)
        return list(db.scalars(stmt).all())

    def count_connectors(
        self,
        db: Session,
        search: Optional[str] = None,
        connector_type: Optional[str] = None,
        status: Optional[str] = None,
        is_active: Optional[bool] = None
    ) -> int:
        """Count matching non-deleted connectors."""
        stmt = select(func.count()).select_from(Connector).where(Connector.deleted_at.is_(None))

        if search:
            s_term = f"%{search.strip().lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(Connector.name).like(s_term),
                    func.lower(Connector.description).like(s_term)
                )
            )

        if connector_type:
            stmt = stmt.where(func.upper(Connector.connector_type) == connector_type.strip().upper())

        if status:
            stmt = stmt.where(
                or_(
                    func.upper(Connector.status) == status.strip().upper(),
                    func.upper(Connector.connection_status) == status.strip().upper()
                )
            )

        if is_active is not None:
            stmt = stmt.where(Connector.is_active == is_active)

        return db.scalar(stmt) or 0

    def get_configuration(self, connector: Connector, mask_secrets: bool = True) -> Dict[str, Any]:
        """Safely parse configuration JSON string and mask sensitive secrets."""
        if not connector.configuration_json:
            return {}
        try:
            raw = json.loads(connector.configuration_json)
            return mask_config_dict(raw) if mask_secrets else raw
        except Exception:
            return {}

class FieldMappingRepository(BaseRepository[FieldMapping]):
    def __init__(self):
        super().__init__(FieldMapping)

    def list_by_connector(self, db: Session, connector_id: str) -> List[FieldMapping]:
        stmt = select(FieldMapping).where(FieldMapping.connector_id == connector_id)
        return list(db.scalars(stmt).all())
