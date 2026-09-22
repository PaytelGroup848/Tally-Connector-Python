"""
Unit tests for Tally Integration Request Builder, Response Parser, Client Validation, and Adapter
"""

import unittest
from apps.backend.adapters.tally.request_builder import build_company_list_xml, build_collection_xml, ALLOWED_METADATA_TYPES
from apps.backend.adapters.tally.response_parser import parse_company_list, parse_metadata_response, parse_tally_xml_response
from apps.backend.adapters.tally.tally_client import TallyClient
from apps.backend.adapters.tally_adapter import TallyConnectorAdapter
from shared.exceptions import ValidationError

class TestTallyIntegrationUnit(unittest.TestCase):
    def test_01_request_builder(self):
        xml_company = build_company_list_xml()
        self.assertIn("<TALLYREQUEST>EXPORT</TALLYREQUEST>", xml_company)
        self.assertIn("<TYPE>Company</TYPE>", xml_company)

        xml_ledger = build_collection_xml("Ledger", ["NAME", "PARENT"], company_name="ABC Enterprises")
        self.assertIn("<SVCURRENTCOMPANY>ABC Enterprises</SVCURRENTCOMPANY>", xml_ledger)
        self.assertIn("<TYPE>Ledger</TYPE>", xml_ledger)

    def test_02_response_parser_valid_xml(self):
        valid_comp_xml = """<ENVELOPE>
            <BODY>
                <DATA>
                    <COLLECTION>
                        <COMPANY>
                            <NAME>Acme Electronics Pvt Ltd</NAME>
                            <GUID>guid-12345</GUID>
                            <BOOKSFROM>20250401</BOOKSFROM>
                        </COMPANY>
                    </COLLECTION>
                </DATA>
            </BODY>
        </ENVELOPE>"""
        companies = parse_company_list(valid_comp_xml)
        self.assertEqual(len(companies), 1)
        self.assertEqual(companies[0]["name"], "Acme Electronics Pvt Ltd")
        self.assertEqual(companies[0]["guid"], "guid-12345")

    def test_03_response_parser_error_xml(self):
        error_xml = """<ENVELOPE>
            <HEADER><STATUS>0</STATUS></HEADER>
            <BODY><LINEERROR>Invalid TDL Collection Request</LINEERROR></BODY>
        </ENVELOPE>"""
        is_ok, root, err = parse_tally_xml_response(error_xml)
        self.assertFalse(is_ok)
        self.assertIn("Line Error", err)

    def test_04_ssrf_host_and_port_validation(self):
        client = TallyClient()
        h, p = client.validate_host_and_port("127.0.0.1", 9000)
        self.assertEqual(h, "127.0.0.1")
        self.assertEqual(p, 9000)

        with self.assertRaises(ValidationError):
            client.validate_host_and_port("http://127.0.0.1", 9000)

        with self.assertRaises(ValidationError):
            client.validate_host_and_port("127.0.0.1", 70000)

    def test_05_adapter_metadata_allow_list(self):
        adapter = TallyConnectorAdapter()
        with self.assertRaises(ValidationError):
            import asyncio
            asyncio.run(adapter.discover_metadata({"host": "127.0.0.1", "port": 9000}, "unsupported_command"))

        self.assertIn("ledgers", ALLOWED_METADATA_TYPES)

if __name__ == "__main__":
    unittest.main()
