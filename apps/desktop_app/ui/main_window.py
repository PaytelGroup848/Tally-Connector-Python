

from pathlib import Path
from PySide6.QtWidgets import QMainWindow, QStackedWidget, QSystemTrayIcon, QApplication, QMessageBox
from PySide6.QtCore import QTimer, QUrl, QThread, Signal
from PySide6.QtGui import QDesktopServices, QIcon

from apps.desktop_app.ui.screens.login_screen import LoginScreen
from apps.desktop_app.ui.screens.connection_probe_screen import ConnectionProbeScreen
from apps.desktop_app.ui.screens.connected_dashboard_screen import ConnectedDashboardScreen
from apps.desktop_app.ui.screens.profile_screen import ProfileScreen
from apps.desktop_app.ui.screens.connection_settings_screen import ConnectionSettingsScreen
from apps.desktop_app.ui.screens.system_requirement_screen import SystemRequirementScreen
from apps.desktop_app.ui.screens.activity_history_screen import ActivityHistoryScreen
from apps.desktop_app.ui.tray_icon import ConnectorSystemTray


class BackgroundUpdateCheckThread(QThread):
    update_result_signal = Signal(dict)

    def __init__(self, current_version=None, parent=None):
        super().__init__(parent)
        self.current_version = current_version

    def run(self):
        try:
            from shared.updater import updater_service
            res = updater_service.check_for_updates(self.current_version)
            self.update_result_signal.emit(res)
        except Exception as exc:
            self.update_result_signal.emit({"update_available": False, "error": str(exc)})


class ConnectorMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CtrlBooks")
        self.setMinimumSize(620, 580)
        self.resize(650, 610)
        self.is_force_exit = False
        self.update_dialog = None
        self.update_check_thread = None

        from apps.desktop_app.ui.asset_helper import get_asset_path
        icon_path = get_asset_path("app_icon.ico")
        if not icon_path.exists():
            icon_path = get_asset_path("app_icon.png")
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        self.init_ui()
        self.setup_tray_icon()

        # Automatic update check on launch (runs in background after 4s)
        QTimer.singleShot(4000, self.check_for_updates_background)

        # Periodic background check every 2 hours
        self.periodic_update_timer = QTimer(self)
        self.periodic_update_timer.timeout.connect(self.check_for_updates_background)
        self.periodic_update_timer.start(2 * 60 * 60 * 1000)

    def init_ui(self):
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.sc_login = LoginScreen()
        self.sc_login.login_successful.connect(self.on_login_successful)

        self.sc_probe = ConnectionProbeScreen()
        self.sc_probe.connection_established.connect(lambda: self.stack.setCurrentWidget(self.sc_dash))
        self.sc_probe.connection_established_for_source.connect(self.on_probe_source_selected)
        self.sc_probe.nav_requested.connect(self.handle_nav)

        self.sc_dash = ConnectedDashboardScreen()
        self.sc_dash.nav_requested.connect(self.handle_nav)
        self.sc_dash.web_view_clicked.connect(self.open_web_view)

        self.sc_profile = ProfileScreen()
        self.sc_profile.back_requested.connect(lambda: self.stack.setCurrentWidget(self.sc_dash))
        self.sc_profile.nav_requested.connect(self.handle_nav)

        self.sc_settings = ConnectionSettingsScreen()
        self.sc_settings.back_requested.connect(lambda: self.stack.setCurrentWidget(self.sc_dash))
        self.sc_settings.nav_requested.connect(self.handle_nav)

        self.sc_system = SystemRequirementScreen()
        self.sc_system.back_requested.connect(lambda: self.stack.setCurrentWidget(self.sc_dash))
        self.sc_system.nav_requested.connect(self.handle_nav)

        self.sc_activity = ActivityHistoryScreen()
        self.sc_activity.back_requested.connect(lambda: self.stack.setCurrentWidget(self.sc_dash))
        self.sc_activity.nav_requested.connect(self.handle_nav)

        self.stack.addWidget(self.sc_login)
        self.stack.addWidget(self.sc_probe)
        self.stack.addWidget(self.sc_dash)
        self.stack.addWidget(self.sc_profile)
        self.stack.addWidget(self.sc_settings)
        self.stack.addWidget(self.sc_system)
        self.stack.addWidget(self.sc_activity)

        for sc in [self.sc_login, self.sc_probe, self.sc_dash, self.sc_profile, self.sc_settings, self.sc_system, self.sc_activity]:
            if hasattr(sc.header, "minimize_clicked"):
                sc.header.minimize_clicked.connect(self.hide)
            if hasattr(sc.header, "close_clicked"):
                sc.header.close_clicked.connect(self.close)

        self.stack.setCurrentWidget(self.sc_login)

    def on_login_successful(self, mobile: str):
        self.stack.setCurrentWidget(self.sc_probe)
        QTimer.singleShot(500, self.sc_probe.check_connection)

    def on_probe_source_selected(self, source_type: str):
        self.sc_dash.set_source_filter(source_type)
        self.stack.setCurrentWidget(self.sc_dash)

    def handle_nav(self, target: str):
        if target == "probe":
            self.stack.setCurrentWidget(self.sc_probe)
            self.sc_probe.check_connection()
        elif target == "profile":
            self.stack.setCurrentWidget(self.sc_profile)
        elif target == "settings":
            self.stack.setCurrentWidget(self.sc_settings)
        elif target == "system":
            self.sc_system.run_system_checks()
            self.stack.setCurrentWidget(self.sc_system)
        elif target == "activity":
            self.sc_activity.load_activities()
            self.stack.setCurrentWidget(self.sc_activity)
        elif target == "logout":
            self.stack.setCurrentWidget(self.sc_login)

    def open_web_view(self, company_name: str):
        from urllib.parse import urlencode
        import re
        from shared.config import get_settings
        from shared.auth.cloud_auth_service import cloud_auth_service
        from shared.logging_config import get_logger

        logger = get_logger("app.desktop.main_window")
        settings = get_settings()
        web_base = (settings.web_portal_url or "https://connector.cloudedata.com").rstrip("/")

        company_id = None
        c_name = (company_name or "").strip()

        # 1. Look up company_id from MongoDB 'companies' collection
        if c_name:
            try:
                from shared.db.mongo_client import get_collection
                col = get_collection("companies")
                doc = col.find_one({
                    "$or": [
                        {"name": c_name},
                        {"company_name": c_name},
                        {"tallyCompanyName": c_name},
                        {"name": {"$regex": f"^{re.escape(c_name)}$", "$options": "i"}},
                        {"company_name": {"$regex": f"^{re.escape(c_name)}$", "$options": "i"}},
                    ]
                })
                if doc:
                    company_id = doc.get("cloud_company_id") or str(doc.get("_id") or "") or doc.get("id")
            except Exception as exc:
                logger.warning(f"Error looking up company_id in MongoDB for '{c_name}': {exc}")

        # 2. Fallback: Query Cloud companies API if not found in MongoDB
        if not company_id and c_name and cloud_auth_service.access_token:
            try:
                import httpx
                headers = {"Authorization": f"Bearer {cloud_auth_service.access_token}"}
                resp = httpx.get(f"{cloud_auth_service.base_url}/companies", headers=headers, timeout=3.0)
                if resp.status_code == 200:
                    c_list = resp.json().get("data", {}).get("companies", [])
                    for item in c_list:
                        item_name = item.get("tallyCompanyName") or item.get("name") or ""
                        if item_name.lower().strip() == c_name.lower().strip():
                            company_id = item.get("id") or item.get("_id")
                            break
            except Exception as exc:
                logger.warning(f"Error querying cloud companies endpoint for '{c_name}': {exc}")

        # Construct target route
        if company_id:
            route = f"{web_base}/company-details/{company_id}"
        else:
            route = f"{web_base}/dashboard"

        # Construct query parameters for auto-authentication & company pre-selection
        params = {}
        token = cloud_auth_service.access_token or ""
        if token:
            params["token"] = token
            params["accessToken"] = token
        if company_id:
            params["companyId"] = company_id
            params["company"] = company_id
        if c_name:
            params["companyName"] = c_name

        email = (
            cloud_auth_service.current_user.get("email")
            or getattr(cloud_auth_service, "email", "")
            or ""
        )
        if not email:
            try:
                from shared.db.mongo_client import get_collection
                up_col = get_collection("user_profile")
                up_doc = up_col.find_one({"profile_id": "current_user"})
                if up_doc and up_doc.get("email"):
                    email = up_doc.get("email")
            except Exception:
                pass
        if email:
            params["email"] = email

        if params:
            full_url = f"{route}?{urlencode(params)}"
        else:
            full_url = route

        logger.info(f"Opening Web Access URL: {full_url}")
        QDesktopServices.openUrl(QUrl(full_url))

    def setup_tray_icon(self):
        self.tray_icon = ConnectorSystemTray(self)
        self.tray_icon.open_dashboard_requested.connect(self.restore_window)
        self.tray_icon.sync_now_requested.connect(self.trigger_sync_now)
        self.tray_icon.toggle_pause_requested.connect(self.on_toggle_pause_sync)
        self.tray_icon.check_updates_requested.connect(self.check_for_updates_interactive)
        self.tray_icon.exit_requested.connect(self.force_exit_app)

    def check_for_updates_background(self):
        self._trigger_update_check(interactive=False)

    def check_for_updates_interactive(self):
        self.restore_window()
        self._trigger_update_check(interactive=True)

    def _trigger_update_check(self, interactive: bool = False):
        if self.update_check_thread and self.update_check_thread.isRunning():
            return

        self.update_check_thread = BackgroundUpdateCheckThread(parent=self)
        self.update_check_thread.update_result_signal.connect(
            lambda res: self.on_update_check_completed(res, interactive)
        )
        self.update_check_thread.start()

    def on_update_check_completed(self, result: dict, interactive: bool):
        if result.get("update_available"):
            latest = result.get("latest_version")
            if hasattr(self, "tray_icon"):
                self.tray_icon.show_toast(
                    "CtrlBooks Update",
                    f"A new version (v{latest}) is available to install.",
                    QSystemTrayIcon.MessageIcon.Information
                )
            self.show_update_dialog(result)
        elif interactive:
            curr = result.get("current_version", "1.0.0")
            err = result.get("error")
            if err:
                QMessageBox.warning(
                    self,
                    "Update Check Failed",
                    f"Could not connect to update server:\n{err}"
                )
            else:
                QMessageBox.information(
                    self,
                    "No Updates Available",
                    f"You are running the latest version (v{curr}) of CtrlBooks."
                )

    def show_update_dialog(self, update_info: dict):
        if self.update_dialog and self.update_dialog.isVisible():
            self.update_dialog.raise_()
            self.update_dialog.activateWindow()
            return

        from apps.desktop_app.ui.widgets.update_dialog import UpdateAvailableDialog
        self.restore_window()
        self.update_dialog = UpdateAvailableDialog(update_info, parent=self)
        self.update_dialog.exec()

    def restore_window(self):
        self.showNormal()
        self.activateWindow()

    def trigger_sync_now(self):
        self.tray_icon.show_toast("Syncing", "Manual background sync started...")

    def on_toggle_pause_sync(self):
        pass

    def closeEvent(self, event):
        if not self.is_force_exit:
            event.ignore()
            self.hide()
            self.tray_icon.show_toast(
                "CtrlBooks",
                "App is running in background system tray.",
                QSystemTrayIcon.MessageIcon.Information,
            )

    def force_exit_app(self):
        self.is_force_exit = True
        QApplication.quit()
