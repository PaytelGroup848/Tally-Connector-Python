"""
CtrlBooks - Unit Tests for Module 9 Data Mapping & Field Mapping Engine
-------------------------------------------------------------------------------------
Tests canonical registry, transformation engine (all 13 types), suggestion engine,
validation service, and preview engine.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from shared.db.base import Base
from shared.db.models.user import User, Role, UserRole, Permission, RolePermission
from shared.db.models.connector import Connector, DataSource, Destination
from shared.db.models.mapping import MappingDefinition, MappingVersion, MappingFieldRule, MappingValidationLog
from shared.mapping.canonical_registry import canonical_registry, CanonicalRegistry
from shared.mapping.transformation_engine import transformation_engine, TransformationError
from shared.mapping.suggestion_engine import field_suggestion_engine
from shared.mapping.validation_service import mapping_validation_service
from shared.mapping.preview_service import mapping_preview_engine

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(bind=engine)
    session = TestingSessionLocal()
    yield session
    session.close()

def test_canonical_registry_entity_support():
    supported = canonical_registry.get_supported_entity_types()
    assert "LEDGER" in supported
    assert "STOCK_ITEM" in supported
    assert "ACCOUNT_GROUP" in supported
    assert canonical_registry.is_entity_type_supported("ledger") is True
    assert canonical_registry.is_entity_type_supported("INVALID_TYPE") is False

def test_canonical_registry_fields_and_capabilities():
    c_fields = canonical_registry.get_canonical_fields("LEDGER")
    assert "name" in c_fields
    assert "closing_balance" in c_fields

    src_fields = canonical_registry.get_supported_source_fields("TALLY", "LEDGER")
    assert len(src_fields) > 0
    tgt_fields = canonical_registry.get_supported_target_fields("TALLY", "LEDGER")
    assert len(tgt_fields) > 0

def test_transformation_engine_all_types():
    assert transformation_engine.apply_transformation("Hello", "NONE") == "Hello"

    assert transformation_engine.apply_transformation("  Hello  ", "TRIM") == "Hello"

    assert transformation_engine.apply_transformation("HELLO", "LOWERCASE") == "hello"

    assert transformation_engine.apply_transformation("hello", "UPPERCASE") == "HELLO"

    assert transformation_engine.apply_transformation("1,250.50", "STRING_TO_NUMBER") == 1250.50
    assert transformation_engine.apply_transformation("100", "STRING_TO_NUMBER") == 100

    assert transformation_engine.apply_transformation(500.2, "NUMBER_TO_STRING", '{"decimals": 2}') == "500.20"

    assert transformation_engine.apply_transformation("25/08/2026", "STRING_TO_DATE") == "2026-08-25"

    assert transformation_engine.apply_transformation("2026-08-25", "DATE_TO_STRING", '{"date_format": "%d-%m-%Y"}') == "25-08-2026"

    assert transformation_engine.apply_transformation("Yes", "BOOLEAN_NORMALIZE") is True
    assert transformation_engine.apply_transformation("0", "BOOLEAN_NORMALIZE") is False

    assert transformation_engine.apply_transformation("", "DEFAULT_VALUE", '{"default_value": "N/A"}') == "N/A"

    vmap_cfg = '{"mapping": {"Male": "M", "Female": "F"}}'
    assert transformation_engine.apply_transformation("Male", "VALUE_MAP", vmap_cfg) == "M"

    concat_cfg = '{"fields": ["line1", "city"], "separator": ", "}'
    ctx = {"line1": "123 Main St", "city": "Mumbai"}
    assert transformation_engine.apply_transformation("ignored", "CONCAT", concat_cfg, record_context=ctx) == "123 Main St, Mumbai"

    split_cfg = '{"delimiter": "-", "index": 1}'
    assert transformation_engine.apply_transformation("INV-9876-2026", "SPLIT", split_cfg) == "9876"

def test_transformation_engine_invalid_type_raises():
    with pytest.raises(TransformationError):
        transformation_engine.apply_transformation("test", "INVALID_TRANS_TYPE")

def test_field_suggestion_engine():
    src_fields = [
        {"field_name": "LedgerName", "data_type": "STRING"},
        {"field_name": "Phone", "data_type": "STRING"},
        {"field_name": "OpBal", "data_type": "NUMBER"}
    ]
    tgt_fields = [
        {"field_name": "AccountName", "data_type": "STRING"},
        {"field_name": "Phone", "data_type": "STRING"},
        {"field_name": "OpeningBalance", "data_type": "NUMBER"}
    ]

    suggs = field_suggestion_engine.suggest_field_mappings("LEDGER", src_fields, tgt_fields)
    assert len(suggs) >= 2

    phone_sugg = next(s for s in suggs if s["source_field"] == "Phone")
    assert phone_sugg["confidence"] == "EXACT"

    ledger_sugg = next(s for s in suggs if s["source_field"] == "LedgerName")
    assert ledger_sugg["confidence"] == "HIGH"
    assert ledger_sugg["target_field"] == "AccountName"

def test_mapping_validation_service(db_session):
    src_conn = Connector(name="Tally Pipeline", connector_type="TALLY", is_active=True, configuration_status="CONFIGURED")
    tgt_conn = Connector(name="Tally Target Pipeline", connector_type="TALLY", is_active=True, configuration_status="CONFIGURED")
    db_session.add_all([src_conn, tgt_conn])
    db_session.commit()

    mapping = MappingDefinition(
        name="Test Validation Mapping",
        source_connector_id=src_conn.id,
        source_company_identifier="Comp A",
        target_connector_id=tgt_conn.id,
        target_company_identifier="Comp B",
        canonical_entity_type="LEDGER",
        status="DRAFT"
    )
    db_session.add(mapping)
    db_session.commit()

    rule1 = MappingFieldRule(mapping_id=mapping.id, source_field="LedgerName", target_field="name", source_data_type="STRING", target_data_type="STRING", is_required=True)
    db_session.add(rule1)
    db_session.commit()

    val_res = mapping_validation_service.validate_mapping_definition(db_session, mapping)
    assert val_res["is_valid"] is True
    assert "name" in val_res["mapped_fields"]

def test_mapping_preview_engine():
    mapping = MappingDefinition(
        id="map-101",
        name="Preview Mapping",
        source_connector_id="conn-1",
        source_company_identifier="Comp A",
        target_connector_id="conn-2",
        target_company_identifier="Comp B",
        canonical_entity_type="LEDGER"
    )

    rules = [
        MappingFieldRule(mapping_id="map-101", source_field="LedgerName", target_field="AccountName", transformation_type="NONE", is_active=True),
        MappingFieldRule(mapping_id="map-101", source_field="Phone", target_field="Mobile", transformation_type="TRIM", is_active=True),
        MappingFieldRule(mapping_id="map-101", source_field="Balance", target_field="OpeningBalance", transformation_type="NUMBER_TO_STRING", transformation_config_json='{"decimals": 2}', is_active=True)
    ]

    sample_record = {
        "LedgerName": "State Bank of India",
        "Phone": "  +91 9999988888  ",
        "Balance": 10500.5
    }

    res = mapping_preview_engine.generate_preview(mapping, sample_record, field_rules=rules)
    assert res["is_preview"] is True
    assert res["target_preview"]["AccountName"] == "State Bank of India"
    assert res["target_preview"]["Mobile"] == "+91 9999988888"
    assert res["target_preview"]["OpeningBalance"] == "10500.50"
