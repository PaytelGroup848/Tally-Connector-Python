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

    @patch("requests.get", side_effect=Exception("Network Offline"))
    @patch("shared.auth.cloud_auth_service.cloud_auth_service.get_connector_version")
    def test_check_for_updates_newer_available(self, mock_get_version, mock_req):
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

    @patch("requests.get", side_effect=Exception("Network Offline"))
    @patch("shared.auth.cloud_auth_service.cloud_auth_service.get_connector_version")
    def test_check_for_updates_already_latest(self, mock_get_version, mock_req):
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

    @patch("requests.get", side_effect=Exception("Network Offline"))
    @patch("shared.auth.cloud_auth_service.cloud_auth_service.get_connector_version")
    def test_check_for_updates_fallback_download_url(self, mock_get_version, mock_req):
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

    @patch("requests.get")
    def test_download_update_identity_encoding_and_granular_progress(self, mock_get):
        import hashlib
        payload = b"CTRLBOOKS_BINARY_DATA" * 4000
        expected_hash = hashlib.sha256(payload).hexdigest()
        mid = len(payload) // 2

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"content-length": str(len(payload))}
        mock_resp.iter_content.return_value = [payload[:mid], payload[mid:]]
        mock_get.return_value = mock_resp

        seen_progress = []
        updater = OTAUpdater()
        ok, path, err = updater.download_update(
            "http://127.0.0.1:8000/downloads/CtrlBooks_Setup_v1.0.3.exe",
            expected_sha256=expected_hash,
            progress_callback=lambda dl, tot: seen_progress.append((dl, tot)),
        )
        self.assertTrue(ok, err)
        self.assertIsNotNone(path)
        mock_get.assert_called_once()
        call_headers = mock_get.call_args.kwargs.get("headers") or {}
        self.assertEqual(call_headers.get("Accept-Encoding"), "identity")
        mock_resp.iter_content.assert_called_once_with(chunk_size=65536)
        self.assertEqual(seen_progress[-1], (len(payload), len(payload)))
        import os
        if path and os.path.exists(path):
            os.remove(path)

    def test_update_dialog_serial_one_by_one_percentage(self):
        import sys
        from PySide6.QtWidgets import QApplication
        from apps.desktop_app.ui.widgets.update_dialog import UpdateAvailableDialog

        app = QApplication.instance() or QApplication(sys.argv)
        dlg = UpdateAvailableDialog({"current_version": "1.0.2", "latest_version": "1.0.3", "download_url": "http://example.com/app.exe"})
        dlg.on_download_progress(5 * 1024 * 1024, 100 * 1024 * 1024)
        self.assertEqual(dlg._target_pct, 5)
        steps = []
        for _ in range(5):
            dlg._step_progress_pct()
            steps.append(dlg.progress_bar.value())
        self.assertEqual(steps, [1, 2, 3, 4, 5])
        dlg.close()

    def test_selective_gzip_skips_downloads(self):
        import asyncio
        from apps.backend.gateway.main import SelectiveGZipMiddleware

        called_direct = []

        async def dummy_app(scope, receive, send):
            called_direct.append(scope["path"])

        mw = SelectiveGZipMiddleware(dummy_app, minimum_size=1000)
        asyncio.run(mw({"type": "http", "path": "/downloads/CtrlBooks_Setup_v1.0.3.exe"}, None, None))
        self.assertEqual(called_direct, ["/downloads/CtrlBooks_Setup_v1.0.3.exe"])


if __name__ == "__main__":
    unittest.main()
