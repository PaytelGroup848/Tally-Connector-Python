import unittest
from apps.backend.adapters.tally.xml_builders.voucher_builder import build_voucher_import_xml


class TestInvoiceAdvancedSettings(unittest.TestCase):

    def test_sales_voucher_with_advanced_settings_dict(self):
        payload = {
            "voucherType": "Sales",
            "voucherNumber": "INV-2026-001",
            "companyName": "Himanshu Pvt Ltd",
            "date": "2026-10-14",
            "partyLedger": "Acme Corp Ltd",
            "amount": 1180.0,
            "items": [
                {
                    "itemName": "laptop",
                    "quantity": 2,
                    "rate": 500,
                    "units": "Pcs",
                    "amount": 1000.0,
                }
            ],
            "advancedSettings": {
                "supplierName": "Himanshu Pvt Ltd",
                "supplierCountry": "India",
                "supplierState": "Delhi",
                "postalCode": "110001",
                "gstinUin": "07AAAAA0000A1Z5",
                "address": "Connaught Place, New Delhi",
                "consigneeName": "Star Logistics Warehouse",
                "consigneeCountry": "India",
                "consigneeState": "Haryana",
                "consigneePostalCode": "122001",
                "consigneeGstinUin": "06BBBBB1111B1Z6",
                "consigneeAddress": "Plot 10, Udyog Vihar, Gurugram",
                "dispatchFrom": "New Delhi Hub",
                "dispatchThrough": "SafeXpress / Road",
                "dispatchDocNo": "LR-887766",
                "dispatchDate": "2026-10-14",
                "orderNo": "PO-9988",
                "orderDate": "2026-10-12",
                "termsOfDelivery": "Door Delivery within 3 days",
                "motorVehicleNo": "DL01AB1234",
            },
        }

        xml = build_voucher_import_xml(payload)

        # Consignee verification
        self.assertIn("<CONSIGNEEMAILINGNAME>Star Logistics Warehouse</CONSIGNEEMAILINGNAME>", xml)
        self.assertIn("<CONSIGNEESTATENAME>Haryana</CONSIGNEESTATENAME>", xml)
        self.assertIn("<CONSIGNEECOUNTRYNAME>India</CONSIGNEECOUNTRYNAME>", xml)
        self.assertIn("<CONSIGNEEPINCODE>122001</CONSIGNEEPINCODE>", xml)
        self.assertIn("<CONSIGNEEGSTIN>06BBBBB1111B1Z6</CONSIGNEEGSTIN>", xml)
        self.assertIn("<CONSIGNEEADDRESS>Plot 10, Udyog Vihar, Gurugram</CONSIGNEEADDRESS>", xml)

        # Dispatch verification
        self.assertIn("<BASICSHIPDOCUMENTNO>LR-887766</BASICSHIPDOCUMENTNO>", xml)
        self.assertIn("<BILLOFLADINGNO>LR-887766</BILLOFLADINGNO>", xml)
        self.assertIn("<BASICSHIPPEDBY>SafeXpress / Road</BASICSHIPPEDBY>", xml)
        self.assertIn("<BASICFINALDESTINATION>New Delhi Hub</BASICFINALDESTINATION>", xml)
        self.assertIn("<BASICSHIPDATE>20261014</BASICSHIPDATE>", xml)
        self.assertIn("<BILLOFLADINGDATE>20261014</BILLOFLADINGDATE>", xml)
        self.assertIn("<VEHICLENO>DL01AB1234</VEHICLENO>", xml)

        # Order verification
        self.assertIn("<BASICORDERREF>PO-9988</BASICORDERREF>", xml)
        self.assertIn("<BASICPURCHASEORDERNO>PO-9988</BASICPURCHASEORDERNO>", xml)
        self.assertIn("<BASICORDERDATE>20261012</BASICORDERDATE>", xml)
        self.assertIn("<BASICORDERTERMS>Door Delivery within 3 days</BASICORDERTERMS>", xml)

    def test_sales_voucher_with_top_level_additional_settings(self):
        payload = {
            "voucherType": "Sales",
            "voucherNumber": "INV-2026-002",
            "companyName": "Himanshu Pvt Ltd",
            "date": "2026-10-14",
            "partyLedger": "Acme Corp Ltd",
            "consigneeName": "Direct Consignee",
            "consigneeState": "Maharashtra",
            "consigneePostalCode": "400001",
            "consigneeGstinUin": "27CCCCCC2222C1Z7",
            "consigneeAddress": "Nariman Point, Mumbai",
            "dispatchDocNo": "BL-554433",
            "dispatchThrough": "Blue Dart Air",
            "dispatchFrom": "Mumbai Port",
            "dispatchDate": "2026-10-14",
            "orderNo": "SO-4433",
            "orderDate": "2026-10-11",
            "termsOfDelivery": "Ex-Factory",
            "vehicleNo": "MH01CD5678",
            "amount": 500.0,
            "items": [
                {
                    "itemName": "laptop",
                    "quantity": 1,
                    "rate": 500,
                    "units": "Pcs",
                    "amount": 500.0,
                }
            ],
        }

        xml = build_voucher_import_xml(payload)

        self.assertIn("<CONSIGNEEMAILINGNAME>Direct Consignee</CONSIGNEEMAILINGNAME>", xml)
        self.assertIn("<CONSIGNEESTATENAME>Maharashtra</CONSIGNEESTATENAME>", xml)
        self.assertIn("<CONSIGNEEPINCODE>400001</CONSIGNEEPINCODE>", xml)
        self.assertIn("<CONSIGNEEGSTIN>27CCCCCC2222C1Z7</CONSIGNEEGSTIN>", xml)
        self.assertIn("<CONSIGNEEADDRESS>Nariman Point, Mumbai</CONSIGNEEADDRESS>", xml)
        self.assertIn("<BASICSHIPDOCUMENTNO>BL-554433</BASICSHIPDOCUMENTNO>", xml)
        self.assertIn("<BASICSHIPPEDBY>Blue Dart Air</BASICSHIPPEDBY>", xml)
        self.assertIn("<BASICFINALDESTINATION>Mumbai Port</BASICFINALDESTINATION>", xml)
        self.assertIn("<BASICSHIPDATE>20261014</BASICSHIPDATE>", xml)
        self.assertIn("<VEHICLENO>MH01CD5678</VEHICLENO>", xml)
        self.assertIn("<BASICORDERREF>SO-4433</BASICORDERREF>", xml)
        self.assertIn("<BASICORDERDATE>20261011</BASICORDERDATE>", xml)
        self.assertIn("<BASICORDERTERMS>Ex-Factory</BASICORDERTERMS>", xml)

    def test_parse_voucher_advanced_settings_from_tally_xml(self):
        from apps.backend.adapters.tally.response_parser import parse_metadata_response

        sample_xml = """<ENVELOPE>
            <BODY>
                <DATA>
                    <COLLECTION>
                        <VOUCHER>
                            <GUID>74cd8431-e2d2-4706-9250-e4b9f8706d6f-00000034</GUID>
                            <VOUCHERNUMBER>15</VOUCHERNUMBER>
                            <VOUCHERTYPENAME>Sales</VOUCHERTYPENAME>
                            <DATE>20261014</DATE>
                            <PARTYLEDGERNAME>Tarun Chaprana</PARTYLEDGERNAME>
                            <AMOUNT>-226.93</AMOUNT>
                            <NARRATION>new Invoice with addvance</NARRATION>
                            <REFERENCE>ADD-001</REFERENCE>
                            <REFERENCEDATE>20261014</REFERENCEDATE>
                            <PLACEOFSUPPLY>Delhi</PLACEOFSUPPLY>
                            <BASICSHIPDOCUMENTNO>DC-999</BASICSHIPDOCUMENTNO>
                            <BILLOFLADINGNO>DC-999</BILLOFLADINGNO>
                            <BASICSHIPDATE>20261014</BASICSHIPDATE>
                            <BILLOFLADINGDATE>20261014</BILLOFLADINGDATE>
                            <BASICSHIPPEDBY>BlueDart</BASICSHIPPEDBY>
                            <BASICFINALDESTINATION>Gurugram</BASICFINALDESTINATION>
                            <VEHICLENO>DL-01-XX-9999</VEHICLENO>
                            <BASICORDERREF>PO-888</BASICORDERREF>
                            <BASICORDERDATE>20261013</BASICORDERDATE>
                            <BASICORDERTERMS.LIST>
                                <BASICORDERTERM>Payment on Delivery</BASICORDERTERM>
                            </BASICORDERTERMS.LIST>
                            <CONSIGNEEMAILINGNAME>Warehouse North</CONSIGNEEMAILINGNAME>
                            <CONSIGNEEADDRESS.LIST>
                                <BASICADDRESS>Sector 18, Gurugram</BASICADDRESS>
                            </CONSIGNEEADDRESS.LIST>
                            <CONSIGNEESTATENAME>Haryana</CONSIGNEESTATENAME>
                            <CONSIGNEEPINCODE>122001</CONSIGNEEPINCODE>
                            <CONSIGNEEGSTIN>06AAAAA0000A1Z5</CONSIGNEEGSTIN>
                            <ALLLEDGERENTRIES.LIST>
                                <LEDGERNAME>Tarun Chaprana</LEDGERNAME>
                                <AMOUNT>-226.93</AMOUNT>
                                <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
                                <ISPARTYLEDGER>Yes</ISPARTYLEDGER>
                            </ALLLEDGERENTRIES.LIST>
                            <ALLLEDGERENTRIES.LIST>
                                <LEDGERNAME>Sales</LEDGERNAME>
                                <AMOUNT>226.93</AMOUNT>
                                <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
                                <ISPARTYLEDGER>No</ISPARTYLEDGER>
                            </ALLLEDGERENTRIES.LIST>
                            <ALLINVENTORYENTRIES.LIST>
                                <STOCKITEMNAME>laptop</STOCKITEMNAME>
                                <RATE>192.31/pcs</RATE>
                                <AMOUNT>192.31</AMOUNT>
                                <BILLEDQTY>1 pcs</BILLEDQTY>
                                <GODOWNNAME>Main Location</GODOWNNAME>
                            </ALLINVENTORYENTRIES.LIST>
                        </VOUCHER>
                    </COLLECTION>
                </DATA>
            </BODY>
        </ENVELOPE>"""

        parsed = parse_metadata_response(sample_xml, tag_name="Voucher")
        self.assertEqual(len(parsed), 1)
        v = parsed[0]

        # Top-level checks
        self.assertEqual(v["voucherNumber"], "15")
        self.assertEqual(v["voucherType"], "Sales")
        self.assertEqual(v["partyLedger"], "Tarun Chaprana")
        self.assertEqual(v["customerName"], "Tarun Chaprana")
        self.assertEqual(v["reference"], "ADD-001")
        self.assertEqual(v["placeOfSupply"], "Delhi")
        self.assertEqual(len(v["items"]), 1)
        self.assertEqual(v["items"][0]["itemName"], "laptop")
        self.assertEqual(len(v["lines"]), 2)

        # Advanced Settings checks
        adv = v.get("advancedSettings") or {}
        self.assertEqual(adv["dispatchDocNo"], "DC-999")
        self.assertEqual(adv["dispatchedThrough"], "BlueDart")
        self.assertEqual(adv["destination"], "Gurugram")
        self.assertEqual(adv["vehicleNo"], "DL-01-XX-9999")
        self.assertEqual(adv["dispatchDate"], "2026-10-14")
        self.assertEqual(adv["orderNo"], "PO-888")
        self.assertEqual(adv["orderDate"], "2026-10-13")
        self.assertEqual(adv["terms"], "Payment on Delivery")
        self.assertEqual(adv["consigneeName"], "Warehouse North")
        self.assertEqual(adv["consigneeState"], "Haryana")
        self.assertEqual(adv["consigneePincode"], "122001")
        self.assertEqual(adv["consigneeGstin"], "06AAAAA0000A1Z5")

        # Raw enrichment checks
        raw = v.get("raw") or {}
        self.assertEqual(raw["reference"], "ADD-001")
        self.assertEqual(raw["customerName"], "Tarun Chaprana")
        self.assertIn("advancedSettings", raw)
        self.assertEqual(raw["advancedSettings"]["dispatchDocNo"], "DC-999")
        self.assertEqual(raw["advancedSettings"]["consigneeName"], "Warehouse North")


if __name__ == "__main__":
    unittest.main()


