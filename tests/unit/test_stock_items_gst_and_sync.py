import unittest
from apps.backend.adapters.tally.response_parser import parse_metadata_response, extract_gst_details
from shared.cloud.cloud_sync_client import CloudSyncClient
from unittest.mock import MagicMock

class TestStockItemsGstAndSync(unittest.TestCase):

    def test_stock_item_gst_details_extraction(self):
        """Tests that response_parser extracts 18% IGST rate and Taxable taxability from modern TallyPrime XML."""
        xml_content = """<ENVELOPE>
            <BODY>
                <DATA>
                    <COLLECTION>
                        <STOCKITEM NAME="Chips">
                            <GUID>74cd8431-0001</GUID>
                            <PARENT>Snacks</PARENT>
                            <CATEGORY>Food</CATEGORY>
                            <BASEUNITS>Pcs</BASEUNITS>
                            <CLOSINGBALANCE>20 Pcs</CLOSINGBALANCE>
                            <CLOSINGRATE>7.00/Pcs</CLOSINGRATE>
                            <CLOSINGVALUE>-140.00</CLOSINGVALUE>
                            <OPENINGBALANCE>20 Pcs</OPENINGBALANCE>
                            <OPENINGRATE>7.00/Pcs</OPENINGRATE>
                            <OPENINGVALUE>-140.00</OPENINGVALUE>
                            <HSNDETAILS.LIST>
                                <HSNCODE>11010000</HSNCODE>
                            </HSNDETAILS.LIST>
                            <GSTDETAILS.LIST>
                                <TAXABILITY>Taxable</TAXABILITY>
                                <STATEWISEDETAILS.LIST>
                                    <RATEDETAILS.LIST>
                                        <GSTRATEDUTYHEAD>CGST</GSTRATEDUTYHEAD>
                                        <GSTRATE>9</GSTRATE>
                                    </RATEDETAILS.LIST>
                                    <RATEDETAILS.LIST>
                                        <GSTRATEDUTYHEAD>SGST</GSTRATEDUTYHEAD>
                                        <GSTRATE>9</GSTRATE>
                                    </RATEDETAILS.LIST>
                                    <RATEDETAILS.LIST>
                                        <GSTRATEDUTYHEAD>IGST</GSTRATEDUTYHEAD>
                                        <GSTRATE>18</GSTRATE>
                                    </RATEDETAILS.LIST>
                                </STATEWISEDETAILS.LIST>
                            </GSTDETAILS.LIST>
                            <BATCHALLOCATIONS.LIST>
                                <GODOWNNAME>Delhi</GODOWNNAME>
                                <BATCHNAME>Batch-01</BATCHNAME>
                            </BATCHALLOCATIONS.LIST>
                        </STOCKITEM>
                    </COLLECTION>
                </DATA>
            </BODY>
        </ENVELOPE>"""

        items = parse_metadata_response(xml_content, tag_name="StockItem")
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item["name"], "Chips")
        self.assertEqual(item["hsnCode"], "11010000")
        self.assertEqual(item["unit"], "Pcs")
        self.assertEqual(item["gstRate"], 18.0)
        self.assertEqual(item["taxability"], "Taxable")
        self.assertEqual(item["godown"], "Delhi")
        self.assertEqual(item["batch"], "Batch-01")
        self.assertEqual(item["quantity"], 20.0)
        self.assertEqual(item["rate"], 7.0)

    def test_cloud_sync_client_stock_payload(self):
        """Tests that CloudSyncClient formats STOCK items with parent, group, category, balances and gstRate."""
        mock_auth = MagicMock()
        mock_auth.base_url = "https://mockapi.example.com"
        mock_auth.access_token = "mock_token"
        client = CloudSyncClient(mock_auth)

        sample_items = [
            {
                "tallyExternalId": "GUID-001",
                "name": "Chips",
                "parent": "Snacks",
                "category": "Food",
                "godown": "Delhi",
                "batch": "Batch-01",
                "quantity": 20.0,
                "rate": 7.0,
                "value": 140.0,
                "openingBalance": 20.0,
                "openingRate": 7.0,
                "openingValue": 140.0,
                "closingBalance": 20.0,
                "closingRate": 7.0,
                "closingValue": 140.0,
                "unit": "Pcs",
                "hsnCode": "11010000",
                "gstRate": 18.0,
                "taxability": "Taxable",
                "gstApplicable": "Applicable",
            }
        ]

        # Intercept httpx client post
        posted_data = {}
        def mock_post(url, json=None, headers=None, timeout=None):
            posted_data.update(json or {})
            res = MagicMock()
            res.status_code = 200
            res.json.return_value = {"status": "SUCCESS", "batchId": "b1"}
            return res

        client._get_client = MagicMock(return_value=MagicMock(post=mock_post))
        ok, msg, res = client.sync_batch("sync_123", "TestCo", "STOCK", sample_items, batch_number=1, is_last_batch=True)
        self.assertTrue(ok)
        self.assertIn("records", posted_data)
        self.assertEqual(len(posted_data["records"]), 1)
        p_item = posted_data["records"][0]
        self.assertEqual(p_item["name"], "Chips")
        self.assertEqual(p_item["parent"], "Snacks")
        self.assertEqual(p_item["group"], "Snacks")
        self.assertEqual(p_item["category"], "Food")
        self.assertEqual(p_item["gstRate"], 18.0)
        self.assertEqual(p_item["taxability"], "Taxable")
        self.assertEqual(p_item["openingBalance"], 20.0)
        self.assertEqual(p_item["closingBalance"], 20.0)
        self.assertEqual(p_item["unit"], "Pcs")
        self.assertEqual(p_item["godown"], "Delhi")
