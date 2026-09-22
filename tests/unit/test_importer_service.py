"""
Unit tests for 2-Way Sync Importer Service and Tally Importer adapter.
"""

import unittest
from unittest.mock import AsyncMock, patch, MagicMock
import asyncio

from apps.backend.adapters.tally.tally_importer import (
    build_voucher_import_xml,
    build_ledger_import_xml,
    build_unit_import_xml,
    build_stock_item_import_xml,
    parse_tally_import_response,
    format_tally_date,
    TallyImporter,
)
from apps.backend.services.importer_service import ImporterService
from shared.exceptions import ValidationError

class TestImporterServiceUnit(unittest.TestCase):

    def test_01_format_tally_date(self):
        self.assertEqual(format_tally_date("2025-04-01"), "20250401")
        self.assertEqual(format_tally_date("01-04-2025"), "20250401")
        self.assertEqual(format_tally_date("20250401"), "20250401")

    def test_02_build_tally_sales_voucher_xml(self):
        voucher_data = {
            "company_name": "Acme Traders",
            "voucher_type": "Sales",
            "date": "2025-04-01",
            "voucher_number": "INV-101",
            "party_ledger": "ABC Enterprises",
            "amount": 15000.0,
            "narration": "Test Sales Invoice",
        }
        xml_output = build_voucher_import_xml(voucher_data)

        self.assertIn("<TALLYREQUEST>Import Data</TALLYREQUEST>", xml_output)
        self.assertIn('<VOUCHER ACTION="Create" VCHTYPE="Sales">', xml_output)
        self.assertIn("<SVCURRENTCOMPANY>Acme Traders</SVCURRENTCOMPANY>", xml_output)
        self.assertIn("<DATE>20250401</DATE>", xml_output)
        self.assertIn("<VOUCHERNUMBER>INV-101</VOUCHERNUMBER>", xml_output)
        self.assertIn("<PARTYLEDGERNAME>ABC Enterprises</PARTYLEDGERNAME>", xml_output)
        self.assertIn("<LEDGERNAME>ABC Enterprises</LEDGERNAME>", xml_output)
        self.assertIn("<ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>", xml_output)
        self.assertIn("<AMOUNT>-15000.00</AMOUNT>", xml_output)

    def test_03_build_tally_receipt_voucher_xml(self):
        voucher_data = {
            "company_name": "Acme Traders",
            "voucher_type": "Receipt",
            "date": "2025-04-01",
            "voucher_number": "REC-501",
            "party_ledger": "ABC Enterprises",
            "bank_ledger": "HDFC Bank",
            "amount": 5000.0,
            "narration": "Payment received",
        }
        xml_output = build_voucher_import_xml(voucher_data)

        self.assertIn('<VOUCHER ACTION="Create" VCHTYPE="Receipt">', xml_output)
        self.assertIn("<VOUCHERNUMBER>REC-501</VOUCHERNUMBER>", xml_output)
        self.assertIn("<LEDGERNAME>HDFC Bank</LEDGERNAME>", xml_output)
        self.assertIn("<ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>", xml_output)
        self.assertIn("<LEDGERNAME>ABC Enterprises</LEDGERNAME>", xml_output)
        self.assertIn("<ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>", xml_output)

    def test_03b_build_tally_payment_voucher_xml(self):
        voucher_data = {
            "company_name": "Acme Traders",
            "voucher_type": "Payment",
            "date": "2025-04-01",
            "voucher_number": "PAY-101",
            "party_ledger": "XYZ Supplier",
            "bank_ledger": "State Bank of India",
            "amount": 2500.0,
            "bill_number": "BILL-999",
            "narration": "Payment made",
        }
        xml_output = build_voucher_import_xml(voucher_data)

        self.assertIn('<VOUCHER ACTION="Create" VCHTYPE="Payment">', xml_output)
        self.assertIn("<VOUCHERNUMBER>PAY-101</VOUCHERNUMBER>", xml_output)
        self.assertIn("<LEDGERNAME>XYZ Supplier</LEDGERNAME>", xml_output)
        self.assertIn("<ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>", xml_output)
        self.assertIn("<AMOUNT>-2500.00</AMOUNT>", xml_output)
        self.assertIn("<NAME>BILL-999</NAME>", xml_output)
        self.assertIn("<BILLTYPE>Agst Ref</BILLTYPE>", xml_output)
        self.assertIn("<LEDGERNAME>State Bank of India</LEDGERNAME>", xml_output)
        self.assertIn("<ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>", xml_output)
        self.assertIn("<AMOUNT>2500.00</AMOUNT>", xml_output)

    def test_03c_build_tally_sales_order_voucher_xml(self):
        voucher_data = {
            "company_name": "Tarun Enterprise (25-26)",
            "voucher_type": "Sales Order",
            "date": "2026-09-16",
            "voucher_number": "SO-5001",
            "party_ledger": "Cash",
            "items": [
                {
                    "item_name": "O RING 15X2.5",
                    "quantity": 7,
                    "unit": "KGS",
                    "rate": 10.0,
                    "amount": 70.0,
                    "godown": "Main Location",
                }
            ],
            "amount": 70.0,
            "narration": "Test Sales Order",
        }
        xml_output = build_voucher_import_xml(voucher_data)

        self.assertIn('<VOUCHER ACTION="Create" VCHTYPE="Sales Order">', xml_output)
        self.assertIn("<VOUCHERNUMBER>SO-5001</VOUCHERNUMBER>", xml_output)
        self.assertIn("<BATCHALLOCATIONS.LIST>", xml_output)
        self.assertIn("<ORDERNO>SO-5001</ORDERNO>", xml_output)
        self.assertIn("<ORDERDUEDATE>20260916</ORDERDUEDATE>", xml_output)

    def test_04_parse_tally_import_response_success(self):
        success_xml = """<ENVELOPE>
            <HEADER><STATUS>1</STATUS></HEADER>
            <BODY>
                <IMPORTDATA>
                    <RESPONSE>
                        <CREATED>1</CREATED>
                        <LASTVOUCHERID>1005</LASTVOUCHERID>
                    </RESPONSE>
                </IMPORTDATA>
            </BODY>
        </ENVELOPE>"""
        success, v_num, err = parse_tally_import_response(success_xml, default_voucher_number="INV-101")
        self.assertTrue(success)
        self.assertEqual(v_num, "INV-101")
        self.assertIsNone(err)

    def test_05_parse_tally_import_response_line_error(self):
        error_xml = """<ENVELOPE>
            <HEADER><STATUS>0</STATUS></HEADER>
            <BODY>
                <IMPORTDATA>
                    <LINEERROR>Ledger 'ABC Enterprises' does not exist!</LINEERROR>
                </IMPORTDATA>
            </BODY>
        </ENVELOPE>"""
        success, v_num, err = parse_tally_import_response(error_xml)
        self.assertFalse(success)
        self.assertIsNone(v_num)
        self.assertIsNotNone(err)
        assert err is not None
        self.assertIn("Tally XML Line Error", err)
        self.assertIn("Ledger 'ABC Enterprises' does not exist!", err)

    def test_08_importer_service_validation(self):
        service = ImporterService()

        with self.assertRaises(ValidationError):
            service.validate_import_payload({"voucher_type": "Sales", "party_ledger": "ABC", "amount": 100})

        with self.assertRaises(ValidationError):
            service.validate_import_payload({"target": "SAP", "voucher_type": "Sales", "party_ledger": "ABC", "amount": 100})

        with self.assertRaises(ValidationError):
            service.validate_import_payload({"target": "TALLY", "voucher_type": "Sales", "amount": 100})

        valid = service.validate_import_payload({
            "target": "tally",
            "voucher_type": "Sales",
            "party_ledger": "ABC Enterprises",
            "amount": 500,
        })
        self.assertEqual(valid["target"], "TALLY")
        self.assertEqual(valid["party_ledger"], "ABC Enterprises")

    def test_09_importer_service_routing_tally(self):
        mock_tally = MagicMock()
        mock_tally.import_voucher = AsyncMock(return_value={
            "success": True,
            "voucher_number": "INV-555",
            "message": "Success",
            "error": None
        })

        service = ImporterService(tally_importer=mock_tally)
        payload = {
            "target": "TALLY",
            "voucher_type": "Sales",
            "voucher_number": "INV-555",
            "party_ledger": "ABC Traders",
            "amount": 1000.0,
            "host": "127.0.0.1",
            "port": 9000,
        }
        res = asyncio.run(service.import_voucher(payload))
        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["voucher_number"], "INV-555")
        mock_tally.import_voucher.assert_called_once()

    def test_10_build_item_sales_invoice_xml(self):
        voucher_data = {
            "company_name": "Tarun Enterprise (25-26)",
            "voucher_type": "Sales",
            "date": "2025-05-15",
            "voucher_number": "WEB-ITEM-101",
            "party_ledger": "Nikhil Kumar",
            "sales_ledger": "Sales",
            "items": [
                {
                    "itemName": "100W Bulb",
                    "quantity": 5,
                    "rate": 120.0,
                    "units": "Pcs",
                    "discount": "10%",
                    "godown": "Main Location",
                }
            ],
            "narration": "Sales with item entries",
        }
        xml_output = build_voucher_import_xml(voucher_data)

        self.assertIn("<ISINVOICE>Yes</ISINVOICE>", xml_output)
        self.assertIn("<STOCKITEMNAME>100W Bulb</STOCKITEMNAME>", xml_output)
        self.assertIn("<RATE>120.00/Pcs</RATE>", xml_output)
        self.assertIn("<ACTUALQTY>5 Pcs</ACTUALQTY>", xml_output)
        self.assertIn("<DISCOUNT>10%</DISCOUNT>", xml_output)
        self.assertIn("<GODOWNNAME>Main Location</GODOWNNAME>", xml_output)
        self.assertIn("<ACCOUNTINGALLOCATIONS.LIST>", xml_output)
        self.assertIn("<LEDGERNAME>Sales</LEDGERNAME>", xml_output)
        self.assertIn("<AMOUNT>540.00</AMOUNT>", xml_output)
        self.assertIn("<AMOUNT>-540.00</AMOUNT>", xml_output)

    def test_11_parse_tally_response_with_lastvchid(self):
        resp_xml = """<ENVELOPE>
            <HEADER><STATUS>1</STATUS></HEADER>
            <BODY>
                <IMPORTDATA>
                    <RESPONSE>
                        <CREATED>1</CREATED>
                        <LASTVCHID>73952</LASTVCHID>
                        <EXCEPTIONS>0</EXCEPTIONS>
                    </RESPONSE>
                </IMPORTDATA>
            </BODY>
        </ENVELOPE>"""
        success, v_num, err = parse_tally_import_response(resp_xml)
        self.assertTrue(success)
        self.assertEqual(v_num, "VCH-73952")
        self.assertIsNone(err)

    def test_12_build_unit_import_xml(self):
        unit_data = {
            "company_name": "Tarun Enterprise (25-26)",
            "name": "BOX",
            "decimal_places": 0,
        }
        xml_output = build_unit_import_xml(unit_data)
        self.assertIn('<UNIT ACTION="Create" NAME="BOX">', xml_output)
        self.assertIn("<NAME>BOX</NAME>", xml_output)
        self.assertIn("<ISSIMPLEUNIT>Yes</ISSIMPLEUNIT>", xml_output)
        self.assertIn("<DECIMALPLACES>0</DECIMALPLACES>", xml_output)

    def test_13_build_stock_item_import_xml(self):
        item_data = {
            "company_name": "Tarun Enterprise (25-26)",
            "name": "Reynolds Pen",
            "unit": "Pcs",
            "hsn_code": "960810",
        }
        xml_output = build_stock_item_import_xml(item_data)
        self.assertIn('<STOCKITEM ACTION="Create" NAME="Reynolds Pen">', xml_output)
        self.assertIn("<NAME>Reynolds Pen</NAME>", xml_output)
        self.assertIn("<BASEUNITS>Pcs</BASEUNITS>", xml_output)
        self.assertIn("<HSNCODE>960810</HSNCODE>", xml_output)
        self.assertIn("<GSTAPPLICABLE>&#4; Applicable</GSTAPPLICABLE>", xml_output)

    def test_14_build_gst_intra_state_voucher_xml(self):
        voucher_data = {
            "company_name": "Tarun Enterprise (25-26)",
            "voucher_type": "Sales",
            "date": "2026-09-10",
            "party_ledger": "Local Customer",
            "company_state": "Tamil Nadu",
            "party_state": "Tamil Nadu",
            "items": [
                {
                    "itemName": "Electronics Item",
                    "quantity": 2,
                    "rate": 1000.0,
                    "units": "NOS",
                    "gst_rate": 18,
                }
            ],
        }
        xml_output = build_voucher_import_xml(voucher_data)
        self.assertIn("<LEDGERNAME>CGST 9%</LEDGERNAME>", xml_output)
        self.assertIn("<LEDGERNAME>SGST 9%</LEDGERNAME>", xml_output)
        self.assertNotIn("IGST", xml_output)
        self.assertIn("<AMOUNT>180.00</AMOUNT>", xml_output)
        self.assertIn("<AMOUNT>-2360.00</AMOUNT>", xml_output)

    def test_15_build_gst_inter_state_voucher_xml(self):
        voucher_data = {
            "company_name": "Tarun Enterprise (25-26)",
            "voucher_type": "Sales",
            "date": "2026-09-10",
            "party_ledger": "Outstation Customer",
            "company_state": "Tamil Nadu",
            "party_state": "Karnataka",
            "items": [
                {
                    "itemName": "Electronics Item",
                    "quantity": 1,
                    "rate": 1000.0,
                    "units": "NOS",
                    "tax_rate": 18,
                }
            ],
        }
        xml_output = build_voucher_import_xml(voucher_data)
        self.assertIn("<LEDGERNAME>IGST 18%</LEDGERNAME>", xml_output)
        self.assertNotIn("CGST", xml_output)
        self.assertNotIn("SGST", xml_output)
        self.assertIn("<AMOUNT>180.00</AMOUNT>", xml_output)
        self.assertIn("<AMOUNT>-1180.00</AMOUNT>", xml_output)

    def test_16_build_receipt_with_bill_allocations(self):
        voucher_data = {
            "company_name": "Tarun Enterprise (25-26)",
            "voucher_type": "Receipt",
            "date": "2026-09-10",
            "voucher_number": "REC-999",
            "party_ledger": "Nikhil Kumar",
            "bank_ledger": "HDFC Bank",
            "amount": 1500.0,
            "bill_number": "INV-1486",
        }
        xml_output = build_voucher_import_xml(voucher_data)
        self.assertIn('<VOUCHER ACTION="Create" VCHTYPE="Receipt">', xml_output)
        self.assertIn("<BILLALLOCATIONS.LIST>", xml_output)
        self.assertIn("<NAME>INV-1486</NAME>", xml_output)
        self.assertIn("<BILLTYPE>Agst Ref</BILLTYPE>", xml_output)
        self.assertIn("<AMOUNT>1500.00</AMOUNT>", xml_output)

    def test_17_importer_service_create_stock_item_and_unit(self):
        mock_tally = MagicMock()
        mock_tally.ensure_stock_item = AsyncMock(return_value=True)
        mock_tally.ensure_unit = AsyncMock(return_value=True)

        service = ImporterService(tally_importer=mock_tally)
        item_res = asyncio.run(service.create_stock_item({
            "name": "New Notebook",
            "unit": "BOX",
            "hsn_code": "4820",
        }))
        self.assertEqual(item_res["status"], "SUCCESS")
        self.assertEqual(item_res["name"], "New Notebook")
        mock_tally.ensure_stock_item.assert_called_once()

        unit_res = asyncio.run(service.create_unit({
            "name": "BOX",
            "decimal_places": 0,
        }))
        self.assertEqual(unit_res["status"], "SUCCESS")
        self.assertEqual(unit_res["name"], "BOX")
        mock_tally.ensure_unit.assert_called_once()
    def test_18_build_credit_note_item_xml(self):
        voucher_data = {
            "company_name": "Annai Agency - 2022-2023",
            "voucher_type": "Credit Note",
            "date": "2022-10-10",
            "voucher_number": "CN-101",
            "party_ledger": "3SIGMA ASSOCIATES",
            "credit_note_ledger": "Sales Return",
            "items": [
                {
                    "itemName": "100W Bulb",
                    "quantity": 2,
                    "rate": 100.0,
                    "units": "Pcs",
                    "godown": "Main",
                }
            ],
        }
        xml_output = build_voucher_import_xml(voucher_data)
        self.assertIn('<VOUCHER ACTION="Create" VCHTYPE="Credit Note">', xml_output)
        self.assertIn("<STOCKITEMNAME>100W Bulb</STOCKITEMNAME>", xml_output)
        # In Credit Note (Sales return), item is incoming (Debit, Yes, negative)
        self.assertIn("<ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>", xml_output)
        self.assertIn("<AMOUNT>-200.00</AMOUNT>", xml_output)
        # Godown 'Main' dynamically resolved to 'Main Location'
        self.assertIn("<GODOWNNAME>Main Location</GODOWNNAME>", xml_output)
        # Party is Credit (No, positive)
        self.assertIn("<LEDGERNAME>3SIGMA ASSOCIATES</LEDGERNAME>", xml_output)
        self.assertIn("<AMOUNT>200.00</AMOUNT>", xml_output)

    def test_19_build_debit_note_item_xml(self):
        voucher_data = {
            "company_name": "Annai Agency - 2022-2023",
            "voucher_type": "Debit Note",
            "date": "2022-08-15",
            "voucher_number": "DN-201",
            "party_ledger": "ABDUL",
            "debit_note_ledger": "Purchase Return",
            "items": [
                {
                    "itemName": "PVC Wire",
                    "quantity": 1,
                    "rate": 500.0,
                    "units": "Coil",
                    "godown": "Main Location",
                }
            ],
        }
        xml_output = build_voucher_import_xml(voucher_data)
        self.assertIn('<VOUCHER ACTION="Create" VCHTYPE="Debit Note">', xml_output)
        self.assertIn("<STOCKITEMNAME>PVC Wire</STOCKITEMNAME>", xml_output)
        # In Debit Note (Purchase return), item goes out (Credit, No, positive)
        self.assertIn("<ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>", xml_output)
        self.assertIn("<AMOUNT>500.00</AMOUNT>", xml_output)
        # Party (Supplier) is Debited (Yes, negative)
        self.assertIn("<LEDGERNAME>ABDUL</LEDGERNAME>", xml_output)
        self.assertIn("<AMOUNT>-500.00</AMOUNT>", xml_output)

    def test_20_build_journal_accounting_items(self):
        voucher_data = {
            "company_name": "Annai Agency - 2022-2023",
            "voucher_type": "Journal",
            "date": "2022-11-15",
            "voucher_number": "JRN-301",
            "party_ledger": "A G ISPATS",
            "amount": 599.0,
            "items": [
                {"type": "Debit", "partyName": "A G ISPATS", "amount": 599.0},
                {"type": "Credit", "partyName": "Commission", "amount": 599.0},
            ],
        }
        xml_output = build_voucher_import_xml(voucher_data)
        self.assertIn('<VOUCHER ACTION="Create" VCHTYPE="Journal">', xml_output)
        self.assertNotIn("<ISINVOICE>Yes</ISINVOICE>", xml_output)
        self.assertIn("<LEDGERNAME>A G ISPATS</LEDGERNAME>", xml_output)
        self.assertIn("<AMOUNT>-599.00</AMOUNT>", xml_output)
        self.assertIn("<LEDGERNAME>Commission</LEDGERNAME>", xml_output)
        self.assertIn("<AMOUNT>599.00</AMOUNT>", xml_output)

    def test_21_build_contra_cash_and_bank(self):
        voucher_data = {
            "company_name": "Annai Agency - 2022-2023",
            "voucher_type": "Contra",
            "date": "2022-07-20",
            "voucher_number": "CNT-401",
            "to_account": "HDFC BANK-7713",
            "from_account": "Cash",
            "amount": 2500.0,
        }
        xml_output = build_voucher_import_xml(voucher_data)
        self.assertIn('<VOUCHER ACTION="Create" VCHTYPE="Contra">', xml_output)
        self.assertIn("<LEDGERNAME>HDFC BANK-7713</LEDGERNAME>", xml_output)
        self.assertIn("<ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>", xml_output)
        self.assertIn("<AMOUNT>-2500.00</AMOUNT>", xml_output)
        self.assertIn("<LEDGERNAME>Cash</LEDGERNAME>", xml_output)
        self.assertIn("<ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>", xml_output)
        self.assertIn("<AMOUNT>2500.00</AMOUNT>", xml_output)

    def test_22_build_purchase_invoice_xml(self):
        voucher_data = {
            "company_name": "Annai Agency - 2022-2023",
            "voucher_type": "Purchase",
            "date": "2022-06-15",
            "voucher_number": "PUR-501",
            "party_ledger": "ABDUL",
            "purchase_ledger": "Purchase",
            "items": [
                {
                    "itemName": "Steel Pipe",
                    "quantity": 10,
                    "rate": 80.0,
                    "units": "Pcs",
                    "godown": "Main",
                }
            ],
        }
        xml_output = build_voucher_import_xml(voucher_data)
        self.assertIn('<VOUCHER ACTION="Create" VCHTYPE="Purchase">', xml_output)
        self.assertIn("<STOCKITEMNAME>Steel Pipe</STOCKITEMNAME>", xml_output)
        # In Purchase, item is incoming (Debit, Yes, negative)
        self.assertIn("<AMOUNT>-800.00</AMOUNT>", xml_output)
        self.assertIn("<GODOWNNAME>Main Location</GODOWNNAME>", xml_output)
        # Supplier is Credited (No, positive)
        self.assertIn("<LEDGERNAME>ABDUL</LEDGERNAME>", xml_output)
        self.assertIn("<AMOUNT>800.00</AMOUNT>", xml_output)

    def test_23_penny_balancing_round_off(self):
        """Verify that floating point penny discrepancy triggers automatic Round Off balancing."""
        from apps.backend.adapters.tally.tally_importer import _balance_double_entry_accounting
        ledger_entries = [
            """<ALLLEDGERENTRIES.LIST><LEDGERNAME>Customer</LEDGERNAME><ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE><AMOUNT>-100.02</AMOUNT></ALLLEDGERENTRIES.LIST>""",
            """<ALLLEDGERENTRIES.LIST><LEDGERNAME>Sales</LEDGERNAME><ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE><AMOUNT>100.00</AMOUNT></ALLLEDGERENTRIES.LIST>""",
        ]
        v_data = {"voucher_number": "TEST-RO-1"}
        _balance_double_entry_accounting(ledger_entries, [], False, v_data)
        self.assertTrue(v_data.get("_has_round_off"))
        combined = "\n".join(ledger_entries)
        self.assertIn("<LEDGERNAME>Round Off</LEDGERNAME>", combined)
        self.assertIn("<AMOUNT>0.02</AMOUNT>", combined)

    def test_24_tally_client_company_lock_and_async(self):
        """Verify TallyClient per-company lock and non-blocking async execution."""
        from apps.backend.adapters.tally.tally_client import TallyClient
        client = TallyClient()
        lock1 = client.get_lock("127.0.0.1", 9000, "Company A")
        lock2 = client.get_lock("127.0.0.1", 9000, "Company A")
        lock3 = client.get_lock("127.0.0.1", 9000, "Company B")
        self.assertIs(lock1, lock2)
        self.assertIsNot(lock1, lock3)

    def test_25_importer_service_idempotency(self):
        """Verify that re-importing the same voucher number returns cached result immediately."""
        service = ImporterService()
        cached_response = {
            "status": "SUCCESS",
            "target": "TALLY",
            "voucher_type": "Sales",
            "voucher_number": "INV-DUP-101",
            "amount": 500.0,
            "company_name": "Test Co",
            "message": "Voucher 'INV-DUP-101' successfully created in Tally Prime.",
        }
        service._idempotency_cache["test co:sales:inv-dup-101"] = cached_response
        
        loop = asyncio.new_event_loop()
        try:
            res = loop.run_until_complete(service.import_voucher({
                "target": "TALLY",
                "company_name": "Test Co",
                "voucher_type": "Sales",
                "voucher_number": "INV-DUP-101",
                "party_ledger": "Customer A",
                "amount": 500.0
            }))
            self.assertEqual(res["status"], "SUCCESS")
            self.assertEqual(res["voucher_number"], "INV-DUP-101")
        finally:
            loop.close()

    def test_26_master_caching_skips_redundant_http(self):
        """Verify TallyImporter caches known masters and skips redundant HTTP calls."""
        importer = TallyImporter()
        importer._known_ledgers["my company"] = {"customer x"}
        loop = asyncio.new_event_loop()
        try:
            ok = loop.run_until_complete(importer.ensure_ledger(
                host="127.0.0.1",
                port=9000,
                company_name="My Company",
                ledger_name="Customer X"
            ))
            self.assertTrue(ok)
        finally:
            loop.close()

if __name__ == "__main__":
    unittest.main()
