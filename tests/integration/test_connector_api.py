"""
Integration tests for Connector Management API endpoints (/api/connectors) under RBAC authorization
"""

import unittest
from fastapi.testclient import TestClient
from apps.backend.gateway.main import app
from shared.database import initialize_database
from shared.db.session import get_db_session
from shared.db.models.user import User
from shared.auth.password import hash_password
from shared.repositories.user_repo import UserRepository, RoleRepository
from shared.repositories.connector_repo import ConnectorRepository
from scripts.seed_rbac import seed_rbac

class TestConnectorAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        initialize_database()
        seed_rbac()
        cls.client = TestClient(app)

        with get_db_session() as db:
            user_repo = UserRepository()
            role_repo = RoleRepository()
            admin_role = role_repo.get_by_code(db, "ADMIN")

            admin_user = user_repo.get_by_username(db, "conn_api_admin")
            if not admin_user:
                u = User(
                    username="conn_api_admin",
                    full_name="Conn API Admin",
                    email="connadmin@example.com",
                    password_hash=hash_password("ConnAdminPass123!"),
                    status="ACTIVE"
                )
                created = user_repo.create(db, u)
                role_repo.assign_role_to_user(db, created.id, admin_role.id)
            else:
                admin_user.password_hash = hash_password("ConnAdminPass123!")
                admin_user.status = "ACTIVE"
                role_repo.assign_role_to_user(db, admin_user.id, admin_role.id)
            db.commit()

        login_res = cls.client.post("/api/auth/login", json={"username": "conn_api_admin", "password": "ConnAdminPass123!"})
        cls.token = login_res.json()["data"]["session"]["access_token"]
        cls.headers = {"Authorization": f"Bearer {cls.token}"}

    def setUp(self):
        with get_db_session() as db:
            repo = ConnectorRepository()
            for name in ["API Tally Pipeline"]:
                c = repo.get_by_name(db, name)
                if c:
                    repo.delete(db, c.id, hard=True)
            db.commit()

    def test_01_list_connectors(self):
        res = self.client.get("/api/connectors?page=1&page_size=10", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body["success"])
        self.assertIn("items", body["data"])
        self.assertIn("pagination", body["data"])

    def test_02_create_connector(self):
        payload = {
            "name": "API Tally Pipeline",
            "connector_type": "TALLY",
            "description": "Integration test Tally connector",
            "configuration": {
                "host": "127.0.0.1",
                "port": 9000,
                "connection_mode": "HTTP_XML"
            }
        }
        res = self.client.post("/api/connectors", json=payload, headers=self.headers)
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["data"]["name"], "API Tally Pipeline")
        self.assertEqual(body["data"]["connector_type"], "TALLY")
        self.assertEqual(body["data"]["configuration_status"], "CONFIGURED")
        self.assertEqual(body["data"]["connection_status"], "UNKNOWN")

    def test_03_get_single_connector(self):
        payload = {
            "name": "API Tally Pipeline",
            "connector_type": "TALLY",
            "configuration": {
                "host": "127.0.0.1",
                "port": 9000,
                "connection_mode": "HTTP_XML"
            }
        }
        create_res = self.client.post("/api/connectors", json=payload, headers=self.headers)
        cid = create_res.json()["data"]["id"]

        get_res = self.client.get(f"/api/connectors/{cid}", headers=self.headers)
        self.assertEqual(get_res.status_code, 200)
        body = get_res.json()
        self.assertEqual(body["data"]["id"], cid)
        self.assertEqual(body["data"]["name"], "API Tally Pipeline")

    def test_04_activate_and_deactivate(self):
        create_res = self.client.post("/api/connectors", json={
            "name": "API Tally Pipeline",
            "connector_type": "TALLY",
            "configuration": {"host": "127.0.0.1", "port": 9000}
        }, headers=self.headers)
        cid = create_res.json()["data"]["id"]

        act_res = self.client.post(f"/api/connectors/{cid}/activate", headers=self.headers)
        self.assertEqual(act_res.status_code, 200)
        self.assertTrue(act_res.json()["data"]["is_active"])

        deact_res = self.client.post(f"/api/connectors/{cid}/deactivate", headers=self.headers)
        self.assertEqual(deact_res.status_code, 200)
        self.assertFalse(deact_res.json()["data"]["is_active"])

    def test_05_test_connection_endpoint(self):
        create_res = self.client.post("/api/connectors", json={
            "name": "API Tally Pipeline",
            "connector_type": "TALLY",
            "configuration": {"host": "127.0.0.1", "port": 9000}
        }, headers=self.headers)
        cid = create_res.json()["data"]["id"]

        test_res = self.client.post(f"/api/connectors/{cid}/test", headers=self.headers)
        self.assertEqual(test_res.status_code, 200)
        body = test_res.json()
        self.assertIn("status", body["data"])
        self.assertIn(body["data"]["status"], ["CONNECTED", "FAILED"])

    def test_06_delete_connector(self):
        create_res = self.client.post("/api/connectors", json={
            "name": "API Tally Pipeline",
            "connector_type": "TALLY",
            "configuration": {"host": "127.0.0.1", "port": 9000}
        }, headers=self.headers)
        cid = create_res.json()["data"]["id"]

        del_res = self.client.delete(f"/api/connectors/{cid}", headers=self.headers)
        self.assertEqual(del_res.status_code, 200)
        self.assertTrue(del_res.json()["data"]["deleted"])

    def test_07_unauthenticated_request_rejected(self):
        res = self.client.get("/api/connectors")
        self.assertEqual(res.status_code, 401)

if __name__ == "__main__":
    unittest.main()
