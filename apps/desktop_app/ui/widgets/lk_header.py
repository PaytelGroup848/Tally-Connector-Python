"""
CtrlBooks - Custom Brand Header Widget
--------------------------------------------------
Clean status bar header:
- Software connection pulse dot badge (🟢 Tally / 🔴 Offline)
- Seamless 'Synced' timestamp label
- Action buttons: 🔍 Detect, ⚡ Sync
- Sleek 3-dots options menu button (Software Probing, Profile, Settings, System, Logout)
  with hidden default menu-indicator arrow.
"""

from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QMenu
from PySide6.QtCore import Signal, Qt

class CtrlBooksHeader(QWidget):
    back_clicked = Signal()
    refresh_clicked = Signal()
    sync_now_clicked = Signal()
    auto_detect_clicked = Signal()
    minimize_clicked = Signal()
    close_clicked = Signal()
    nav_requested = Signal(str)

    def __init__(self, title: str = "", show_back: bool = False, parent=None):
        super().__init__(parent)
        self.title_text = title
        self.show_back = show_back
        self.init_ui()

    def init_ui(self):
        self.setFixedHeight(54)
        self.setStyleSheet("""
            QWidget#HeaderContainer {
                background-color: #FFFFFF;
                border-bottom: 1px solid #E2E8F0;
            }
            QLabel {
                border: none;
                background: transparent;
            }
        """)
        self.setObjectName("HeaderContainer")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(8)

        if self.show_back:
            self.back_btn = QPushButton("← " + (self.title_text or "Back"))
            self.back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.back_btn.setStyleSheet("""
                QPushButton {
                    border: none;
                    font-size: 13px;
                    font-weight: 800;
                    color: #0F172A;
                    text-align: left;
                    background: transparent;
                    padding: 4px 6px;
                    border-radius: 6px;
                }
                QPushButton:hover {
                    color: #0284C7;
                    background-color: #F1F5F9;
                }
            """)
            self.back_btn.clicked.connect(self.back_clicked.emit)
            self.back_btn.clicked.connect(lambda: self.nav_requested.emit("probe"))
            layout.addWidget(self.back_btn)
            layout.addStretch()
        else:
            from PySide6.QtGui import QPixmap
            from apps.desktop_app.ui.asset_helper import get_asset_path
            self.logo_lbl = QLabel()
            self.logo_lbl.setStyleSheet("background: transparent; border: none;")
            logo_path = get_asset_path("ctrlbooks_logo.png")
            if logo_path.exists():
                pix = QPixmap(str(logo_path)).scaledToHeight(30, Qt.TransformationMode.SmoothTransformation)
                self.logo_lbl.setPixmap(pix)
            else:
                self.logo_lbl.setText("CtrlBooks")
                self.logo_lbl.setStyleSheet("font-size: 15px; font-weight: 800; color: #0284C7;")
            layout.addWidget(self.logo_lbl)
            layout.addStretch()

            self.sync_now_btn = QPushButton("🔄 Sync")
            self.sync_now_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.sync_now_btn.setFixedHeight(28)
            self.sync_now_btn.setStyleSheet("""
                QPushButton {
                    background-color: #FFFFFF;
                    color: #0284C7;
                    font-size: 11px;
                    font-weight: 700;
                    padding: 0 10px;
                    border-radius: 14px;
                    border: 1px solid #BAE6FD;
                }
                QPushButton:hover {
                    background-color: #F0F9FF;
                    border-color: #0284C7;
                }
            """)
            self.sync_now_btn.clicked.connect(self.sync_now_clicked.emit)
            self.sync_now_btn.clicked.connect(self.refresh_clicked.emit)
            self.refresh_btn = self.sync_now_btn
            layout.addWidget(self.sync_now_btn)

            self.insight_btn = QPushButton("📊 Insights")
            self.insight_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.insight_btn.setFixedHeight(28)
            self.insight_btn.setStyleSheet("""
                QPushButton {
                    background-color: #ECFDF5;
                    color: #059669;
                    font-size: 11px;
                    font-weight: 700;
                    padding: 0 10px;
                    border-radius: 14px;
                    border: 1px solid #A7F3D0;
                }
                QPushButton:hover {
                    background-color: #D1FAE5;
                    border-color: #059669;
                }
            """)
            self.insight_btn.clicked.connect(lambda: self.nav_requested.emit("profile"))
            layout.addWidget(self.insight_btn)

        from apps.desktop_app.ui.asset_helper import create_more_dots_icon
        self.menu_btn = QPushButton()
        self.menu_btn.setIcon(create_more_dots_icon("#0F172A", 24))
        self.menu_btn.setToolTip("Options & Settings")
        self.menu_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.menu_btn.setFixedSize(30, 30)
        self.menu_btn.setStyleSheet("""
            QPushButton {
                background-color: #F8FAFC;
                border: 1.5px solid #CBD5E1;
                border-radius: 8px;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: #E2E8F0;
                border-color: #0284C7;
            }
            QPushButton::menu-indicator {
                image: none;
                width: 0px;
            }
        """)
        self.setup_menu()
        layout.addWidget(self.menu_btn)

        self.status_pulse = QLabel("🔴 Offline")
        self.last_sync_lbl = QLabel("Synced: Just now")
        self.auto_detect_btn = QPushButton("🔍 Detect")

    def setup_menu(self):
        menu = QMenu(self)
        menu.setCursor(Qt.CursorShape.PointingHandCursor)
        menu.setStyleSheet("""
            QMenu {
                background-color: #FFFFFF;
                color: #0F172A;
                border: 1px solid #CBD5E1;
                border-radius: 8px;
                padding: 4px;
            }
            QMenu::item {
                background-color: transparent;
                color: #0F172A;
                padding: 6px 18px;
                font-size: 11px;
                font-weight: 600;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #ECFDF5;
                color: #059669;
            }
            QMenu::separator {
                height: 1px;
                background-color: #E2E8F0;
                margin: 4px 6px;
            }
        """)
        act_history = menu.addAction("📋 Web Sync Activity")
        probe_act = menu.addAction("🔍 Software Probing")
        p_act = menu.addAction("👤 Profile")
        s_act = menu.addAction("⚙️ Settings")
        sys_act = menu.addAction("💻 System Checks")
        menu.addSeparator()
        log_act = menu.addAction("🚪 Logout")

        act_history.triggered.connect(lambda: self.nav_requested.emit("activity"))
        probe_act.triggered.connect(lambda: self.nav_requested.emit("probe"))
        p_act.triggered.connect(lambda: self.nav_requested.emit("profile"))
        s_act.triggered.connect(lambda: self.nav_requested.emit("settings"))
        sys_act.triggered.connect(lambda: self.nav_requested.emit("system"))
        log_act.triggered.connect(lambda: self.nav_requested.emit("logout"))
        self.menu_btn.setMenu(menu)

    def update_connection_status(self, is_connected: bool, software_name: str = "Tally", port: int = 9000):
        if is_connected:
            self.status_pulse.setText(f"🟢 {software_name} ({port})")
            self.status_pulse.setStyleSheet(
                "font-size: 10px; font-weight: 800; color: #059669; background-color: #ECFDF5; "
                "padding: 3px 8px; border-radius: 12px; border: 1px solid #A7F3D0;"
            )
        else:
            self.status_pulse.setText("🔴 Offline")
            self.status_pulse.setStyleSheet(
                "font-size: 10px; font-weight: 800; color: #DC2626; background-color: #FEF2F2; "
                "padding: 3px 8px; border-radius: 12px; border: 1px solid #FCA5A5;"
            )

    def update_last_sync(self, time_str: str = "Just now"):
        self.last_sync_lbl.setText(f"Synced: {time_str}")


CtrlBooksHeader = CtrlBooksHeader
