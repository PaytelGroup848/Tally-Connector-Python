

from pathlib import Path
from PySide6.QtWidgets import QSystemTrayIcon, QMenu, QStyle, QApplication, QMessageBox
from PySide6.QtCore import Signal
from PySide6.QtGui import QIcon
from shared.logging_config import get_logger

logger = get_logger("app.ui.tray")

class ConnectorSystemTray(QSystemTrayIcon):
    open_dashboard_requested = Signal()
    sync_now_requested = Signal()
    toggle_pause_requested = Signal()
    check_updates_requested = Signal()
    exit_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_paused = False
        self.init_ui()

    def init_ui(self):
        from apps.desktop_app.ui.asset_helper import get_asset_path
        icon_path = get_asset_path("app_icon.png")
        if icon_path.exists():
            self.setIcon(QIcon(str(icon_path)))
        else:
            style = QApplication.style()
            if style is not None:
                self.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_ComputerIcon))

        self.setToolTip("CtrlBooks - Background Sync Active")

        self.menu = QMenu()

        self.action_open = self.menu.addAction("Open Dashboard")
        self.action_open.triggered.connect(self.open_dashboard_requested.emit)

        self.menu.addSeparator()

        self.action_sync_now = self.menu.addAction("Sync Now")
        self.action_sync_now.triggered.connect(self.sync_now_requested.emit)

        self.action_pause = self.menu.addAction("Pause Sync")
        self.action_pause.triggered.connect(self.on_toggle_pause)

        self.menu.addSeparator()

        self.action_check_updates = self.menu.addAction("Check for Updates")
        self.action_check_updates.triggered.connect(self.check_updates_requested.emit)

        self.action_exit = self.menu.addAction("Quit / Exit")
        self.action_exit.triggered.connect(self.on_confirm_exit)

        self.setContextMenu(self.menu)

        self.activated.connect(self.on_tray_activated)
        self.show()

    def on_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.open_dashboard_requested.emit()

    def on_toggle_pause(self):
        self.is_paused = not self.is_paused
        self.action_pause.setText("Resume Sync" if self.is_paused else "Pause Sync")
        self.toggle_pause_requested.emit()
        status_text = "paused" if self.is_paused else "resumed"
        self.show_toast("Sync Status", f"Background data sync has been {status_text}.")

    def update_pause_state(self, is_paused: bool):
        self.is_paused = is_paused
        self.action_pause.setText("Resume Sync" if self.is_paused else "Pause Sync")

    def on_confirm_exit(self):
        reply = QMessageBox.question(
            None,
            "Quit CtrlBooks",
            "Are you sure you want to exit?\nBackground data synchronization will be paused.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.exit_requested.emit()

    def show_toast(self, title: str, message: str, icon: QSystemTrayIcon.MessageIcon = QSystemTrayIcon.MessageIcon.Information):
        """Displays Windows native toast notification."""
        try:
            self.showMessage(title, message, icon, 3000)
            logger.info(f"System Tray Toast: [{title}] {message}")
        except Exception as exc:
            logger.warning(f"Unable to show system tray toast: {exc}")
