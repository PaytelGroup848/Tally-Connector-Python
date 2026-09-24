"""
Unit tests for Windows Credential Manager Session Storage & 24-Hour Expiry
"""

import unittest
import time
from unittest.mock import patch, MagicMock

from shared.auth.win_credential_store import (
    save_persisted_session,
    load_persisted_session,
    clear_persisted_session,
    CRED_TARGET_NAME,
    SESSION_LIFETIME_SECONDS,
)
from shared.auth.cloud_auth_service import CloudAuthService


class TestWinCredentialStore(unittest.TestCase):
    def setUp(self):
        clear_persisted_session()

    def tearDown(self):
        clear_persisted_session()

    def test_01_save_and_load_valid_session(self):
        """Verify saving a session stores data and can be retrieved within 24 hours."""
        user_info = {
            "id": "usr_9988",
            "email": "test_win_cred@ctrlbooks.com",
            "full_name": "WinCred User",
            "role": "User"
        }
        ok = save_persisted_session(
            username="test_win_cred@ctrlbooks.com",
            access_token="mock_access_token_abc_123",
            refresh_token="mock_refresh_token_xyz_789",
            user_dict=user_info,
            ttl_seconds=86400  # 24 hours
        )
        self.assertTrue(ok)

        loaded = load_persisted_session()
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["username"], "test_win_cred@ctrlbooks.com")
        self.assertEqual(loaded["access_token"], "mock_access_token_abc_123")
        self.assertEqual(loaded["refresh_token"], "mock_refresh_token_xyz_789")
        self.assertEqual(loaded["user"]["id"], "usr_9988")
        self.assertGreater(loaded["expires_at"], int(time.time()))

    def test_02_expired_session_purged_automatically(self):
        """Verify that sessions exceeding TTL are purged and return None."""
        user_info = {"id": "usr_expired", "email": "expired@ctrlbooks.com"}

        # Save with negative/past TTL so it is already expired
        save_persisted_session(
            username="expired@ctrlbooks.com",
            access_token="expired_token",
            user_dict=user_info,
            ttl_seconds=-10  # Expired 10 seconds ago
        )

        loaded = load_persisted_session()
        self.assertIsNone(loaded, "Expired session must return None")

        # Second load should also be None as it was purged
        self.assertIsNone(load_persisted_session())

    def test_03_clear_persisted_session(self):
        """Verify clear_persisted_session deletes the credential."""
        save_persisted_session(
            username="to_delete@ctrlbooks.com",
            access_token="delete_me_token"
        )
        self.assertIsNotNone(load_persisted_session())

        del_ok = clear_persisted_session()
        self.assertTrue(del_ok)
        self.assertIsNone(load_persisted_session())

    def test_04_cloud_auth_service_integration(self):
        """Verify CloudAuthService save_session, load_session, and logout with Windows Credential Manager."""
        service = CloudAuthService()
        dummy_user = {"id": "u1", "email": "cloud_win@ctrlbooks.com", "username": "cloud_win"}

        # Save session
        service.save_session(
            access_token="cat_token_999",
            refresh_token="crt_token_999",
            user=dummy_user
        )
        self.assertTrue(service.is_authenticated)

        # Clear in-memory state and reload
        service.access_token = None
        service.current_user = {}
        self.assertFalse(service.is_authenticated)

        service.load_session()
        self.assertTrue(service.is_authenticated)
        self.assertEqual(service.access_token, "cat_token_999")
        self.assertEqual(service.current_user.get("id"), "u1")

        # Logout should clear Windows Credential Manager
        service.logout()
        self.assertFalse(service.is_authenticated)
        self.assertIsNone(load_persisted_session())


if __name__ == "__main__":
    unittest.main()

