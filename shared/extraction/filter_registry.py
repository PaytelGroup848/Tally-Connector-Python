"""
CtrlBooks - Extraction Filter Registry & Validator
----------------------------------------------------------------
Defines allowed filters per canonical entity type, validates page size limits,
and enforces date range boundaries to prevent arbitrary query injection.
"""

from datetime import datetime, date
from typing import Dict, Any, List, Optional
from shared.exceptions import ValidationError

ALLOWED_ENTITY_FILTERS: Dict[str, List[str]] = {
    "LEDGER": ["name", "identifier", "parent", "is_active"],
    "STOCK_ITEM": ["name", "identifier", "group", "code"],
    "VOUCHER": ["date_from", "date_to", "voucher_type", "identifier"],
    "ACCOUNT_GROUP": ["name", "parent"],
    "VOUCHER_TYPE": ["name"],
    "UNIT": ["name", "symbol"],
    "GODOWN": ["name"],
    "COST_CENTRE": ["name", "category"]
}

MAX_PAGE_SIZE = 500
DEFAULT_PAGE_SIZE = 100
MAX_PREVIEW_LIMIT = 50
DEFAULT_PREVIEW_LIMIT = 10
MAX_DATE_SPAN_DAYS = 365

class ExtractionFilterRegistry:
    @staticmethod
    def get_allowed_filters(canonical_entity_type: str) -> List[str]:
        entity = (canonical_entity_type or "").strip().upper()
        return ALLOWED_ENTITY_FILTERS.get(entity, ["name", "identifier"])

    @staticmethod
    def validate_page_size(page_size: Optional[int], is_preview: bool = False) -> int:
        if page_size is None:
            return DEFAULT_PREVIEW_LIMIT if is_preview else DEFAULT_PAGE_SIZE
        try:
            val = int(page_size)
            if val < 1:
                raise ValidationError("Page size must be greater than 0.")
            max_limit = MAX_PREVIEW_LIMIT if is_preview else MAX_PAGE_SIZE
            if val > max_limit:
                raise ValidationError(f"Page size '{val}' exceeds maximum allowed limit of {max_limit}.")
            return val
        except ValueError:
            raise ValidationError(f"Invalid page_size value '{page_size}'. Must be an integer.")

    @staticmethod
    def validate_filters(canonical_entity_type: str, filters: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not filters:
            return {}

        entity = (canonical_entity_type or "").strip().upper()
        allowed = ExtractionFilterRegistry.get_allowed_filters(entity)

        clean_filters: Dict[str, Any] = {}
        for k, v in filters.items():
            k_clean = str(k).strip().lower()
            if k_clean not in allowed:
                raise ValidationError(f"Filter '{k}' is not allowed for entity type '{entity}'. Allowed filters: {', '.join(allowed)}")
            clean_filters[k_clean] = v

        d_from = clean_filters.get("date_from")
        d_to = clean_filters.get("date_to")

        dt_from_obj: Optional[date] = None
        dt_to_obj: Optional[date] = None

        if d_from:
            dt_from_obj = ExtractionFilterRegistry._parse_date_string(str(d_from), "date_from")
        if d_to:
            dt_to_obj = ExtractionFilterRegistry._parse_date_string(str(d_to), "date_to")

        if dt_from_obj and dt_to_obj:
            if dt_from_obj > dt_to_obj:
                raise ValidationError(f"date_from ({dt_from_obj}) cannot be after date_to ({dt_to_obj}).")
            
            span_days = (dt_to_obj - dt_from_obj).days
            if span_days > MAX_DATE_SPAN_DAYS:
                raise ValidationError(f"Extraction date range ({span_days} days) exceeds maximum limit of {MAX_DATE_SPAN_DAYS} days.")

        return clean_filters

    @staticmethod
    def _parse_date_string(val_str: str, field_name: str) -> date:
        clean = val_str.strip()
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(clean[:10], fmt[:8] if "T" in fmt else fmt).date()
            except ValueError:
                continue
        raise ValidationError(f"Invalid date format for '{field_name}': '{val_str}'. Expected format: YYYY-MM-DD.")

extraction_filter_registry = ExtractionFilterRegistry()
