"""
Integration tests for API Gateway Foundation (apps/backend/gateway/main.py)
Tests request correlation IDs, app info, health check, and error response schema.
"""

import unittest
from fastapi.testclient import TestClient
from apps.backend.gateway.main import app

class TestGatewayFoundation(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_app_info_endpoint(self):
        response = self.client.get("/api/app/info")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertIn("app_name", data["data"])
        self.assertIn("version", data["data"])
        self.assertIn("X-Request-ID", response.headers)

    def test_health_endpoint(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["status"], "healthy")
        self.assertIn("microservices", data["data"])

    def test_request_id_header_propagation(self):
        custom_req_id = "custom-id-9999"
        response = self.client.get("/api/app/info", headers={"X-Request-ID": custom_req_id})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("X-Request-ID"), custom_req_id)
        data = response.json()
        self.assertEqual(data["request_id"], custom_req_id)

    def test_not_found_standard_error(self):
        response = self.client.get("/api/non-existent-endpoint-xyz")
        self.assertEqual(response.status_code, 404)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertEqual(data["error"]["code"], "NOT_FOUND")
        self.assertIn("request_id", data)

if __name__ == "__main__":
    unittest.main()
