"""
Unit tests for shared/cloud_client.py - Central Cloud Server API Client Module
"""

import unittest
from unittest.mock import MagicMock, patch
import requests

from shared.cloud_client import CloudClient, CloudClientError

class TestCloudClientUnit(unittest.TestCase):

    def setUp(self):
        self.client = CloudClient(
            base_url="https://api.testcloud.com",
            auth_token="test-secret-token",
            client_id="client-machine-001",
            connect_timeout=2.0,
            read_timeout=10.0,
        )

    def test_01_headers_and_auth_initialization(self):
        headers = self.client.session.headers
        self.assertEqual(headers["Authorization"], "Bearer test-secret-token")
        self.assertEqual(headers["X-Client-Id"], "client-machine-001")
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertEqual(headers["Accept"], "application/json")

        self.client.update_auth(auth_token="new-token-999", client_id="client-machine-002")
        self.assertEqual(self.client.session.headers["Authorization"], "Bearer new-token-999")
        self.assertEqual(self.client.session.headers["X-Client-Id"], "client-machine-002")

    @patch.object(requests.Session, "request")
    def test_02_sync_masters(self, mock_request):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "success", "synced_count": 2}
        mock_request.return_value = mock_response

        masters = [{"name": "Sales Ledger"}, {"name": "Stock Item A"}]
        res = self.client.sync_masters(masters, company_identifier="COMP123")

        mock_request.assert_called_once()
        args, kwargs = mock_request.call_args
        self.assertEqual(args[0], "POST")
        self.assertEqual(args[1], "https://api.testcloud.com/api/v1/connector/sync-masters")
        self.assertEqual(kwargs["json"]["company_identifier"], "COMP123")
        self.assertEqual(len(kwargs["json"]["masters"]), 2)
        self.assertEqual(res["synced_count"], 2)

    @patch.object(requests.Session, "request")
    def test_03_sync_vouchers(self, mock_request):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "success", "synced_count": 1}
        mock_request.return_value = mock_response

        vouchers = [{"voucher_number": "INV-101", "amount": 5000.0}]
        res = self.client.sync_vouchers(vouchers)

        mock_request.assert_called_once()
        args, kwargs = mock_request.call_args
        self.assertEqual(args[0], "POST")
        self.assertEqual(args[1], "https://api.testcloud.com/api/v1/connector/sync-vouchers")
        self.assertEqual(res["synced_count"], 1)

    @patch.object(requests.Session, "request")
    def test_04_get_pending_invoices(self, mock_request):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "invoices": [
                {"id": "inv_001", "party_name": "ABC Enterprises", "amount": 1200.0},
                {"id": "inv_002", "party_name": "XYZ Retailers", "amount": 3400.0},
            ]
        }
        mock_request.return_value = mock_response

        invoices = self.client.get_pending_invoices(limit=10)

        mock_request.assert_called_once()
        args, kwargs = mock_request.call_args
        self.assertEqual(args[0], "GET")
        self.assertEqual(args[1], "https://api.testcloud.com/api/v1/connector/invoices/pending")
        self.assertEqual(kwargs["params"], {"limit": 10})
        self.assertEqual(len(invoices), 2)
        self.assertEqual(invoices[0]["id"], "inv_001")

    @patch.object(requests.Session, "request")
    def test_05_acknowledge_invoice(self, mock_request):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"acknowledged": True}
        mock_request.return_value = mock_response

        res = self.client.acknowledge_invoice(
            invoice_id="inv_001",
            status="SUCCESS",
            voucher_number="VCH-999",
            error_message=None,
        )

        mock_request.assert_called_once()
        args, kwargs = mock_request.call_args
        self.assertEqual(args[0], "POST")
        self.assertEqual(args[1], "https://api.testcloud.com/api/v1/connector/invoices/inv_001/ack")
        self.assertEqual(kwargs["json"]["status"], "SUCCESS")
        self.assertEqual(kwargs["json"]["voucher_number"], "VCH-999")
        self.assertEqual(res["acknowledged"], True)

    @patch.object(requests.Session, "request")
    def test_06_http_error_handling(self, mock_request):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_response.json.side_effect = Exception("No JSON")
        mock_request.return_value = mock_response

        with self.assertRaises(CloudClientError) as ctx:
            self.client.sync_masters([])

        self.assertIn("HTTP 500", str(ctx.exception))

    @patch.object(requests.Session, "request")
    def test_07_timeout_handling(self, mock_request):
        mock_request.side_effect = requests.exceptions.Timeout("Read timeout")

        with self.assertRaises(CloudClientError) as ctx:
            self.client.get_pending_invoices()

        self.assertIn("Timeout connecting to Cloud Server", str(ctx.exception))

if __name__ == "__main__":
    unittest.main()
