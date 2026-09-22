"""
CtrlBooks - Common Data Extraction Abstraction Contracts
----------------------------------------------------------------------
Defines standard data model contracts and abstract base classes for source extractors,
record normalizers, batch generators, and extraction result structures.
Must strictly stay under 150 lines of code.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Generator

@dataclass
class CanonicalDataRecord:
    """Standardized representation of a single extracted accounting record."""
    record_id: str
    connector_id: str
    company_identifier: str
    source_type: str
    source_entity_type: str
    canonical_entity_type: str
    source_identifier: str
    data: Dict[str, Any]
    source_metadata: Dict[str, Any] = field(default_factory=dict)
    extracted_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "record_id": self.record_id,
            "connector_id": self.connector_id,
            "company_identifier": self.company_identifier,
            "source_type": self.source_type,
            "source_entity_type": self.source_entity_type,
            "canonical_entity_type": self.canonical_entity_type,
            "source_identifier": self.source_identifier,
            "data": self.data,
            "source_metadata": self.source_metadata,
            "extracted_at": self.extracted_at.isoformat() if self.extracted_at else None
        }

class BaseRecordNormalizer(ABC):
    @abstractmethod
    def normalize(self, raw_record: Dict[str, Any], connector_id: str, company_identifier: str, canonical_entity_type: str) -> CanonicalDataRecord:
        pass

class BaseDataExtractor(ABC):
    @property
    @abstractmethod
    def provider_type(self) -> str:
        pass

    @abstractmethod
    def validate_request(self, connector_config: Dict[str, Any], company_identifier: str, canonical_entity_type: str, filters: Optional[Dict[str, Any]] = None) -> None:
        pass

    @abstractmethod
    def extract(self, connector_config: Dict[str, Any], company_identifier: str, canonical_entity_type: str, filters: Optional[Dict[str, Any]] = None, cursor: Optional[str] = None, page_size: int = 100) -> Dict[str, Any]:
        pass

    def extract_batches(self, connector_config: Dict[str, Any], company_identifier: str, canonical_entity_type: str, filters: Optional[Dict[str, Any]] = None, batch_size: int = 200) -> Generator[List[CanonicalDataRecord], None, None]:
        """Generator yielding records in chunks of 200-500 to keep memory low and prevent UI freeze."""
        cursor = None
        while True:
            res = self.extract(connector_config, company_identifier, canonical_entity_type, filters=filters, cursor=cursor, page_size=batch_size)
            recs = res.get("records", [])
            if recs:
                yield recs
            cursor = res.get("next_cursor")
            if not cursor or not recs:
                break

    @abstractmethod
    def extract_single(self, connector_config: Dict[str, Any], company_identifier: str, canonical_entity_type: str, source_identifier: str) -> Optional[CanonicalDataRecord]:
        pass

    @abstractmethod
    def extract_preview(self, connector_config: Dict[str, Any], company_identifier: str, canonical_entity_type: str, limit: int = 10) -> List[CanonicalDataRecord]:
        pass
