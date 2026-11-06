"""
Unit tests for verifying startDate and endDate injection into LEDGER sync payloads.
"""

import unittest
from unittest.mock import MagicMock, patch
from shared.cloud.cloud_sync_client import CloudSyncClient


class TestLedgerDateSync(unittest.TestCase):

    def setUp(self):
        self.mock_auth = MagicMock()
        self.mock_auth.access_token = "fake-jwt-token"
        self.mock_client = MagicMock()
        mock_res = MagicMock()
        mock_res.status_code = 200
        mock_res.json.return_value = {"success": True, "data": {"upserted": 1}}
        mock_res.text = '{"success": true}'
        self.mock_client.post.return_value = mock_res
        self.mock_auth._get_client.return_value = self.mock_client

        self.sync_client = CloudSyncClient(self.mock_auth)

        self.ledger_item = {
            "tallyExternalId": "ledg-001",
            "name": "Sales GST",
            "parent": "Sales Accounts",
            "closingBalance": 6186977.38
        }

    def test_01_ledger_batch_with_explicit_dates(self):
        """Verifies startDate and endDate are included in top-level payload and records when passed explicitly."""
        ok, msg, data = self.sync_client.sync_batch(
            sync_id="sync-ledger-101",
            company_name="Tarun Enterprise (25-26)",
            entity_type="LEDGER",
            items=[self.ledger_item],
            batch_number=1,
            is_last_batch=True,
            company_id="comp-6accd8b5",
            sync_type="INCREMENTAL",
            is_full_replace=False,
            start_date="2026-04-01",
            end_date="2026-11-04"
        )
        self.assertTrue(ok)
        call_args = self.mock_client.post.call_args
        sent_body = call_args[1]["json"]

        self.assertEqual(sent_body["entityType"], "LEDGER")
        self.assertEqual(sent_body["startDate"], "2026-04-01")
        self.assertEqual(sent_body["endDate"], "2026-11-04")
        self.assertEqual(len(sent_body["records"]), 1)

        rec = sent_body["records"][0]
        self.assertEqual(rec["name"], "Sales GST")
        self.assertEqual(rec["startDate"], "2026-04-01")
        self.assertEqual(rec["endDate"], "2026-11-04")

    @patch("shared.cloud.helpers.get_company_sync_dates", return_value=("2026-04-01", "2026-11-04", True))
    def test_02_ledger_batch_with_checkpoint_dates_fallback(self, mock_dates):
        """Verifies startDate and endDate are loaded from checkpoints when omitted from caller arguments."""
        ok, msg, data = self.sync_client.sync_batch(
            sync_id="sync-ledger-102",
            company_name="Tarun Enterprise (25-26)",
            entity_type="LEDGER",
            items=[self.ledger_item],
            batch_number=1,
            is_last_batch=True,
            company_id="comp-6accd8b5",
            sync_type="INCREMENTAL",
            is_full_replace=False
        )
        self.assertTrue(ok)
        call_args = self.mock_client.post.call_args
        sent_body = call_args[1]["json"]

        self.assertEqual(sent_body["entityType"], "LEDGER")
        self.assertEqual(sent_body["startDate"], "2026-04-01")
        self.assertEqual(sent_body["endDate"], "2026-11-04")
        self.assertEqual(sent_body["records"][0]["startDate"], "2026-04-01")
        self.assertEqual(sent_body["records"][0]["endDate"], "2026-11-04")


if __name__ == "__main__":
    unittest.main()

