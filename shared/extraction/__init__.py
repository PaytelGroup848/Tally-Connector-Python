"""
CtrlBooks - Data Extraction Engine Package Index
--------------------------------------------------------------
Exports core extraction interfaces, source extractors, record normalizers, filter registry, and validation service.
"""

from shared.extraction.base import (
    CanonicalDataRecord,
    BaseRecordNormalizer,
    BaseDataExtractor
)
from shared.extraction.filter_registry import (
    ExtractionFilterRegistry,
    extraction_filter_registry
)
from shared.extraction.validation_service import (
    CanonicalRecordValidationService,
    canonical_record_validation_service
)
from shared.extraction.tally_extractor import (
    TallyRecordNormalizer,
    TallyDataExtractor,
    tally_data_extractor
)

__all__ = [
    "CanonicalDataRecord",
    "BaseRecordNormalizer",
    "BaseDataExtractor",
    "ExtractionFilterRegistry",
    "extraction_filter_registry",
    "CanonicalRecordValidationService",
    "canonical_record_validation_service",
    "TallyRecordNormalizer",
    "TallyDataExtractor",
    "tally_data_extractor",
]
