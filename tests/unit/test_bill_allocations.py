import unittest
from apps.backend.adapters.tally.response_parser import parse_metadata_response

class TestBillAllocationsParsing(unittest.TestCase):
    def test_sales_voucher_bill_allocation(self):
        sample_xml = """<ENVELOPE>
            <BODY>
                <DATA>
                    <COLLECTION>
                        <VOUCHER>
                            <DATE>20260412</DATE>
                            <VOUCHERTYPENAME>Sales</VOUCHERTYPENAME>
                            <VOUCHERNUMBER>INV-101</VOUCHERNUMBER>
                            <GUID>voucher-guid-101</GUID>
                            <PARTYLEDGERNAME>Customer A</PARTYLEDGERNAME>
                            <AMOUNT>-11800.00</AMOUNT>
                            <ALLLEDGERENTRIES.LIST>
                                <LEDGERNAME>Customer A</LEDGERNAME>
                                <AMOUNT>-11800.00</AMOUNT>
                                <BILLALLOCATIONS.LIST>
                                    <NAME>INV-101</NAME>
                                    <BILLTYPE>New Ref</BILLTYPE>
                                    <AMOUNT>-11800.00</AMOUNT>
                                    <BILLCREDITPERIOD>30 Days</BILLCREDITPERIOD>
                                </BILLALLOCATIONS.LIST>
                            </ALLLEDGERENTRIES.LIST>
                            <ALLLEDGERENTRIES.LIST>
                                <LEDGERNAME>Sales Account</LEDGERNAME>
                                <AMOUNT>10000.00</AMOUNT>
                            </ALLLEDGERENTRIES.LIST>
                            <ALLLEDGERENTRIES.LIST>
                                <LEDGERNAME>Output GST</LEDGERNAME>
                                <AMOUNT>1800.00</AMOUNT>
                            </ALLLEDGERENTRIES.LIST>
                        </VOUCHER>
                    </COLLECTION>
                </DATA>
            </BODY>
        </ENVELOPE>"""
        vouchers = parse_metadata_response(sample_xml, "Voucher")
        self.assertEqual(len(vouchers), 1)
        v = vouchers[0]
        self.assertEqual(v["voucherNumber"], "INV-101")
        self.assertEqual(v["voucherType"], "Sales")
        self.assertEqual(v["partyLedger"], "Customer A")
        self.assertEqual(v["amount"], 11800.0)

        bills = v.get("billAllocations", [])
        self.assertEqual(len(bills), 1)
        b = bills[0]
        self.assertEqual(b["billName"], "INV-101")
        self.assertEqual(b["billType"], "New Ref")
        self.assertEqual(b["amount"], 11800.0)  # Positive for sales invoice
        self.assertEqual(b["dueDate"], "2026-05-12")  # 30 days after 2026-04-12
        self.assertTrue(b["tallyExternalId"].startswith("voucher-guid-101:bill:"))

    def test_receipt_voucher_bill_settlement(self):
        sample_xml = """<ENVELOPE>
            <BODY>
                <DATA>
                    <COLLECTION>
                        <VOUCHER>
                            <DATE>20260420</DATE>
                            <VOUCHERTYPENAME>Receipt</VOUCHERTYPENAME>
                            <VOUCHERNUMBER>REC-501</VOUCHERNUMBER>
                            <GUID>receipt-guid-501</GUID>
                            <PARTYLEDGERNAME>Customer A</PARTYLEDGERNAME>
                            <AMOUNT>11800.00</AMOUNT>
                            <ALLLEDGERENTRIES.LIST>
                                <LEDGERNAME>Customer A</LEDGERNAME>
                                <AMOUNT>11800.00</AMOUNT>
                                <BILLALLOCATIONS.LIST>
                                    <NAME>INV-101</NAME>
                                    <BILLTYPE>Agst Ref</BILLTYPE>
                                    <AMOUNT>11800.00</AMOUNT>
                                </BILLALLOCATIONS.LIST>
                            </ALLLEDGERENTRIES.LIST>
                            <ALLLEDGERENTRIES.LIST>
                                <LEDGERNAME>HDFC Bank</LEDGERNAME>
                                <AMOUNT>-11800.00</AMOUNT>
                            </ALLLEDGERENTRIES.LIST>
                        </VOUCHER>
                    </COLLECTION>
                </DATA>
            </BODY>
        </ENVELOPE>"""
        vouchers = parse_metadata_response(sample_xml, "Voucher")
        self.assertEqual(len(vouchers), 1)
        v = vouchers[0]
        self.assertEqual(v["voucherType"], "Receipt")
        bills = v.get("billAllocations", [])
        self.assertEqual(len(bills), 1)
        b = bills[0]
        self.assertEqual(b["billName"], "INV-101")
        self.assertEqual(b["billType"], "Against Ref")  # Normalized from Agst Ref
        self.assertEqual(b["amount"], -11800.0)  # Negative for receipt/settlement
        self.assertEqual(b["tallyExternalId"], "receipt-guid-501:bill:0")

if __name__ == "__main__":
    unittest.main()

