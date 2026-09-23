"""
Unit tests for Central Cloud Authentication Client (send_otp, verify_otp, refresh, logout, me).
"""

import unittest
from unittest.mock import patch, MagicMock
from shared.auth.cloud_auth_service import CloudAuthService, get_or_create_device_id


class TestCloudAuthService(unittest.TestCase):

    def setUp(self):
        self.auth_svc = CloudAuthService(base_url="https://connector.cloudata.in/api/connector")
        self.auth_svc.sync_user_to_mongodb = MagicMock()
        def mock_save(access_token, refresh_token=None, user=None):
            self.auth_svc.access_token = access_token
            self.auth_svc.refresh_token_val = refresh_token
            if user:
                self.auth_svc.current_user = user
        self.auth_svc.save_session = mock_save

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

    @patch("shared.auth.cloud_auth_service.AUTH_SESSION_FILE")
    @patch("httpx.Client.post")
    def test_logout(self, mock_post, mock_session_file):
        mock_session_file.exists.return_value = False
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

    @patch("httpx.Client.post")
    def test_send_heartbeat_success(self, mock_post):
        self.auth_svc.access_token = "tok_test_123"
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '{"success": true, "message": "Heartbeat recorded", "data": {"status": "ONLINE", "tallyConnected": true}}'
        mock_resp.json.return_value = {"success": True, "message": "Heartbeat recorded", "data": {"status": "ONLINE", "tallyConnected": True}}
        mock_post.return_value = mock_resp

        ok, msg, data = self.auth_svc.send_heartbeat(tally_connected=True)
        self.assertTrue(ok)
        self.assertEqual(data["status"], "ONLINE")
        self.assertTrue(data["tallyConnected"])
        mock_post.assert_called_once()

    @patch("socket.socket")
    def test_is_tally_online_check(self, mock_socket_cls):
        mock_sock = MagicMock()
        mock_sock.connect_ex.return_value = 0
        mock_socket_cls.return_value = mock_sock

        is_online = self.auth_svc.is_tally_online("127.0.0.1", 9000)
        self.assertTrue(is_online)

        mock_sock.connect_ex.return_value = 111
        is_online_fail = self.auth_svc.is_tally_online("127.0.0.1", 9000)
        self.assertFalse(is_online_fail)


if __name__ == "__main__":
    unittest.main()



