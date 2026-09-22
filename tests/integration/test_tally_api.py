"""
Integration tests for Tally Integration API Endpoints (/api/connectors/{id}/tally/*) under RBAC authorization
"""

import unittest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from apps.backend.gateway.main import app
from shared.database import initialize_database
from shared.db.session import get_db_session
from shared.db.models.user import User
from shared.auth.password import hash_password
from shared.repositories.user_repo import UserRepository, RoleRepository
from shared.repositories.connector_repo import ConnectorRepository
from scripts.seed_rbac import seed_rbac

class TestTallyAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        initialize_database()
        seed_rbac()
        cls.client = TestClient(app)

        with get_db_session() as db:
            user_repo = UserRepository()
            role_repo = RoleRepository()
            admin_role = role_repo.get_by_code(db, "ADMIN")

            admin_user = user_repo.get_by_username(db, "tally_api_admin")
            if not admin_user:
                u = User(
                    username="tally_api_admin",
                    full_name="Tally API Admin",
                    email="tallyadmin@example.com",
                    password_hash=hash_password("TallyAdminPass123!"),
                    status="ACTIVE"
                )
                created = user_repo.create(db, u)
                role_repo.assign_role_to_user(db, created.id, admin_role.id)
            else:
                admin_user.password_hash = hash_password("TallyAdminPass123!")
                admin_user.status = "ACTIVE"
                role_repo.assign_role_to_user(db, admin_user.id, admin_role.id)
            db.commit()

        login_res = cls.client.post("/api/auth/login", json={"username": "tally_api_admin", "password": "TallyAdminPass123!"})
        cls.token = login_res.json()["data"]["session"]["access_token"]
        cls.headers = {"Authorization": f"Bearer {cls.token}"}

    def setUp(self):
        with get_db_session() as db:
            repo = ConnectorRepository()
            c = repo.get_by_name(db, "Tally Integration Pipeline")
            if c:
                repo.delete(db, c.id, hard=True)
            db.commit()

        res = self.client.post("/api/connectors", json={
            "name": "Tally Integration Pipeline",
            "connector_type": "TALLY",
            "configuration": {"host": "127.0.0.1", "port": 9000}
        }, headers=self.headers)
        self.cid = res.json()["data"]["id"]

    @patch("apps.backend.adapters.tally_adapter.TallyConnectorAdapter.discover_companies", new_callable=AsyncMock)
    def test_01_get_tally_companies(self, mock_discover):
        mock_discover.return_value = [{"name": "Mock Tally Enterprise", "guid": "guid-999", "books_from": "20250401", "status": "OPEN"}]
        res = self.client.get(f"/api/connectors/{self.cid}/tally/companies", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body["success"])
        self.assertEqual(len(body["data"]["companies"]), 1)
        self.assertEqual(body["data"]["companies"][0]["name"], "Mock Tally Enterprise")

    @patch("apps.backend.adapters.tally_adapter.TallyConnectorAdapter.discover_companies", new_callable=AsyncMock)
    def test_02_select_tally_company(self, mock_discover):
        mock_discover.return_value = [{"name": "Mock Tally Enterprise", "guid": "guid-999", "books_from": "20250401", "status": "OPEN"}]
        res = self.client.post(f"/api/connectors/{self.cid}/tally/company", json={"company_name": "Mock Tally Enterprise"}, headers=self.headers)
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["data"]["selected_company"], "Mock Tally Enterprise")

    @patch("apps.backend.adapters.tally_adapter.TallyConnectorAdapter.discover_metadata", new_callable=AsyncMock)
    def test_03_get_tally_metadata(self, mock_discover):
        mock_discover.return_value = [{"name": "Cash Account", "parent": "Cash-in-Hand", "guid": "g-1"}]
        res = self.client.get(f"/api/connectors/{self.cid}/tally/metadata?type=ledgers", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["data"]["metadata_type"], "ledgers")
        self.assertEqual(len(body["data"]["items"]), 1)

    def test_04_unsupported_metadata_type_rejected(self):
        res = self.client.get(f"/api/connectors/{self.cid}/tally/metadata?type=unsupported_cmd", headers=self.headers)
        self.assertEqual(res.status_code, 400)
        self.assertIn("Unsupported metadata type", res.json()["error"]["message"])

    def test_05_unauthenticated_request_rejected(self):
        res = self.client.get(f"/api/connectors/{self.cid}/tally/companies")
        self.assertEqual(res.status_code, 401)

if __name__ == "__main__":
    unittest.main()
