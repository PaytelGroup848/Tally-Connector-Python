import pytest
from apps.backend.adapters.tally.xml_builders.ledger_builder import build_ledger_import_xml
from apps.backend.adapters.tally.response_parser import parse_metadata_response

def test_build_ledger_with_bank_details():
    payload = {
        "companyId": "6accd8b51c686ca6b74fec00",
        "company_name": "Apna Ganesh Pvt Ltd",
        "ledgerName": "ICICI Bank",
        "parent": "Bank Accounts",
        "ledgerType": "BANK",
        "openingBalance": 0,
        "bankDetails": {
            "accountHolderName": "Himanshu Pvt Ltd",
            "accountNumber": "67341044007859",
            "ifscCode": "BKID0008976",
            "swiftCode": "ICICINBB",
            "branchName": "sector-21 faridabad",
            "bankName": "ICICI Bank"
        }
    }
    xml = build_ledger_import_xml(payload, action="Create")
    assert "<LEDGER ACTION=\"Create\" NAME=\"ICICI Bank\">" in xml
    assert "<PARENT>Bank Accounts</PARENT>" in xml
    assert "<BANKACCOUNTNUMBER>67341044007859</BANKACCOUNTNUMBER>" in xml
    assert "<IFSCODE>BKID0008976</IFSCODE>" in xml
    assert "<BANKNAME>ICICI Bank</BANKNAME>" in xml
    assert "<BRANCHNAME>sector-21 faridabad</BRANCHNAME>" in xml
    assert "<ACCOUNTHOLDERNAME>Himanshu Pvt Ltd</ACCOUNTHOLDERNAME>" in xml
    assert "<ACCOUNTNUMBER>67341044007859</ACCOUNTNUMBER>" in xml

def test_parse_tally_bank_ledger_response():
    tally_xml = """<ENVELOPE>
      <BODY>
        <DATA>
          <COLLECTION>
            <LEDGER NAME="HDFC Bank" RESERVEDNAME="">
              <PARENT>Bank Accounts</PARENT>
              <IFSCODE>HDFC0001234</IFSCODE>
              <BANKDETAILS>50200012345678</BANKDETAILS>
              <CLOSINGBALANCE>150000.00</CLOSINGBALANCE>
            </LEDGER>
          </COLLECTION>
        </DATA>
      </BODY>
    </ENVELOPE>"""
    ledgers = parse_metadata_response(tally_xml, tag_name="Ledger")
    assert len(ledgers) == 1
    bank_led = ledgers[0]
    assert bank_led["name"] == "HDFC Bank"
    assert bank_led["parent"] == "Bank Accounts"
    assert "bankDetails" in bank_led
    b = bank_led["bankDetails"]
    assert b["accountNumber"] == "50200012345678"
    assert b["ifscCode"] == "HDFC0001234"
    assert b["bankName"] == "HDFC Bank"

def test_cloud_sync_client_batch_with_bank_details(monkeypatch):
    from unittest.mock import MagicMock
    from shared.cloud.cloud_sync_client import CloudSyncClient
    
    mock_auth = MagicMock()
    mock_auth.base_url = "http://localhost:8000"
    mock_auth.access_token = "mock-token"
    mock_auth.refresh_token_val = "mock-refresh"

    captured_payload = {}
    class MockClient:
        def post(self, url, json=None, headers=None):
            nonlocal captured_payload
            captured_payload = json
            class MockResp:
                status_code = 200
                text = '{"success": true}'
                def json(self):
                    return {"success": True}
            return MockResp()

    mock_auth._get_client.return_value = MockClient()
    client = CloudSyncClient(mock_auth)

    items = [{
        "name": "ICICI Bank",
        "parent": "Bank Accounts",
        "ledgerType": "BANK",
        "bankDetails": {
            "accountHolderName": "Himanshu Pvt Ltd",
            "accountNumber": "67341044007859",
            "ifscCode": "BKID0008976",
            "swiftCode": "",
            "branchName": "sector-21 faridabad",
            "bankName": "ICICI Bank"
        }
    }]
    ok, msg, data = client.sync_batch("sync-123", "Test Co", "LEDGER", items)
    assert ok is True
    records = captured_payload.get("records", [])
    assert len(records) == 1
    assert "bankDetails" in records[0]
    assert records[0]["bankDetails"]["accountNumber"] == "67341044007859"
    assert records[0]["bankDetails"]["ifscCode"] == "BKID0008976"
    assert records[0]["bankDetails"]["bankName"] == "ICICI Bank"
