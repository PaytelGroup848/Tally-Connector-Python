"""
CtrlBooks - Integration Test Suite for Data Discovery & Metadata APIs
----------------------------------------------------------------------------------
Integration tests for /api/connectors/{id}/metadata/discover, /refresh, list, detail, and search endpoints.
"""

import unittest
import json
import uuid
from fastapi.testclient import TestClient
from apps.backend.gateway.main import app
from shared.database import initialize_database
from shared.db.session import get_db_session
from shared.db.models.connector import Connector
from shared.db.models.metadata import UnifiedSourceMetadata
from shared.db.models.user import User
from shared.auth.password import hash_password
from shared.repositories.user_repo import UserRepository, RoleRepository
from scripts.seed_rbac import seed_rbac

class TestMetadataAPIIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        initialize_database()
        seed_rbac()
        cls.client = TestClient(app)

        with get_db_session() as db:
            user_repo = UserRepository()
            role_repo = RoleRepository()
            admin_role = role_repo.get_by_code(db, "ADMIN")

            admin_user = user_repo.get_by_username(db, "meta_api_admin")
            if not admin_user:
                u = User(
                    username="meta_api_admin",
                    full_name="Meta API Admin",
                    email="metaadmin@example.com",
                    password_hash=hash_password("MetaAdminPass123!"),
                    status="ACTIVE"
                )
                created = user_repo.create(db, u)
                role_repo.assign_role_to_user(db, created.id, admin_role.id)
            else:
                admin_user.password_hash = hash_password("MetaAdminPass123!")
                admin_user.status = "ACTIVE"
                role_repo.assign_role_to_user(db, admin_user.id, admin_role.id)
            db.commit()

        login_res = cls.client.post("/api/auth/login", json={"username": "meta_api_admin", "password": "MetaAdminPass123!"})
        cls.token = login_res.json()["data"]["session"]["access_token"]
        cls.headers = {"Authorization": f"Bearer {cls.token}"}

        unique_suffix = uuid.uuid4().hex[:6]
        with get_db_session() as db:
            tally_conn = Connector(
                name=f"API Test Tally {unique_suffix}",
                connector_type="TALLY",
                configuration_status="CONFIGURED",
                connection_status="CONNECTED",
                status="ACTIVE",
                is_active=True,
                configuration_json=json.dumps({"host": "127.0.0.1", "port": 9000, "company_name": "Delhi Test Tally Comp"})
            )
            db.add_all([tally_conn])
            db.commit()
            db.refresh(tally_conn)
            cls.tally_conn_id = str(tally_conn.id)

            meta1 = UnifiedSourceMetadata(
                connector_id=cls.tally_conn_id,
                company_identifier="Delhi Test Tally Comp",
                source_type="TALLY",
                source_entity_type="Ledger",
                canonical_entity_type="LEDGER",
                source_identifier="tally-led-100",
                source_name="State Bank of India",
                display_name="State Bank of India",
                parent_display_name="Bank Accounts",
                status="ACTIVE"
            )
            db.add(meta1)
            db.commit()
            db.refresh(meta1)
            cls.meta1_id = str(meta1.id)

    def test_list_connector_metadata(self):
        res = self.client.get(f"/api/connectors/{self.tally_conn_id}/metadata", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        data = res.json().get("data", {})
        self.assertGreaterEqual(data["total_count"], 1)

    def test_get_metadata_detail(self):
        res = self.client.get(f"/api/connectors/{self.tally_conn_id}/metadata/{self.meta1_id}", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        data = res.json().get("data", {})
        self.assertEqual(data["id"], self.meta1_id)
        self.assertEqual(data["canonical_entity_type"], "LEDGER")

    def test_search_metadata(self):
        res = self.client.get("/api/metadata/search?query=State Bank", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        data = res.json().get("data", {})
        self.assertGreaterEqual(data["total_count"], 1)

    def test_discover_metadata_endpoint(self):
        payload = {"entity_types": ["LEDGER", "VOUCHER_TYPE"]}
        res = self.client.post(f"/api/connectors/{self.tally_conn_id}/metadata/discover", json=payload, headers=self.headers)
        self.assertEqual(res.status_code, 200)
        data = res.json().get("data", {})
        self.assertIn("discovery_run_id", data)
        self.assertIn(data["status"], ["SUCCESS", "PARTIAL_SUCCESS", "FAILED"])

if __name__ == "__main__":
    unittest.main()
