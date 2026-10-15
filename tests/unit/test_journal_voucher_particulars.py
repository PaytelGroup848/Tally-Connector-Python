import unittest
from apps.backend.adapters.tally.xml_builders.voucher_builder import (
    build_voucher_import_xml,
    _extract_party_ledger
)


class TestJournalVoucherParticulars(unittest.TestCase):

    def test_journal_voucher_with_particulars_xml_generation(self):
        payload = {
            "voucherType": "Journal",
            "voucherNo": "JRN-101",
            "date": "2026-10-13",
            "particulars": [
                {
                    "type": "Debit",
                    "partyName": "Tarun Chaprana",
                    "amount": 1000
                },
                {
                    "type": "Credit",
                    "partyName": "Cash",
                    "amount": 1000
                }
            ],
            "narration": "Journal voucher test payment"
        }

        # 1. Party ledger should extract Tarun Chaprana, not Cash
        extracted_party = _extract_party_ledger(payload)
        self.assertEqual(extracted_party, "Tarun Chaprana")

        # 2. Build XML
        xml_output = build_voucher_import_xml(payload)

        # 3. Verify XML structure
        self.assertIn("<VOUCHERTYPENAME>Journal</VOUCHERTYPENAME>", xml_output)
        self.assertIn("<VOUCHERNUMBER>JRN-101</VOUCHERNUMBER>", xml_output)
        self.assertIn("<NARRATION>Journal voucher test payment</NARRATION>", xml_output)

        # 4. Verify Ledger Entries for double entry
        self.assertIn("<LEDGERNAME>Tarun Chaprana</LEDGERNAME>", xml_output)
        self.assertIn("<ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>", xml_output)
        self.assertIn("<AMOUNT>-1000.00</AMOUNT>", xml_output)

        self.assertIn("<LEDGERNAME>Cash</LEDGERNAME>", xml_output)
        self.assertIn("<ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>", xml_output)
        self.assertIn("<AMOUNT>1000.00</AMOUNT>", xml_output)

        # 5. Verify payload amount got updated from particulars
        self.assertEqual(payload.get("amount"), 1000.0)

    def test_journal_voucher_with_ledger_entries_format(self):
        payload = {
            "voucher_type": "Journal",
            "voucher_number": "JRN-202",
            "date": "2026-10-13",
            "ledger_entries": [
                {
                    "type": "Dr",
                    "ledger_name": "Office Expense",
                    "amount": 500
                },
                {
                    "type": "Cr",
                    "ledger_name": "Bank Account",
                    "amount": 500
                }
            ]
        }

        xml_output = build_voucher_import_xml(payload)

        self.assertIn("<VOUCHERTYPENAME>Journal</VOUCHERTYPENAME>", xml_output)
        self.assertIn("<VOUCHERNUMBER>JRN-202</VOUCHERNUMBER>", xml_output)
        self.assertIn("<LEDGERNAME>Office Expense</LEDGERNAME>", xml_output)
        self.assertIn("<AMOUNT>-500.00</AMOUNT>", xml_output)
        self.assertIn("<LEDGERNAME>Bank Account</LEDGERNAME>", xml_output)
        self.assertIn("<AMOUNT>500.00</AMOUNT>", xml_output)
        self.assertEqual(payload.get("amount"), 500.0)

    def test_contra_voucher_with_items_format_from_portal(self):
        # Exact structure sent by ctrlbooks.com for Contra vouchers
        payload = {
            "voucher_type": "Contra",
            "voucher_number": "CTR-001",
            "date": "2026-10-14",
            "items": [
                {
                    "type": "Debit",
                    "partyName": "20 Microns Limited",
                    "amount": 11.0
                },
                {
                    "type": "Credit",
                    "partyName": "A K ENTERPRISES",
                    "amount": 11.0
                }
            ],
            "narration": "Contra transfer test"
        }

        # Party should extract 20 Microns Limited, not Cash
        extracted_party = _extract_party_ledger(payload)
        self.assertEqual(extracted_party, "20 Microns Limited")

        xml_output = build_voucher_import_xml(payload)

        # Voucher type and number
        self.assertIn("<VOUCHERTYPENAME>Contra</VOUCHERTYPENAME>", xml_output)
        self.assertIn("<VOUCHERNUMBER>CTR-001</VOUCHERNUMBER>", xml_output)

        # Double entry entries
        self.assertIn("<LEDGERNAME>20 Microns Limited</LEDGERNAME>", xml_output)
        self.assertIn("<ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>", xml_output)
        self.assertIn("<AMOUNT>-11.00</AMOUNT>", xml_output)

        self.assertIn("<LEDGERNAME>A K ENTERPRISES</LEDGERNAME>", xml_output)
        self.assertIn("<ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>", xml_output)
        self.assertIn("<AMOUNT>11.00</AMOUNT>", xml_output)

        # Amount must be single-leg sum (11.0), not doubled (22.0)
        self.assertEqual(payload.get("amount"), 11.0)
        # Ensure no inventory entries were created
        self.assertNotIn("<ALLINVENTORYENTRIES.LIST>", xml_output)

    def test_contra_voucher_with_to_and_from_account(self):
        payload = {
            "voucher_type": "Contra",
            "voucher_number": "CTR-002",
            "date": "2026-10-14",
            "amount": 2500.0,
            "to_account": "HDFC Bank",
            "from_account": "Cash"
        }

        xml_output = build_voucher_import_xml(payload)
        self.assertIn("<VOUCHERTYPENAME>Contra</VOUCHERTYPENAME>", xml_output)
        self.assertIn("<LEDGERNAME>HDFC Bank</LEDGERNAME>", xml_output)
        self.assertIn("<AMOUNT>-2500.00</AMOUNT>", xml_output)
        self.assertIn("<LEDGERNAME>Cash</LEDGERNAME>", xml_output)
        self.assertIn("<AMOUNT>2500.00</AMOUNT>", xml_output)


if __name__ == "__main__":
    unittest.main()


