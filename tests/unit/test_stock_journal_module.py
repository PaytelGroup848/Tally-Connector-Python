import unittest
from unittest.mock import AsyncMock, MagicMock
from apps.backend.adapters.tally.xml_builders.voucher_builder import build_voucher_import_xml
from apps.backend.adapters.tally.tally_importer import diagnose_voucher_rejection
from apps.backend.services.importer_service import ImporterService
from apps.desktop_app.ui.threads.command_handlers.voucher_command_handler import execute_voucher_command


class TestStockJournalModule(unittest.TestCase):

    def test_stock_journal_xml_generation_with_camel_case(self):
        payload = {
            "voucherType": "Stock Journal",
            "voucherNumber": "SJ-001",
            "companyName": "Test Company",
            "date": "2026-10-14",
            "narration": "Transfer from Raw to Finished godown",
            "sourceItems": [
                {
                    "itemName": "Raw Material A",
                    "quantity": 5,
                    "rate": 100,
                    "units": "Pcs",
                    "sourceGodown": "Raw Godown",
                }
            ],
            "destinationItems": [
                {
                    "itemName": "Finished Good B",
                    "quantity": 2,
                    "rate": 250,
                    "units": "Pcs",
                    "destinationGodown": "Finished Godown",
                }
            ],
        }

        xml = build_voucher_import_xml(payload)

        self.assertIn("<VOUCHERTYPENAME>Stock Journal</VOUCHERTYPENAME>", xml)
        self.assertIn("<VOUCHERNUMBER>SJ-001</VOUCHERNUMBER>", xml)
        self.assertIn("<INVENTORYENTRIESOUT.LIST>", xml)
        self.assertIn("<STOCKITEMNAME>Raw Material A</STOCKITEMNAME>", xml)
        self.assertIn("<GODOWNNAME>Raw Godown</GODOWNNAME>", xml)
        self.assertIn("<INVENTORYENTRIESIN.LIST>", xml)
        self.assertIn("<STOCKITEMNAME>Finished Good B</STOCKITEMNAME>", xml)
        self.assertIn("<GODOWNNAME>Finished Godown</GODOWNNAME>", xml)
        self.assertIn("<ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>", xml)
        self.assertIn("<ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>", xml)

    def test_stock_journal_diagnose_rejection_no_false_zero_value(self):
        payload = {
            "voucherType": "Stock Journal",
            "voucherNumber": "SJ-002",
            "date": "2026-10-14",
            "amount": 0.0,
            "sourceItems": [
                {
                    "itemName": "laptop",
                    "quantity": 2,
                    "rate": 500,
                }
            ],
            "destinationItems": [
                {
                    "itemName": "laptop refurbished",
                    "quantity": 2,
                    "rate": 500,
                }
            ],
        }

        diag = diagnose_voucher_rejection(payload, tally_response_text="<RESPONSE><STATUS>0</STATUS></RESPONSE>")
        # Must NOT report "Zero-Value Invoice" or "Missing Customer"
        self.assertNotIn("Zero-Value Invoice", diag["reason"])
        self.assertNotIn("Missing Customer", diag["reason"])
        self.assertEqual(diag["party"], "Inventory / Stock")

    def test_importer_service_stock_journal_validation(self):
        service = ImporterService(tally_importer=MagicMock())
        payload = {
            "target": "tally",
            "voucherType": "Stock Journal",
            "voucherNumber": "SJ-003",
            "date": "2026-10-14",
            "sourceItems": [
                {"itemName": "item1", "quantity": 10, "rate": 50}
            ],
            "destinationItems": [
                {"itemName": "item2", "quantity": 5, "rate": 100}
            ],
        }

        validated = service.validate_import_payload(payload)
        self.assertEqual(validated["voucher_type"], "Stock Journal")
        self.assertEqual(validated["party_ledger"], "Inventory / Stock")
        self.assertEqual(validated["amount"], 500.0)  # max(500, 500)

    def test_voucher_command_handler_create_stock_journal(self):
        payload = {
            "sourceItems": [
                {"itemName": "item1", "quantity": 2, "rate": 100}
            ],
            "destinationItems": [
                {"itemName": "item2", "quantity": 2, "rate": 100}
            ]
        }
        cmd = {"id": "test-cmd-sj-1"}

        mock_worker = MagicMock()
        mock_worker.importer_service.import_voucher = AsyncMock(return_value={"status": "SUCCESS", "voucher_number": "SJ-001"})

        norm_payload, success, result_data, error_msg, error_details, should_continue = execute_voucher_command(
            worker=mock_worker,
            payload=payload,
            cmd=cmd,
            cmd_id="test-cmd-sj-1",
            cmd_type="CREATE_STOCK_JOURNAL",
            comp_id="comp-1",
            resolved_company="Test Company",
            active_host="localhost",
            active_port=9000,
            amt=0.0,
            curr_email=None,
            curr_org=None,
        )

        self.assertEqual(norm_payload["voucher_type"], "Stock Journal")
        self.assertEqual(norm_payload["party_ledger"], "Inventory / Stock")
        self.assertEqual(norm_payload["amount"], 200.0)
        self.assertTrue(len(norm_payload["items"]) > 0)
        self.assertTrue(success)

    def test_stock_journal_with_ctrlbooks_web_dict_payload(self):
        # Exact payload structure sent by ctrlbooks.com web form
        payload = {
            "voucherType": "Stock Journal",
            "voucherNumber": "1234564",
            "date": "2026-10-14",
            "narration": "Stock transfer test",
            "companyName": "Himanshu Pvt Ltd",
            "items": {
                "source": [
                    {
                        "item": "laptop",
                        "qty": 2,
                        "rate": 260,
                        "godown": "Main Location",
                        "amount": 520,
                    }
                ],
                "destination": [
                    {
                        "item": "laptop",
                        "qty": 2,
                        "rate": 260,
                        "godown": "Finished Goods",
                        "amount": 520,
                    }
                ],
            },
        }

        # 1. XML generation test
        xml = build_voucher_import_xml(payload)
        self.assertIn("<VOUCHERTYPENAME>Stock Journal</VOUCHERTYPENAME>", xml)
        self.assertIn("<VOUCHERNUMBER>1234564</VOUCHERNUMBER>", xml)
        self.assertIn("<INVENTORYENTRIESOUT.LIST>", xml)
        self.assertIn("<STOCKITEMNAME>laptop</STOCKITEMNAME>", xml)
        self.assertIn("<GODOWNNAME>Main Location</GODOWNNAME>", xml)
        self.assertIn("<INVENTORYENTRIESIN.LIST>", xml)
        self.assertIn("<GODOWNNAME>Finished Goods</GODOWNNAME>", xml)

        # 2. Rejection diagnosis test
        diag = diagnose_voucher_rejection(payload, tally_response_text="<RESPONSE><STATUS>0</STATUS></RESPONSE>")
        self.assertNotIn("Zero-Value Invoice", diag["reason"])
        self.assertNotIn("Missing Customer", diag["reason"])

        # 3. Voucher command handler execution test
        mock_worker = MagicMock()
        mock_worker.importer_service.import_voucher = AsyncMock(return_value={"status": "SUCCESS", "voucher_number": "1234564"})

        norm_payload, success, result_data, error_msg, error_details, should_continue = execute_voucher_command(
            worker=mock_worker,
            payload=payload,
            cmd={"id": "test-cmd-sj-web"},
            cmd_id="test-cmd-sj-web",
            cmd_type="CREATE_VOUCHER",
            comp_id="comp-1",
            resolved_company="Himanshu Pvt Ltd",
            active_host="localhost",
            active_port=9047,
            amt=0.0,
            curr_email=None,
            curr_org=None,
        )

        self.assertEqual(norm_payload["voucher_type"], "Stock Journal")
        self.assertEqual(norm_payload["party_ledger"], "Inventory / Stock")
        self.assertEqual(norm_payload["amount"], 520.0)
        self.assertTrue(success)


if __name__ == "__main__":
    unittest.main()

