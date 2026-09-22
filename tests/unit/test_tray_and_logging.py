"""
Unit tests for System Tray Icon & Qt Live Logging Handler.
"""

import sys
import logging
import unittest
from unittest.mock import MagicMock
from PySide6.QtWidgets import QApplication

from apps.desktop_app.ui.widgets.live_log_viewer import QtLogEmitter, QtLogHandler
from apps.desktop_app.ui.tray_icon import ConnectorSystemTray

app = QApplication.instance()
if not app:
    app = QApplication(sys.argv)


class TestTrayAndLoggingUnit(unittest.TestCase):

    def test_01_qt_log_handler_emission(self):
        emitter = QtLogEmitter()
        received_logs = []

        def on_log(ts, level, msg):
            received_logs.append((ts, level, msg))

        emitter.log_emitted.connect(on_log)

        handler = QtLogHandler(emitter)
        logger = logging.getLogger("test_logger")
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

        logger.info("Test sync log message")

        self.assertEqual(len(received_logs), 1)
        ts, level, msg = received_logs[0]
        self.assertEqual(level, "INFO")
        self.assertIn("Test sync log message", msg)

    def test_02_tray_icon_pause_state_toggle(self):
        tray = ConnectorSystemTray()
        self.assertFalse(tray.is_paused)

        tray.on_toggle_pause()
        self.assertTrue(tray.is_paused)

        tray.update_pause_state(False)
        self.assertFalse(tray.is_paused)


if __name__ == "__main__":
    unittest.main()
