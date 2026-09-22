"""
CtrlBooks - Centralized Metadata Registry
------------------------------------------------------
Controlled mapping of canonical entity categories (LEDGER, STOCK_ITEM, VOUCHER_TYPE, etc.)
to source-specific entity types for Tally Prime and BUSY Accounting.
"""

from typing import Dict, List

CANONICAL_METADATA_CATEGORIES = [
    "COMPANY",
    "ACCOUNT_GROUP",
    "LEDGER",
    "VOUCHER_TYPE",
    "STOCK_GROUP",
    "STOCK_CATEGORY",
    "STOCK_ITEM",
    "UNIT",
    "GODOWN",
    "COST_CENTRE"
]

METADATA_SOURCE_MAP = {
    "COMPANY": {
        "TALLY": {"source_entity_type": "Company", "adapter_query_type": "companies"}
    },
    "ACCOUNT_GROUP": {
        "TALLY": {"source_entity_type": "Group", "adapter_query_type": "groups"}
    },
    "LEDGER": {
        "TALLY": {"source_entity_type": "Ledger", "adapter_query_type": "ledgers"}
    },
    "VOUCHER_TYPE": {
        "TALLY": {"source_entity_type": "VoucherType", "adapter_query_type": "voucher_types"}
    },
    "STOCK_GROUP": {
        "TALLY": {"source_entity_type": "StockGroup", "adapter_query_type": "stock_groups"}
    },
    "STOCK_CATEGORY": {
        "TALLY": {"source_entity_type": "StockCategory", "adapter_query_type": "stock_categories"}
    },
    "STOCK_ITEM": {
        "TALLY": {"source_entity_type": "StockItem", "adapter_query_type": "stock_items"}
    },
    "UNIT": {
        "TALLY": {"source_entity_type": "Unit", "adapter_query_type": "units"}
    },
    "GODOWN": {
        "TALLY": {"source_entity_type": "Godown", "adapter_query_type": "godowns"}
    },
    "COST_CENTRE": {
        "TALLY": {"source_entity_type": "CostCentre", "adapter_query_type": "cost_centres"}
    }
}

class MetadataRegistry:
    @staticmethod
    def get_allowed_categories() -> List[str]:
        return list(CANONICAL_METADATA_CATEGORIES)

    @staticmethod
    def validate_canonical_type(canonical_entity_type: str) -> str:
        clean = (canonical_entity_type or "").strip().upper()
        if clean not in CANONICAL_METADATA_CATEGORIES:
            raise ValueError(f"Invalid canonical entity type '{canonical_entity_type}'. Allowed categories: {', '.join(CANONICAL_METADATA_CATEGORIES)}")
        return clean

    @staticmethod
    def get_source_mapping(canonical_entity_type: str, source_type: str) -> Dict[str, str]:
        c_type = MetadataRegistry.validate_canonical_type(canonical_entity_type)
        src = (source_type or "").strip().upper()
        
        mapping = METADATA_SOURCE_MAP.get(c_type, {}).get(src)
        if not mapping:
            raise ValueError(f"Metadata category '{c_type}' is not supported for source type '{source_type}'.")
        return mapping

metadata_registry_service = MetadataRegistry()
