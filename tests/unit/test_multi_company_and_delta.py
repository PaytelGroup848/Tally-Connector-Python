"""
Unit tests for Multi-Company Selective Sync Toggle & ALTERID Incremental Sync.
"""

import unittest
from unittest.mock import MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from shared.db.base import Base
from shared.db.models.company import CompanySyncConfig
from shared.repositories.company_repository import (
    upsert_company_config,
    set_company_sync_enabled,
    is_company_sync_enabled,
    update_company_last_alter_id,
    get_enabled_company_configs,
)
from shared.extraction.tally_extractor import TallyDataExtractor

class TestMultiCompanyAndDeltaUnit(unittest.TestCase):

    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)
        self.session = self.SessionLocal()

        self.db_patcher = patch("shared.repositories.company_repository.get_db_session")
        self.mock_db_session = self.db_patcher.start()
        self.mock_db_session.return_value.__enter__.return_value = self.session

    def tearDown(self):
        self.db_patcher.stop()
        self.session.close()
        Base.metadata.drop_all(self.engine)

    def test_01_multi_company_sync_toggle(self):
        upsert_company_config("TALLY", "Acme Enterprises Pvt Ltd", "guid-101", "01-Apr-2025")
        self.assertTrue(is_company_sync_enabled("TALLY", "Acme Enterprises Pvt Ltd"))

        set_company_sync_enabled("TALLY", "Acme Enterprises Pvt Ltd", False)
        self.assertFalse(is_company_sync_enabled("TALLY", "Acme Enterprises Pvt Ltd"))

        set_company_sync_enabled("TALLY", "Acme Enterprises Pvt Ltd", True)
        self.assertTrue(is_company_sync_enabled("TALLY", "Acme Enterprises Pvt Ltd"))

    def test_02_get_enabled_company_configs(self):
        upsert_company_config("TALLY", "Company A", "guid-A")
        upsert_company_config("TALLY", "Company B", "guid-B")
        set_company_sync_enabled("TALLY", "Company B", False)

        enabled = get_enabled_company_configs("TALLY")
        self.assertEqual(len(enabled), 1)
        self.assertEqual(enabled[0]["company_name"], "Company A")

    def test_03_update_company_last_alter_id(self):
        upsert_company_config("TALLY", "Company A", "guid-A")

        update_company_last_alter_id("TALLY", "Company A", 1050)

        cfg = self.session.query(CompanySyncConfig).filter_by(company_name="Company A").first()
        self.assertEqual(cfg.last_alter_id, 1050)

        update_company_last_alter_id("TALLY", "Company A", 800)
        self.assertEqual(cfg.last_alter_id, 1050)

    @patch("shared.extraction.tally_extractor.is_company_sync_enabled", return_value=False)
    def test_04_tally_extractor_skips_disabled_company(self, mock_is_enabled):
        extractor = TallyDataExtractor()
        res = extractor.extract(
            connector_config={"host": "127.0.0.1", "port": 9000},
            company_identifier="Disabled Company",
            canonical_entity_type="LEDGER",
        )

        self.assertEqual(res["status"], "DISABLED")
        self.assertEqual(res["returned"], 0)
        self.assertIn("Sync is disabled for company", res["error"])

if __name__ == "__main__":
    unittest.main()
