import unittest
from apps.backend.adapters.tally.response_parser import parse_metadata_response
from shared.cloud.cloud_sync_client import CloudSyncClient


class TestPartiesModule(unittest.TestCase):
    def test_ledger_parsing_complete_fields(self):
        ledger_xml = """<ENVELOPE>
<BODY><DATA><COLLECTION>
<LEDGER NAME="AVN Enterprises">
    <GUID>avn-guid-999</GUID>
    <PARENT>Sundry Debtors</PARENT>
    <PARTYGSTIN>07AAAAA0000A1Z5</PARTYGSTIN>
    <INCOMETAXNUMBER>AAAAA0000A</INCOMETAXNUMBER>
    <EMAIL>avn@traders.com</EMAIL>
    <LEDGERPHONE>9876543210</LEDGERPHONE>
    <ADDRESS.LIST><ADDRESS>Plot 12, Ind Area</ADDRESS><ADDRESS>Delhi</ADDRESS></ADDRESS.LIST>
    <STATENAME>Delhi</STATENAME>
    <COUNTRYNAME>India</COUNTRYNAME>
    <PINCODE>110020</PINCODE>
    <GSTREGISTRATIONTYPE>Regular</GSTREGISTRATIONTYPE>
    <CREDITLIMIT>75000</CREDITLIMIT>
    <BILLCREDITPERIOD>45 Days</BILLCREDITPERIOD>
    <OPENINGBALANCE>-25000</OPENINGBALANCE>
    <CLOSINGBALANCE>-35000</CLOSINGBALANCE>
</LEDGER>
</COLLECTION></DATA></BODY></ENVELOPE>"""
        res = parse_metadata_response(ledger_xml, "Ledger")
        self.assertEqual(len(res), 1)
        l = res[0]
        self.assertEqual(l["name"], "AVN Enterprises")
        self.assertEqual(l["gstin"], "07AAAAA0000A1Z5")
        self.assertEqual(l["pan"], "AAAAA0000A")
        self.assertEqual(l["email"], "avn@traders.com")
        self.assertEqual(l["phone"], "9876543210")
        self.assertIn("Plot 12, Ind Area", l["address"])
        self.assertEqual(l["state"], "Delhi")
        self.assertEqual(l["country"], "India")
        self.assertEqual(l["pincode"], "110020")
        self.assertEqual(l["registration_type"], "Regular")
        self.assertEqual(l["creditLimit"], 75000.0)
        self.assertEqual(l["creditDays"], 45)
        self.assertEqual(l["creditPeriod"], "45 Days")
        self.assertEqual(l["openingBalance"], -25000.0)
        self.assertEqual(l["closingBalance"], -35000.0)

    def test_voucher_party_ledger_flag(self):
        voucher_xml = """<ENVELOPE>
<BODY><DATA><COLLECTION>
<VOUCHER VCHNUM="INV-001">
    <DATE>20261012</DATE>
    <VOUCHERTYPENAME>Sales</VOUCHERTYPENAME>
    <PARTYLEDGERNAME>AVN Enterprises</PARTYLEDGERNAME>
    <AMOUNT>-11800</AMOUNT>
    <ALLLEDGERENTRIES.LIST>
        <LEDGERNAME>AVN Enterprises</LEDGERNAME>
        <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
        <AMOUNT>-11800</AMOUNT>
    </ALLLEDGERENTRIES.LIST>
    <ALLLEDGERENTRIES.LIST>
        <LEDGERNAME>Sales Account</LEDGERNAME>
        <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
        <AMOUNT>10000</AMOUNT>
    </ALLLEDGERENTRIES.LIST>
    <ALLLEDGERENTRIES.LIST>
        <LEDGERNAME>CGST</LEDGERNAME>
        <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
        <AMOUNT>900</AMOUNT>
    </ALLLEDGERENTRIES.LIST>
    <ALLLEDGERENTRIES.LIST>
        <LEDGERNAME>SGST</LEDGERNAME>
        <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
        <AMOUNT>900</AMOUNT>
    </ALLLEDGERENTRIES.LIST>
</VOUCHER>
</COLLECTION></DATA></BODY></ENVELOPE>"""
        res = parse_metadata_response(voucher_xml, "Voucher")
        self.assertEqual(len(res), 1)
        v = res[0]
        self.assertEqual(v["partyLedger"], "AVN Enterprises")
        lines = v["ledgerEntries"]
        party_line = next(line for line in lines if line["ledgerName"] == "AVN Enterprises")
        sales_line = next(line for line in lines if line["ledgerName"] == "Sales Account")
        self.assertTrue(party_line["isPartyLedger"], "Party line must have isPartyLedger=True")
        self.assertFalse(sales_line["isPartyLedger"], "Sales line must have isPartyLedger=False")


if __name__ == "__main__":
    unittest.main()

