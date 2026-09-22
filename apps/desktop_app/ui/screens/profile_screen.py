"""
CtrlBooks - User Profile & Cloud Identity Screen
------------------------------------------------------------
Displays user account information, Cloud Connector hardware identity,
Subscription Plan, and Granted API Permissions fetched live from Cloud API
(GET /api/connector/me) and synchronized into MongoDB Atlas.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QComboBox, QFrame, QScrollArea, QGridLayout, QGraphicsDropShadowEffect, QStackedWidget
)
from PySide6.QtCore import Signal, Qt, QTimer
from PySide6.QtGui import QColor
from pathlib import Path
import json
from datetime import datetime, timezone
from typing import List

from apps.desktop_app.ui.widgets.lk_header import CtrlBooksHeader
from apps.desktop_app.ui.widgets.lk_footer import CtrlBooksFooter
from apps.desktop_app.ui.widgets.toast import ToastNotification
from shared.auth.cloud_auth_service import cloud_auth_service
from shared.db.mongo_client import get_collection
from shared.logging_config import get_logger

logger = get_logger("app.ui.profile")

import os

def _get_writable_profile_file() -> Path:
    p = Path("data/profile.json")
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    except Exception:
        fallback = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "CtrlBooks" / "data" / "profile.json"
        fallback.parent.mkdir(parents=True, exist_ok=True)
        return fallback

PROFILE_CACHE_FILE = _get_writable_profile_file()

class ProfileScreen(QWidget):
    back_requested = Signal()
    nav_requested = Signal(str)

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

        user_card = QFrame()
        user_card.setStyleSheet("""
            QFrame#UserCard {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 16px;
            }
        """)
        user_card.setObjectName("UserCard")

        shadow1 = QGraphicsDropShadowEffect(user_card)
        shadow1.setBlurRadius(16)
        shadow1.setColor(QColor(15, 23, 42, 14))
        shadow1.setOffset(0, 3)
        user_card.setGraphicsEffect(shadow1)

        u_layout = QVBoxLayout(user_card)
        u_layout.setContentsMargins(18, 14, 18, 14)
        u_layout.setSpacing(10)

        u_header = QHBoxLayout()
        u_header.addStretch()
        u_title = QLabel("👤 User Profile Information")
        u_title.setStyleSheet("font-size: 14px; font-weight: 800; color: #0F172A; border: none; background: transparent;")
        u_header.addWidget(u_title)
        u_header.addStretch()

        avatar_badge = QLabel("👤")
        avatar_badge.setFixedSize(34, 34)
        avatar_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar_badge.setStyleSheet("""
            QLabel {
                background-color: #334155;
                color: #FFFFFF;
                font-size: 15px;
                border-radius: 17px;
                border: 2px solid #E2E8F0;
            }
        """)
        u_header.addWidget(avatar_badge)
        u_layout.addLayout(u_header)

        u_divider = QFrame()
        u_divider.setFrameShape(QFrame.Shape.HLine)
        u_divider.setStyleSheet("background-color: #F1F5F9; border: none; max-height: 1px;")
        u_layout.addWidget(u_divider)

        self.profile_stack = QStackedWidget()
        self.profile_stack.setStyleSheet("border: none; background: transparent;")

        view_widget = QWidget()
        view_widget.setStyleSheet("border: none; background: transparent;")
        v_layout = QVBoxLayout(view_widget)
        v_layout.setContentsMargins(0, 0, 0, 0)
        v_layout.setSpacing(10)

        details_box = QVBoxLayout()
        details_box.setSpacing(8)

        def make_detail_row(icon: str, label_text: str, default_val: str):
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            lbl = QLabel(f"{icon} {label_text}")
            lbl.setStyleSheet("font-size: 11px; font-weight: 700; color: #64748B; border: none; background: transparent;")
            val = QLabel(default_val)
            val.setStyleSheet("font-size: 12px; font-weight: 700; color: #0F172A; border: none; background: transparent;")
            val.setWordWrap(True)
            val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            row.addWidget(lbl)
            row.addStretch()
            row.addWidget(val)
            details_box.addLayout(row)
            return val

        self.val_name_lbl = make_detail_row("👤", "Full Name", "Not Provided")
        self.val_mobile_lbl = make_detail_row("📞", "Mobile Number", "Not Provided")
        self.val_email_lbl = make_detail_row("✉️", "Email Address", "Not Provided")
        self.val_zip_lbl = make_detail_row("📍", "Location / PIN", "Not Provided")

        v_layout.addLayout(details_box)

        v_footer = QHBoxLayout()
        v_footer.setContentsMargins(0, 6, 0, 0)

        status_pill = QLabel("🟢 Verified Profile")
        status_pill.setStyleSheet("""
            QLabel {
                background-color: #ECFDF5;
                color: #065F46;
                font-size: 10px;
                font-weight: 800;
                padding: 4px 10px;
                border-radius: 12px;
                border: 1px solid #A7F3D0;
            }
        """)
        v_footer.addWidget(status_pill)
        v_footer.addStretch()

        self.edit_btn = QPushButton("✏️ Edit Profile")
        self.edit_btn.setFixedHeight(34)
        self.edit_btn.setMinimumWidth(110)
        self.edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.edit_btn.setStyleSheet("""
            QPushButton {
                background-color: #FFFFFF;
                border: 1.5px solid #10B981;
                border-radius: 17px;
                color: #10B981;
                font-size: 11px;
                font-weight: 800;
                padding: 0 14px;
            }
            QPushButton:hover {
                background-color: #10B981;
                color: #FFFFFF;
            }
        """)
        self.edit_btn.clicked.connect(lambda: self.profile_stack.setCurrentIndex(1))
        v_footer.addWidget(self.edit_btn)
        v_layout.addLayout(v_footer)

        self.profile_stack.addWidget(view_widget)

        edit_widget = QWidget()
        edit_widget.setStyleSheet("border: none; background: transparent;")
        e_layout = QVBoxLayout(edit_widget)
        e_layout.setContentsMargins(0, 0, 0, 0)
        e_layout.setSpacing(10)

        lbl1 = QLabel("Full Name")
        lbl1.setStyleSheet("font-size: 11px; font-weight: 700; color: #475569; border: none; background: transparent;")
        e_layout.addWidget(lbl1)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("👤 Enter your full name")
        self.name_input.setFixedHeight(38)
        self.name_input.setStyleSheet("""
            QLineEdit {
                border: 1.5px solid #CBD5E1;
                border-radius: 10px;
                padding: 0 14px;
                font-size: 12px;
                background-color: #F8FAFC;
                color: #0F172A;
            }
            QLineEdit:focus {
                border: 1.5px solid #10B981;
                background-color: #FFFFFF;
            }
        """)
        e_layout.addWidget(self.name_input)

        lbl2 = QLabel("Mobile Number")
        lbl2.setStyleSheet("font-size: 11px; font-weight: 700; color: #475569; border: none; background: transparent;")
        e_layout.addWidget(lbl2)

        m_box = QHBoxLayout()
        m_box.setSpacing(8)

        self.c_combo = QComboBox()
        self.c_combo.addItems(["🇮🇳 IN +91", "🇺🇸 US +1", "🇦🇪 AE +971", "🇬🇧 UK +44"])
        self.c_combo.setFixedWidth(100)
        self.c_combo.setFixedHeight(38)
        self.c_combo.setStyleSheet("""
            QComboBox {
                border: 1.5px solid #CBD5E1;
                border-radius: 10px;
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
        self.mobile_input = QLineEdit()
        self.mobile_input.setPlaceholderText("Enter your mobile number  📞")
        self.mobile_input.setFixedHeight(38)
        self.mobile_input.setStyleSheet("""
            QLineEdit {
                border: 1.5px solid #CBD5E1;
                border-radius: 10px;
                padding: 0 14px;
                font-size: 12px;
                background-color: #F8FAFC;
                color: #0F172A;
            }
            QLineEdit:focus {
                border: 1.5px solid #10B981;
                background-color: #FFFFFF;
            }
        """)
        m_box.addWidget(self.c_combo)
        m_box.addWidget(self.mobile_input, stretch=1)
        e_layout.addLayout(m_box)

        lbl3 = QLabel("Email Address")
        lbl3.setStyleSheet("font-size: 11px; font-weight: 700; color: #475569; border: none; background: transparent;")
        e_layout.addWidget(lbl3)

        self.email_input = QLineEdit()
        self.email_input.setPlaceholderText("Enter email address  ✉️")
        self.email_input.setFixedHeight(38)
        self.email_input.setStyleSheet("""
            QLineEdit {
                border: 1.5px solid #CBD5E1;
                border-radius: 10px;
                padding: 0 14px;
                font-size: 12px;
                background-color: #F8FAFC;
                color: #0F172A;
            }
            QLineEdit:focus {
                border: 1.5px solid #10B981;
                background-color: #FFFFFF;
            }
        """)
        e_layout.addWidget(self.email_input)

        lbl4 = QLabel("Postal Code / Location")
        lbl4.setStyleSheet("font-size: 11px; font-weight: 700; color: #475569; border: none; background: transparent;")
        e_layout.addWidget(lbl4)

        self.zip_input = QLineEdit()
        self.zip_input.setPlaceholderText("📍 Enter PIN / Postal code")
        self.zip_input.setFixedHeight(38)
        self.zip_input.setStyleSheet("""
            QLineEdit {
                border: 1.5px solid #CBD5E1;
                border-radius: 10px;
                padding: 0 14px;
                font-size: 12px;
                background-color: #F8FAFC;
                color: #0F172A;
            }
            QLineEdit:focus {
                border: 1.5px solid #10B981;
                background-color: #FFFFFF;
            }
        """)
        e_layout.addWidget(self.zip_input)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 4, 0, 0)
        btn_row.setSpacing(10)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setFixedHeight(36)
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #F1F5F9;
                border: 1px solid #CBD5E1;
                border-radius: 18px;
                color: #475569;
                font-size: 11px;
                font-weight: 700;
                padding: 0 14px;
            }
            QPushButton:hover {
                background-color: #E2E8F0;
                color: #0F172A;
            }
        """)
        self.cancel_btn.clicked.connect(lambda: self.profile_stack.setCurrentIndex(0))
        btn_row.addWidget(self.cancel_btn)
        btn_row.addStretch()

        self.save_btn = QPushButton("Save Profile")
        self.save_btn.setFixedHeight(36)
        self.save_btn.setFixedWidth(130)
        self.save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #10B981, stop:1 #059669);
                color: #FFFFFF;
                font-weight: 800;
                border-radius: 18px;
                border: none;
                font-size: 12px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #059669, stop:1 #047857);
            }
            QPushButton:pressed {
                background-color: #047857;
            }
        """)
        self.save_btn.clicked.connect(self.save_profile)
        btn_row.addWidget(self.save_btn)
        e_layout.addLayout(btn_row)

        self.profile_stack.addWidget(edit_widget)
        u_layout.addWidget(self.profile_stack)

        body_layout.addWidget(user_card)

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
        """Loads full profile and identity data from Cloud API, MongoDB Atlas, and local cache."""
        raw_cloud_data = {}

        try:
            ok, me_data = cloud_auth_service.get_me()
            if ok and me_data:
                raw_cloud_data = me_data
        except Exception as exc:
            logger.debug(f"Cloud API /me profile load notice: {exc}")

        user_email = (
            cloud_auth_service.current_user.get("email")
            or getattr(cloud_auth_service, "email", "")
            or ""
        ).strip().lower()

        db_profile = {}
        try:
            col = get_collection("user_profile")
            doc = None
            if user_email:
                doc = col.find_one({"$or": [{"profile_id": user_email}, {"email": user_email}]})
            if not doc:
                doc = col.find_one({"profile_id": "current_user"})
            if doc:
                db_profile = doc
                if not raw_cloud_data:
                    raw_cloud_data = doc.get("raw") or doc
        except Exception as exc:
            logger.debug(f"MongoDB profile load notice: {exc}")

        cache_profile = {}
        cache_file = _get_writable_profile_file()
        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    cache_profile = json.load(f)
            except Exception:
                pass

        cloud_user = raw_cloud_data.get("user") or (raw_cloud_data if isinstance(raw_cloud_data, dict) else {})
        name_val = (
            db_profile.get("name")
            or cache_profile.get("name")
            or cloud_user.get("name")
            or cloud_user.get("fullName")
            or ""
        )
        mobile_val = (
            db_profile.get("mobile")
            or cache_profile.get("mobile")
            or cloud_user.get("mobile")
            or cloud_user.get("phone")
            or ""
        )
        email_val = (
            user_email
            or db_profile.get("email")
            or cache_profile.get("email")
            or cloud_user.get("email")
            or ""
        )
        zip_val = (
            db_profile.get("postal_code")
            or cache_profile.get("postal_code")
            or cloud_user.get("postal_code")
            or cloud_user.get("zip")
            or ""
        )
        c_code = (
            db_profile.get("country_code")
            or cache_profile.get("country_code")
            or "🇮🇳 IN +91"
        )

        self.name_input.setText(name_val)
        self.mobile_input.setText(mobile_val)
        self.email_input.setText(email_val)
        self.zip_input.setText(zip_val)
        idx = self.c_combo.findText(c_code)
        if idx >= 0:
            self.c_combo.setCurrentIndex(idx)

        self.val_name_lbl.setText(name_val or "Not Provided")
        self.val_mobile_lbl.setText(f"{c_code} {mobile_val}" if mobile_val else "Not Provided")
        self.val_email_lbl.setText(email_val or "Not Provided")
        self.val_zip_lbl.setText(zip_val or "Not Provided")

        if name_val or email_val or mobile_val:
            self.profile_stack.setCurrentIndex(0)
        else:
            self.profile_stack.setCurrentIndex(1)

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

    def save_profile(self):
        """Persists profile data to MongoDB Atlas and local cache file."""
        name = self.name_input.text().strip()
        mobile = self.mobile_input.text().strip()
        email = self.email_input.text().strip()
        postal_code = self.zip_input.text().strip()
        country_code = self.c_combo.currentText()
        now_iso = datetime.now(timezone.utc).isoformat()

        user_email = (
            email
            or cloud_auth_service.current_user.get("email")
            or getattr(cloud_auth_service, "email", "")
            or ""
        ).strip().lower()

        profile_key = user_email if user_email else "current_user"

        profile_doc = {
            "profile_id": profile_key,
            "name": name,
            "mobile": mobile,
            "email": user_email or email,
            "postal_code": postal_code,
            "country_code": country_code,
            "updated_at": now_iso,
        }

        try:
            col = get_collection("user_profile")
            col.update_one({"profile_id": profile_key}, {"$set": profile_doc}, upsert=True)
            if profile_key != "current_user":
                col.update_one({"profile_id": "current_user"}, {"$set": profile_doc}, upsert=True)
            logger.info(f"User profile for '{name}' saved successfully in MongoDB Atlas.")
        except Exception as exc:
            logger.error(f"MongoDB profile save error: {exc}")

        cache_file = _get_writable_profile_file()
        try:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(profile_doc, f, indent=2)
        except Exception as exc:
            logger.error(f"Cache file profile save error: {exc}")

        self.val_name_lbl.setText(name or "Not Provided")
        self.val_mobile_lbl.setText(f"{country_code} {mobile}" if mobile else "Not Provided")
        self.val_email_lbl.setText(user_email or email or "Not Provided")
        self.val_zip_lbl.setText(postal_code or "Not Provided")

        self.profile_stack.setCurrentIndex(0)

        toast = ToastNotification("Profile details saved successfully!", "success", self)
        toast.show()

    def handle_logout(self):
        """Logs out from Cloud Auth API and navigates back to Login Screen."""
        cloud_auth_service.logout()
        toast = ToastNotification("Logged out successfully.", "info", self)
        toast.show()
        self.nav_requested.emit("login")
