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


def test_safe_ledger_classification():
    from apps.backend.adapters.tally.xml_builders.common import (
        classify_safe_ledger_parent,
        is_bank_ledger_name,
        is_cash_ledger_name,
        is_expense_ledger_name,
        is_tax_ledger_name,
    )

    # Banks must never be Debtors or Creditors
    assert is_bank_ledger_name("Axis Bank") is True
    assert is_bank_ledger_name("HDFC Bank A/c") is True
    assert is_bank_ledger_name("ICICI Bank Current A/c") is True
    assert is_bank_ledger_name("State Bank of India") is True
    assert classify_safe_ledger_parent("Axis Bank", "Sundry Creditors") == "Bank Accounts"
    assert classify_safe_ledger_parent("Axis Bank", "Sundry Debtors") == "Bank Accounts"
    assert classify_safe_ledger_parent("HDFC Bank", "Sundry Creditors") == "Bank Accounts"

    # Cash must always be Cash-in-hand
    assert is_cash_ledger_name("Petty Cash") is True
    assert is_cash_ledger_name("Office Cash") is True
    assert is_cash_ledger_name("Cash A/c") is True
    assert classify_safe_ledger_parent("Petty Cash", "Bank Accounts") == "Cash-in-hand"
    assert classify_safe_ledger_parent("Cash A/c", "Sundry Creditors") == "Cash-in-hand"

    # Tax must be Duties & Taxes
    assert is_tax_ledger_name("CGST") is True
    assert is_tax_ledger_name("Output SGST") is True
    assert classify_safe_ledger_parent("CGST", "Sundry Debtors") == "Duties & Taxes"

    # Expenses must be Indirect Expenses
    assert is_expense_ledger_name("Office Rent") is True
    assert is_expense_ledger_name("Electricity Expenses") is True
    assert classify_safe_ledger_parent("Office Rent", "Sundry Creditors") == "Indirect Expenses"

    # Normal parties remain intact
    assert classify_safe_ledger_parent("Himanshu Pvt Ltd", "Sundry Debtors") == "Sundry Debtors"
    assert classify_safe_ledger_parent("AVN Traders", "Sundry Creditors") == "Sundry Creditors"


def test_build_ledger_protects_bank_against_sundry_creditors():
    from apps.backend.adapters.tally.xml_builders.ledger_builder import build_ledger_import_xml

    # Malformed payload attempting to put Axis Bank under Sundry Creditors
    malicious_payload = {
        "name": "Axis Bank",
        "parent": "Sundry Creditors",
        "partyType": "SUPPLIER"
    }
    xml = build_ledger_import_xml(malicious_payload)
    assert "<PARENT>Bank Accounts</PARENT>" in xml
    assert "Sundry Creditors" not in xml


@pytest.mark.anyio
async def test_importer_protects_bank_during_receipt_and_payment():
    from unittest.mock import AsyncMock, MagicMock
    from apps.backend.adapters.tally.tally_importer import TallyImporter

    importer = TallyImporter()
    ensured_ledgers = []

    async def mock_send_xml(host, port, xml_content, serialize_company=None):
        if "<LEDGER " in xml_content:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(xml_content)
            for led in root.findall(".//LEDGER"):
                name = led.get("NAME") or ""
                parent_elem = led.find("PARENT")
                parent = parent_elem.text if parent_elem is not None else ""
                ensured_ledgers.append((name, parent))
        return True, 200, "<RESPONSE><CREATED>1</CREATED></RESPONSE>", None

    importer.client = MagicMock()
    importer.client.send_xml_request_async = AsyncMock(side_effect=mock_send_xml)

    # Receipt voucher with Axis Bank and a Vendor (partyType="SUPPLIER")
    receipt_voucher = {
        "voucher_type": "Receipt",
        "company_name": "Test Company",
        "bank_ledger": "Axis Bank",
        "party_ledger": "Vendor XYZ",
        "partyType": "SUPPLIER",
        "amount": 50000.0,
        "date": "2026-10-22",
        "particulars": [
            {"ledgerName": "Axis Bank", "type": "Debit", "amount": 50000.0},
            {"ledgerName": "Vendor XYZ", "type": "Credit", "amount": 50000.0, "partyType": "SUPPLIER"}
        ]
    }

    await importer.import_voucher("127.0.0.1", 9000, receipt_voucher)

    # Verify: Axis Bank was NEVER ensured as Sundry Creditors or Sundry Debtors
    for name, parent in ensured_ledgers:
        if "axis bank" in name.lower():
            assert parent == "Bank Accounts", f"Axis Bank must be Bank Accounts, but got: {parent}"
        if "vendor xyz" in name.lower():
            assert parent == "Sundry Creditors"


def test_update_ledger_bank_payload_generation():
    payload = {
        "companyId": "6accd8b51c686ca6b74fec00",
        "tallyExternalId": "29dc2f05-6a14-467d-8a1f-f819cd82ac4d-000000ef",
        "ledgerId": "6ad869643bb757caa88baab1",
        "ledgerName": "ICICI Bank",
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
    }
    xml = build_ledger_import_xml(payload, action="Alter")
    assert "<LEDGER ACTION=\"Alter\" NAME=\"ICICI Bank\">" in xml
    assert "<PARENT>Bank Accounts</PARENT>" in xml
    assert "<BANKACCHOLDERNAME>Himanshu Pvt Ltd</BANKACCHOLDERNAME>" in xml
    assert "<ACCOUNTHOLDERNAME>Himanshu Pvt Ltd</ACCOUNTHOLDERNAME>" in xml
    assert "<BANKACCOUNTNUMBER>67341044007859</BANKACCOUNTNUMBER>" in xml
    assert "<IFSCODE>BKID0008976</IFSCODE>" in xml
    assert "<BRANCHNAME>sector-21 faridabad</BRANCHNAME>" in xml
    assert "<PAYMENTDETAILS.LIST>" in xml
    assert "<ACCOUNTNUMBER>67341044007859</ACCOUNTNUMBER>" in xml


def test_parse_tally_bank_with_bankaccholdername():
    tally_xml = """<ENVELOPE>
      <BODY>
        <DATA>
          <COLLECTION>
            <LEDGER NAME="ICICI Bank" RESERVEDNAME="">
              <PARENT>Bank Accounts</PARENT>
              <IFSCODE>BKID0008976</IFSCODE>
              <BRANCHNAME>sector-21 faridabad</BRANCHNAME>
              <BANKACCHOLDERNAME>Himanshu Pvt Ltd</BANKACCHOLDERNAME>
              <PAYMENTDETAILS.LIST>
                <BANKNAME>ICICI Bank</BANKNAME>
                <BRANCHNAME>sector-21 faridabad</BRANCHNAME>
                <IFSCODE>BKID0008976</IFSCODE>
                <ACCOUNTNUMBER>67341044007859</ACCOUNTNUMBER>
              </PAYMENTDETAILS.LIST>
            </LEDGER>
          </COLLECTION>
        </DATA>
      </BODY>
    </ENVELOPE>"""
    ledgers = parse_metadata_response(tally_xml, tag_name="Ledger")
    assert len(ledgers) == 1
    bank_led = ledgers[0]
    assert bank_led["name"] == "ICICI Bank"
    assert bank_led["parent"] == "Bank Accounts"
    b = bank_led["bankDetails"]
    assert b["accountHolderName"] == "Himanshu Pvt Ltd"
    assert b["accountNumber"] == "67341044007859"
    assert b["ifscCode"] == "BKID0008976"
    assert b["branchName"] == "sector-21 faridabad"
    assert b["bankName"] == "ICICI Bank"

