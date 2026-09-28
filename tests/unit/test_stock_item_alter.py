import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from apps.backend.adapters.tally.tally_importer import (
    build_stock_item_alter_xml,
    TallyImporter,
)
from apps.backend.services.importer_service import ImporterService


class TestStockItemAlter(unittest.TestCase):
    def test_build_stock_item_alter_xml_structure(self):
        item_data = {
            "company_name": "DRA Marketing LLP",
            "name": "1 1/4\" 40*15KGF GARUDA PVC PIPES",
            "quantity": 25,
            "rate": 75,
            "value": 1875,
            "unit": "Pcs",
            "hsnCode": "39172310",
            "godown": "Main Location",
            "batch": "Primary Batch",
        }
        xml = build_stock_item_alter_xml(item_data)
        self.assertIn('<STOCKITEM ACTION="Alter"', xml)
        self.assertIn('1 1/4&quot; 40*15KGF GARUDA PVC PIPES', xml)
        self.assertIn('<SVCURRENTCOMPANY>DRA Marketing LLP</SVCURRENTCOMPANY>', xml)
        self.assertIn('<OPENINGBALANCE>25.0 Pcs</OPENINGBALANCE>', xml)
        self.assertIn('<OPENINGRATE>75.0/Pcs</OPENINGRATE>', xml)
        self.assertIn('<OPENINGVALUE>-1875.00</OPENINGVALUE>', xml)
        self.assertIn('<HSNCODE>39172310</HSNCODE>', xml)
        self.assertIn('<GODOWNNAME>Main Location</GODOWNNAME>', xml)
        self.assertIn('<BATCHNAME>Primary Batch</BATCHNAME>', xml)

    def test_build_stock_item_alter_xml_zero_qty(self):
        item_data = {
            "name": "Empty Item",
            "quantity": 0,
            "rate": 0,
            "unit": "Nos",
        }
        xml = build_stock_item_alter_xml(item_data)
        self.assertIn('<STOCKITEM ACTION="Alter" NAME="Empty Item">', xml)
        self.assertIn('<OPENINGBALANCE>0</OPENINGBALANCE>', xml)
        self.assertIn('<OPENINGVALUE>0</OPENINGVALUE>', xml)
        self.assertNotIn('<BATCHALLOCATIONS.LIST>', xml)

    def test_alter_stock_item_success(self):
        import asyncio
        client_mock = MagicMock()
        success_xml = """<RESPONSE>
            <CREATED>0</CREATED>
            <ALTERED>1</ALTERED>
            <ERRORS>0</ERRORS>
        </RESPONSE>"""
        client_mock.send_xml_request_async = AsyncMock(return_value=(True, 200, success_xml, 0.05))

        importer = TallyImporter(client=client_mock)
        importer.ensure_unit = AsyncMock(return_value=True)

        service = ImporterService(tally_importer=importer)

        payload = {
            "company_name": "DRA Marketing LLP",
            "itemName": "1 1/4\" 40*15KGF GARUDA PVC PIPES",
            "quantity": 25,
            "rate": 75,
            "value": 1875,
            "unit": "Pcs",
            "hsnCode": "39172310",
        }
        loop = asyncio.new_event_loop()
        try:
            res = loop.run_until_complete(service.update_stock_item(payload))
            self.assertEqual(res["status"], "SUCCESS")
            self.assertEqual(res["target"], "TALLY")
            self.assertIn("1 1/4\" 40*15KGF GARUDA PVC PIPES", res["message"])
        finally:
            loop.close()


if __name__ == "__main__":
    unittest.main()
