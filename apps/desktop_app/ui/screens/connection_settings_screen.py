

from typing import Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QCheckBox, QProgressBar, QComboBox, QFrame, QGraphicsDropShadowEffect
)
from PySide6.QtCore import Signal, Qt, QThread
from PySide6.QtGui import QColor
from apps.desktop_app.ui.widgets.lk_header import CtrlBooksHeader
from apps.desktop_app.ui.widgets.lk_footer import CtrlBooksFooter
from shared.updater import updater_service
from shared.config import get_settings

class UpdateCheckThread(QThread):
    finished_signal = Signal(dict)

    def run(self):
        result = updater_service.check_for_updates()
        self.finished_signal.emit(result)

class UpdateDownloadThread(QThread):
    progress_signal = Signal(int, int)
    finished_signal = Signal(bool, str, str)

    def __init__(self, download_url: str, expected_sha256: Optional[str] = None):
        super().__init__()
        self.download_url = download_url
        self.expected_sha256 = expected_sha256

    def run(self):
        def on_progress(dl, total):
            self.progress_signal.emit(dl, total)

        success, path, err = updater_service.download_update(
            self.download_url, self.expected_sha256, progress_callback=on_progress
        )
        self.finished_signal.emit(success, path or "", err or "")

class ConnectionSettingsScreen(QWidget):
    back_requested = Signal()
    nav_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = get_settings()
        self.update_info = None
        self.downloaded_path = None
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.header = CtrlBooksHeader(title="Connection Settings", show_back=True)
        self.header.back_clicked.connect(self.back_requested.emit)
        self.header.nav_requested.connect(self.nav_requested.emit)
        layout.addWidget(self.header)

        body = QWidget()
        body.setStyleSheet("background-color: #F8FAFC;")
        body_layout = QVBoxLayout(body)
        body_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body_layout.setContentsMargins(18, 14, 18, 14)

        card = QFrame()
        card.setMaximumWidth(480)
        card.setStyleSheet("""
            QFrame#SettingsCard {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 16px;
            }
        """)
        card.setObjectName("SettingsCard")

        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(15, 23, 42, 20))
        shadow.setOffset(0, 4)
        card.setGraphicsEffect(shadow)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 18, 20, 18)
        card_layout.setSpacing(12)

        t_row = QHBoxLayout()
        t_row.setSpacing(16)

        t_lbl = QLabel("Connected")
        t_lbl.setStyleSheet("font-size: 12px; font-weight: 800; color: #1E293B; border: none; background: transparent;")

        self.auto_chk = QCheckBox("AUTO")
        self.auto_chk.setChecked(True)
        self.auto_chk.setStyleSheet("""
            QCheckBox {
                color: #059669;
                font-weight: 800;
                font-size: 11px;
                border: none;
                background: transparent;
            }
        """)

        from shared.system_startup import enable_run_on_startup, disable_run_on_startup, is_startup_enabled

        self.startup_chk = QCheckBox("Start with Windows")
        self.startup_chk.setChecked(is_startup_enabled())
        self.startup_chk.setStyleSheet("""
            QCheckBox {
                color: #334155;
                font-weight: 700;
                font-size: 11px;
                border: none;
                background: transparent;
            }
        """)
        self.startup_chk.toggled.connect(lambda val: enable_run_on_startup() if val else disable_run_on_startup())

        t_row.addStretch()
        t_row.addWidget(t_lbl)
        t_row.addWidget(self.auto_chk)
        t_row.addWidget(self.startup_chk)
        t_row.addStretch()
        card_layout.addLayout(t_row)

        hp_row = QHBoxLayout()
        hp_row.setSpacing(12)

        v_host = QVBoxLayout()
        v_host.setSpacing(4)
        lbl_h = QLabel("Host Name")
        lbl_h.setStyleSheet("font-size: 11px; font-weight: 700; color: #475569; border: none; background: transparent;")
        v_host.addWidget(lbl_h)
        self.host_input = QLineEdit("localhost")
        self.host_input.setFixedHeight(38)
        self.host_input.setStyleSheet("""
            QLineEdit {
                border: 1.5px solid #CBD5E1;
                border-radius: 8px;
                padding: 0 12px;
                font-size: 12px;
                background-color: #F8FAFC;
                color: #0F172A;
            }
            QLineEdit:focus {
                border: 1.5px solid #10B981;
                background-color: #FFFFFF;
            }
        """)
        v_host.addWidget(self.host_input)

        v_port = QVBoxLayout()
        v_port.setSpacing(4)
        lbl_p = QLabel("Port Number")
        lbl_p.setStyleSheet("font-size: 11px; font-weight: 700; color: #475569; border: none; background: transparent;")
        v_port.addWidget(lbl_p)
        self.port_input = QLineEdit("9000")
        self.port_input.setFixedHeight(38)
        self.port_input.setStyleSheet("""
            QLineEdit {
                border: 1.5px solid #CBD5E1;
                border-radius: 8px;
                padding: 0 12px;
                font-size: 12px;
                background-color: #F8FAFC;
                color: #0F172A;
            }
            QLineEdit:focus {
                border: 1.5px solid #10B981;
                background-color: #FFFFFF;
            }
        """)
        v_port.addWidget(self.port_input)

        hp_row.addLayout(v_host)
        hp_row.addLayout(v_port)
        card_layout.addLayout(hp_row)

        sync_row = QHBoxLayout()
        sync_row.setSpacing(8)

        sync_lbl = QLabel("Sync Interval Frequency:")
        sync_lbl.setStyleSheet("font-size: 12px; font-weight: 700; color: #334155; border: none; background: transparent;")

        self.interval_combo = QComboBox()
        self.interval_combo.addItems(["Real-time", "1 min", "5 mins", "15 mins", "1 hour", "Manual"])
        self.interval_combo.setCurrentText("5 mins")
        self.interval_combo.setFixedHeight(34)
        self.interval_combo.setFixedWidth(110)
        self.interval_combo.setStyleSheet("""
            QComboBox {
                border: 1.5px solid #CBD5E1;
                border-radius: 8px;
                padding: 0 8px;
                font-size: 11px;
                font-weight: bold;
                background-color: #FFFFFF;
                color: #0F172A;
            }
            QComboBox:focus {
                border-color: #10B981;
            }
        """)

        sync_row.addStretch()
        sync_row.addWidget(sync_lbl)
        sync_row.addWidget(self.interval_combo)
        sync_row.addStretch()
        card_layout.addLayout(sync_row)

        self.save_btn = QPushButton("Save Settings")
        self.save_btn.setFixedHeight(38)
        self.save_btn.setFixedWidth(170)
        self.save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #10B981, stop:1 #059669);
                color: #FFFFFF;
                font-weight: 800;
                border-radius: 19px;
                border: none;
                font-size: 13px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #059669, stop:1 #047857);
            }
            QPushButton:pressed {
                background-color: #047857;
            }
        """)
        self.save_btn.clicked.connect(self.save_settings)
        card_layout.addWidget(self.save_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("background-color: #E2E8F0; border: none; max-height: 1px; margin: 4px 0;")
        card_layout.addWidget(divider)

        ota_lbl = QLabel("App Version & Updates")
        ota_lbl.setStyleSheet("font-size: 13px; font-weight: 800; color: #334155; border: none; background: transparent;")
        card_layout.addWidget(ota_lbl, alignment=Qt.AlignmentFlag.AlignCenter)

        ver_text = f"Current Version: v{self.settings.app_version}"
        self.lbl_update_status = QLabel(ver_text)
        self.lbl_update_status.setStyleSheet("font-size: 11px; color: #64748B; border: none; background: transparent;")
        card_layout.addWidget(self.lbl_update_status, alignment=Qt.AlignmentFlag.AlignCenter)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(10)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar { border: 1px solid #CBD5E1; border-radius: 5px; text-align: center; }
            QProgressBar::chunk { background-color: #10B981; border-radius: 5px; }
        """)
        card_layout.addWidget(self.progress_bar)

        upd_btn_row = QHBoxLayout()
        self.btn_check_updates = QPushButton("Check for Updates")
        self.btn_check_updates.setFixedHeight(36)
        self.btn_check_updates.setFixedWidth(160)
        self.btn_check_updates.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_check_updates.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0284C7, stop:1 #0369A1);
                color: #FFFFFF;
                font-weight: 800;
                border-radius: 18px;
                border: none;
                font-size: 12px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0369A1, stop:1 #075985);
            }
            QPushButton:pressed {
                background-color: #075985;
            }
        """)
        self.btn_check_updates.clicked.connect(self.check_for_updates)

        self.btn_install_update = QPushButton("Download & Install")
        self.btn_install_update.setFixedHeight(36)
        self.btn_install_update.setFixedWidth(160)
        self.btn_install_update.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_install_update.setVisible(False)
        self.btn_install_update.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #D97706, stop:1 #B45309);
                color: #FFFFFF;
                font-weight: 800;
                border-radius: 18px;
                border: none;
                font-size: 12px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #B45309, stop:1 #92400E);
            }
        """)
        self.btn_install_update.clicked.connect(self.download_and_install_update)

        upd_btn_row.addStretch()
        upd_btn_row.addWidget(self.btn_check_updates)
        upd_btn_row.addWidget(self.btn_install_update)
        upd_btn_row.addStretch()
        card_layout.addLayout(upd_btn_row)

        body_layout.addWidget(card)
        layout.addWidget(body, stretch=1)

        self.footer = CtrlBooksFooter()
        layout.addWidget(self.footer)

    def save_settings(self):
        try:
            import httpx
            payload = {
                "host": self.host_input.text().strip(),
                "port": int(self.port_input.text().strip() or "9000"),
                "auto_connect": self.auto_chk.isChecked(),
                "sync_interval_minutes": self.interval_combo.currentText(),
            }
            from shared.config import get_settings
            gateway = get_settings().gateway_url.rstrip("/")
            httpx.post(f"{gateway}/api/system/settings/connection", json=payload, timeout=2.0)
        except Exception:

            pass
        self.save_btn.setText("Settings Saved ✓")
        self.save_btn.setStyleSheet("background-color: #059669; color: white; font-weight: 800; border-radius: 19px; border: none; font-size: 13px;")

    def check_for_updates(self):
        self.btn_check_updates.setEnabled(False)
        self.lbl_update_status.setText("Checking Cloud API for updates...")

        self.check_thread = UpdateCheckThread()
        self.check_thread.finished_signal.connect(self.on_update_check_finished)
        self.check_thread.start()

    def on_update_check_finished(self, result: dict):
        self.btn_check_updates.setEnabled(True)
        if result.get("update_available"):
            latest = result.get("latest_version")
            self.update_info = result
            self.lbl_update_status.setText(f"New Version Available: v{latest} 🎉")
            self.lbl_update_status.setStyleSheet("font-size: 11px; font-weight: bold; color: #00C853;")
            self.btn_install_update.setVisible(True)

            try:
                from apps.desktop_app.ui.widgets.update_dialog import UpdateAvailableDialog
                dlg = UpdateAvailableDialog(result, parent=self)
                dlg.exec()
            except Exception:
                pass
        else:
            self.lbl_update_status.setText(f"App is up to date (v{self.settings.app_version}) ✓")
            self.lbl_update_status.setStyleSheet("font-size: 11px; color: #64748B;")
            self.btn_install_update.setVisible(False)

    def download_and_install_update(self):
        if not self.update_info or not self.update_info.get("download_url"):
            self.lbl_update_status.setText("No download URL available.")
            return

        self.btn_install_update.setEnabled(False)
        self.btn_check_updates.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.lbl_update_status.setText("Downloading update package...")

        d_url = str(self.update_info["download_url"])
        s_sha = self.update_info.get("sha256")
        if s_sha is not None:
            s_sha = str(s_sha)

        self.dl_thread = UpdateDownloadThread(d_url, s_sha)
        self.dl_thread.progress_signal.connect(self.on_download_progress)
        self.dl_thread.finished_signal.connect(self.on_download_finished)
        self.dl_thread.start()

    def on_download_progress(self, downloaded: int, total: int):
        if total > 0:
            pct = int((downloaded / total) * 100)
            self.progress_bar.setValue(pct)

    def on_download_finished(self, success: bool, dest_path: str, err_msg: str):
        self.btn_install_update.setEnabled(True)
        self.btn_check_updates.setEnabled(True)

        if success and dest_path:
            self.downloaded_path = dest_path
            self.progress_bar.setValue(100)
            self.lbl_update_status.setText("Update verified! Launching setup installer...")
            self.lbl_update_status.setStyleSheet("font-size: 11px; font-weight: bold; color: #00C853;")

            launched = updater_service.install_and_restart(dest_path)
            if launched:
                from PySide6.QtWidgets import QApplication
                QApplication.quit()
        else:
            self.progress_bar.setVisible(False)
            self.lbl_update_status.setText(f"Update failed: {err_msg}")
            self.lbl_update_status.setStyleSheet("font-size: 11px; color: #EF4444;")
