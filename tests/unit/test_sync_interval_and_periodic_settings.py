import pytest
from unittest.mock import MagicMock, patch
from shared.connection_config import parse_interval_to_ms, save_connection_config, load_connection_config


def test_01_parse_interval_to_ms_all_cases():
    # Real-time
    assert parse_interval_to_ms("Real-time") == 30_000
    assert parse_interval_to_ms("real time") == 30_000
    assert parse_interval_to_ms("realtime") == 30_000

    # Minutes
    assert parse_interval_to_ms("1 min") == 60_000
    assert parse_interval_to_ms("1 minute") == 60_000
    assert parse_interval_to_ms("1") == 60_000
    assert parse_interval_to_ms("2 mins") == 120_000
    assert parse_interval_to_ms("5 mins") == 300_000
    assert parse_interval_to_ms("10 mins") == 600_000
    assert parse_interval_to_ms("15 mins") == 900_000
    assert parse_interval_to_ms("30 mins") == 1_800_000

    # Hours
    assert parse_interval_to_ms("1 hour") == 3_600_000
    assert parse_interval_to_ms("2 hours") == 7_200_000

    # Manual / Disabled
    assert parse_interval_to_ms("Manual") == 0
    assert parse_interval_to_ms("0") == 0
    assert parse_interval_to_ms("off") == 0
    assert parse_interval_to_ms("disabled") == 0

    # Default fallback (1 minute / 60,000 ms)
    assert parse_interval_to_ms(None) == 60_000
    assert parse_interval_to_ms("") == 60_000


def test_02_connection_settings_persistence(tmp_path):
    # Save 1 min
    save_connection_config(host="127.0.0.1", port=9047, sync_interval_minutes="1 min", auto_connect=True)
    cfg = load_connection_config()
    assert cfg.get("sync_interval_minutes") == "1 min"
    assert cfg.get("tally_port") == 9047

    # Save Real-time
    save_connection_config(host="127.0.0.1", port=9000, sync_interval_minutes="Real-time", auto_connect=True)
    cfg2 = load_connection_config()
    assert cfg2.get("sync_interval_minutes") == "Real-time"
    assert cfg2.get("tally_port") == 9000


def test_03_periodic_sync_worker_prioritizes_open_tally_companies(monkeypatch):
    from apps.desktop_app.ui.threads.sync_worker import BackgroundSyncWorker

    open_tally_comps = [
        {"name": "Madan Pvt Ltd", "guid": "guid-madan-123"}
    ]
    cloud_configs = [
        {"company_name": "Sanjay Limited", "cloud_company_id": "sanjay-id"},
        {"company_name": "Madan Pvt Ltd", "cloud_company_id": "madan-id"}
    ]

    worker = BackgroundSyncWorker(target_company="", source="TALLY", is_periodic=True)
    monkeypatch.setattr(worker, "_discover_tally_ports", lambda: 9000)
    monkeypatch.setattr(worker, "_get_open_tally_companies", lambda port: open_tally_comps)
    monkeypatch.setattr("apps.desktop_app.ui.threads.sync_worker.get_all_company_configs", lambda: cloud_configs)

    synced_comps = []
    def fake_sync(comp, idx, total, port, open_comps):
        synced_comps.append(comp["company_name"])
        return True, ""

    monkeypatch.setattr(worker, "_sync_single_company", fake_sync)

    worker.run()
    # It must sync Madan Pvt Ltd which is OPEN in Tally, NOT Sanjay Limited which is closed!
    assert synced_comps == ["Madan Pvt Ltd"]


def test_04_periodic_sync_worker_silently_idles_when_no_company_open(monkeypatch):
    from apps.desktop_app.ui.threads.sync_worker import BackgroundSyncWorker

    worker = BackgroundSyncWorker(target_company="", source="TALLY", is_periodic=True)
    monkeypatch.setattr(worker, "_discover_tally_ports", lambda: 9000)
    monkeypatch.setattr(worker, "_get_open_tally_companies", lambda port: [])
    monkeypatch.setattr("apps.desktop_app.ui.threads.sync_worker.get_all_company_configs", lambda: [])

    failed_emitted = []
    worker.sync_failed.connect(lambda err: failed_emitted.append(err))

    worker.run()
    # Periodic sync MUST NOT emit sync_failed when no company is open!
    assert len(failed_emitted) == 0


def test_05_refresh_sync_interval_live_timer_update():
    from PySide6.QtWidgets import QApplication
    from apps.desktop_app.ui.screens.connected_dashboard_screen import ConnectedDashboardScreen

    app = QApplication.instance() or QApplication([])
    dash = ConnectedDashboardScreen()

    # 1. Default or 1 min -> 60,000 ms
    dash.refresh_sync_interval("1 min")
    assert dash.periodic_sync_timer.interval() == 60_000
    assert dash.c3_val.text() == "🟢 Every 1 min"

    # 2. Change to 2 mins -> 120,000 ms
    dash.refresh_sync_interval("2 mins")
    assert dash.periodic_sync_timer.interval() == 120_000
    assert dash.c3_val.text() == "🟢 Every 2 mins"

    # 3. Change to 15 mins -> 900,000 ms
    dash.refresh_sync_interval("15 mins")
    assert dash.periodic_sync_timer.interval() == 900_000
    assert dash.c3_val.text() == "🟢 Every 15 mins"

    # 4. Change to Real-time -> 30,000 ms
    dash.refresh_sync_interval("Real-time")
    assert dash.periodic_sync_timer.interval() == 30_000
    assert dash.c3_val.text() == "🟢 Every Real-time"

    # 5. Change to Manual -> Stopped (0 ms)
    dash.refresh_sync_interval("Manual")
    assert not dash.periodic_sync_timer.isActive()
    assert dash.c3_val.text() == "⚪ Manual Sync"

    dash.cleanup()


def test_06_dynamic_discovery_does_not_overwrite_user_sync_interval():
    """Verify that background port discoveries do not overwrite the user's sync interval setting."""
    # User selects 5 mins
    save_connection_config(sync_interval_minutes="5 mins")
    assert load_connection_config().get("sync_interval_minutes") == "5 mins"

    # Dynamic port discovery updates port/host without interval
    save_connection_config(host="127.0.0.1", port=9000)
    save_connection_config(port=9001)
    save_connection_config(host="localhost")

    # Sync interval must REMAIN 5 mins
    cfg = load_connection_config()
    assert cfg.get("sync_interval_minutes") == "5 mins"

    # User selects Manual
    save_connection_config(sync_interval_minutes="Manual")
    assert load_connection_config().get("sync_interval_minutes") == "Manual"

    save_connection_config(port=9000)
    assert load_connection_config().get("sync_interval_minutes") == "Manual"

    # Reset to default 1 min
    save_connection_config(sync_interval_minutes="1 min", port=9000)
    assert load_connection_config().get("sync_interval_minutes") == "1 min"



