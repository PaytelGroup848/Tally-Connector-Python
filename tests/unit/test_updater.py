import unittest
from unittest.mock import patch, MagicMock
from shared.updater import parse_version_tuple, OTAUpdater


class TestOTAUpdater(unittest.TestCase):
    def test_parse_version_tuple(self):
        self.assertEqual(parse_version_tuple("1.0.0"), (1, 0, 0))
        self.assertEqual(parse_version_tuple("v1.2.3"), (1, 2, 3))
        self.assertEqual(parse_version_tuple("2.0"), (2, 0, 0))
        self.assertEqual(parse_version_tuple("1.0.1-beta"), (1, 0, 1))
        self.assertTrue(parse_version_tuple("1.0.1") > parse_version_tuple("1.0.0"))
        self.assertTrue(parse_version_tuple("1.1.0") > parse_version_tuple("1.0.9"))
        self.assertTrue(parse_version_tuple("2.0.0") > parse_version_tuple("1.9.9"))
        self.assertFalse(parse_version_tuple("1.0.0") > parse_version_tuple("1.0.0"))

    @patch("shared.auth.cloud_auth_service.cloud_auth_service.get_connector_version")
    def test_check_for_updates_newer_available(self, mock_get_version):
        mock_get_version.return_value = (
            True,
            "Success",
            {
                "latestVersion": "1.0.1",
                "downloadUrl": "https://ctrlbooks.com/downloads/CtrlBooks_Setup_v1.0.1.exe",
                "releaseNotes": "Fixes and performance updates.",
                "mandatory": False,
            }
        )

        updater = OTAUpdater()
        res = updater.check_for_updates("1.0.0")

        self.assertTrue(res["update_available"])
        self.assertEqual(res["latest_version"], "1.0.1")
        self.assertEqual(res["current_version"], "1.0.0")
        self.assertIn("v1.0.1.exe", res["download_url"])
        self.assertFalse(res["mandatory"])

    @patch("shared.auth.cloud_auth_service.cloud_auth_service.get_connector_version")
    def test_check_for_updates_already_latest(self, mock_get_version):
        mock_get_version.return_value = (
            True,
            "Success",
            {
                "latestVersion": "1.0.0",
                "downloadUrl": None,
                "releaseNotes": "Up to date",
            }
        )

        updater = OTAUpdater()
        res = updater.check_for_updates("1.0.0")

        self.assertFalse(res["update_available"])
        self.assertEqual(res["latest_version"], "1.0.0")

    @patch("shared.auth.cloud_auth_service.cloud_auth_service.get_connector_version")
    def test_check_for_updates_fallback_download_url(self, mock_get_version):
        mock_get_version.return_value = (
            True,
            "Success",
            {
                "latestVersion": "1.0.5",
                "downloadUrl": None,  # No explicit downloadUrl provided
            }
        )

        updater = OTAUpdater()
        res = updater.check_for_updates("1.0.0")

        self.assertTrue(res["update_available"])
        self.assertIsNotNone(res["download_url"])
        self.assertIn("CtrlBooks_Setup.exe", res["download_url"])


if __name__ == "__main__":
    unittest.main()
