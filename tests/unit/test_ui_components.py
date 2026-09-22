"""
Unit tests for Desktop Application UI Components & Widgets.
"""

import sys
import unittest
from unittest.mock import MagicMock, patch
from PySide6.QtWidgets import QApplication

from apps.desktop_app.ui.widgets.lk_header import CtrlBooksHeader
from apps.desktop_app.ui.widgets.live_log_viewer import LiveLogViewerWidget
from apps.desktop_app.ui.tray_icon import ConnectorSystemTray

app = QApplication.instance()
if not app:
    app = QApplication(sys.argv)


class TestUIComponentsUnit(unittest.TestCase):

    def test_01_header_status_pulse_update(self):
        header = CtrlBooksHeader()
        header.update_connection_status(True, "Tally Prime", 9000)
        self.assertIn("Tally Prime", header.status_pulse.text())
        self.assertIn("9000", header.status_pulse.text())

        header.update_connection_status(False)
        self.assertIn("Offline", header.status_pulse.text())

    def test_02_header_last_sync_update(self):
        header = CtrlBooksHeader()
        header.update_last_sync("2 mins ago")
        self.assertIn("2 mins ago", header.last_sync_lbl.text())

    def test_03_live_log_viewer_append_and_clear(self):
        viewer = LiveLogViewerWidget()
        viewer.append_log("11:20:01", "INFO", "Synced 50 Ledgers")
        self.assertIn("Synced 50 Ledgers", viewer.log_display.toPlainText())

        viewer.clear_logs()
        self.assertEqual(viewer.log_display.toPlainText(), "")

    @patch("PySide6.QtWidgets.QMessageBox.question")
    def test_04_tray_exit_confirmation(self, mock_question):
        from PySide6.QtWidgets import QMessageBox
        mock_question.return_value = QMessageBox.Yes

        tray = ConnectorSystemTray()
        exit_emitted = []
        tray.exit_requested.connect(lambda: exit_emitted.append(True))

        tray.on_confirm_exit()

        mock_question.assert_called_once()
        self.assertTrue(len(exit_emitted) == 1)

    def test_05_activity_history_screen_instantiation(self):
        from apps.desktop_app.ui.screens.activity_history_screen import ActivityHistoryScreen
        screen = ActivityHistoryScreen()
        self.assertIsNotNone(screen)
        self.assertIsNotNone(screen.header)

    def test_06_connection_probe_screen_instantiation(self):
        from apps.desktop_app.ui.screens.connection_probe_screen import ConnectionProbeScreen
        screen = ConnectionProbeScreen()
        self.assertIsNotNone(screen)

    def test_07_connection_settings_screen_instantiation(self):
        from apps.desktop_app.ui.screens.connection_settings_screen import ConnectionSettingsScreen
        screen = ConnectionSettingsScreen()
        self.assertIsNotNone(screen)

    def test_08_profile_and_system_screens_instantiation(self):
        from apps.desktop_app.ui.screens.profile_screen import ProfileScreen
        from apps.desktop_app.ui.screens.system_requirement_screen import SystemRequirementScreen
        profile = ProfileScreen()
        system = SystemRequirementScreen()
        self.assertIsNotNone(profile)
        self.assertIsNotNone(system)

    def test_09_dynamic_company_card_stats(self):
        from apps.desktop_app.ui.screens.connected_dashboard_screen import ConnectedDashboardScreen
        screen = ConnectedDashboardScreen()
        stats = {"ledgers": 500, "vouchers": 12000, "items": 350}
        card = screen.create_company_card("Test Corp", "C:\\Data", True, "TALLY", stats=stats)
        self.assertEqual(card.chip_ledgers.text(), "500 Ledgers")
        self.assertEqual(card.chip_vouchers.text(), "12,000 Vouchers")
        self.assertEqual(card.chip_items.text(), "350 Items")

    @patch("httpx.post")
    def test_10_fetch_tally_company_statistics(self, mock_post):
        from apps.desktop_app.ui.threads.company_fetch_worker import fetch_tally_company_statistics
        sample_xml = """<ENVELOPE>
            <STATNAME>Sales</STATNAME><STATVALUE><STATDIRECT>10</STATDIRECT></STATVALUE>
            <STATNAME>Purchase</STATNAME><STATVALUE><STATDIRECT>5</STATDIRECT></STATVALUE>
            <STATNAME>Ledgers</STATNAME><STATVALUE><STATDIRECT>120</STATDIRECT></STATVALUE>
            <STATNAME>Stock Items</STATNAME><STATVALUE><STATDIRECT>45</STATDIRECT></STATVALUE>
        </ENVELOPE>"""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = sample_xml
        mock_post.return_value = mock_resp

        res = fetch_tally_company_statistics("Mock Company")
        self.assertEqual(res["ledgers"], 120)
        self.assertEqual(res["items"], 45)
        self.assertEqual(res["vouchers"], 15)


if __name__ == "__main__":
    unittest.main()

