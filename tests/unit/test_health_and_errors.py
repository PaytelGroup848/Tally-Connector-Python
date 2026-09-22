"""
Unit tests for Health Check & Error Handling (shared/health.py & shared/exceptions.py)
"""

import unittest
from shared.health import get_system_health, get_app_info
from shared.exceptions import AppException, ValidationError, NotFoundException, create_error_payload
from shared.response import success_response, error_response

class TestHealthAndErrors(unittest.TestCase):
    def test_health_check_payload(self):
        res = get_system_health("req-123")
        self.assertTrue(res["success"])
        self.assertEqual(res["request_id"], "req-123")
        self.assertIn("status", res["data"])
        self.assertIn("components", res["data"])
        self.assertEqual(res["data"]["components"]["application"], "healthy")
        self.assertEqual(res["data"]["components"]["logging"], "healthy")

    def test_app_info_payload(self):
        res = get_app_info("req-456")
        self.assertTrue(res["success"])
        self.assertEqual(res["request_id"], "req-456")
        self.assertIn("app_name", res["data"])
        self.assertIn("version", res["data"])
        self.assertIn("config", res["data"])

    def test_domain_exceptions(self):
        exc = ValidationError("Bad payload details")
        self.assertEqual(exc.status_code, 400)
        self.assertEqual(exc.error_code, "VALIDATION_ERROR")

        not_found = NotFoundException("Item missing")
        self.assertEqual(not_found.status_code, 404)
        self.assertEqual(not_found.error_code, "NOT_FOUND")

    def test_standard_response_helpers(self):
        s_res = success_response(data={"id": 1}, message="Done", request_id="r1")
        self.assertTrue(s_res["success"])
        self.assertEqual(s_res["data"], {"id": 1})
        self.assertEqual(s_res["request_id"], "r1")

        e_res = error_response(code="VALIDATION_ERROR", message="Invalid", request_id="r2")
        self.assertFalse(e_res["success"])
        self.assertEqual(e_res["error"]["code"], "VALIDATION_ERROR")
        self.assertEqual(e_res["request_id"], "r2")

if __name__ == "__main__":
    unittest.main()
