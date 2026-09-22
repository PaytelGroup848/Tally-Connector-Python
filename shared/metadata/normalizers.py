"""
CtrlBooks - Source Metadata Normalizers
---------------------------------------------------
Normalizes raw accounting data items from Tally Prime and BUSY Accounting
into unified canonical metadata records.
"""

import json
from abc import ABC, abstractmethod
from typing import Dict, Any, List
from shared.metadata.registry import MetadataRegistry

class BaseMetadataNormalizer(ABC):
    @abstractmethod
    def normalize(
        self,
        raw_items: List[Dict[str, Any]],
        canonical_entity_type: str,
        connector_id: str,
        company_identifier: str
    ) -> List[Dict[str, Any]]:
        pass

class TallyMetadataNormalizer(BaseMetadataNormalizer):
    def normalize(
        self,
        raw_items: List[Dict[str, Any]],
        canonical_entity_type: str,
        connector_id: str,
        company_identifier: str
    ) -> List[Dict[str, Any]]:
        mapping = MetadataRegistry.get_source_mapping(canonical_entity_type, "TALLY")
        src_entity_type = mapping["source_entity_type"]

        normalized = []
        for item in raw_items:
            name = item.get("name") or item.get("Name")
            if not name:
                continue

            guid = item.get("guid") or item.get("GUID") or str(name).strip()
            parent_name = item.get("parent") or item.get("Parent") or item.get("category")
            parent_guid = item.get("parent_guid") or parent_name

            extra_attrs = {k: v for k, v in item.items() if k not in ("name", "parent", "guid", "category")}

            record = {
                "connector_id": connector_id,
                "company_identifier": company_identifier,
                "source_type": "TALLY",
                "source_entity_type": src_entity_type,
                "canonical_entity_type": canonical_entity_type,
                "source_identifier": str(guid).strip(),
                "source_name": str(name).strip(),
                "display_name": str(name).strip(),
                "parent_source_identifier": str(parent_guid).strip() if parent_guid else None,
                "parent_display_name": str(parent_name).strip() if parent_name else None,
                "status": "ACTIVE",
                "source_metadata_json": json.dumps(extra_attrs) if extra_attrs else None
            }
            normalized.append(record)

        return normalized

tally_normalizer = TallyMetadataNormalizer()
