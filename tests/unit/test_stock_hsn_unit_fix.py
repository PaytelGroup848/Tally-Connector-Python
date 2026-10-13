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

    def test_stock_item_import_and_alter_xml_gst_details(self):
        """Tests that build_stock_item_import_xml and alter_xml produce valid modern TallyPrime 3.0+ GST and HSN tags."""
        from apps.backend.adapters.tally.xml_builders.stock_builder import (
            build_stock_item_import_xml,
            build_stock_item_alter_xml,
        )

        item_data = {
            "name": "Laptop Pro",
            "unit": "Pcs",
            "hsn_code": "84713010",
            "hsn_description": "Laptops & Notebooks",
            "gst_rate": 18.0,
            "applicable_from": "20250401",
        }

        # 1. Create XML verification
        create_xml = build_stock_item_import_xml(item_data)
        self.assertIn("<STOCKITEM ACTION=\"Create\" NAME=\"Laptop Pro\">", create_xml)
        self.assertIn("<HSNCODE>84713010</HSNCODE>", create_xml)
        self.assertIn("<HSNDETAILS.LIST>", create_xml)
        self.assertIn("<SRCOFHSNDETAILS>Specify Details Here</SRCOFHSNDETAILS>", create_xml)
        self.assertIn("<GSTDETAILS.LIST>", create_xml)
        self.assertIn("<SRCOFGSTDETAILS>Specify Details Here</SRCOFGSTDETAILS>", create_xml)
        self.assertIn("<TAXABILITY>Taxable</TAXABILITY>", create_xml)
        self.assertIn("<GSTRATEDUTYHEAD>CGST</GSTRATEDUTYHEAD>", create_xml)
        self.assertIn("<GSTRATE>9</GSTRATE>", create_xml)
        self.assertIn("<GSTRATEDUTYHEAD>SGST/UTGST</GSTRATEDUTYHEAD>", create_xml)
        self.assertIn("<GSTRATEDUTYHEAD>IGST</GSTRATEDUTYHEAD>", create_xml)
        self.assertIn("<GSTRATE>18</GSTRATE>", create_xml)

        # 2. Alter XML verification
        alter_data = dict(item_data)
        alter_data["quantity"] = 10
        alter_data["rate"] = 55000.0
        alter_xml = build_stock_item_alter_xml(alter_data)
        self.assertIn("<STOCKITEM ACTION=\"Alter\" NAME=\"Laptop Pro\">", alter_xml)
        self.assertIn("<OPENINGBALANCE>10.0 Pcs</OPENINGBALANCE>", alter_xml)
        self.assertIn("<HSNDETAILS.LIST>", alter_xml)
        self.assertIn("<GSTDETAILS.LIST>", alter_xml)
        self.assertIn("<SRCOFGSTDETAILS>Specify Details Here</SRCOFGSTDETAILS>", alter_xml)

    def test_stock_item_import_xml_opening_balance_and_batch_allocations(self):
        """Tests that build_stock_item_import_xml injects opening balance, rate, value, and batch allocations."""
        from apps.backend.adapters.tally.xml_builders.stock_builder import (
            build_stock_item_import_xml,
            build_godown_import_xml,
        )

        item_data = {
            "name": "Tomato",
            "unit": "Kg",
            "quantity": 800,
            "rate": 70,
            "value": 56000,
            "godown": "Mumbai",
            "batch": "B-1",
            "hsn_code": "9608",
            "gst_rate": 18.0,
        }

        xml = build_stock_item_import_xml(item_data)
        self.assertIn("<STOCKITEM ACTION=\"Create\" NAME=\"Tomato\">", xml)
        self.assertIn("<OPENINGBALANCE>800.0 Kg</OPENINGBALANCE>", xml)
        self.assertIn("<OPENINGRATE>70.0/Kg</OPENINGRATE>", xml)
        self.assertIn("<OPENINGVALUE>-56000.00</OPENINGVALUE>", xml)
        self.assertIn("<BATCHALLOCATIONS.LIST>", xml)
        self.assertIn("<GODOWNNAME>Mumbai</GODOWNNAME>", xml)
        self.assertIn("<BATCHNAME>B-1</BATCHNAME>", xml)
        self.assertIn("<OPENINGVALUE>-56000.00</OPENINGVALUE>", xml)
        self.assertIn("<HSNCODE>9608</HSNCODE>", xml)

        # Godown XML verification
        godown_xml = build_godown_import_xml("Mumbai", "Venkateshwara Traders")
        self.assertIn("<GODOWN ACTION=\"Create\" NAME=\"Mumbai\">", godown_xml)
        self.assertIn("<NAME>Mumbai</NAME>", godown_xml)

if __name__ == "__main__":
    unittest.main()


