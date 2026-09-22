"""
Unit tests for Smart Pending Voucher Queue and Multi-Tenant Isolation.
"""

import unittest
from unittest.mock import AsyncMock, patch, MagicMock
import asyncio

from shared.repositories.voucher_queue_repository import voucher_queue_repo
from apps.backend.adapters.tally.tally_importer import TallyImporter
from apps.backend.services.importer_service import ImporterService


class TestVoucherQueueUnit(unittest.TestCase):

    def setUp(self):
        self.test_cmd_id = "test_cmd_12345"
        self.test_company = "Tarun Enterprise (25-26)"
        self.test_email = "testuser@example.com"
        self.test_org_id = "org_98765"
        self.payload = {
            "target": "TALLY",
            "voucher_type": "Payment",
            "party_ledger": "20 Microns Limited",
            "amount": 999.91,
            "company_name": self.test_company,
            "voucher_number": "PAY-001"
        }

    def tearDown(self):
        voucher_queue_repo.delete_pending_voucher(self.test_cmd_id)
        voucher_queue_repo.delete_pending_voucher("test_cmd_99999")

    def test_01_enqueue_and_retrieve_pending_voucher(self):
        """Tests that vouchers are enqueued and retrievable by tenant and company."""
        q_id = voucher_queue_repo.enqueue_pending_voucher(
            cmd_id=self.test_cmd_id,
            cmd_type="CREATE_PAYMENT",
            payload=self.payload,
            target_company=self.test_company,
            user_email=self.test_email,
            organization_id=self.test_org_id,
            reason="Company not opened in Tally"
        )
        self.assertIsNotNone(q_id)

        # Retrieve with matching tenant & company
        items = voucher_queue_repo.get_pending_vouchers(
            organization_id=self.test_org_id,
            user_email=self.test_email,
            company_name=self.test_company
        )
        matching = [it for it in items if it.get("cmd_id") == self.test_cmd_id]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]["target_company"], self.test_company)
        self.assertEqual(matching[0]["status"], "PENDING_TALLY")

    def test_02_tenant_isolation_skips_unmatched_tenant(self):
        """Tests that pending queue retrieval filters out other tenants."""
        voucher_queue_repo.enqueue_pending_voucher(
            cmd_id="test_cmd_99999",
            cmd_type="CREATE_PAYMENT",
            payload=self.payload,
            target_company=self.test_company,
            user_email="otheruser@tenant2.com",
            organization_id="org_other_tenant",
            reason="Waiting for Tally"
        )

        # Query for user 1 should NOT return user 2's voucher
        user1_items = voucher_queue_repo.get_pending_vouchers(
            organization_id=self.test_org_id,
            user_email=self.test_email
        )
        other_matching = [it for it in user1_items if it.get("cmd_id") == "test_cmd_99999"]
        self.assertEqual(len(other_matching), 0)

    def test_03_mark_voucher_completed(self):
        """Tests marking pending voucher as completed."""
        voucher_queue_repo.enqueue_pending_voucher(
            cmd_id=self.test_cmd_id,
            cmd_type="CREATE_PAYMENT",
            payload=self.payload,
            target_company=self.test_company,
            user_email=self.test_email,
            organization_id=self.test_org_id
        )

        ok = voucher_queue_repo.mark_voucher_completed(self.test_cmd_id, "TALLY-VCH-888")
        self.assertTrue(ok)

        # Should no longer be pending
        pending = voucher_queue_repo.get_pending_vouchers(organization_id=self.test_org_id)
        matching = [it for it in pending if it.get("cmd_id") == self.test_cmd_id]
        self.assertEqual(len(matching), 0)

    def test_04_tally_offline_flags_should_queue(self):
        """Tests that TallyImporter flags should_queue=True when Tally is offline."""
        mock_client = MagicMock()
        mock_client.send_xml_request_async = AsyncMock(return_value=(False, 0, "", "Connection refused"))
        importer = TallyImporter(client=mock_client)

        loop = asyncio.new_event_loop()
        try:
            res = loop.run_until_complete(importer.import_voucher("127.0.0.1", 9000, self.payload))
            self.assertFalse(res["success"])
            self.assertTrue(res.get("should_queue"))
            self.assertEqual(res.get("status"), "TALLY_OFFLINE")
        finally:
            loop.close()

    def test_05_company_not_loaded_flags_should_queue(self):
        """Tests that TallyImporter flags should_queue=True when target company is not loaded."""
        mock_client = MagicMock()
        # Return company list with a different company loaded
        other_comp_xml = """<ENVELOPE><BODY><DATA><COLLECTION>
            <COMPANY><NAME>Other Firm Ltd</NAME><GUID>guid-1</GUID></COMPANY>
        </COLLECTION></DATA></BODY></ENVELOPE>"""
        mock_client.send_xml_request_async = AsyncMock(return_value=(True, 200, other_comp_xml, None))
        importer = TallyImporter(client=mock_client)

        loop = asyncio.new_event_loop()
        try:
            res = loop.run_until_complete(importer.import_voucher("127.0.0.1", 9000, self.payload))
            self.assertFalse(res["success"])
            self.assertTrue(res.get("should_queue"))
            self.assertEqual(res.get("status"), "COMPANY_NOT_LOADED")
        finally:
            loop.close()

    def test_06_importer_service_passes_should_queue(self):
        """Tests that ImporterService passes should_queue and status=QUEUED."""
        mock_tally = MagicMock()
        mock_tally.import_voucher = AsyncMock(return_value={
            "success": False,
            "should_queue": True,
            "status": "COMPANY_NOT_LOADED",
            "message": "Company not open in Tally",
            "reason": "Tarun Enterprise is not open in Tally",
            "action": "Open Tarun Enterprise in Tally"
        })
        service = ImporterService(tally_importer=mock_tally)

        loop = asyncio.new_event_loop()
        try:
            res = loop.run_until_complete(service.import_voucher(self.payload))
            self.assertEqual(res["status"], "QUEUED")
            self.assertTrue(res["should_queue"])
        finally:
            loop.close()


if __name__ == "__main__":
    unittest.main()

