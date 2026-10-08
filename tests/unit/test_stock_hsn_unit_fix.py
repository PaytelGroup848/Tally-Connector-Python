import unittest
import xml.etree.ElementTree as ET
from apps.backend.adapters.tally.response_parser import parse_metadata_response
from apps.backend.adapters.tally.tally_importer import (
    _lookup_item_master_unit,
    _lookup_item_master_hsn,
    build_voucher_import_xml,
    _ITEM_MASTER_UNIT_CACHE,
    _ITEM_MASTER_HSN_CACHE,
)

class TestStockHsnUnitFix(unittest.TestCase):
    def test_stock_item_tariff_and_classification_hsn_parsing(self):
        """Tests that response_parser extracts HSN from TARIFFCODE, GSTCLASSIFICATION, and GSTHSNNAME."""
        xml_tariff = """<ENVELOPE>
            <BODY>
                <DATA>
                    <COLLECTION>
                        <STOCKITEM NAME="MAGNESITE GROG">
                            <PARENT>RAW MATERIAL</PARENT>
                            <BASEUNITS>MT</BASEUNITS>
                            <CLOSINGBALANCE>10 MT</CLOSINGBALANCE>
                            <TARIFFLIST.LIST>
                                <TARIFFCODE>69021040</TARIFFCODE>
                            </TARIFFLIST.LIST>
                        </STOCKITEM>
                    </COLLECTION>
                </DATA>
            </BODY>
        </ENVELOPE>"""
        items = parse_metadata_response(xml_tariff, tag_name="StockItem")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["name"], "MAGNESITE GROG")
        self.assertEqual(items[0]["unit"], "MT")
        self.assertEqual(items[0]["units"], "MT")
        self.assertEqual(items[0]["hsnCode"], "69021040")

    def test_stock_group_hsn_parsing(self):
        """Tests that response_parser extracts HSN from StockGroup."""
        xml_group = """<ENVELOPE>
            <BODY>
                <DATA>
                    <COLLECTION>
                        <STOCKGROUP NAME="RAW MATERIAL">
                            <PARENT>Primary</PARENT>
                            <TARIFFLIST.LIST>
                                <TARIFFCODE>25199020</TARIFFCODE>
                            </TARIFFLIST.LIST>
                        </STOCKGROUP>
                    </COLLECTION>
                </DATA>
            </BODY>
        </ENVELOPE>"""
        groups = parse_metadata_response(xml_group, tag_name="StockGroup")
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["name"], "RAW MATERIAL")
        self.assertEqual(groups[0]["hsnCode"], "25199020")
        self.assertEqual(groups[0]["hsn"], "25199020")

    def test_voucher_xml_includes_master_hsn_and_unit(self):
        """Tests that build_voucher_import_xml includes GSTHSNNAME and uses master unit."""
        _ITEM_MASTER_UNIT_CACHE[("Test Co", "ferro chrome")] = "MT"
        _ITEM_MASTER_HSN_CACHE[("Test Co", "ferro chrome")] = "72024100"

        voucher_data = {
            "voucher_type": "Sales",
            "date": "2026-10-05",
            "company_name": "Test Co",
            "party_ledger": "Test Buyer",
            "items": [
                {
                    "name": "FERRO CHROME",
                    "quantity": 5,
                    "rate": 96633.5,
                    "unit": "",      # Empty from web form
                    "hsn_code": ""   # Empty from web form
                }
            ]
        }
        xml_res = build_voucher_import_xml(voucher_data)
        self.assertIn("<STOCKITEMNAME>FERRO CHROME</STOCKITEMNAME>", xml_res)
        self.assertIn("<GSTHSNNAME>72024100</GSTHSNNAME>", xml_res)
        self.assertIn("<ACTUALQTY>5 MT</ACTUALQTY>", xml_res)
        self.assertIn("<BILLEDQTY>5 MT</BILLEDQTY>", xml_res)

if __name__ == "__main__":
    unittest.main()

