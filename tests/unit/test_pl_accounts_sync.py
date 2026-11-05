import pytest
from unittest.mock import MagicMock, patch
from apps.desktop_app.ui.threads.sync_handlers.pl_syncer import sync_pl_accounts
from shared.cloud.cloud_sync_client import CloudSyncClient

def test_sync_pl_accounts_extraction():
    mock_tally_client = MagicMock()
    
    # Mock response for collection
    collection_xml_response = """<ENVELOPE>
        <BODY>
            <DATA>
                <COLLECTION>
                    <LEDGER>
                        <NAME>Purchase GST</NAME>
                        <PARENT>Purchase Accounts</PARENT>
                        <CLOSINGBALANCE>-6289307.73</CLOSINGBALANCE>
                    </LEDGER>
                    <LEDGER>
                        <NAME>Purchase</NAME>
                        <PARENT>Purchase Accounts</PARENT>
                        <CLOSINGBALANCE>2444.00</CLOSINGBALANCE>
                    </LEDGER>
                    <LEDGER>
                        <NAME>Sales GST</NAME>
                        <PARENT>Sales Accounts</PARENT>
                        <CLOSINGBALANCE>6186977.38</CLOSINGBALANCE>
                    </LEDGER>
                    <LEDGER>
                        <NAME>Sales</NAME>
                        <PARENT>Sales Accounts</PARENT>
                        <CLOSINGBALANCE>161711.63</CLOSINGBALANCE>
                    </LEDGER>
                </COLLECTION>
            </DATA>
        </BODY>
    </ENVELOPE>"""

    # Mock response for report
    report_xml_response = """<ENVELOPE>
        <DSPACCNAME><DSPDISPNAME>Opening Stock</DSPDISPNAME></DSPACCNAME>
        <PLAMT><PLSUBAMT>-191066.77</PLSUBAMT></PLAMT>
        <DSPACCNAME><DSPDISPNAME>Less: Closing Stock</DSPDISPNAME></DSPACCNAME>
        <PLAMT><PLSUBAMT>-974522.29</PLSUBAMT></PLAMT>
    </ENVELOPE>"""

    mock_tally_client.send_xml_request.side_effect = [
        (True, 200, collection_xml_response, None),
        (True, 200, report_xml_response, None),
    ]

    records = sync_pl_accounts(
        mock_tally_client,
        "127.0.0.1",
        9000,
        "Tarun Enterprise (25-26)",
        from_date="2026-04-01",
        to_date="2026-10-03"
    )

    assert len(records) == 3
    
    # Check Purchase Accounts
    p_rec = next(r for r in records if r["category"] == "PURCHASE_ACCOUNTS")
    assert p_rec["groupName"] == "Purchase Accounts"
    assert p_rec["side"] == "DEBIT"
    assert p_rec["startDate"] == "2026-04-01"
    assert p_rec["endDate"] == "2026-10-03"
    assert p_rec["totalAmount"] == 6286863.73  # 6289307.73 - 2444.00
    assert len(p_rec["ledgers"]) == 2
    assert p_rec["ledgers"][0]["ledgerName"] == "Purchase GST"
    assert p_rec["ledgers"][0]["amount"] == 6289307.73
    assert p_rec["ledgers"][1]["ledgerName"] == "Purchase"
    assert p_rec["ledgers"][1]["amount"] == -2444.00

    # Check Sales Accounts
    s_rec = next(r for r in records if r["category"] == "SALES_ACCOUNTS")
    assert s_rec["groupName"] == "Sales Accounts"
    assert s_rec["side"] == "CREDIT"
    assert s_rec["startDate"] == "2026-04-01"
    assert s_rec["endDate"] == "2026-10-03"
    assert s_rec["totalAmount"] == 6348689.01  # 6186977.38 + 161711.63
    assert len(s_rec["ledgers"]) == 2

    # Check PL Summary
    sum_rec = next(r for r in records if r["category"] == "PL_SUMMARY")
    assert sum_rec["openingStock"] == 191066.77
    assert sum_rec["closingStock"] == 974522.29


def test_voucher_batch_with_pl_data_payload():
    mock_auth = MagicMock()
    mock_auth.base_url = "https://connector.cloudata.in/api/connector"
    mock_auth.access_token = "valid_token_xyz"
    mock_auth.refresh_token_val = "refresh_val"
    mock_auth._extract_error_message.return_value = "error"

    mock_client = MagicMock()
    mock_post_res = MagicMock()
    mock_post_res.status_code = 200
    mock_post_res.text = '{"success": true, "data": {"upserted": 1, "failed": 0}}'
    mock_post_res.json.return_value = {"success": True, "data": {"upserted": 1, "failed": 0}}
    mock_client.post.return_value = mock_post_res
    mock_auth._get_client.return_value = mock_client

    sync_client = CloudSyncClient(mock_auth)

    voucher_items = [
        {
            "voucherId": "v101",
            "voucherNumber": "1",
            "voucherType": "Sales",
            "date": "2026-04-10",
            "amount": 5000.0,
            "partyLedger": "Test Party",
            "raw": {
                "voucherId": "v101",
                "voucherNumber": "1",
                "voucherType": "Sales",
                "amount": 5000.0
            }
        }
    ]

    pl_data = {
        "purchaseAccounts": {
            "groupName": "Purchase Accounts",
            "totalAmount": 6344357.58,
            "ledgers": [{"ledgerName": "Purchase GST", "amount": 6289307.73}]
        },
        "salesAccounts": {
            "groupName": "Sales Accounts",
            "totalAmount": 6422473.35,
            "ledgers": [{"ledgerName": "Sales GST", "amount": 6186977.38}]
        },
        "plSummary": {
            "openingStock": 191066.77,
            "closingStock": 974522.29,
            "grossProfit": 860941.29,
            "nettProfit": 891673.81
        },
        "plAccounts": [
            {"category": "PURCHASE_ACCOUNTS", "totalAmount": 6344357.58},
            {"category": "SALES_ACCOUNTS", "totalAmount": 6422473.35}
        ]
    }

    ok, msg, data = sync_client.sync_batch(
        sync_id="job-v-12345",
        company_name="Tarun Enterprise (25-26)",
        entity_type="VOUCHER",
        items=voucher_items,
        batch_number=1,
        is_last_batch=True,
        company_id="6ae5d28e170b689d53e13f31",
        sync_type="INITIAL",
        is_full_replace=True,
        start_date="2026-04-01",
        end_date="2026-10-03",
        pl_data=pl_data
    )

    assert ok is True
    call_args = mock_client.post.call_args
    target_url = call_args[0][0]
    sent_body = call_args[1]["json"]

    # Verify standard entityType is VOUCHER (accepted by server validator)
    assert sent_body["entityType"] == "VOUCHER"
    assert sent_body["syncJobId"] == "job-v-12345"
    assert sent_body["companyId"] == "6ae5d28e170b689d53e13f31"
    assert sent_body["isLastBatch"] is True

    # Verify PL data attached to top-level payload
    assert "purchaseAccounts" in sent_body
    assert sent_body["purchaseAccounts"]["totalAmount"] == 6344357.58
    assert "salesAccounts" in sent_body
    assert sent_body["salesAccounts"]["totalAmount"] == 6422473.35
    assert "plSummary" in sent_body
    assert sent_body["plSummary"]["grossProfit"] == 860941.29
    assert "plAccounts" in sent_body
    assert len(sent_body["plAccounts"]) == 2

    # Verify PL data also injected into record and record.raw (for MongoDB persistence)
    rec = sent_body["records"][0]
    assert rec["purchaseAccounts"]["totalAmount"] == 6344357.58
    assert rec["salesAccounts"]["totalAmount"] == 6422473.35
    assert rec["raw"]["purchaseAccounts"]["totalAmount"] == 6344357.58
    assert rec["raw"]["salesAccounts"]["totalAmount"] == 6422473.35
    assert rec["raw"]["plSummary"]["grossProfit"] == 860941.29
