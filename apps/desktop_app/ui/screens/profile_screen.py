from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, QScrollArea, QGraphicsDropShadowEffect
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QColor
from datetime import datetime
from typing import List, Optional

from apps.desktop_app.ui.widgets.lk_header import CtrlBooksHeader
from apps.desktop_app.ui.widgets.lk_footer import CtrlBooksFooter
from apps.desktop_app.ui.widgets.toast import ToastNotification
from shared.auth.cloud_auth_service import cloud_auth_service
from shared.logging_config import get_logger

logger = get_logger("app.ui.profile")


class ProfileScreen(QWidget):
    back_requested = Signal()
    nav_requested = Signal(str)

    # Class attribute type annotations to guarantee 0 Pylance / type-checker warnings
    lbl_last_heartbeat: Optional[QLabel] = None
    lbl_user_name: Optional[QLabel] = None
    lbl_role_tag: Optional[QLabel] = None
    avatar_lbl: Optional[QLabel] = None

    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
        self.load_profile()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.header = CtrlBooksHeader(title="My Profile & Identity", show_back=True)
        self.header.back_clicked.connect(self.back_requested.emit)
        self.header.nav_requested.connect(self.nav_requested.emit)
        main_layout.addWidget(self.header)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setStyleSheet("QScrollArea { background-color: #F8FAFC; border: none; }")

        content_widget = QWidget()
        content_widget.setStyleSheet("background-color: #F8FAFC;")
        body_layout = QVBoxLayout(content_widget)
        body_layout.setContentsMargins(18, 14, 18, 16)
        body_layout.setSpacing(14)

        conn_card = QFrame()
        conn_card.setStyleSheet("""
            QFrame#ConnCard {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 16px;
            }
        """)
        conn_card.setObjectName("ConnCard")
        shadow2 = QGraphicsDropShadowEffect(conn_card)
        shadow2.setBlurRadius(16)
        shadow2.setColor(QColor(15, 23, 42, 12))
        shadow2.setOffset(0, 3)
        conn_card.setGraphicsEffect(shadow2)

        c_layout = QVBoxLayout(conn_card)
        c_layout.setContentsMargins(18, 14, 18, 14)
        c_layout.setSpacing(10)

        c_header = QHBoxLayout()
        c_title = QLabel("🔌 Cloud Connector Identity")
        c_title.setStyleSheet("font-size: 13px; font-weight: 800; color: #0F172A; border: none; background: transparent;")
        self.conn_status_badge = QLabel("🟢 ONLINE")
        self.conn_status_badge.setStyleSheet(
            "background-color: #ECFDF5; color: #059669; font-size: 10px; font-weight: bold; "
            "padding: 3px 10px; border-radius: 10px; border: 1px solid #A7F3D0;"
        )
        c_header.addWidget(c_title)
        c_header.addStretch()
        c_header.addWidget(self.conn_status_badge)
        c_layout.addLayout(c_header)

        c_info_box = QVBoxLayout()
        c_info_box.setSpacing(8)

        self.lbl_device_name = self._create_info_item(c_info_box, "Device Name", "Himanshu-PC")
        self.lbl_device_id = self._create_info_item(c_info_box, "Device ID", "TEST-DEVICE-001")
        self.lbl_connector_version = self._create_info_item(c_info_box, "Connector Version", "1.0.0")
        self.lbl_org_id = self._create_info_item(c_info_box, "Organization ID", "6a966e12f843d1e46a933378")
        self.lbl_heartbeat = self._create_info_item(c_info_box, "Last Heartbeat", "Just now")
        self.lbl_tally_state = self._create_info_item(c_info_box, "Tally Bridge Status", "Connected (Port 9000)")

        c_layout.addLayout(c_info_box)
        body_layout.addWidget(conn_card)

        plan_card = QFrame()
        plan_card.setStyleSheet("""
            QFrame#PlanCard {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 16px;
            }
        """)
        plan_card.setObjectName("PlanCard")
        shadow3 = QGraphicsDropShadowEffect(plan_card)
        shadow3.setBlurRadius(16)
        shadow3.setColor(QColor(15, 23, 42, 12))
        shadow3.setOffset(0, 3)
        plan_card.setGraphicsEffect(shadow3)
        p_layout = QVBoxLayout(plan_card)
        p_layout.setContentsMargins(18, 14, 18, 14)
        p_layout.setSpacing(10)

        p_header = QHBoxLayout()
        p_title = QLabel("⭐ Plan & Subscription")
        p_title.setStyleSheet("font-size: 13px; font-weight: 800; color: #0F172A; border: none; background: transparent;")
        self.plan_badge = QLabel("PRO PLAN")
        self.plan_badge.setStyleSheet(
            "background-color: #E0E7FF; color: #3730A3; font-size: 11px; font-weight: 800; "
            "padding: 3px 10px; border-radius: 10px; border: none;"
        )
        p_header.addWidget(p_title)
        p_header.addStretch()
        p_header.addWidget(self.plan_badge)
        p_layout.addLayout(p_header)

        p_info_box = QVBoxLayout()
        p_info_box.setSpacing(8)

        self.lbl_sub_status = self._create_info_item(p_info_box, "Subscription Status", "ACTIVE")
        self.lbl_valid_period = self._create_info_item(p_info_box, "Validity Period", "01-Sep-2026 to 01-Sep-2027")

        p_layout.addLayout(p_info_box)
        body_layout.addWidget(plan_card)

        logout_btn = QPushButton("Logout")
        logout_btn.setFixedHeight(38)
        logout_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        logout_btn.setStyleSheet("""
            QPushButton {
                background-color: #FFFFFF;
                border: 1.5px solid #FECACA;
                color: #DC2626;
                font-size: 12px;
                font-weight: 700;
                border-radius: 10px;
            }
            QPushButton:hover {
                background-color: #FEF2F2;
                border-color: #EF4444;
            }
        """)
        logout_btn.clicked.connect(lambda: self.nav_requested.emit("logout"))
        body_layout.addWidget(logout_btn)

        self.perm_tags_layout = QHBoxLayout()

        scroll_area.setWidget(content_widget)
        main_layout.addWidget(scroll_area, stretch=1)

        self.footer = CtrlBooksFooter()
        main_layout.addWidget(self.footer)

    def _create_info_item(self, parent_layout: QVBoxLayout, label: str, default_val: str) -> QLabel:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        lbl = QLabel(label)
        lbl.setStyleSheet("font-size: 11px; font-weight: 600; color: #64748B; border: none;")
        val_lbl = QLabel(default_val)
        val_lbl.setStyleSheet("font-size: 11px; font-weight: 700; color: #0F172A; border: none;")
        val_lbl.setWordWrap(True)
        val_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(lbl)
        row.addStretch()
        row.addWidget(val_lbl)
        parent_layout.addLayout(row)
        return val_lbl

    def showEvent(self, event):
        super().showEvent(event)
        self.load_profile()

    def load_profile(self):
        """Loads connector identity and subscription data live from Cloud API and session."""
        raw_cloud_data = {}

        try:
            ok, me_data = cloud_auth_service.get_me()
            if ok and me_data:
                raw_cloud_data = me_data
        except Exception as exc:
            logger.debug(f"Cloud API /me profile load notice: {exc}")

        connector = raw_cloud_data.get("connector") or {}
        if connector:
            self.lbl_device_name.setText(connector.get("deviceName") or "Default-PC")
            self.lbl_device_id.setText(connector.get("deviceId") or cloud_auth_service.device_id)
            self.lbl_connector_version.setText(connector.get("connectorVersion") or "1.0.0")
            self.lbl_org_id.setText(str(connector.get("organizationId") or "N/A"))
            
            hb = connector.get("lastHeartbeatAt")
            if hb:
                try:
                    hb_clean = hb.replace("Z", "+00:00")
                    dt = datetime.fromisoformat(hb_clean)
                    self.lbl_heartbeat.setText(dt.strftime("%d-%b-%Y %H:%M:%S UTC"))
                except Exception:
                    self.lbl_heartbeat.setText(str(hb))
            else:
                self.lbl_heartbeat.setText("Active (Live)")

            status_val = connector.get("status", "ONLINE").upper()
            if status_val == "ONLINE":
                self.conn_status_badge.setText("🟢 ONLINE")
                self.conn_status_badge.setStyleSheet("background-color: #DCFCE7; color: #166534; font-size: 10px; font-weight: bold; padding: 3px 8px; border-radius: 10px;")
            else:
                self.conn_status_badge.setText(f"🔴 {status_val}")
                self.conn_status_badge.setStyleSheet("background-color: #FEE2E2; color: #991B1B; font-size: 10px; font-weight: bold; padding: 3px 8px; border-radius: 10px;")

        plan = raw_cloud_data.get("plan") or {}
        if plan:
            self.plan_badge.setText(f"{plan.get('name', 'Pro').upper()} PLAN")

        sub = raw_cloud_data.get("subscription") or {}
        if sub:
            sub_status = sub.get("status", "ACTIVE").upper()
            self.lbl_sub_status.setText(f"🟢 {sub_status}" if sub.get("active", True) else f"🔴 {sub_status}")
            from_d = sub.get("fromDate", "")[:10]
            to_d = sub.get("toDate", "")[:10]
            if from_d and to_d:
                self.lbl_valid_period.setText(f"{from_d} to {to_d}")
            else:
                self.lbl_valid_period.setText("Active Subscription")

        permissions = raw_cloud_data.get("permissions") or (plan.get("features") if plan else []) or [
            "COMPANY_READ", "LEDGER_READ", "VOUCHER_READ", "STOCK_READ", "SYNC_LEDGER"
        ]
        self._populate_permission_tags(permissions)

    def _populate_permission_tags(self, perms: List[str]):
        while self.perm_tags_layout.count():
            item = self.perm_tags_layout.takeAt(0)
            if item is not None:
                w = item.widget()
                if w is not None:
                    w.deleteLater()

        for p in perms[:4]:
            tag = QLabel(p)
            tag.setStyleSheet(
                "background-color: #F1F5F9; color: #0284C7; font-size: 10px; font-weight: 700; "
                "padding: 3px 8px; border-radius: 4px; border: 1px solid #CBD5E1;"
            )
            self.perm_tags_layout.addWidget(tag)

        if len(perms) > 4:
            more_tag = QLabel(f"+{len(perms) - 4} more")
            more_tag.setStyleSheet("background-color: #E2E8F0; color: #475569; font-size: 10px; font-weight: 700; padding: 3px 8px; border-radius: 4px;")
            self.perm_tags_layout.addWidget(more_tag)

        self.perm_tags_layout.addStretch()

    def handle_logout(self):
        """Logs out from Cloud Auth API and navigates back to Login Screen."""
        cloud_auth_service.logout()
        toast = ToastNotification("Logged out successfully.", "info", self)
        toast.show()
        self.nav_requested.emit("login")

    def reset_fields(self):
        """Clears device labels, subscription badges and permission tags on logout."""
        # Reset device and organization labels
        if hasattr(self, "lbl_device_name") and self.lbl_device_name:
            self.lbl_device_name.setText("-")
        if hasattr(self, "lbl_device_id") and self.lbl_device_id:
            self.lbl_device_id.setText("-")
        if hasattr(self, "lbl_org_id") and self.lbl_org_id:
            self.lbl_org_id.setText("-")
        if hasattr(self, "lbl_heartbeat") and self.lbl_heartbeat:
            self.lbl_heartbeat.setText("Never")
        if hasattr(self, "lbl_tally_state") and self.lbl_tally_state:
            self.lbl_tally_state.setText("-")
        if hasattr(self, "conn_status_badge") and self.conn_status_badge:
            self.conn_status_badge.setText("🔴 OFFLINE")
        if hasattr(self, "lbl_last_heartbeat") and self.lbl_last_heartbeat:
            self.lbl_last_heartbeat.setText("-")
        if hasattr(self, "lbl_user_name") and self.lbl_user_name:
            self.lbl_user_name.setText("-")
        if hasattr(self, "lbl_role_tag") and self.lbl_role_tag:
            self.lbl_role_tag.setText("-")
        if hasattr(self, "avatar_lbl") and self.avatar_lbl:
            self.avatar_lbl.setText("👤")

        # Reset plan badge and subscription status
        if hasattr(self, "plan_badge") and self.plan_badge:
            self.plan_badge.setText("FREE PLAN")
        if hasattr(self, "lbl_sub_status") and self.lbl_sub_status:
            self.lbl_sub_status.setText("INACTIVE")
        if hasattr(self, "lbl_valid_period") and self.lbl_valid_period:
            self.lbl_valid_period.setText("-")

        # Clean up permission chips from layout
        if hasattr(self, "perm_tags_layout") and self.perm_tags_layout:
            while self.perm_tags_layout.count():
                item = self.perm_tags_layout.takeAt(0)
                if item:
                    widget = item.widget()
                    if widget:
                        widget.deleteLater()
