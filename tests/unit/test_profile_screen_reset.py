import pytest
from PySide6.QtWidgets import QApplication
from apps.desktop_app.ui.screens.profile_screen import ProfileScreen


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_profile_screen_init_and_reset_fields(qapp):
    """Verify that ProfileScreen initializes and reset_fields resets all UI elements cleanly."""
    screen = ProfileScreen()

    # Pre-populate some fields
    screen.lbl_device_name.setText("My-Laptop")
    screen.lbl_heartbeat.setText("10:00 AM")
    screen.plan_badge.setText("ENTERPRISE")
    screen.lbl_sub_status.setText("ACTIVE")

    # Call reset_fields (simulating logout)
    screen.reset_fields()

    # Verify reset values
    assert screen.lbl_device_name.text() == "-"
    assert screen.lbl_device_id.text() == "-"
    assert screen.lbl_org_id.text() == "-"
    assert screen.lbl_heartbeat.text() == "Never"
    assert screen.lbl_tally_state.text() == "-"
    assert screen.conn_status_badge.text() == "🔴 OFFLINE"

    assert screen.plan_badge.text() == "FREE PLAN"
    assert screen.lbl_sub_status.text() == "INACTIVE"
    assert screen.lbl_valid_period.text() == "-"
