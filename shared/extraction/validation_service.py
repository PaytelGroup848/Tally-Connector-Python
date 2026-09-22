

from typing import List, Dict, Any, Tuple, Optional
from shared.extraction.base import CanonicalDataRecord
from shared.mapping.canonical_registry import canonical_registry, FIELD_REQUIREMENT_REQUIRED
from shared.logging_config import get_logger

logger = get_logger("app.extraction.validator")

class CanonicalRecordValidationService:
    @staticmethod
    def validate_record(record: CanonicalDataRecord) -> Tuple[bool, Optional[str]]:
        """
        Validates a single CanonicalDataRecord.
        Returns tuple (is_valid, failure_reason).
        """
        if not record.source_identifier or not str(record.source_identifier).strip():
            return False, "Record source_identifier is empty or missing."

        if not canonical_registry.is_entity_type_supported(record.canonical_entity_type):
            return False, f"Unsupported canonical entity type '{record.canonical_entity_type}'."

        try:
            field_defs = canonical_registry.get_canonical_fields(record.canonical_entity_type)
            for fname, fdef in field_defs.items():
                if fdef.get("requirement_level") == FIELD_REQUIREMENT_REQUIRED:
                    val = record.data.get(fname)
                    if val is None or str(val).strip() == "":
                        return False, f"Missing required canonical field '{fname}' for entity type '{record.canonical_entity_type}'."
        except Exception as exc:
            return False, f"Validation exception: {str(exc)}"

        return True, None

    @staticmethod
    def process_records(
        records: List[CanonicalDataRecord]
    ) -> Tuple[List[CanonicalDataRecord], List[Dict[str, Any]], int, int]:
        """
        Validates a batch of CanonicalDataRecord objects.
        Returns tuple (valid_records, failed_details, valid_count, failed_count).
        """
        valid_list: List[CanonicalDataRecord] = []
        failed_list: List[Dict[str, Any]] = []

        for rec in records:
            is_valid, reason = CanonicalRecordValidationService.validate_record(rec)
            if is_valid:
                valid_list.append(rec)
            else:
                failed_list.append({
                    "record_id": rec.record_id,
                    "source_identifier": rec.source_identifier,
                    "reason": reason
                })
                logger.warning(f"Record validation failed for '{rec.source_identifier}': {reason}")

        return valid_list, failed_list, len(valid_list), len(failed_list)

canonical_record_validation_service = CanonicalRecordValidationService()
