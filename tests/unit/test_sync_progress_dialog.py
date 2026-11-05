import pytest
from unittest.mock import MagicMock
from PySide6.QtWidgets import QApplication, QWidget
from apps.desktop_app.ui.widgets.sync_progress_dialog import SyncProgressDialog


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_sync_progress_dialog_initialization(qapp):
    parent = QWidget()
    dlg = SyncProgressDialog(
        company_name="Tarun Enterprise (25-26)",
        source="TALLY",
        from_date="2025-04-01",
        to_date="2026-03-31",
        parent=parent
    )
    assert dlg.company_name == "Tarun Enterprise (25-26)"
    assert dlg._current_pct == 0
    assert dlg.progress_bar.value() == 0
    assert "Tarun Enterprise" in dlg.title_lbl.text()
    assert "2025-04-01" in dlg.sub_lbl.text()
    dlg.close()


def test_sync_progress_dialog_1_by_1_counter(qapp):
    dlg = SyncProgressDialog(company_name="Test Co", parent=None)
    # Receive progress update to 15%
    dlg.on_progress_changed(15, "Extracting Ledgers...")
    assert dlg._target_pct == 15
    assert "Extracting Ledgers" in dlg.status_lbl.text()

    # Step the counter 5 times: percentage should increase 1 by 1
    for i in range(1, 6):
        dlg._step_counter()
        assert dlg._current_pct == i
        assert dlg.pct_lbl.text() == f"{i}%"
        assert dlg.progress_bar.value() == i

    dlg.close()


def test_sync_progress_dialog_completion_and_blur(qapp):
    parent = QWidget()
    dlg = SyncProgressDialog(company_name="Test Co", parent=parent)
    # Background blur should be active
    assert dlg.parent_window.graphicsEffect() is not None

    dlg.on_progress_changed(99, "Pushing Vouchers...")
    dlg.on_sync_completed("All data synced")
    assert dlg._is_completed is True
    assert dlg._target_pct == 100

    # Fast forward counter to 100
    dlg._current_pct = 100
    dlg._step_counter()
    assert "Sync Complete!" in dlg.title_lbl.text()
    assert "✓ 100% Synced" in dlg.spinner_lbl.text()

    # Dialog dismiss removes background blur
    dlg.accept()
    assert dlg.parent_window.graphicsEffect() is None
    dlg.close()


def test_sync_progress_dialog_failure_state(qapp):
    parent = QWidget()
    dlg = SyncProgressDialog(company_name="Test Co", parent=parent)
    dlg.on_sync_failed("Tally connection timeout")

    assert dlg._is_failed is True
    assert "Sync Incomplete" in dlg.title_lbl.text()
    assert "Tally connection timeout" in dlg.status_lbl.text()
    assert dlg.action_btn.isHidden() is False
    assert dlg.action_btn.text() == "Close"

    dlg.close()
    assert dlg.parent_window.graphicsEffect() is None
