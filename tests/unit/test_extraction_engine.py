"""
CtrlBooks - Module 10 Unit Tests
---------------------------------------------
Unit testing for BaseDataExtractor interface, Tally normalizers,
filter registry, canonical record validation service, cursor pagination, and mapping integration.
"""

import pytest
from datetime import date, datetime
from shared.extraction.base import CanonicalDataRecord, BaseDataExtractor, BaseRecordNormalizer
from shared.extraction.filter_registry import extraction_filter_registry, MAX_PAGE_SIZE, MAX_PREVIEW_LIMIT
from shared.extraction.validation_service import canonical_record_validation_service
from shared.extraction.tally_extractor import tally_data_extractor, TallyRecordNormalizer
from shared.exceptions import ValidationError

def test_canonical_data_record_creation():
    rec = CanonicalDataRecord(
        record_id="rec-101",
        connector_id="conn-1",
        company_identifier="Demo Comp",
        source_type="TALLY",
        source_entity_type="LEDGER",
        canonical_entity_type="LEDGER",
        source_identifier="Cash",
        data={"name": "Cash", "parent": "Cash-in-Hand", "opening_balance": 5000.0},
        source_metadata={"guid": "guid-123"}
    )
    assert rec.record_id == "rec-101"
    assert rec.source_identifier == "Cash"
    assert rec.data["name"] == "Cash"
    
    d = rec.to_dict()
    assert d["record_id"] == "rec-101"
    assert d["source_type"] == "TALLY"
    assert d["canonical_entity_type"] == "LEDGER"

def test_tally_record_normalizer_ledger():
    normalizer = TallyRecordNormalizer()
    raw = {
        "name": "State Bank of India",
        "parent": "Bank Accounts",
        "guid": "tally-guid-999",
        "closing_balance": 150000.0,
        "opening_balance": 100000.0,
        "phone": "+91 9876543210",
        "gstin": "07AAAAA0000A1Z5",
        "_raw_tag": "LEDGER"
    }
    rec = normalizer.normalize(raw, "conn-tally", "Test Company", "LEDGER")
    assert rec.source_type == "TALLY"
    assert rec.canonical_entity_type == "LEDGER"
    assert rec.source_identifier == "State Bank of India"
    assert rec.data["name"] == "State Bank of India"
    assert rec.data["parent"] == "Bank Accounts"
    assert rec.data["closing_balance"] == 150000.0
    assert rec.data["tax_identifier"] == "07AAAAA0000A1Z5"

def test_tally_record_normalizer_stock_item():
    normalizer = TallyRecordNormalizer()
    raw = {
        "name": "Widget X",
        "parent": "Hardware",
        "base_units": "PCS",
        "opening_balance": 50.0,
        "guid": "guid-widget",
        "_raw_tag": "STOCKITEM"
    }
    rec = normalizer.normalize(raw, "conn-tally", "Test Company", "STOCK_ITEM")
    assert rec.canonical_entity_type == "STOCK_ITEM"
    assert rec.data["name"] == "Widget X"
    assert rec.data["group"] == "Hardware"
    assert rec.data["unit"] == "PCS"

def test_filter_registry_allowed_filters():
    assert "name" in extraction_filter_registry.get_allowed_filters("LEDGER")
    assert "date_from" in extraction_filter_registry.get_allowed_filters("VOUCHER")
    assert "date_to" in extraction_filter_registry.get_allowed_filters("VOUCHER")

def test_filter_registry_validation_success():
    clean = extraction_filter_registry.validate_filters("LEDGER", {"name": "Cash"})
    assert clean["name"] == "Cash"

def test_filter_registry_invalid_filter_rejection():
    with pytest.raises(ValidationError) as exc:
        extraction_filter_registry.validate_filters("LEDGER", {"unknown_sql_command": "DROP TABLE"})
    assert "Filter 'unknown_sql_command' is not allowed" in str(exc.value)

def test_filter_registry_date_range_validation():
    clean = extraction_filter_registry.validate_filters("VOUCHER", {"date_from": "2026-01-01", "date_to": "2026-03-31"})
    assert clean["date_from"] == "2026-01-01"

    with pytest.raises(ValidationError) as exc:
        extraction_filter_registry.validate_filters("VOUCHER", {"date_from": "2026-05-01", "date_to": "2026-01-01"})
    assert "cannot be after" in str(exc.value)

def test_filter_registry_page_size_validation():
    assert extraction_filter_registry.validate_page_size(50) == 50
    assert extraction_filter_registry.validate_page_size(None) == 100
    assert extraction_filter_registry.validate_page_size(10, is_preview=True) == 10

    with pytest.raises(ValidationError):
        extraction_filter_registry.validate_page_size(1000)

    with pytest.raises(ValidationError):
        extraction_filter_registry.validate_page_size(100, is_preview=True)

def test_canonical_record_validation_success():
    rec = CanonicalDataRecord(
        record_id="rec-1",
        connector_id="conn-1",
        company_identifier="Comp A",
        source_type="TALLY",
        source_entity_type="LEDGER",
        canonical_entity_type="LEDGER",
        source_identifier="Valid Ledger",
        data={"name": "Valid Ledger", "parent": "Assets"}
    )
    ok, err = canonical_record_validation_service.validate_record(rec)
    assert ok is True
    assert err is None

def test_canonical_record_validation_missing_required_field():
    rec = CanonicalDataRecord(
        record_id="rec-2",
        connector_id="conn-1",
        company_identifier="Comp A",
        source_type="TALLY",
        source_entity_type="LEDGER",
        canonical_entity_type="LEDGER",
        source_identifier="No Name",
        data={"name": "", "parent": "Assets"}
    )
    ok, err = canonical_record_validation_service.validate_record(rec)
    assert ok is False
    assert "Missing required canonical field 'name'" in err

def test_canonical_record_batch_processing():
    r1 = CanonicalDataRecord(record_id="r1", connector_id="c1", company_identifier="Comp A", source_type="TALLY", source_entity_type="LEDGER", canonical_entity_type="LEDGER", source_identifier="Ledger 1", data={"name": "Ledger 1"})
    r2 = CanonicalDataRecord(record_id="r2", connector_id="c1", company_identifier="Comp A", source_type="TALLY", source_entity_type="LEDGER", canonical_entity_type="LEDGER", source_identifier="Ledger 2", data={"name": ""})

    valid, failed, v_cnt, f_cnt = canonical_record_validation_service.process_records([r1, r2])
    assert v_cnt == 1
    assert f_cnt == 1
    assert len(valid) == 1
    assert len(failed) == 1
    assert failed[0]["record_id"] == "r2"

def test_tally_extractor_validation():
    with pytest.raises(ValidationError):
        tally_data_extractor.validate_request({"host": "127.0.0.1", "port": 9000}, "Comp", "UNSUPPORTED_ENTITY")
