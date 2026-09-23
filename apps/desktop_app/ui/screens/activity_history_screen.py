import logging
import threading
from datetime import datetime
from typing import Dict, Any, List
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton,
    QScrollArea, QGraphicsDropShadowEffect
)
from PySide6.QtCore import Signal, Qt, QTimer
from PySide6.QtGui import QColor, QCursor
from apps.desktop_app.ui.widgets.lk_header import CtrlBooksHeader
from apps.desktop_app.ui.widgets.lk_footer import CtrlBooksFooter
from shared.repositories.activity_history_repository import activity_history_repo
from shared.auth.cloud_auth_service import cloud_auth_service
from shared.config import get_settings

logger = logging.getLogger("app.desktop.activity_history")

def format_voucher_date(d_str: Any) -> str:
    if not d_str:
        return ""
    s = str(d_str).strip()
    if len(s) == 8 and s.isdigit():
        try:
            return datetime.strptime(s, "%Y%m%d").strftime("%d-%b-%Y")
        except Exception:
            pass
    try:
        if "T" in s:
            s = s.split("T")[0]
        dt = datetime.strptime(s, "%Y-%m-%d")
        return dt.strftime("%d-%b-%Y")
    except Exception:
        pass
    return s

class ActivityHistoryScreen(QWidget):
    back_requested = Signal()
    nav_requested = Signal(str)
    activities_loaded = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.activities_loaded.connect(self._on_activities_loaded)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.header = CtrlBooksHeader(title="Web Activity History", show_back=True)
        self.header.back_clicked.connect(self.back_requested.emit)
        self.header.refresh_clicked.connect(self.load_activities)
        self.header.nav_requested.connect(self.nav_requested.emit)
        layout.addWidget(self.header)

        main_content = QWidget()
        main_content.setStyleSheet("background-color: #F8FAFC;")
        main_content.setObjectName("MainContent")
        content_layout = QVBoxLayout(main_content)
        content_layout.setContentsMargins(18, 14, 18, 14)
        content_layout.setSpacing(12)

        # Central Elevated Card
        self.central_card = QFrame()
        self.central_card.setStyleSheet("""
            QFrame#CentralCard {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 16px;
            }
        """)
        self.central_card.setObjectName("CentralCard")

        from PySide6.QtWidgets import QGraphicsDropShadowEffect
        from PySide6.QtGui import QColor
        shadow = QGraphicsDropShadowEffect(self.central_card)
        shadow.setBlurRadius(16)
        shadow.setColor(QColor(15, 23, 42, 12))
        shadow.setOffset(0, 3)
        self.central_card.setGraphicsEffect(shadow)

        card_inner_layout = QVBoxLayout(self.central_card)
        card_inner_layout.setContentsMargins(18, 16, 18, 16)
        card_inner_layout.setSpacing(12)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title_lbl = QLabel("Activity History")
        title_lbl.setStyleSheet("font-size: 14px; font-weight: 800; color: #0F172A; border: none; background: transparent;")
        sub_lbl = QLabel("Cloud incoming voucher execution and sync audit log")
        sub_lbl.setStyleSheet("font-size: 11px; color: #64748B; border: none; background: transparent;")
        sub_lbl.setWordWrap(True)
        title_box.addWidget(title_lbl)
        title_box.addWidget(sub_lbl)
        top_row.addLayout(title_box, stretch=1)

        self.btn_refresh = QPushButton("🔄 Refresh")
        self.btn_refresh.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_refresh.setStyleSheet("""
            QPushButton {
                background-color: #FFFFFF;
                border: 1px solid #CBD5E1;
                color: #1E293B;
                font-size: 11px;
                font-weight: 700;
                padding: 4px 10px;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #F8FAFC;
                border-color: #0284C7;
                color: #0284C7;
            }
        """)
        self.btn_refresh.clicked.connect(lambda: self.load_activities(is_manual=True))
        top_row.addWidget(self.btn_refresh)

        self.btn_clear = QPushButton("🗑️ Clear")
        self.btn_clear.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_clear.setStyleSheet("""
            QPushButton {
                background-color: #FFFFFF;
                border: 1px solid #FECACA;
                color: #DC2626;
                font-size: 11px;
                font-weight: 700;
                padding: 4px 10px;
                border-radius: 6px;
            }
            QPushButton:hover {
                background-color: #FEF2F2;
                border-color: #EF4444;
            }
        """)
        self.btn_clear.clicked.connect(self.on_clear_clicked)
        top_row.addWidget(self.btn_clear)

        card_inner_layout.addLayout(top_row)

        stats_layout = QHBoxLayout()
        stats_layout.setContentsMargins(0, 0, 0, 0)
        stats_layout.setSpacing(8)

        self.total_lbl = QLabel("Total: 0")
        self.total_lbl.setStyleSheet("""
            QLabel {
                background-color: #475569;
                color: #FFFFFF;
                font-size: 11px;
                font-weight: 700;
                padding: 4px 12px;
                border-radius: 12px;
                border: none;
            }
        """)
        stats_layout.addWidget(self.total_lbl)

        self.synced_lbl = QLabel("Synced: 0")
        self.synced_lbl.setStyleSheet("""
            QLabel {
                background-color: #ECFDF5;
                color: #059669;
                font-size: 11px;
                font-weight: 700;
                padding: 4px 12px;
                border-radius: 12px;
                border: 1px solid #A7F3D0;
            }
        """)
        stats_layout.addWidget(self.synced_lbl)

        self.failed_lbl = QLabel("Failed: 0")
        self.failed_lbl.setStyleSheet("""
            QLabel {
                background-color: #FEF2F2;
                color: #DC2626;
                font-size: 11px;
                font-weight: 700;
                padding: 4px 12px;
                border-radius: 12px;
                border: 1px solid #FECACA;
            }
        """)
        stats_layout.addWidget(self.failed_lbl)

        stats_layout.addStretch()
        card_inner_layout.addLayout(stats_layout)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.cards_container = QWidget()
        self.cards_container.setStyleSheet("background: transparent;")
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(0, 4, 0, 4)
        self.cards_layout.setSpacing(8)

        scroll.setWidget(self.cards_container)
        card_inner_layout.addWidget(scroll, stretch=1)

        content_layout.addWidget(self.central_card, stretch=1)
        layout.addWidget(main_content, stretch=1)

        insights_bar = QWidget()
        insights_bar.setStyleSheet("background-color: #FFFFFF; border-top: 1px solid #E2E8F0;")
        in_layout = QHBoxLayout(insights_bar)
        in_layout.setContentsMargins(14, 6, 14, 6)
        in_layout.setSpacing(6)

        c1 = QFrame()
        c1.setStyleSheet("QFrame { background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 4px 6px; }")
        c1_lay = QVBoxLayout(c1)
        c1_lay.setContentsMargins(2, 2, 2, 2)
        c1_lay.setSpacing(2)
        c1_lbl1 = QLabel("Companies")
        c1_lbl1.setStyleSheet("font-size: 9px; font-weight: bold; color: #64748B; border: none; background: transparent;")
        c1_val = QLabel("📊 2 Active")
        c1_val.setStyleSheet("font-size: 10px; font-weight: 800; color: #0F172A; border: none; background: transparent;")
        c1_lay.addWidget(c1_lbl1)
        c1_lay.addWidget(c1_val)
        in_layout.addWidget(c1, stretch=1)

        c2 = QFrame()
        c2.setStyleSheet("QFrame { background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 4px 6px; }")
        c2_lay = QVBoxLayout(c2)
        c2_lay.setContentsMargins(2, 2, 2, 2)
        c2_lay.setSpacing(2)
        c2_lbl1 = QLabel("Sync Engine")
        c2_lbl1.setStyleSheet("font-size: 9px; font-weight: bold; color: #64748B; border: none; background: transparent;")
        c2_val = QLabel("⚡ Live (15s)")
        c2_val.setStyleSheet("font-size: 10px; font-weight: 800; color: #059669; border: none; background: transparent;")
        c2_lay.addWidget(c2_lbl1)
        c2_lay.addWidget(c2_val)
        in_layout.addWidget(c2, stretch=1)

        c3 = QFrame()
        c3.setStyleSheet("QFrame { background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 4px 6px; }")
        c3_lay = QVBoxLayout(c3)
        c3_lay.setContentsMargins(2, 2, 2, 2)
        c3_lay.setSpacing(2)
        c3_lbl1 = QLabel("Cloud Commands")
        c3_lbl1.setStyleSheet("font-size: 9px; font-weight: bold; color: #64748B; border: none; background: transparent;")
        self.c3_val = QLabel("📥 Auto-Sync")
        self.c3_val.setStyleSheet("font-size: 10px; font-weight: 800; color: #0284C7; border: none; background: transparent;")
        c3_lay.addWidget(c3_lbl1)
        c3_lay.addWidget(self.c3_val)
        in_layout.addWidget(c3, stretch=1)

        layout.addWidget(insights_bar)

        self.footer = CtrlBooksFooter()
        layout.addWidget(self.footer)

        self.load_activities(is_manual=False)

        # 10s Background Auto-Refresh Timer
        self.auto_refresh_timer = QTimer(self)
        self.auto_refresh_timer.setInterval(10000)
        self.auto_refresh_timer.timeout.connect(lambda: self.load_activities(is_manual=False))
        self.auto_refresh_timer.start()

    def load_activities(self, is_manual: bool = False):
        """Loads activity cards dynamically from the repository in the background."""
        if is_manual:
            self.btn_refresh.setText("⏳ Refreshing...")
            self.btn_refresh.setEnabled(False)

        def _fetch_bg():
            try:
                curr_org = cloud_auth_service.organization_id or ""
                curr_email = cloud_auth_service.email or ""

                activities = activity_history_repo.get_recent_activities(
                    limit=50,
                    organization_id=curr_org,
                    user_email=curr_email
                )
                self.activities_loaded.emit(activities or [])
            except Exception as exc:
                logger.debug(f"Async activity fetch error: {exc}")
                self.activities_loaded.emit([])

        threading.Thread(target=_fetch_bg, daemon=True, name="ActivityFetchThread").start()

    def _on_activities_loaded(self, activities: list):
        self.btn_refresh.setText("🔄 Refresh")
        self.btn_refresh.setEnabled(True)
        self.btn_clear.setText("🗑️ Clear")
        self.btn_clear.setEnabled(True)

        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            if item is not None:
                w = item.widget()
                if w is not None:
                    w.deleteLater()

        total_cnt = len(activities)
        synced_cnt = sum(1 for a in activities if a.get("status") == "SUCCESS")
        failed_cnt = sum(1 for a in activities if a.get("status") != "SUCCESS")

        self.total_lbl.setText(f"Total: {total_cnt}")
        self.synced_lbl.setText(f"Synced: {synced_cnt}")
        self.failed_lbl.setText(f"Failed: {failed_cnt}")

        if not activities:
            empty_frame = QFrame()
            empty_frame.setStyleSheet("""
                QFrame {
                    background-color: #FFFFFF;
                    border: 1px dashed #CBD5E1;
                    border-radius: 12px;
                    padding: 30px;
                }
            """)
            emp_lay = QVBoxLayout(empty_frame)
            emp_lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
            emp_icon = QLabel("📥")
            emp_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
            emp_icon.setStyleSheet("font-size: 32px; border: none; background: transparent;")
            emp_txt = QLabel("No incoming web sync orders recorded yet.\nNew commands from cloud will appear here live.")
            emp_txt.setAlignment(Qt.AlignmentFlag.AlignCenter)
            emp_txt.setWordWrap(True)
            emp_txt.setStyleSheet("font-size: 12px; font-weight: 600; color: #64748B; border: none; background: transparent;")
            emp_lay.addWidget(emp_icon)
            emp_lay.addWidget(emp_txt)
            self.cards_layout.addWidget(empty_frame)
            self.cards_layout.addStretch()
            return

        for act in activities:
            card = self.create_activity_card(act)
            self.cards_layout.addWidget(card)

        self.cards_layout.addStretch()

    def create_activity_card(self, act: Dict[str, Any]) -> QFrame:
        card = QFrame()
        is_success = (act.get("status") == "SUCCESS")

        card.setStyleSheet("""
            QFrame {
                background-color: #F8FAFC;
                border: 1px solid #E2E8F0;
                border-radius: 10px;
            }
            QFrame:hover {
                border-color: #BAE6FD;
                background-color: #F1F5F9;
            }
        """)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 10, 14, 10)
        card_layout.setSpacing(6)

        time_str = act.get("time", "")
        v_type = act.get("voucher_type", "Sales Bill")
        party = act.get("party", "Cash")
        amt = float(act.get("amount", 0.0))
        amt_str = f"₹ {amt:,.2f}".replace(".00", "")
        v_num = act.get("voucher_number") or ""
        company_name = act.get("company") or act.get("company_name", "")

        # Row 1: Voucher Info + Amount + Status
        r1 = QHBoxLayout()
        r1.setSpacing(8)

        v_type_lbl = QLabel(f"📄 {v_type}")
        v_type_lbl.setStyleSheet("font-size: 13px; font-weight: 800; color: #0F172A; border: none; background: transparent;")
        r1.addWidget(v_type_lbl)

        if v_num:
            v_num_lbl = QLabel(f"#{v_num}")
            v_num_lbl.setStyleSheet("font-size: 11px; font-weight: 700; color: #64748B; border: none; background: transparent;")
            r1.addWidget(v_num_lbl)

        r1.addStretch()

        a_val = QLabel(amt_str)
        a_val.setStyleSheet("font-size: 13px; font-weight: 800; color: #0F172A; border: none; background: transparent;")
        r1.addWidget(a_val)

        if is_success:
            status_pill = QLabel("🟢 Synced")
            status_pill.setStyleSheet("""
                QLabel {
                    background-color: #ECFDF5;
                    color: #059669;
                    font-size: 10px;
                    font-weight: 700;
                    padding: 2px 8px;
                    border-radius: 6px;
                    border: 1px solid #A7F3D0;
                }
            """)
        else:
            err = act.get("error") or "Failed"
            status_pill = QLabel("🔴 Failed")
            status_pill.setToolTip(f"Reason: {err}")
            status_pill.setStyleSheet("""
                QLabel {
                    background-color: #FEF2F2;
                    color: #DC2626;
                    font-size: 10px;
                    font-weight: 700;
                    padding: 2px 8px;
                    border-radius: 6px;
                    border: 1px solid #FECACA;
                }
            """)
        r1.addWidget(status_pill)
        card_layout.addLayout(r1)

        # Row 2: Party, Company, Time
        r2 = QHBoxLayout()
        r2.setSpacing(12)

        party_lbl = QLabel(f"👤 {party}")
        party_lbl.setStyleSheet("font-size: 11px; font-weight: 600; color: #334155; border: none; background: transparent;")
        r2.addWidget(party_lbl)

        comp_lbl = QLabel(f"🏢 {company_name or 'Tally Prime'}")
        comp_lbl.setStyleSheet("font-size: 11px; color: #64748B; border: none; background: transparent;")
        r2.addWidget(comp_lbl)

        r2.addStretch()

        if time_str:
            time_lbl = QLabel(f"🕒 {time_str}")
            time_lbl.setStyleSheet("font-size: 10px; color: #94A3B8; border: none; background: transparent;")
            r2.addWidget(time_lbl)

        card_layout.addLayout(r2)
        return card

    def on_clear_clicked(self):
        self.btn_clear.setText("⏳ Clearing...")
        self.btn_clear.setEnabled(False)

        # Clear UI cards immediately for instant responsiveness
        self._on_activities_loaded([])

        import threading
        def _clear_bg():
            try:
                settings = get_settings()
                curr_org = cloud_auth_service.organization_id or getattr(settings, "organization_id", None)
                curr_email = cloud_auth_service.email or getattr(settings, "user_email", None)

                activity_history_repo.clear_activities(
                    organization_id=curr_org,
                    user_email=curr_email
                )
            except Exception as exc:
                logger.debug(f"Async activity clear error: {exc}")

        threading.Thread(target=_clear_bg, daemon=True, name="ActivityClearThread").start()
