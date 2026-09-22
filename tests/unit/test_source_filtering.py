"""
Unit tests for Software-Specific Source Filtering (Tally vs BUSY).
"""

import sys
import unittest
from PySide6.QtWidgets import QApplication

from apps.desktop_app.ui.screens.connection_probe_screen import ConnectionProbeScreen
from apps.desktop_app.ui.screens.connected_dashboard_screen import ConnectedDashboardScreen

app = QApplication.instance()
if not app:
    app = QApplication(sys.argv)

class TestSourceFilteringUnit(unittest.TestCase):

    def test_01_probe_screen_source_signal_emission(self):
        screen = ConnectionProbeScreen()
        received_sources = []

        screen.connection_established_for_source.connect(lambda s: received_sources.append(s))

        screen.on_source_connect_clicked("TALLY")
        self.assertEqual(len(received_sources), 1)
        self.assertEqual(received_sources[0], "TALLY")

    def test_02_dashboard_source_tab_filtering(self):
        dash = ConnectedDashboardScreen()

        dash.set_source_filter("TALLY")
        self.assertEqual(dash.active_source_filter, "TALLY")
        dash.cleanup()

if __name__ == "__main__":
    unittest.main()
