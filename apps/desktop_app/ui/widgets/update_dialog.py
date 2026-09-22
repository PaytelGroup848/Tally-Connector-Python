"""
CtrlBooks - Update Available Notification Dialog
-----------------------------------------------------------
Modern modal pop-up that alerts user when a new software version
is available on the cloud server, displaying changelog notes,
version comparison, download progress, and 1-click update installation.
"""

import os
from typing import Dict, Any, Optional
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QFrame, QTextEdit, QApplication
)
from PySide6.QtCore import Qt, QThread, Signal, QUrl
from PySide6.QtGui import QDesktopServices, QColor
from PySide6.QtWidgets import QGraphicsDropShadowEffect

from shared.updater import updater_service
from shared.logging_config import get_logger

logger = get_logger("app.ui.update_dialog")


class UpdateDownloadThread(QThread):
    progress_signal = Signal(int, int)
    finished_signal = Signal(bool, str, str)

    def __init__(self, download_url: str, expected_sha256: Optional[str] = None):
        super().__init__()
        self.download_url = download_url
        self.expected_sha256 = expected_sha256

    def run(self):
        def on_progress(dl: int, total: int):
            self.progress_signal.emit(dl, total)

        success, path, err = updater_service.download_update(
            self.download_url, self.expected_sha256, progress_callback=on_progress
        )
        self.finished_signal.emit(success, path or "", err or "")


class UpdateAvailableDialog(QDialog):
    """
    Modal pop-up window displayed when an update is available.
    """

    def __init__(self, update_info: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.update_info = update_info or {}
        self.dl_thread: Optional[UpdateDownloadThread] = None

        self.setWindowTitle("Update Available - CtrlBooks")
        self.setFixedWidth(500)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self.setStyleSheet("""
            QDialog {
                background-color: #F8FAFC;
            }
        """)

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Main Card container
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 14px;
            }
        """)
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(15, 23, 42, 20))
        shadow.setOffset(0, 4)
        card.setGraphicsEffect(shadow)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setSpacing(14)

        # Header with icon and title
        header_row = QHBoxLayout()
        header_row.setSpacing(12)

        icon_lbl = QLabel("🚀")
        icon_lbl.setStyleSheet("font-size: 30px; border: none; background: transparent;")

        title_col = QVBoxLayout()
        title_col.setSpacing(2)

        title_lbl = QLabel("New Version Available!")
        title_lbl.setStyleSheet("font-size: 17px; font-weight: 800; color: #0F172A; border: none; background: transparent;")

        sub_lbl = QLabel("A new software update is ready for installation.")
        sub_lbl.setStyleSheet("font-size: 12px; color: #64748B; border: none; background: transparent;")

        title_col.addWidget(title_lbl)
        title_col.addWidget(sub_lbl)

        header_row.addWidget(icon_lbl)
        header_row.addLayout(title_col)
        header_row.addStretch()
        card_layout.addLayout(header_row)

        # Version Pill Box
        curr_ver = self.update_info.get("current_version", "1.0.0")
        latest_ver = self.update_info.get("latest_version", "1.0.1")

        ver_box = QFrame()
        ver_box.setStyleSheet("""
            QFrame {
                background-color: #F1F5F9;
                border: 1px solid #E2E8F0;
                border-radius: 8px;
                padding: 6px;
            }
        """)
        ver_layout = QHBoxLayout(ver_box)
        ver_layout.setContentsMargins(12, 8, 12, 8)

        lbl_curr = QLabel(f"Installed: <b>v{curr_ver}</b>")
        lbl_curr.setStyleSheet("font-size: 12px; color: #475569; border: none; background: transparent;")

        lbl_arrow = QLabel("➔")
        lbl_arrow.setStyleSheet("font-size: 13px; color: #94A3B8; font-weight: bold; border: none; background: transparent;")

        lbl_latest = QLabel(f"New: v{latest_ver}")
        lbl_latest.setStyleSheet("""
            background-color: #ECFDF5;
            color: #059669;
            font-size: 12px;
            font-weight: 800;
            border: 1px solid #A7F3D0;
            border-radius: 6px;
            padding: 2px 10px;
        """)

        ver_layout.addWidget(lbl_curr)
        ver_layout.addStretch()
        ver_layout.addWidget(lbl_arrow)
        ver_layout.addStretch()
        ver_layout.addWidget(lbl_latest)
        card_layout.addWidget(ver_box)

        # Release Notes / Description
        notes_text = self.update_info.get("release_notes") or "• Performance enhancements\n• Bug fixes and stability improvements\n• Tally synchronization optimizations"
        lbl_notes_title = QLabel("What's New in this Update:")
        lbl_notes_title.setStyleSheet("font-size: 12px; font-weight: 700; color: #334155; border: none; background: transparent;")
        card_layout.addWidget(lbl_notes_title)

        self.notes_box = QTextEdit()
        self.notes_box.setReadOnly(True)
        self.notes_box.setPlainText(str(notes_text))
        self.notes_box.setFixedHeight(85)
        self.notes_box.setStyleSheet("""
            QTextEdit {
                background-color: #F8FAFC;
                border: 1px solid #E2E8F0;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 11px;
                color: #334155;
                line-height: 1.4;
            }
        """)
        card_layout.addWidget(self.notes_box)

        # Mandatory Warning (if applicable)
        if self.update_info.get("mandatory"):
            lbl_mand = QLabel("⚠️ This update is required to maintain cloud synchronization.")
            lbl_mand.setStyleSheet("font-size: 11px; font-weight: bold; color: #D97706; border: none; background: transparent;")
            card_layout.addWidget(lbl_mand)

        # Download Progress Area (Initially Hidden)
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(12)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #CBD5E1;
                border-radius: 6px;
                text-align: center;
                background-color: #F1F5F9;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #10B981, stop:1 #059669);
                border-radius: 5px;
            }
        """)
        card_layout.addWidget(self.progress_bar)

        self.lbl_status = QLabel("")
        self.lbl_status.setVisible(False)
        self.lbl_status.setStyleSheet("font-size: 11px; color: #64748B; border: none; background: transparent;")
        card_layout.addWidget(self.lbl_status)

        layout.addWidget(card)

        # Action Buttons Row
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        self.btn_later = QPushButton("Remind Me Later")
        self.btn_later.setFixedHeight(40)
        self.btn_later.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_later.setStyleSheet("""
            QPushButton {
                background-color: #FFFFFF;
                border: 1.5px solid #CBD5E1;
                color: #475569;
                font-weight: 700;
                font-size: 12px;
                border-radius: 20px;
                padding: 0 18px;
            }
            QPushButton:hover {
                background-color: #F1F5F9;
                border-color: #94A3B8;
                color: #0F172A;
            }
        """)
        self.btn_later.clicked.connect(self.reject)

        self.btn_update = QPushButton("Download & Update Now")
        self.btn_update.setFixedHeight(40)
        self.btn_update.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_update.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #10B981, stop:1 #059669);
                color: #FFFFFF;
                font-weight: 800;
                font-size: 13px;
                border-radius: 20px;
                border: none;
                padding: 0 22px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #059669, stop:1 #047857);
            }
            QPushButton:disabled {
                background-color: #94A3B8;
                color: #E2E8F0;
            }
        """)
        self.btn_update.clicked.connect(self.start_update)

        if not self.update_info.get("mandatory"):
            btn_row.addWidget(self.btn_later)
        btn_row.addStretch()
        btn_row.addWidget(self.btn_update)
        layout.addLayout(btn_row)

    def start_update(self):
        download_url = self.update_info.get("download_url")
        if not download_url:
            self.lbl_status.setText("No download URL available.")
            self.lbl_status.setVisible(True)
            return

        self.btn_update.setEnabled(False)
        self.btn_later.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.lbl_status.setVisible(True)
        self.lbl_status.setText("Connecting to update server...")

        expected_sha = self.update_info.get("sha256")
        self.dl_thread = UpdateDownloadThread(download_url, expected_sha)
        self.dl_thread.progress_signal.connect(self.on_download_progress)
        self.dl_thread.finished_signal.connect(self.on_download_finished)
        self.dl_thread.start()

    def on_download_progress(self, downloaded: int, total: int):
        if total > 0:
            pct = int((downloaded / total) * 100)
            self.progress_bar.setValue(pct)
            mb_dl = downloaded / (1024 * 1024)
            mb_tot = total / (1024 * 1024)
            self.lbl_status.setText(f"Downloading update: {mb_dl:.1f} MB / {mb_tot:.1f} MB ({pct}%)")
        else:
            mb_dl = downloaded / (1024 * 1024)
            self.lbl_status.setText(f"Downloading update: {mb_dl:.1f} MB...")

    def on_download_finished(self, success: bool, dest_path: str, err_msg: str):
        self.btn_update.setEnabled(True)
        self.btn_later.setEnabled(True)

        if success and dest_path:
            self.progress_bar.setValue(100)
            self.lbl_status.setText("Download complete! Launching setup installer...")
            self.lbl_status.setStyleSheet("font-size: 11px; font-weight: bold; color: #059669; border: none;")

            # Launch installer and exit current application
            launched = updater_service.install_and_restart(dest_path)
            if launched:
                logger.info(f"Update installer launched ({dest_path}). Exiting current process for update.")
                QApplication.quit()
            else:
                self.lbl_status.setText(f"Installer downloaded at: {dest_path}")
        else:
            self.lbl_status.setText(f"Download error: {err_msg}")
            self.lbl_status.setStyleSheet("font-size: 11px; color: #EF4444; border: none;")

            # Fallback button to open download page in browser
            download_url = self.update_info.get("download_url")
            if download_url:
                self.btn_update.setText("Open Download in Browser")
                self.btn_update.clicked.disconnect()
                self.btn_update.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(download_url)))

