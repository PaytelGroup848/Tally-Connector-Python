import pytest
from unittest.mock import MagicMock
from apps.backend.adapters.tally.response_parser import (
    parse_metadata_response,
    parse_tally_balance,
    is_asset_ledger,
    compute_signed_balance,
    map_ctrlbooks_balance_type,
)
from shared.cloud.cloud_sync_client import CloudSyncClient


def test_parse_tally_balance_helper():
    # Negative in Tally XML indicates Debit (Dr)
    amt, b_type, is_dp = parse_tally_balance("-55930.00")
    assert amt == 55930.0
    assert b_type == "Dr"
    assert is_dp is True

    # Positive in Tally XML indicates Credit (Cr)
    amt, b_type, is_dp = parse_tally_balance("20000.00")
    assert amt == 20000.0
    assert b_type == "Cr"
    assert is_dp is False

    # String with explicit 'Dr' or 'Cr'
    amt, b_type, is_dp = parse_tally_balance("15,500.50 Dr")
    assert amt == 15500.5
    assert b_type == "Dr"
    assert is_dp is True

    # Zero balance
    amt, b_type, is_dp = parse_tally_balance("0.00")
    assert amt == 0.0
    assert b_type == ""


def test_compute_signed_balance_rule():
    # 1. ASSET & BANK (including Bank OD): Tally Debit (-) -> Positive (+), Tally Credit (+) -> Negative (-)
    assert is_asset_ledger("BANK", "Bank Accounts") is True
    assert is_asset_ledger("BANK", "Bank OD A/c") is True
    assert is_asset_ledger("CASH", "Cash-in-Hand") is True
    assert is_asset_ledger("CUSTOMER", "Sundry Debtors") is True
    assert compute_signed_balance("-55930.00", is_asset=True) == 55930.0
    assert compute_signed_balance("25000.00", is_asset=True) == -25000.0

    # 2. LIABILITY: Tally Debit (-) -> Negative (-), Tally Credit (+) -> Positive (+)
    assert is_asset_ledger("VENDOR", "Sundry Creditors") is False
    assert is_asset_ledger("LIABILITY", "Capital Account") is False
    assert compute_signed_balance("120000.00", is_asset=False) == 120000.0
    assert compute_signed_balance("-20000.00", is_asset=False) == -20000.0


def test_bank_and_cash_ledger_xml_parsing_signed():
    xml = """<ENVELOPE>
    <BODY><DATA><COLLECTION>
    <LEDGER NAME="State Bank of India">
        <PARENT>Bank Accounts</PARENT>
        <OPENINGBALANCE>-10000.00</OPENINGBALANCE>
        <CLOSINGBALANCE>-55930.00</CLOSINGBALANCE>
    </LEDGER>
    <LEDGER NAME="HDFC Overdraft A/c">
        <PARENT>Bank OD A/c</PARENT>
        <OPENINGBALANCE>5000.00</OPENINGBALANCE>
        <CLOSINGBALANCE>25000.00</CLOSINGBALANCE>
    </LEDGER>
    <LEDGER NAME="Cash Account">
        <PARENT>Cash-in-Hand</PARENT>
        <OPENINGBALANCE>-2000.00</OPENINGBALANCE>
        <CLOSINGBALANCE>-12450.00</CLOSINGBALANCE>
    </LEDGER>
    </COLLECTION></DATA></BODY>
    </ENVELOPE>"""

    ledgers = parse_metadata_response(xml, "Ledger")
    assert len(ledgers) == 3

    # 1. State Bank of India (Asset: Tally Dr -55930 -> +55930)
    sbi = ledgers[0]
    assert sbi["name"] == "State Bank of India"
    assert sbi["closingBalance"] == 55930.0
    assert sbi["openingBalance"] == 10000.0
    assert sbi["isDeemedPositive"] is True

    # 2. HDFC Overdraft A/c (Bank OD: Tally Cr +25000 -> -25000)
    hdfc_od = ledgers[1]
    assert hdfc_od["name"] == "HDFC Overdraft A/c"
    assert hdfc_od["closingBalance"] == -25000.0
    assert hdfc_od["openingBalance"] == -5000.0
    assert hdfc_od["isDeemedPositive"] is False

    # 3. Cash in Hand (Asset: Tally Dr -12450 -> +12450)
    cash = ledgers[2]
    assert cash["name"] == "Cash Account"
    assert cash["closingBalance"] == 12450.0
    assert cash["openingBalance"] == 2000.0
    assert cash["isDeemedPositive"] is True


def test_cloud_sync_client_sends_signed_balances():
    mock_auth = MagicMock()
    mock_auth.base_url = "http://mock-api.cloudata.in"
    mock_auth.access_token = "test-token"
    mock_auth.refresh_token_val = "test-refresh"
    mock_auth._device_id = "test-dev-123"

    client = CloudSyncClient(auth_service=mock_auth)

    captured_batches = []
    class MockHttp:
        def post(self, url, json=None, headers=None):
            captured_batches.append(json)
            class MockResp:
                status_code = 200
                text = '{"success": true}'
                def json(self):
                    return {"success": True, "message": "Batch accepted"}
            return MockResp()

    client._get_client = MagicMock(return_value=MockHttp())

    # 1. Sync LEDGER entity
    ledger_items = [
        {
            "name": "State Bank of India",
            "parent": "Bank Accounts",
            "closingBalance": -55930.00,
            "openingBalance": -10000.00
        },
        {
            "name": "HDFC OD Account",
            "parent": "Bank OD A/c",
            "closingBalance": 25000.00,
            "openingBalance": 5000.00
        }
    ]
    ok, msg, _ = client.sync_batch("sync-1", "Test Co", "LEDGER", ledger_items, batch_number=1, is_last_batch=False)
    assert ok is True
    batch1 = captured_batches[0]["records"]
    assert len(batch1) == 2
    # Bank (Asset: -55930 -> +55930)
    assert batch1[0]["name"] == "State Bank of India"
    assert batch1[0]["closingBalance"] == 55930.0
    assert batch1[0]["isDeemedPositive"] is True

    # Bank OD (Tally Cr +25000 -> -25000)
    assert batch1[1]["name"] == "HDFC OD Account"
    assert batch1[1]["closingBalance"] == -25000.0
    assert batch1[1]["isDeemedPositive"] is False

    # 2. Sync CUSTOMER entity (Asset: -75000 -> +75000)
    cust_items = [
        {
            "name": "Reliance Retail Ltd",
            "parent": "Sundry Debtors",
            "closingBalance": -75000.00,
            "openingBalance": -25000.00
        }
    ]
    ok, msg, _ = client.sync_batch("sync-1", "Test Co", "CUSTOMER", cust_items, batch_number=2, is_last_batch=False)
    assert ok is True
    batch2 = captured_batches[1]["records"]
    assert batch2[0]["name"] == "Reliance Retail Ltd"
    assert batch2[0]["closingBalance"] == 75000.0

    # 3. Sync SUPPLIER entity (Liability: +120000 -> +120000)
    supp_items = [
        {
            "name": "Tata Steel Ltd",
            "parent": "Sundry Creditors",
            "closingBalance": 120000.00,
            "openingBalance": 40000.00
        }
    ]
    ok, msg, _ = client.sync_batch("sync-1", "Test Co", "SUPPLIER", supp_items, batch_number=3, is_last_batch=True)
    assert ok is True
    batch3 = captured_batches[2]["records"]
    assert batch3[0]["name"] == "Tata Steel Ltd"
    assert batch3[0]["closingBalance"] == 120000.0
