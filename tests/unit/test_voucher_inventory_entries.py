import unittest
from apps.backend.adapters.tally.response_parser import parse_metadata_response, parse_qty, parse_rate


class TestVoucherInventoryEntriesParsing(unittest.TestCase):

    def test_parse_qty(self):
        qty, unit = parse_qty("10 Nos")
        self.assertEqual(qty, 10.0)
        self.assertEqual(unit, "Nos")

        qty, unit = parse_qty(" 25.50 pcs ")
        self.assertEqual(qty, 25.5)
        self.assertEqual(unit, "pcs")

        qty, unit = parse_qty(None)
        self.assertEqual(qty, 0.0)
        self.assertEqual(unit, "")

    def test_parse_rate(self):
        rate = parse_rate("826.00/Nos")
        self.assertEqual(rate, 826.0)

        rate = parse_rate("150.00/pcs")
        self.assertEqual(rate, 150.0)

        rate = parse_rate(None)
        self.assertEqual(rate, 0.0)

    def test_parse_voucher_with_inventory_entries(self):
        xml_content = """<ENVELOPE>
            <BODY>
                <DATA>
                    <TALLYMESSAGE>
                        <VOUCHER VCHTYPE="Sales" ACTION="Create">
                            <DATE>20261010</DATE>
                            <VOUCHERNUMBER>TEST-INV-99</VOUCHERNUMBER>
                            <VOUCHERTYPENAME>Sales</VOUCHERTYPENAME>
                            <PARTYLEDGERNAME>AVN Traders</PARTYLEDGERNAME>
                            <AMOUNT>8260.00</AMOUNT>
                            <GUID>tally-vch-guid-99</GUID>
                            <ALLLEDGERENTRIES.LIST>
                                <LEDGERNAME>AVN Traders</LEDGERNAME>
                                <AMOUNT>-8260.00</AMOUNT>
                            </ALLLEDGERENTRIES.LIST>
                            <ALLLEDGERENTRIES.LIST>
                                <LEDGERNAME>Sales</LEDGERNAME>
                                <AMOUNT>8260.00</AMOUNT>
                            </ALLLEDGERENTRIES.LIST>
                            <ALLINVENTORYENTRIES.LIST>
                                <STOCKITEMNAME>Refractory Brick</STOCKITEMNAME>
                                <RATE>826.00/Nos</RATE>
                                <AMOUNT>8260.00</AMOUNT>
                                <BILLEDQTY>10 Nos</BILLEDQTY>
                                <ACTUALQTY>10 Nos</ACTUALQTY>
                                <GODOWNNAME>Main Location</GODOWNNAME>
                                <HSNCODE>69021000</HSNCODE>
                                <GUID>tally-item-guid-123</GUID>
                            </ALLINVENTORYENTRIES.LIST>
                        </VOUCHER>
                    </TALLYMESSAGE>
                </DATA>
            </BODY>
        </ENVELOPE>"""

        vouchers = parse_metadata_response(xml_content, tag_name="Voucher")
        self.assertEqual(len(vouchers), 1)
        v = vouchers[0]

        # Verify ledger lines
        self.assertEqual(len(v["ledgerEntries"]), 2)
        self.assertEqual(v["ledgerEntries"][0]["ledgerName"], "AVN Traders")
        self.assertEqual(v["ledgerEntries"][0]["amount"], -8260.0)
        self.assertEqual(v["ledgerEntries"][1]["ledgerName"], "Sales")
        self.assertEqual(v["ledgerEntries"][1]["amount"], 8260.0)

        # Verify inventoryEntries
        inv = v.get("inventoryEntries")
        self.assertIsNotNone(inv)
        self.assertEqual(len(inv), 1)

        entry = inv[0]
        self.assertEqual(entry["itemName"], "Refractory Brick")
        self.assertEqual(entry["itemTallyExternalId"], "tally-item-guid-123")
        self.assertEqual(entry["hsnCode"], "69021000")
        self.assertEqual(entry["quantity"], 10)
        self.assertEqual(entry["unit"], "Nos")
        self.assertEqual(entry["rate"], 826.0)
        self.assertEqual(entry["amount"], 8260.0)
        self.assertEqual(entry["godown"], "Main Location")


if __name__ == "__main__":
    unittest.main()

