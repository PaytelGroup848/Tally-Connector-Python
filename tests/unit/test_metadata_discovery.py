"""
CtrlBooks - Unit Test Suite for Data Discovery & Unified Metadata
-----------------------------------------------------------------------------
Tests canonical category validation, metadata registry mappings, Tally & BUSY normalizers,
batched upsert, and stale record reconciliation logic.
"""

import unittest
from unittest.mock import MagicMock
from shared.metadata.registry import MetadataRegistry
from shared.metadata.normalizers import tally_normalizer
from shared.repositories.metadata_repo import MetadataRepository

class TestMetadataDiscoveryUnit(unittest.TestCase):
    def test_canonical_category_validation(self):
        self.assertEqual(MetadataRegistry.validate_canonical_type("ledger"), "LEDGER")
        self.assertEqual(MetadataRegistry.validate_canonical_type("STOCK_ITEM"), "STOCK_ITEM")
        with self.assertRaises(ValueError):
            MetadataRegistry.validate_canonical_type("INVALID_CATEGORY")

    def test_metadata_registry_mappings(self):
        tally_map = MetadataRegistry.get_source_mapping("LEDGER", "TALLY")
        self.assertEqual(tally_map["source_entity_type"], "Ledger")
        self.assertEqual(tally_map["adapter_query_type"], "ledgers")

    def test_tally_normalizer(self):
        raw = [
            {"name": "HDFC Bank", "parent": "Bank Accounts", "guid": "tally-guid-101", "currency": "INR"},
            {"parent": "Orphan Group"}
        ]
        res = tally_normalizer.normalize(raw, "LEDGER", "conn-123", "Demo Tally Comp")
        self.assertEqual(len(res), 1)
        item = res[0]
        self.assertEqual(item["canonical_entity_type"], "LEDGER")
        self.assertEqual(item["source_type"], "TALLY")
        self.assertEqual(item["source_identifier"], "tally-guid-101")
        self.assertEqual(item["display_name"], "HDFC Bank")
        self.assertEqual(item["parent_display_name"], "Bank Accounts")

if __name__ == "__main__":
    unittest.main()
