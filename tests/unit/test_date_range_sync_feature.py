import pytest
from unittest.mock import MagicMock
from PySide6.QtWidgets import QApplication
import sys

from shared.cloud.helpers import (
    format_to_tally_date,
    get_company_sync_dates,
    save_company_sync_dates,
    get_local_checkpoint
)

@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


def test_01_format_to_tally_date_formats():
    assert format_to_tally_date("2024-04-01") == "20240401"
    assert format_to_tally_date("01-04-2024") == "20240401"
    assert format_to_tally_date("31-03-2025") == "20250331"
    assert format_to_tally_date("2025-03-31") == "20250331"
    assert format_to_tally_date("20240401") == "20240401"
    assert format_to_tally_date("01/04/2024") == "20240401"
    assert format_to_tally_date("") == ""


def test_02_save_and_get_company_sync_dates():
    comp = "Test Company Date Ltd"
    save_company_sync_dates(comp, "2024-04-01", "2025-03-31", fy_label="FY 2024-2025")

    f_date, t_date, is_conf = get_company_sync_dates(comp)
    assert is_conf is True
    assert f_date == "2024-04-01"
    assert t_date == "2025-03-31"

    cp = get_local_checkpoint(comp)
    assert cp["financial_year"] == "FY 2024-2025"
    assert cp["date_configured"] is True


def test_03_date_change_resets_voucher_alter_id():
    comp = "Test Reset Co"
    # First save with alter_id
    from shared.cloud.helpers import set_local_checkpoint
    set_local_checkpoint(comp, last_voucher_alter_id=4500)
    cp = get_local_checkpoint(comp)
    assert cp["last_voucher_alter_id"] == 4500

    # User changes date range -> must reset voucher alter id to 0
    save_company_sync_dates(comp, "2023-04-01", "2024-03-31", fy_label="FY 2023-2024", reset_voucher_checkpoint=True)
    cp_after = get_local_checkpoint(comp)
    assert cp_after["last_voucher_alter_id"] == 0
    assert cp_after["sync_from_date"] == "2023-04-01"


def test_04_sync_date_dialog_presets(qapp):
    from apps.desktop_app.ui.widgets.sync_date_dialog import SyncDateDialog

    dlg = SyncDateDialog("Nikhil Trader", initial_from_date="2024-04-01", initial_to_date="2025-03-31")
    f_str, t_str, fy = dlg.get_dates()
    assert f_str == "2024-04-01"
    assert t_str == "2025-03-31"
    assert fy == "FY 2024-2025"

    # Switch preset to FY 2025-2026
    dlg.combo_presets.setCurrentIndex(0)
    f_str2, t_str2, fy2 = dlg.get_dates()
    assert f_str2 == "2025-04-01"
    assert t_str2 == "2026-03-31"
    assert fy2 == "FY 2025-2026"


def test_05_voucher_syncer_uses_saved_dates_in_xml(monkeypatch):
    from apps.desktop_app.ui.threads.sync_handlers.voucher_syncer import sync_vouchers

    comp = "Nikhil Trader"
    save_company_sync_dates(comp, "2024-04-01", "2025-03-31", fy_label="FY 2024-2025")

    captured_xmls = []
    fake_client = MagicMock()
    def fake_send(host, port, xml_text, timeout=300.0):
        captured_xmls.append(xml_text)
        return True, 200, "<ENVELOPE></ENVELOPE>", None
    fake_client.send_xml_request = fake_send

    fake_worker = MagicMock()
    fake_worker.tally_client = fake_client
    fake_worker.tally_host = "127.0.0.1"

    sync_vouchers(fake_worker, comp, 9000, "2026-10-29T00:00:00Z", None, None)

    assert len(captured_xmls) > 0
    first_xml = captured_xmls[0]
    # Must contain the user's selected date range in Tally YYYYMMDD format
    assert '<SVFROMDATE TYPE="Date">20240401</SVFROMDATE>' in first_xml
    assert '<SVTODATE TYPE="Date">20250331</SVTODATE>' in first_xml


def test_06_checkpoint_update_preserves_date_range():
    from shared.cloud.helpers import set_local_checkpoint

    comp_name = "Persistent Maurya Ltd"
    cloud_cid = "6ae2ef21dc9ff2faff789999"

    # Step 1: User saves dates in UI dialog
    save_company_sync_dates(
        company_key=comp_name,
        from_date="2024-04-01",
        to_date="2027-03-31",
        fy_label="Custom Date Range",
        company_name=comp_name
    )

    f, t, is_conf = get_company_sync_dates(comp_name)
    assert is_conf is True
    assert f == "2024-04-01"
    assert t == "2027-03-31"

    # Step 2: Background sync finishes and updates checkpoint with alter_id and cloud_company_id
    set_local_checkpoint(
        company_key=cloud_cid,
        last_alter_id=500,
        last_voucher_alter_id=45,
        status="SYNCED",
        company_name=comp_name,
        cloud_company_id=cloud_cid,
        stats={"ledgers": 10, "vouchers": 5, "items": 2}
    )

    # Step 3: Verify dates were NOT wiped out by set_local_checkpoint
    f_after, t_after, is_conf_after = get_company_sync_dates(comp_name)
    assert is_conf_after is True, "Date range should NOT be wiped out by set_local_checkpoint!"
    assert f_after == "2024-04-01"
    assert t_after == "2027-03-31"

    # Check by cloud_cid as well
    f_cid, t_cid, is_conf_cid = get_company_sync_dates(cloud_cid)
    assert is_conf_cid is True
    assert f_cid == "2024-04-01"
    assert t_cid == "2027-03-31"

    # Step 4: Verify checkpoint data contains both alter_ids AND date fields
    cp_by_name = get_local_checkpoint(comp_name)
    assert cp_by_name["last_alter_id"] == 500
    assert cp_by_name["last_voucher_alter_id"] == 45
    assert cp_by_name["sync_from_date"] == "2024-04-01"
    assert cp_by_name["sync_to_date"] == "2027-03-31"
    assert cp_by_name["date_configured"] is True


def test_07_sync_vouchers_drops_out_of_range_vouchers(monkeypatch):
    from apps.desktop_app.ui.threads.sync_handlers.voucher_syncer import sync_vouchers

    comp = "Date Filtered Enterprise"
    save_company_sync_dates(comp, "2024-04-01", "2025-03-31", fy_label="FY 2024-2025")

    # Mock XML response with 3 vouchers: 1 before range, 1 in range, 1 after range
    fake_tally_xml = """<ENVELOPE>
        <BODY>
            <DATA>
                <COLLECTION>
                    <VOUCHER>
                        <DATE>20220510</DATE>
                        <VOUCHERNUMBER>OLD-01</VOUCHERNUMBER>
                        <ALTERID>100</ALTERID>
                    </VOUCHER>
                    <VOUCHER>
                        <DATE>20240815</DATE>
                        <VOUCHERNUMBER>VALID-FY24-01</VOUCHERNUMBER>
                        <ALTERID>200</ALTERID>
                    </VOUCHER>
                    <VOUCHER>
                        <DATE>20260210</DATE>
                        <VOUCHERNUMBER>FUTURE-01</VOUCHERNUMBER>
                        <ALTERID>300</ALTERID>
                    </VOUCHER>
                </COLLECTION>
            </DATA>
        </BODY>
    </ENVELOPE>"""

    fake_client = MagicMock()
    fake_client.send_xml_request = MagicMock(return_value=(True, 200, fake_tally_xml, None))

    fake_worker = MagicMock()
    fake_worker.tally_client = fake_client
    fake_worker.tally_host = "127.0.0.1"

    vchs, max_alter = sync_vouchers(
        fake_worker, comp, 9000, "2026-10-29T00:00:00Z", None, None,
        from_date="2024-04-01", to_date="2025-03-31"
    )

    # MUST keep only the 1 voucher within FY 2024-2025!
    assert len(vchs) == 1, f"Expected 1 voucher in range, got {len(vchs)}"
    assert vchs[0]["voucherNumber"] == "VALID-FY24-01"
    assert max_alter == 200



