import pytest
from unittest.mock import MagicMock, patch
from shared.cloud.helpers import set_local_checkpoint, get_local_checkpoint
from apps.desktop_app.ui.threads.sync_handlers.voucher_syncer import sync_vouchers

def test_voucher_alter_id_decoupled_from_master_alter():
    comp = "Unit Test Decouple Co"
    # Given a company checkpoint where masters (ledgers/items) alter ID is 215,
    # but vouchers have never synced (last_voucher_alter_id = 0)
    set_local_checkpoint(
        comp,
        last_alter_id=215,
        last_voucher_alter_id=0,
        company_name=comp,
        force_voucher_alter_reset=True
    )
    
    cp = get_local_checkpoint(comp)
    assert cp["last_alter_id"] == 215
    assert cp["last_voucher_alter_id"] == 0

    # In sync_worker logic, raw_alt should only read last_voucher_alter_id
    raw_alt = cp.get("last_voucher_alter_id")
    # Must NOT fall back to 215
    assert raw_alt == 0

def test_self_healing_voucher_extraction_recovers_when_checkpoint_exceeds_tally():
    """
    If a checkpoint alter_id was 210, but Tally vouchers only have alterid 1 and 2,
    sync_vouchers should self-heal and extract them.
    """
    mock_worker = MagicMock()
    mock_worker.tally_host = "127.0.0.1"
    mock_worker.tally_client = MagicMock()
    
    # 1. Delta request with from_alter_id=210 returns 0 vouchers (simulating Tally filtering them out)
    # 2. Self-healing check returns 2 vouchers with alterid 1 and 2
    # 3. Full extraction recovers the 2 vouchers
    mock_tally_vouchers = [
        {"voucherNumber": "1", "alterid": "1", "amount": 39235.0, "voucherType": "Sales"},
        {"voucherNumber": "2", "alterid": "2", "amount": 20650.0, "voucherType": "Sales"}
    ]
    
    # First call (delta query): returns empty XML
    # Second call (check query): returns metadata with 2 vouchers
    # Third call (re-extraction query): returns metadata with 2 vouchers
    empty_xml = "<ENVELOPE><BODY><DATA><COLLECTION></COLLECTION></DATA></BODY></ENVELOPE>"
    v_xml = "<ENVELOPE><BODY><DATA><COLLECTION><VOUCHER><VOUCHERNUMBER>1</VOUCHERNUMBER><ALTERID>1</ALTERID></VOUCHER><VOUCHER><VOUCHERNUMBER>2</VOUCHERNUMBER><ALTERID>2</ALTERID></VOUCHER></COLLECTION></DATA></BODY></ENVELOPE>"
    
    mock_worker.tally_client.send_xml_request.side_effect = [
        (True, 200, empty_xml, ""), # delta query -> 0 items
        (True, 200, v_xml, ""),     # check query -> finds max alter 2
        (True, 200, v_xml, "")      # re-extraction -> extracts both vouchers
    ]
    
    with patch("apps.desktop_app.ui.threads.sync_handlers.voucher_syncer.parse_metadata_response") as mock_parse:
        mock_parse.side_effect = [
            [],                   # delta returns []
            mock_tally_vouchers,  # check returns 2 vouchers
            mock_tally_vouchers   # re-extraction returns 2 vouchers
        ]
        
        extracted, max_alter = sync_vouchers(
            mock_worker,
            "Self Healing Co",
            9000,
            "2026-10-29T00:00:00Z",
            None,
            None,
            from_alter_id=210
        )
        
        # Self-healing should have recovered the 2 vouchers and set max_alter = 2
        assert len(extracted) == 2
        assert max_alter == 2

