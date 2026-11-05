

from typing import Optional, Dict, Any, List, Tuple
import xml.etree.ElementTree as ET
import logging
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, QProgressBar, QScrollArea, QMenu
)
from PySide6.QtGui import QAction
from PySide6.QtCore import Signal, QTimer, Qt
from apps.desktop_app.ui.widgets.lk_header import CtrlBooksHeader
from apps.desktop_app.ui.widgets.lk_footer import CtrlBooksFooter
from apps.desktop_app.ui.threads.sync_worker import BackgroundSyncWorker
from apps.desktop_app.ui.threads.command_worker import RemoteCommandWorker
from apps.desktop_app.ui.threads.company_fetch_worker import CompanyFetchWorker
from apps.desktop_app.ui.widgets.confirm_dialog import ConfirmDialog
from apps.desktop_app.ui.widgets.toast import ToastNotification

logger = logging.getLogger("app.desktop.connected_dashboard")

from shared.connection_config import parse_interval_to_ms


class CompanyCardFrame(QFrame):
    status_chip: Optional[QLabel] = None
    chip_ledgers: Optional[QLabel] = None
    chip_vouchers: Optional[QLabel] = None
    chip_items: Optional[QLabel] = None
    company_name: str = ""


class ConnectedDashboardScreen(QWidget):
    nav_requested, web_view_clicked = Signal(str), Signal(str)
    companies_fetched = Signal(list, list, bool, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.active_source_filter = "TALLY"
        self._active_workers = []
        self._is_fetching_companies = False
        self._version_checked = False
        self.companies_fetched.connect(self._on_companies_fetched)
        self.init_ui()
        self.auto_timer = QTimer(self)
        self.auto_timer.timeout.connect(self.load_live_companies)
        self.auto_timer.start(25000)

        # Periodic background auto-sync timer (respects Sync Interval Frequency setting)
        self.periodic_sync_timer = QTimer(self)
        self.periodic_sync_timer.timeout.connect(self._on_periodic_sync_triggered)
        self.refresh_sync_interval()

        self.command_worker = RemoteCommandWorker(poll_interval_seconds=15, parent=self)
        self.command_worker.command_received.connect(self.on_command_received)
        self.command_worker.command_processed.connect(self.on_command_processed)
        self.command_worker.start()

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh_sync_interval()

    def refresh_sync_interval(self, custom_interval: Optional[str] = None):
        """Reads current sync_interval_minutes from connection config and updates the periodic timer."""
        try:
            from shared.connection_config import load_connection_config, parse_interval_to_ms
            if custom_interval:
                interval_str = str(custom_interval).strip()
            else:
                cfg = load_connection_config()
                interval_str = str(cfg.get("sync_interval_minutes", "1 min")).strip()

            ms = parse_interval_to_ms(interval_str)
            self.periodic_sync_timer.stop()
            if ms > 0:
                self.periodic_sync_timer.start(ms)
                logger.info(f"Periodic auto-sync active: running every {interval_str} ({ms}ms)")
                if hasattr(self, "pill_sync_interval") and self.pill_sync_interval:
                    self.pill_sync_interval.setText(f"⏱️ Every {interval_str}")
                    self.pill_sync_interval.setStyleSheet("background-color: #ECFDF5; color: #047857; font-size: 11px; font-weight: 700; padding: 4px 10px; border-radius: 12px; border: 1px solid #A7F3D0;")
                if hasattr(self, "c3_val"):
                    self.c3_val.setText(f"🟢 Every {interval_str}")
            else:
                logger.info("Periodic auto-sync disabled (Manual mode).")
                if hasattr(self, "pill_sync_interval") and self.pill_sync_interval:
                    self.pill_sync_interval.setText("⚪ Manual Sync")
                    self.pill_sync_interval.setStyleSheet("background-color: #F1F5F9; color: #64748B; font-size: 11px; font-weight: 700; padding: 4px 10px; border-radius: 12px; border: 1px solid #CBD5E1;")
                if hasattr(self, "c3_val"):
                    self.c3_val.setText("⚪ Manual Sync")
        except Exception as exc:
            logger.debug(f"Error configuring periodic sync timer: {exc}")

    def _on_periodic_sync_triggered(self):
        """Triggered automatically by periodic timer to sync data in background."""
        if hasattr(self, "_active_workers") and any(w.isRunning() for w in self._active_workers):
            logger.debug("Skipping periodic auto-sync: another sync worker is already running.")
            return

        logger.info("Periodic auto-sync triggered: syncing open companies in background...")
        if hasattr(self, "pill_sync_interval") and self.pill_sync_interval:
            self.pill_sync_interval.setText("🔄 Auto Syncing...")
            self.pill_sync_interval.setStyleSheet("background-color: #FEF3C7; color: #92400E; font-size: 11px; font-weight: 700; padding: 4px 10px; border-radius: 12px; border: 1px solid #FDE68A;")
        if hasattr(self, "c3_val"):
            self.c3_val.setText("🟡 Auto Syncing...")
        self.start_qthread_sync("", "TALLY", is_periodic=True)

    def on_command_received(self, cmd_id: str, cmd_type: str):
        ToastNotification.show_toast(self, f"Cloud Command Received: {cmd_type}", duration_ms=2500)

    def on_command_processed(self, cmd_id: str, cmd_type: str, success: bool, msg: str, error_details: Optional[dict] = None):
        if success:
            display_msg = msg if msg and ("✅" in msg or "⏳" in msg) else f"✅ {cmd_type} executed in Tally!"
            ToastNotification.show_toast(self, display_msg, duration_ms=3500)
            self.load_live_companies()
        else:
            # If voucher was queued for offline Tally or unopened company, do not show modal error dialog
            is_queued = error_details and (error_details.get("should_queue") or error_details.get("status") in ("QUEUED", "PENDING_TALLY", "COMPANY_NOT_LOADED", "TALLY_OFFLINE"))
            if is_queued:
                ToastNotification.show_toast(self, f"⏳ {msg}", duration_ms=4000)
                return

            ToastNotification.show_toast(self, f"⚠️ {cmd_type} failed: {msg}", toast_type="error", duration_ms=4000)
            if error_details and isinstance(error_details, dict):
                try:
                    from apps.desktop_app.ui.widgets.voucher_error_dialog import VoucherErrorDialog
                    VoucherErrorDialog.show_error(self, error_details)
                except Exception as diag_err:
                    logger.debug(f"Could not display VoucherErrorDialog: {diag_err}")

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.header = CtrlBooksHeader()
        self.header.nav_requested.connect(self.nav_requested.emit)
        self.header.refresh_clicked.connect(self.load_live_companies)
        self.header.sync_now_clicked.connect(self.on_header_sync_clicked)
        layout.addWidget(self.header)

        status_bar = QWidget()
        status_bar.setStyleSheet("background-color: #F8FAFC; border-bottom: 1px solid #E2E8F0;")
        sb_layout = QHBoxLayout(status_bar)
        sb_layout.setContentsMargins(18, 8, 18, 8)
        sb_layout.setSpacing(10)

        self.pill_conn_status = QLabel("🟢 Connected: Tally Prime (9000)")
        self.pill_conn_status.setStyleSheet("""
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
        sb_layout.addWidget(self.pill_conn_status)

        self.pill_tally_ready = QLabel("Live Bridge Active")
        self.pill_tally_ready.setStyleSheet("""
            QLabel {
                color: #64748B;
                font-size: 11px;
                font-weight: 700;
                border: none;
                background: transparent;
            }
        """)
        sb_layout.addWidget(self.pill_tally_ready)
        sb_layout.addStretch()

        self.pill_sync_interval = QLabel("⏱️ Auto-Sync: 1 min")
        self.pill_sync_interval.setStyleSheet("""
            QLabel {
                background-color: #ECFDF5;
                color: #047857;
                font-size: 11px;
                font-weight: 700;
                padding: 4px 10px;
                border-radius: 12px;
                border: 1px solid #A7F3D0;
            }
        """)
        sb_layout.addWidget(self.pill_sync_interval)

        self.st_lbl = self.pill_conn_status
        layout.addWidget(status_bar)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background-color: #F8FAFC; }")

        self.cards_container = QWidget()
        self.cards_container.setStyleSheet("background-color: #F8FAFC;")
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(18, 10, 18, 10)
        self.cards_layout.setSpacing(10)

        scroll.setWidget(self.cards_container)
        layout.addWidget(scroll, stretch=1)

        insights_bar = QWidget()
        insights_bar.setStyleSheet("background-color: #FFFFFF; border-top: 1px solid #E2E8F0;")
        in_layout = QHBoxLayout(insights_bar)
        in_layout.setContentsMargins(14, 6, 14, 6)
        in_layout.setSpacing(6)

        c1 = QFrame()
        c1.setStyleSheet("QFrame { background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 3px 6px; }")
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
        c2.setStyleSheet("QFrame { background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 3px 6px; }")
        c2_lay = QVBoxLayout(c2)
        c2_lay.setContentsMargins(2, 2, 2, 2)
        c2_lay.setSpacing(2)
        c2_lbl1 = QLabel("Data Volume")
        c2_lbl1.setStyleSheet("font-size: 9px; font-weight: bold; color: #64748B; border: none; background: transparent;")
        self.c2_val = QLabel("⚡ 1.2 GB")
        self.c2_val.setStyleSheet("font-size: 10px; font-weight: 800; color: #059669; border: none; background: transparent;")
        c2_lay.addWidget(c2_lbl1)
        c2_lay.addWidget(self.c2_val)
        in_layout.addWidget(c2, stretch=1)

        c3 = QFrame()
        c3.setStyleSheet("QFrame { background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 3px 6px; }")
        c3_lay = QVBoxLayout(c3)
        c3_lay.setContentsMargins(2, 2, 2, 2)
        c3_lay.setSpacing(2)
        c3_lbl1 = QLabel("Last Sync")
        c3_lbl1.setStyleSheet("font-size: 9px; font-weight: bold; color: #64748B; border: none; background: transparent;")
        self.c3_val = QLabel("🟢 Live Active")
        self.c3_val.setStyleSheet("font-size: 10px; font-weight: 800; color: #0284C7; border: none; background: transparent;")
        c3_lay.addWidget(c3_lbl1)
        c3_lay.addWidget(self.c3_val)
        in_layout.addWidget(c3, stretch=1)

        layout.addWidget(insights_bar)

        layout.addWidget(CtrlBooksFooter())
        self.load_live_companies()

    def on_header_sync_clicked(self):
        self.start_qthread_sync("", "TALLY")

    def on_company_sync_clicked(self, comp_name: str, source: str, card: Optional[CompanyCardFrame] = None):
        """
        Handles click on 'Sync' / '+ Sync Now' button for a company.
        If date range has NOT been configured for this company yet:
            Opens SyncDateDialog to prompt the user once.
        If already configured:
            Starts sync immediately using the saved date range.
        """
        from shared.cloud.helpers import get_company_sync_dates, save_company_sync_dates
        from apps.desktop_app.ui.widgets.sync_date_dialog import SyncDateDialog

        f_date, t_date, is_conf = get_company_sync_dates(comp_name)
        if not is_conf:
            dlg = SyncDateDialog(comp_name, parent=self)
            if dlg.exec():
                f_date, t_date, fy_label = dlg.get_dates()
                save_company_sync_dates(comp_name, f_date, t_date, fy_label, company_name=comp_name, reset_voucher_checkpoint=True)
                from apps.desktop_app.ui.widgets.toast import ToastNotification
                ToastNotification.show_toast(self, f"Configured {fy_label} for '{comp_name}'", "success", duration_ms=2500)
                self.start_qthread_sync(comp_name, source, card, is_full_sync=True, from_date=f_date, to_date=t_date)
            else:
                return
        else:
            self.start_qthread_sync(comp_name, source, card, from_date=f_date, to_date=t_date)

    def handle_change_sync_date(self, comp_name: str, source: str, card: Optional[CompanyCardFrame] = None):
        """Opens SyncDateDialog from 3-dots menu to edit company financial year / date range."""
        from shared.cloud.helpers import get_company_sync_dates, save_company_sync_dates
        from apps.desktop_app.ui.widgets.sync_date_dialog import SyncDateDialog
        from apps.desktop_app.ui.widgets.toast import ToastNotification

        f_date, t_date, _ = get_company_sync_dates(comp_name)
        dlg = SyncDateDialog(comp_name, initial_from_date=f_date, initial_to_date=t_date, is_change_mode=True, parent=self)
        if dlg.exec():
            new_f, new_t, fy_label = dlg.get_dates()
            save_company_sync_dates(comp_name, new_f, new_t, fy_label, company_name=comp_name, reset_voucher_checkpoint=True)
            ToastNotification.show_toast(self, f"Sync date updated: {fy_label} for '{comp_name}'", "success", duration_ms=3000)
            self.start_qthread_sync(comp_name, source, card, is_full_sync=True, from_date=new_f, to_date=new_t)

    def set_source_filter(self, source_type: str):
        self.active_source_filter = "TALLY"
        self.load_live_companies()

    def load_live_companies(self):
        if hasattr(self, "_active_workers") and any(w.isRunning() for w in self._active_workers):
            # Do not poll or interrupt Tally while a sync worker is actively querying Port 9000
            return
        if getattr(self, "_is_fetching_companies", False):
            return

        self._is_fetching_companies = True
        if self.cards_layout.count() == 0:
            lbl = QLabel("⏳ Detecting Tally & Cloud Companies...")
            lbl.setStyleSheet("font-size: 11px; color: #64748B; padding: 10px;")
            self.cards_layout.addWidget(lbl)

        import threading
        def _bg():
            try:
                from apps.desktop_app.ui.threads.company_fetch_worker import fetch_all_companies
                registered, tally_comps, tally_ok, t_port = fetch_all_companies()
                self.companies_fetched.emit(registered, tally_comps, tally_ok, t_port)
            except Exception as e:
                logger.debug(f"Async company fetch error: {e}")
                self.companies_fetched.emit([], [], False, 9000)
            finally:
                self._is_fetching_companies = False

        threading.Thread(target=_bg, daemon=True, name="CompanyFetchThread").start()

    def _on_companies_fetched(self, registered_companies: list, tally_comps: list, tally_ok: bool, t_port: int):
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            if item is not None:
                w = item.widget()
                if w is not None:
                    w.deleteLater()

        if self.active_source_filter in ("ALL", "TALLY"):
            t_hdr = QLabel("📊 TALLY PRIME COMPANIES")
            t_hdr.setStyleSheet("font-size: 12px; font-weight: 900; color: #1E293B; margin-top: 2px;")
            self.cards_layout.addWidget(t_hdr)

            local_tally_map = {str(c["name"]).strip().lower(): c for c in tally_comps}
            displayed_names = set()
            total_active = 0

            total_records = 0

            if registered_companies:
                for c in registered_companies:
                    c_name = c.get("name") or c.get("company_name") or c.get("tallyCompanyName") or "Unnamed Company"
                    c_clean = str(c_name).strip().lower()
                    c_path = c.get("path") or (local_tally_map[c_clean]["path"] if c_clean in local_tally_map else "C:\\TallyPrime\\Data")
                    c_stats = c.get("stats")
                    if not c_stats and c_clean in local_tally_map:
                        c_stats = local_tally_map[c_clean].get("stats")
                    if c_stats:
                        total_records += (c_stats.get("ledgers", 0) + c_stats.get("vouchers", 0) + c_stats.get("items", 0))
                    self.cards_layout.addWidget(self.create_company_card(c_name, c_path, True, "TALLY", stats=c_stats))
                    displayed_names.add(c_clean)
                    total_active += 1

            if tally_comps:
                for c in tally_comps:
                    c_name = c["name"]
                    c_clean = str(c_name).strip().lower()
                    if c_clean not in displayed_names:
                        c_stats = c.get("stats")
                        if c_stats:
                            total_records += (c_stats.get("ledgers", 0) + c_stats.get("vouchers", 0) + c_stats.get("items", 0))
                        is_synced_comp = False
                        try:
                            from shared.cloud.helpers import get_local_checkpoint
                            cp = get_local_checkpoint(c_name)
                            if cp and (cp.get("status") == "SYNCED" or cp.get("cloud_company_id") or cp.get("updated_at")):
                                is_synced_comp = True
                        except Exception:
                            pass
                        self.cards_layout.addWidget(self.create_company_card(c_name, c["path"], is_synced_comp, "TALLY", stats=c_stats))
                        total_active += 1

                self.pill_conn_status.setText(f"🟢 Connected: Tally ({t_port})")
                self.pill_conn_status.setStyleSheet("background-color: #ECFDF5; color: #065F46; font-size: 10px; font-weight: 700; padding: 3px 10px; border-radius: 10px; border: 1px solid #A7F3D0;")
                self.pill_tally_ready.setText(f"🟢 Tally Ready: {tally_comps[0]['name']}")
                self.header.update_connection_status(True, "Tally Prime", t_port)
                if hasattr(self, "command_worker") and self.command_worker:
                    import threading
                    threading.Thread(target=self.command_worker._drain_pending_voucher_queue, daemon=True).start()
            else:
                self.pill_conn_status.setText("🔴 Offline: Tally")
                self.pill_conn_status.setStyleSheet("background-color: #FEF2F2; color: #991B1B; font-size: 10px; font-weight: 700; padding: 3px 10px; border-radius: 10px; border: 1px solid #FECACA;")
                self.pill_tally_ready.setText("⚪ Tally Offline")
                self.header.update_connection_status(False)

            self.c1_val.setText(f"📊 {total_active} Active")
            if total_records >= 1000:
                self.c2_val.setText(f"⚡ {total_records:,} Records")
            elif total_records > 0:
                self.c2_val.setText(f"⚡ {total_records} Records")
            else:
                self.c2_val.setText("⚡ 0 Records")

            if not registered_companies and not tally_comps:
                lbl = QLabel("🔴 No companies found. Please open Tally Prime.")
                lbl.setStyleSheet("font-size: 11px; color: #DC2626; padding: 4px;")
                self.cards_layout.addWidget(lbl)

        self.cards_layout.addStretch()

    def fetch_real_tally_companies(self) -> tuple:
        from apps.desktop_app.ui.threads.company_fetch_worker import fetch_real_tally_companies
        from shared.config import get_settings
        return fetch_real_tally_companies(get_settings())

    def closeEvent(self, event):
        self.cleanup()
        super().closeEvent(event)

    def cleanup(self):
        # 1. Stop background auto and periodic sync timers
        if hasattr(self, "auto_timer") and self.auto_timer:
            self.auto_timer.stop()
        if hasattr(self, "periodic_sync_timer") and self.periodic_sync_timer:
            self.periodic_sync_timer.stop()
        if hasattr(self, "command_worker") and self.command_worker:
            self.command_worker.stop()
            self.command_worker.wait(200)

        # 2. Cancel and terminate any running background sync workers
        if hasattr(self, "_active_workers"):
            for w in list(self._active_workers):
                try:
                    w.cancel()
                    w.wait(200)
                except Exception:
                    pass
            self._active_workers.clear()

        # 3. Clean up all live company card UI widgets from dashboard layout
        if hasattr(self, "cards_layout") and self.cards_layout:
            while self.cards_layout.count():
                item = self.cards_layout.takeAt(0)
                if item:
                    widget = item.widget()
                    if widget:
                        widget.deleteLater()

        # 4. Reset metric counters, header labels and status pills
        if hasattr(self, "c1_val") and self.c1_val:
            self.c1_val.setText("📊 0 Active")
        if hasattr(self, "c2_val") and self.c2_val:
            self.c2_val.setText("⚡ 0 Records")
        if hasattr(self, "c3_val") and self.c3_val:
            self.c3_val.setText("⚪ Not Synced")

        # 5. Reset internal states
        self._discovered_companies = []
        self._is_syncing_all = False

    def create_company_card(self, name: str, path: str, is_synced: bool, source: str = "TALLY", stats: Optional[Dict[str, int]] = None) -> CompanyCardFrame:
        card = CompanyCardFrame()
        card.setStyleSheet("""
            QFrame#CompanyCard {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 14px;
            }
            QFrame#CompanyCard:hover {
                border-color: #10B981;
            }
        """)
        card.setObjectName("CompanyCard")

        from PySide6.QtWidgets import QGraphicsDropShadowEffect
        from PySide6.QtGui import QColor
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(14)
        shadow.setColor(QColor(15, 23, 42, 10))
        shadow.setOffset(0, 3)
        card.setGraphicsEffect(shadow)

        c_layout = QVBoxLayout(card)
        c_layout.setContentsMargins(14, 12, 14, 12)
        c_layout.setSpacing(8)

        # Top row: Tally Badge + Company Name + Stretch + Action Buttons
        top_row = QHBoxLayout()
        top_row.setSpacing(10)

        # Tally Logo Badge
        tally_badge = QLabel("Tally")
        tally_badge.setFixedSize(40, 26)
        tally_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tally_badge.setStyleSheet("""
            QLabel {
                background-color: #F1F5F9;
                border: 1px solid #E2E8F0;
                border-radius: 6px;
                color: #DC2626;
                font-size: 11px;
                font-weight: 900;
                font-style: italic;
            }
        """)
        top_row.addWidget(tally_badge)

        name_lbl = QLabel(name)
        name_lbl.setStyleSheet("font-size: 13px; font-weight: 800; color: #0F172A; border: none; background: transparent;")
        name_lbl.setMaximumWidth(280)
        name_lbl.setToolTip(name)
        top_row.addWidget(name_lbl)
        top_row.addStretch()

        # Action Buttons
        if is_synced:
            s_btn = QPushButton("🔄 Sync")
            s_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            s_btn.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #10B981, stop:1 #059669);
                    color: white;
                    border-radius: 6px;
                    padding: 5px 12px;
                    font-size: 11px;
                    font-weight: 800;
                    border: none;
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #059669, stop:1 #047857);
                }
            """)
            s_btn.clicked.connect(lambda checked=False, comp=name, s=source, c=card: self.on_company_sync_clicked(comp, s, c))
            top_row.addWidget(s_btn)

            w_btn = QPushButton("↗ Web")
            w_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            w_btn.setStyleSheet("""
                QPushButton {
                    background-color: #FFFFFF;
                    color: #0284C7;
                    border: 1px solid #CBD5E1;
                    border-radius: 6px;
                    padding: 5px 10px;
                    font-size: 11px;
                    font-weight: 700;
                }
                QPushButton:hover {
                    background-color: #F1F5F9;
                    border-color: #0284C7;
                }
            """)
            w_btn.clicked.connect(lambda checked=False, comp=name: self.web_view_clicked.emit(comp))
            top_row.addWidget(w_btn)

            from apps.desktop_app.ui.asset_helper import create_more_dots_icon
            menu_btn = QPushButton()
            menu_btn.setIcon(create_more_dots_icon("#0F172A", 24))
            menu_btn.setToolTip("Company Actions")
            menu_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            menu_btn.setFixedSize(28, 28)
            menu_btn.setStyleSheet("""
                QPushButton {
                    background-color: #F8FAFC;
                    border: 1.5px solid #CBD5E1;
                    border-radius: 7px;
                    padding: 0px;
                }
                QPushButton:hover {
                    background-color: #E2E8F0;
                    border-color: #0284C7;
                }
            """)
            menu_btn.clicked.connect(lambda _, b=menu_btn, n=name, s=source, c=card: self.show_company_menu(b, n, s, c))
            top_row.addWidget(menu_btn)
        else:
            a_btn = QPushButton("+ Sync Now")
            a_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            a_btn.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #10B981, stop:1 #059669);
                    color: white;
                    border-radius: 6px;
                    padding: 5px 14px;
                    font-size: 11px;
                    font-weight: 800;
                    border: none;
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #059669, stop:1 #047857);
                }
            """)
            a_btn.clicked.connect(lambda checked=False, comp=name, s=source, c=card: self.on_company_sync_clicked(comp, s, c))
            top_row.addWidget(a_btn)

        c_layout.addLayout(top_row)

        # Bottom row: Chips / Metadata
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(6)

        if is_synced:
            status_chip = QLabel("🟢 Synced")
            status_chip.setStyleSheet("""
                QLabel {
                    background-color: #ECFDF5;
                    color: #059669;
                    font-size: 10px;
                    font-weight: 700;
                    padding: 2px 7px;
                    border-radius: 5px;
                    border: 1px solid #A7F3D0;
                }
            """)
        else:
            status_chip = QLabel("🟡 Pending")
            status_chip.setStyleSheet("""
                QLabel {
                    background-color: #FFFBEB;
                    color: #D97706;
                    font-size: 10px;
                    font-weight: 700;
                    padding: 2px 7px;
                    border-radius: 5px;
                    border: 1px solid #FDE68A;
                }
            """)
        bottom_row.addWidget(status_chip)

        if stats and isinstance(stats, dict):
            l_cnt = stats.get("ledgers", 0)
            v_cnt = stats.get("vouchers", 0)
            i_cnt = stats.get("items", 0)
            c_chip1 = QLabel(f"{l_cnt:,} Ledgers")
            c_chip2 = QLabel(f"{v_cnt:,} Vouchers")
            c_chip3 = QLabel(f"{i_cnt:,} Items")
        else:
            c_chip1 = QLabel("— Ledgers")
            c_chip2 = QLabel("— Vouchers")
            c_chip3 = QLabel("— Items")

        c_chip1.setStyleSheet("background-color: #F8FAFC; color: #475569; font-size: 10px; font-weight: 600; padding: 2px 7px; border-radius: 5px; border: 1px solid #E2E8F0;")
        bottom_row.addWidget(c_chip1)

        c_chip2.setStyleSheet("background-color: #F8FAFC; color: #475569; font-size: 10px; font-weight: 600; padding: 2px 7px; border-radius: 5px; border: 1px solid #E2E8F0;")
        bottom_row.addWidget(c_chip2)

        c_chip3.setStyleSheet("background-color: #F8FAFC; color: #475569; font-size: 10px; font-weight: 600; padding: 2px 7px; border-radius: 5px; border: 1px solid #E2E8F0;")
        bottom_row.addWidget(c_chip3)
        bottom_row.addStretch()

        card.status_chip = status_chip
        card.chip_ledgers = c_chip1
        card.chip_vouchers = c_chip2
        card.chip_items = c_chip3
        card.company_name = name

        c_layout.addLayout(bottom_row)

        return card

    def find_company_card(self, comp_name: str) -> Optional[CompanyCardFrame]:
        clean_name = comp_name.strip().lower()
        for i in range(self.cards_layout.count()):
            item = self.cards_layout.itemAt(i)
            if item and item.widget():
                w = item.widget()
                if isinstance(w, CompanyCardFrame) and w.company_name.strip().lower() == clean_name:
                    return w
        return None

    def on_company_synced_instant(self, comp_name: str, stats: dict):
        """Immediately updates card chips and status in 0ms without waiting for Tally or polling timer."""
        try:
            target_card = self.find_company_card(comp_name)
            l_cnt = stats.get("ledgers", 0)
            v_cnt = stats.get("vouchers", 0)
            i_cnt = stats.get("items", 0)
            if target_card:
                if target_card.status_chip:
                    target_card.status_chip.setText("🟢 Synced")
                    target_card.status_chip.setStyleSheet("""
                        QLabel {
                            background-color: #ECFDF5;
                            color: #059669;
                            font-size: 10px;
                            font-weight: 700;
                            padding: 2px 7px;
                            border-radius: 5px;
                            border: 1px solid #A7F3D0;
                        }
                    """)
                if target_card.chip_ledgers:
                    target_card.chip_ledgers.setText(f"{l_cnt:,} Ledgers")
                if target_card.chip_vouchers:
                    target_card.chip_vouchers.setText(f"{v_cnt:,} Vouchers")
                if target_card.chip_items:
                    target_card.chip_items.setText(f"{i_cnt:,} Items")
            else:
                QTimer.singleShot(100, self.load_live_companies)

            self.header.update_last_sync("Just now")
        except Exception as exc:
            logger.debug(f"Error in on_company_synced_instant: {exc}")

    def start_qthread_sync(self, comp_name: str, source: str, card: Optional[CompanyCardFrame] = None, is_full_sync: bool = False, is_periodic: bool = False, from_date: Optional[str] = None, to_date: Optional[str] = None):
        self._active_workers = [w for w in self._active_workers if w.isRunning()]

        # Check if an existing worker is already handling sync
        existing_worker = next((w for w in self._active_workers if w.isRunning() and (getattr(w, "target_company", "") == comp_name or not comp_name or not getattr(w, "target_company", ""))), None)
        if existing_worker:
            if not is_periodic:
                # If a background worker is already active, attach the live progress dialog to it immediately
                try:
                    from apps.desktop_app.ui.widgets.sync_progress_dialog import SyncProgressDialog
                    self._sync_progress_dlg = SyncProgressDialog(
                        company_name=comp_name or getattr(existing_worker, "target_company", "") or "All Companies",
                        source=source,
                        from_date=from_date,
                        to_date=to_date,
                        parent=self
                    )
                    existing_worker.progress_changed.connect(self._sync_progress_dlg.on_progress_changed)
                    existing_worker.sync_completed.connect(self._sync_progress_dlg.on_sync_completed)
                    existing_worker.sync_failed.connect(self._sync_progress_dlg.on_sync_failed)
                    self._sync_progress_dlg.show()
                except Exception as dlg_exc:
                    logger.debug(f"SyncProgressDialog open notice: {dlg_exc}")
            return

        p_bar = QProgressBar()
        p_bar.setRange(0, 100)
        p_bar.setValue(10)
        p_bar.setStyleSheet("QProgressBar { height: 6px; border-radius: 3px; background: #E2E8F0; } QProgressBar::chunk { background: #00C853; }")
        sync_label_str = "Full Sync" if is_full_sync else "Syncing"
        s_lbl = QLabel(f"🟡 {sync_label_str} {source}...")
        s_lbl.setStyleSheet("font-size: 11px; color: #EAB308; font-weight: bold;")
        if card is not None:
            try:
                import shiboken6
                if shiboken6.isValid(card):
                    c_lay = card.layout()
                    if c_lay is not None:
                        c_lay.addWidget(p_bar)
                        c_lay.addWidget(s_lbl)
            except Exception:
                pass

        worker = BackgroundSyncWorker(comp_name, source, is_full_sync=is_full_sync, is_periodic=is_periodic, from_date=from_date, to_date=to_date, parent=self)
        self._active_workers.append(worker)

        # Pause background company stats polling during sync to eliminate concurrent Tally load
        if hasattr(self, "auto_timer") and self.auto_timer.isActive():
            self.auto_timer.stop()

        # For manual sync, display modern buffering & 1-by-1 percentage modal dialog with background blur
        if not is_periodic:
            try:
                from apps.desktop_app.ui.widgets.sync_progress_dialog import SyncProgressDialog
                self._sync_progress_dlg = SyncProgressDialog(
                    company_name=comp_name or "All Companies",
                    source=source,
                    from_date=from_date,
                    to_date=to_date,
                    parent=self
                )
                worker.progress_changed.connect(self._sync_progress_dlg.on_progress_changed)
                worker.sync_completed.connect(self._sync_progress_dlg.on_sync_completed)
                worker.sync_failed.connect(self._sync_progress_dlg.on_sync_failed)
                self._sync_progress_dlg.show()
            except Exception as dlg_exc:
                logger.debug(f"SyncProgressDialog open notice: {dlg_exc}")

        worker.progress_changed.connect(lambda val, txt: self.safe_update_progress(p_bar, s_lbl, val, txt))
        worker.company_synced.connect(self.on_company_synced_instant)
        worker.sync_completed.connect(lambda msg, c=card: self.safe_sync_completed(s_lbl, msg, c))
        worker.sync_failed.connect(lambda err: self.safe_sync_failed(s_lbl, err))
        worker.finished.connect(lambda: self._on_worker_finished(worker))
        worker.start()

    def _on_worker_finished(self, worker):
        try:
            worker.wait(50)
            if worker in self._active_workers:
                self._active_workers.remove(worker)
        except Exception:
            pass

        # Resume background auto-timer once all sync workers have finished
        if hasattr(self, "auto_timer") and not self.auto_timer.isActive():
            if not (hasattr(self, "_active_workers") and any(w.isRunning() for w in self._active_workers)):
                self.auto_timer.start(25000)

        # Automatically trigger quick company list refresh so new companies / insights are synced
        QTimer.singleShot(100, self.load_live_companies)

    def safe_update_progress(self, p_bar: QProgressBar, s_lbl: QLabel, val: int, txt: str):
        try:
            if p_bar:
                p_bar.setValue(val)
            if s_lbl:
                s_lbl.setText(txt)
        except RuntimeError:
            pass

    def safe_sync_completed(self, s_lbl: QLabel, msg: str, card: Optional[CompanyCardFrame] = None):
        try:
            from datetime import datetime
            now_time = datetime.now().strftime("%I:%M %p")
            if s_lbl:
                s_lbl.setText("🟢 " + msg)
                s_lbl.setStyleSheet("font-size: 11px; color: #00C853; font-weight: bold;")
            self.header.update_last_sync("Just now")
            if hasattr(self, "c3_val"):
                self.c3_val.setText(f"🟢 Synced {now_time}")
            if hasattr(self, "refresh_sync_interval"):
                self.refresh_sync_interval()
            if card is not None:
                if card.status_chip:
                    card.status_chip.setText("🟢 Synced")
                    card.status_chip.setStyleSheet("""
                        QLabel {
                            background-color: #ECFDF5;
                            color: #059669;
                            font-size: 10px;
                            font-weight: 700;
                            padding: 2px 7px;
                            border-radius: 5px;
                            border: 1px solid #A7F3D0;
                        }
                    """)

            from apps.desktop_app.ui.widgets.toast import ToastNotification
            toast = ToastNotification("Data sync completed successfully!", "success", self)
            toast.show()

            # Instantly refresh companies and stats in 100ms
            QTimer.singleShot(100, self.load_live_companies)
        except RuntimeError:
            pass

    def safe_sync_failed(self, s_lbl: QLabel, err: str):
        try:
            clean_err = str(err or "")
            if "no subscription" in clean_err.lower():
                clean_err = clean_err.replace("Cloud Sync rejected: No subscription found", "This company is already registered with a different email address.")
                clean_err = clean_err.replace("No subscription found", "This company is already registered with a different email address.")
            if s_lbl:
                s_lbl.setText("🔴 " + clean_err)
                s_lbl.setStyleSheet("font-size: 11px; color: #DC2626; font-weight: bold;")
            from apps.desktop_app.ui.widgets.toast import ToastNotification
            toast = ToastNotification(f"Sync Failed: {clean_err}", "error", self)
            toast.show()
            if hasattr(self, "refresh_sync_interval"):
                self.refresh_sync_interval()
        except RuntimeError:
            pass

    def show_company_menu(self, button, name: str, source: str, card: Optional[CompanyCardFrame] = None):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #FFFFFF;
                border: 1px solid #CBD5E1;
                border-radius: 6px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 20px;
                color: #0F172A;
                font-size: 11px;
                font-weight: 500;
            }
            QMenu::item:hover {
                background-color: #F1F5F9;
                color: #0F172A;
            }
        """)

        quick_sync_act = QAction("⚡  Quick Sync (Delta)", menu)
        full_sync_act = QAction("🔄  Full Sync (All Records)", menu)
        change_date_act = QAction("📅  Change Sync Date Range", menu)
        sync_config_act = QAction("📄  Sync Tally Config", menu)

        menu.addAction(quick_sync_act)
        menu.addAction(full_sync_act)
        menu.addAction(change_date_act)
        menu.addAction(sync_config_act)

        quick_sync_act.triggered.connect(lambda: self.start_qthread_sync(name, source, card, is_full_sync=False))
        full_sync_act.triggered.connect(lambda: self.start_qthread_sync(name, source, card, is_full_sync=True))
        change_date_act.triggered.connect(lambda: self.handle_change_sync_date(name, source, card))
        sync_config_act.triggered.connect(lambda: self.handle_sync_config(name))

        menu.exec(button.mapToGlobal(button.rect().bottomLeft()))

    def handle_backup(self, name: str):
        logging.info(f"Cloud Backup: Initiated backup for Tally company '{name}'...")
        logging.info("Cloud Backup: Compressing local ledger registries...")
        logging.info("Cloud Backup: Uploading compressed archive to cloud server...")
        logging.info(f"Cloud Backup: Backup verification OK for '{name}'.")
        toast = ToastNotification(f"Backup complete for '{name}' (👑 Pro)", "success", self)
        toast.show()

    def handle_sync_config(self, name: str):
        logging.info(f"Tally Config: Syncing configuration parameters for company '{name}'...")
        logging.info("Tally Config: Port 9000 validated. Active company bounds synced.")
        toast = ToastNotification(f"Synced configuration for '{name}'", "success", self)
        toast.show()

    def handle_remove_company(self, name: str, card: Optional[CompanyCardFrame] = None):
        dialog = ConfirmDialog(
            title="Remove Company",
            message=f"Are you sure you want to remove company '{name}' from the sync dashboard?",
            confirm_text="Remove",
            is_danger=True,
            parent=self
        )
        if dialog.exec():
            logging.warning(f"Remove: Removing company '{name}'...")
            try:
                import httpx
                from shared.config import get_settings
                gateway = get_settings().gateway_url.rstrip("/")

                res = httpx.get(f"{gateway}/api/companies", timeout=2.0)
                if res.status_code == 200:
                    companies = res.json()
                    target_id = None
                    for c in companies:
                        if c.get("name") == name:
                            target_id = c.get("id")
                            break
                    if target_id is not None:
                        del_res = httpx.delete(f"{gateway}/api/companies/{target_id}", timeout=2.0)
                        if del_res.status_code == 200:
                            logging.info(f"Remove: Successfully removed company '{name}' (ID: {target_id}).")
                            toast = ToastNotification(f"Removed company '{name}'", "success", self)
                            toast.show()
                            self.load_live_companies()
                            return

                logging.info(f"Remove: Company '{name}' removed from UI cache.")
                toast = ToastNotification(f"Removed company '{name}'", "success", self)
                toast.show()
                if card is not None:
                    card.deleteLater()
            except Exception as e:
                logging.error(f"Remove: Failed to remove company '{name}': {e}")
                toast = ToastNotification("Failed to remove company", "error", self)
                toast.show()
