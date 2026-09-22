"""
Unit tests for Central Cloud Authentication Client (send_otp, verify_otp, refresh, logout, me).
"""

import unittest
from unittest.mock import patch, MagicMock
from shared.auth.cloud_auth_service import CloudAuthService, get_or_create_device_id


class TestCloudAuthService(unittest.TestCase):

    def setUp(self):
        self.auth_svc = CloudAuthService(base_url="https://connector.cloudata.in/api/connector")

    def test_device_id_generation(self):
        """Verifies device ID is created and is non-empty."""
        dev_id = get_or_create_device_id()
        self.assertTrue(len(dev_id) > 10)

    @patch("httpx.Client.post")
    def test_send_otp_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '{"success": true, "message": "OTP sent successfully"}'
        mock_resp.json.return_value = {"success": True, "message": "OTP sent successfully"}
        mock_post.return_value = mock_resp

        ok, msg = self.auth_svc.send_otp("user@cloudata.in")
        self.assertTrue(ok)
        self.assertIn("OTP sent", msg)

    @patch("httpx.Client.post")
    def test_verify_otp_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '{"success": true, "data": {"accessToken": "tok_123", "refreshToken": "ref_456", "user": {"email": "user@cloudata.in"}}}'
        mock_resp.json.return_value = {
            "success": True,
            "data": {
                "accessToken": "tok_123",
                "refreshToken": "ref_456",
                "user": {"email": "user@cloudata.in", "fullName": "Test User"}
            }
        }
        mock_post.return_value = mock_resp

        ok, msg, user = self.auth_svc.verify_otp("user@cloudata.in", "1234")
        self.assertTrue(ok)
        self.assertEqual(self.auth_svc.access_token, "tok_123")

    @patch("httpx.Client.post")
    def test_logout(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '{"success": true}'
        mock_resp.json.return_value = {"success": True}
        mock_post.return_value = mock_resp

        ok, msg = self.auth_svc.logout()
        self.assertTrue(ok)
        self.assertIsNone(self.auth_svc.access_token)

    @patch("httpx.Client.post")
    def test_link_company(self, mock_post):
        self.auth_svc.access_token = "tok_test_123"
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '{"success": true, "message": "Company linked successfully", "data": {"id": "c1"}}'
        mock_resp.json.return_value = {"success": True, "message": "Company linked successfully", "data": {"id": "c1"}}
        mock_post.return_value = mock_resp

        ok, msg, data = self.auth_svc.link_company("Demo Company", "GUID-99", "2025-2026")
        self.assertTrue(ok)
        self.assertIn("Company linked", msg)

    @patch("httpx.Client.get")
    def test_get_cloud_companies(self, mock_get):
        self.auth_svc.access_token = "tok_test_123"
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '{"success": true, "data": [{"companyName": "Demo Enterprise", "companyGuid": "G1"}]}'
        mock_resp.json.return_value = {"success": True, "data": [{"companyName": "Demo Enterprise", "companyGuid": "G1"}]}
        mock_get.return_value = mock_resp

        ok, companies = self.auth_svc.get_cloud_companies()
        self.assertTrue(ok)
        self.assertEqual(len(companies), 1)
        self.assertEqual(companies[0]["companyName"], "Demo Enterprise")

    @patch("httpx.Client.post")
    def test_sync_start(self, mock_post):
        self.auth_svc.access_token = "tok_test_123"
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '{"success": true, "message": "Sync started", "data": {"syncId": "sync_101"}}'
        mock_resp.json.return_value = {"success": True, "message": "Sync started", "data": {"syncId": "sync_101"}}
        mock_post.return_value = mock_resp

        ok, msg, data = self.auth_svc.sync_start("Demo Company", "G1", "FULL", 100)
        self.assertTrue(ok)
        self.assertEqual(data["syncId"], "sync_101")

    @patch("httpx.Client.post")
    def test_sync_batch(self, mock_post):
        self.auth_svc.access_token = "tok_test_123"
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '{"success": true, "message": "Batch synced", "data": {"synced": 2}}'
        mock_resp.json.return_value = {"success": True, "message": "Batch synced", "data": {"synced": 2}}
        mock_post.return_value = mock_resp

        ok, msg, data = self.auth_svc.sync_batch("sync_101", "Demo Company", "LEDGERS", [{"name": "L1"}, {"name": "L2"}], 1, True)
        self.assertTrue(ok)
        self.assertEqual(data["synced"], 2)

    @patch("httpx.Client.post")
    def test_sync_complete(self, mock_post):
        self.auth_svc.access_token = "tok_test_123"
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '{"success": true, "message": "Sync completed", "data": {"totalSynced": 100}}'
        mock_resp.json.return_value = {"success": True, "message": "Sync completed", "data": {"totalSynced": 100}}
        mock_post.return_value = mock_resp

        ok, msg, data = self.auth_svc.sync_complete("sync_101", "Demo Company", "COMPLETED", 100, 20205)
        self.assertTrue(ok)
        self.assertEqual(data["totalSynced"], 100)


if __name__ == "__main__":
    unittest.main()



