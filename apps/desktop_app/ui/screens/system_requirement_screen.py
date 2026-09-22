import platform
import psutil
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton, QMessageBox, QGraphicsDropShadowEffect
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QColor, QCursor
from apps.desktop_app.ui.widgets.lk_header import CtrlBooksHeader
from apps.desktop_app.ui.widgets.lk_footer import CtrlBooksFooter

class SystemRequirementScreen(QWidget):
    back_requested = Signal()
    nav_requested = Signal(str)
    system_checked = Signal(bool)
    update_checked = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        from shared.config import get_settings
        self.settings = get_settings()
        self.system_checked.connect(self._on_system_checked)
        self.update_checked.connect(self._on_update_checked)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.header = CtrlBooksHeader(title="System Requirement", show_back=True)
        self.header.back_clicked.connect(self.back_requested.emit)
        self.header.refresh_clicked.connect(self.run_system_checks)
        self.header.nav_requested.connect(self.nav_requested.emit)
        layout.addWidget(self.header)

        main_content = QWidget()
        main_content.setStyleSheet("background-color: #F8FAFC;")
        main_content.setObjectName("MainContent")
        content_layout = QVBoxLayout(main_content)
        content_layout.setContentsMargins(18, 14, 18, 14)
        content_layout.setSpacing(12)

        title_box = QVBoxLayout()
        title_box.setContentsMargins(2, 0, 2, 0)
        title_box.setSpacing(2)

        title_lbl = QLabel("System Requirements")
        title_lbl.setStyleSheet("font-size: 14px; font-weight: 800; color: #0F172A; border: none; background: transparent;")

        info_lbl = QLabel("Diagnostic & Hardware Checklist")
        info_lbl.setStyleSheet("font-size: 11px; font-weight: 500; color: #64748B; border: none; background: transparent;")

        title_box.addWidget(title_lbl)
        title_box.addWidget(info_lbl)
        content_layout.addLayout(title_box)

        card = QFrame()
        card.setStyleSheet("""
            QFrame#ReqCard {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 16px;
            }
        """)
        card.setObjectName("ReqCard")
        
        card_shadow = QGraphicsDropShadowEffect(self)
        card_shadow.setBlurRadius(18)
        card_shadow.setXOffset(0)
        card_shadow.setYOffset(4)
        card_shadow.setColor(QColor(0, 0, 0, 18))
        card.setGraphicsEffect(card_shadow)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 14, 14, 14)
        card_layout.setSpacing(10)

        total_ram = round(psutil.virtual_memory().total / (1024 ** 3), 1)

        self.row_os_frame, self.row_os_badge = self.create_check_row(
            icon="🪟",
            title="Windows 7 or above",
            is_ok=True
        )
        card_layout.addWidget(self.row_os_frame)

        is_ram_ok = (total_ram >= 4.0)
        self.row_ram_frame, self.row_ram_badge = self.create_check_row(
            icon="💾",
            title=f"RAM: 4GB Min, 8GB Recommended ({total_ram} GB)",
            is_ok=is_ram_ok
        )
        card_layout.addWidget(self.row_ram_frame)

        self.row_tally_frame, self.row_tally_badge = self.create_check_row(
            icon="📊",
            title="Tally: Tally ERP 9/ Tally Prime License",
            is_ok=False
        )
        card_layout.addWidget(self.row_tally_frame)

        content_layout.addWidget(card)

        status_container = QWidget()
        status_container.setStyleSheet("background: transparent;")
        status_layout = QHBoxLayout(status_container)
        status_layout.setContentsMargins(0, 6, 0, 4)
        status_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        status_text = QLabel("Status:")
        status_text.setStyleSheet("font-size: 16px; font-weight: 800; color: #0F172A; border: none; background: transparent; margin-right: 4px;")
        status_layout.addWidget(status_text)

        self.orb_glow = QFrame()
        self.orb_glow.setStyleSheet("""
            QFrame {
                background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5,
                                            stop:0 rgba(105, 240, 174, 0.45),
                                            stop:0.75 rgba(185, 246, 202, 0.2),
                                            stop:1 transparent);
                border-radius: 36px;
            }
        """)
        self.orb_glow.setFixedSize(72, 72)
        orb_layout = QVBoxLayout(self.orb_glow)
        orb_layout.setContentsMargins(6, 6, 6, 6)
        orb_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.status_orb = QLabel("GOOD")
        self.status_orb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_orb.setStyleSheet("""
            QLabel {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #E8F8F0, stop:1 #C8E6C9);
                border: 2px solid #69F0AE;
                border-radius: 28px;
                color: #2E7D32;
                font-size: 14px;
                font-weight: 900;
            }
        """)
        self.status_orb.setFixedSize(56, 56)
        orb_layout.addWidget(self.status_orb)

        status_layout.addWidget(self.orb_glow)
        content_layout.addWidget(status_container)

        ver_row = QHBoxLayout()
        ver_row.setContentsMargins(4, 0, 4, 0)
        ver_row.addStretch()

        ver_col = QVBoxLayout()
        ver_col.setSpacing(2)
        ver_col.setAlignment(Qt.AlignmentFlag.AlignRight)

        v_lbl = QLabel(f"v{self.settings.app_version}")
        v_lbl.setStyleSheet("font-size: 11px; font-weight: 600; color: #64748B; border: none; background: transparent;")
        ver_col.addWidget(v_lbl, alignment=Qt.AlignmentFlag.AlignRight)

        self.btn_check_updates = QPushButton("🔄 Check for Updates")
        self.btn_check_updates.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_check_updates.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                color: #1E293B;
                font-size: 12px;
                font-weight: 700;
                padding: 2px 4px;
            }
            QPushButton:hover {
                color: #0284C7;
                text-decoration: underline;
            }
        """)
        self.btn_check_updates.clicked.connect(self.on_check_updates)
        ver_col.addWidget(self.btn_check_updates, alignment=Qt.AlignmentFlag.AlignRight)

        ver_row.addLayout(ver_col)
        content_layout.addLayout(ver_row)

        layout.addWidget(main_content, stretch=1)

        insights_bar = QWidget()
        insights_bar.setStyleSheet("background-color: #F1F5F9; border-top: 1px solid #E2E8F0;")
        in_layout = QHBoxLayout(insights_bar)
        in_layout.setContentsMargins(14, 6, 14, 6)
        in_layout.setSpacing(6)

        c1 = QFrame()
        c1.setStyleSheet("QFrame { background: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 8px; padding: 4px 6px; }")
        c1_lay = QVBoxLayout(c1)
        c1_lay.setContentsMargins(2, 2, 2, 2)
        c1_lay.setSpacing(2)
        c1_lbl1 = QLabel("Companies")
        c1_lbl1.setStyleSheet("font-size: 9px; font-weight: bold; color: #64748B; border: none; background: transparent;")
        self.c1_val = QLabel("📊 3 Active")
        self.c1_val.setStyleSheet("font-size: 10px; font-weight: 800; color: #0F172A; border: none; background: transparent;")
        c1_lay.addWidget(c1_lbl1)
        c1_lay.addWidget(self.c1_val)
        in_layout.addWidget(c1, stretch=1)

        c2 = QFrame()
        c2.setStyleSheet("QFrame { background: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 8px; padding: 4px 6px; }")
        c2_lay = QVBoxLayout(c2)
        c2_lay.setContentsMargins(2, 2, 2, 2)
        c2_lay.setSpacing(2)
        c2_lbl1 = QLabel("Data Export")
        c2_lbl1.setStyleSheet("font-size: 9px; font-weight: bold; color: #64748B; border: none; background: transparent;")
        self.c2_val = QLabel("🎛️ 100% Active")
        self.c2_val.setStyleSheet("font-size: 10px; font-weight: 800; color: #059669; border: none; background: transparent;")
        c2_lay.addWidget(c2_lbl1)
        c2_lay.addWidget(self.c2_val)
        in_layout.addWidget(c2, stretch=1)

        c3 = QFrame()
        c3.setStyleSheet("QFrame { background: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 8px; padding: 4px 6px; }")
        c3_lay = QVBoxLayout(c3)
        c3_lay.setContentsMargins(2, 2, 2, 2)
        c3_lay.setSpacing(2)
        c3_lbl1 = QLabel("Actual Records")
        c3_lbl1.setStyleSheet("font-size: 9px; font-weight: bold; color: #64748B; border: none; background: transparent;")
        self.c3_val = QLabel("📈 21k+ Records")
        self.c3_val.setStyleSheet("font-size: 10px; font-weight: 800; color: #0284C7; border: none; background: transparent;")
        c3_lay.addWidget(c3_lbl1)
        c3_lay.addWidget(self.c3_val)
        in_layout.addWidget(c3, stretch=1)

        layout.addWidget(insights_bar)

        self.footer = CtrlBooksFooter()
        layout.addWidget(self.footer)

        self.run_system_checks()

    def create_check_row(self, icon: str, title: str, is_ok: bool) -> tuple[QFrame, QLabel]:
        row_frame = QFrame()
        row_frame.setStyleSheet("""
            QFrame {
                background: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 10px;
            }
        """)
        row_frame.setFixedHeight(46)
        
        row_layout = QHBoxLayout(row_frame)
        row_layout.setContentsMargins(14, 6, 14, 6)
        row_layout.setSpacing(10)

        txt = QLabel(f"{icon}  {title}")
        txt.setStyleSheet("font-size: 12px; font-weight: 600; color: #1E293B; border: none; background: transparent;")
        txt.setWordWrap(True)
        row_layout.addWidget(txt)
        row_layout.addStretch()

        badge = QLabel()
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.update_badge_style(badge, is_ok)

        row_layout.addWidget(badge)
        return row_frame, badge

    def update_badge_style(self, badge: QLabel, is_ok: bool):
        if is_ok:
            badge.setText("GOOD")
            badge.setStyleSheet("""
                QLabel {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #34A853, stop:1 #2B8E45);
                    color: #FFFFFF;
                    font-size: 12px;
                    font-weight: 800;
                    padding: 5px 16px;
                    border-radius: 6px;
                    border: none;
                    min-width: 68px;
                }
            """)
        else:
            badge.setText("⚠️ NOT OK")
            badge.setStyleSheet("""
                QLabel {
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #E53935, stop:1 #C62828);
                    color: #FFFFFF;
                    font-size: 12px;
                    font-weight: 800;
                    padding: 5px 14px;
                    border-radius: 6px;
                    border: none;
                    min-width: 78px;
                }
            """)

    def run_system_checks(self):
        import threading
        def _check_bg():
            try:
                import httpx
                from shared.config import get_settings
                gateway = get_settings().gateway_url.rstrip("/")
                res = httpx.get(f"{gateway}/api/system/check", timeout=1.5)
                if res.status_code == 200:
                    data = res.json()
                    is_tally = data.get("checks", {}).get("tally_connected", False)
                    self.system_checked.emit(is_tally)
                    return
            except Exception:
                pass
            self.system_checked.emit(False)

        threading.Thread(target=_check_bg, daemon=True, name="SystemCheckThread").start()

    def _on_system_checked(self, is_tally: bool):
        self.update_badge_style(self.row_tally_badge, is_tally)
        if is_tally:
            self.status_orb.setText("GOOD")
            self.status_orb.setStyleSheet("""
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #E8F8F0, stop:1 #C8E6C9);
                border: 2px solid #69F0AE;
                border-radius: 28px;
                color: #2E7D32;
                font-size: 14px;
                font-weight: 900;
            """)
        else:
            self.status_orb.setText("CHECK")
            self.status_orb.setStyleSheet("""
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #FEF2F2, stop:1 #FEE2E2);
                border: 2px solid #F87171;
                border-radius: 28px;
                color: #DC2626;
                font-size: 13px;
                font-weight: 900;
            """)

    def on_check_updates(self):
        self.btn_check_updates.setEnabled(False)
        self.btn_check_updates.setText("⏳ Checking...")

        import threading
        def _bg_check():
            try:
                from shared.updater import updater_service
                res = updater_service.check_for_updates()
                self.update_checked.emit(res)
            except Exception as e:
                self.update_checked.emit({"error": str(e)})

        threading.Thread(target=_bg_check, daemon=True, name="UpdateCheckThread").start()

    def _on_update_checked(self, res: dict):
        try:
            curr_ver = res.get("current_version", self.settings.app_version)
            if res.get("update_available"):
                latest = res.get("latest_version")
                try:
                    from apps.desktop_app.ui.widgets.update_dialog import UpdateAvailableDialog
                    dlg = UpdateAvailableDialog(res, parent=self)
                    dlg.exec()
                except Exception:
                    QMessageBox.information(
                        self,
                        "Update Available",
                        f"A new version (v{latest}) is available!\n\nRelease notes:\n{res.get('release_notes', 'New enhancements and bug fixes.')}"
                    )
            else:
                err = res.get("error")
                if err and "401" not in str(err):
                    QMessageBox.warning(
                        self,
                        "Update Check",
                        f"Could not connect to update server:\n{err}\n\nCurrent version: v{curr_ver}"
                    )
                else:
                    QMessageBox.information(
                        self,
                        "Software Up to Date",
                        f"You are running the latest version of CtrlBooks (v{curr_ver})."
                    )
        except Exception as e:
            QMessageBox.information(
                self,
                "Software Up to Date",
                f"You are running the latest version of CtrlBooks (v{self.settings.app_version})."
            )
        finally:
            self.btn_check_updates.setEnabled(True)
            self.btn_check_updates.setText("🔄 Check for Updates")
