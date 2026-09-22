"""
CtrlBooks - Website REST API & Record Persistence Integration Tests
---------------------------------------------------------------------------------
Verifies persistent record database storage, query operations, company summary aggregation,
high-level dashboard stats, and external website REST API endpoints (/api/v1/website/*).
"""

import unittest
import json
import uuid
import tempfile
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

from apps.backend.gateway.main import app
from shared.database import initialize_database
from shared.db.session import get_db_session
from shared.db.models.user import User, Role
from shared.db.models.connector import Connector
from shared.repositories.user_repo import UserRepository, RoleRepository
from shared.repositories.connector_repo import ConnectorRepository, DataSourceRepository, DestinationRepository
from shared.repositories.storage_repo import extracted_record_repository
from shared.auth.password import hash_password

client = TestClient(app)

class TestWebsiteAPIIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with get_db_session() as db:
            user_repo = UserRepository()
            role_repo = RoleRepository()

            admin_role = role_repo.get_by_name(db, "ADMIN")
            if not admin_role:
                admin_role = role_repo.create(db, Role(name="ADMIN", description="Admin"))

            admin_user = user_repo.get_by_username(db, "website_api_admin")
            if not admin_user:
                u = User(
                    username="website_api_admin",
                    full_name="Website API Admin",
                    email="websiteadmin@example.com",
                    password_hash=hash_password("WebsiteAdminPass123!"),
                    status="ACTIVE"
                )
                created = user_repo.create(db, u)
                role_repo.assign_role_to_user(db, created.id, admin_role.id)
            else:
                admin_user.password_hash = hash_password("WebsiteAdminPass123!")
                admin_user.status = "ACTIVE"
                role_repo.assign_role_to_user(db, admin_user.id, admin_role.id)
            db.commit()

        login_res = client.post("/api/auth/login", json={"username": "website_api_admin", "password": "WebsiteAdminPass123!"})
        cls.token = login_res.json()["data"]["session"]["access_token"]
        cls.headers = {"Authorization": f"Bearer {cls.token}"}

    def test_01_upsert_and_query_stored_records(self):
        with get_db_session() as db:
            conn_repo = ConnectorRepository()
            ds_repo = DataSourceRepository()
            dest_repo = DestinationRepository()

            src = ds_repo.create_source(db, name=f"Website Test Source {uuid.uuid4().hex[:6]}", source_type="TALLY", config={})
            dest = dest_repo.create_destination(db, name=f"Website Test Dest {uuid.uuid4().hex[:6]}", destination_type="REST_API", config={})
            conn = conn_repo.create(db, Connector(
                name=f"Website Test Connector {uuid.uuid4().hex[:6]}",
                connector_type="TALLY",
                source_id=src.id,
                destination_id=dest.id,
                configuration_json='{"host": "127.0.0.1", "port": 9000}',
                is_active=True,
                connection_status="CONNECTED",
                status="ACTIVE"
            ))

            records = [
                {"record_id": "rec-cash", "name": "Main Cash Ledger", "data": {"name": "Main Cash Ledger", "balance": 50000}},
                {"record_id": "rec-bank", "name": "SBI Bank Account", "data": {"name": "SBI Bank Account", "balance": 120000}}
            ]
            inserted, updated = extracted_record_repository.upsert_batch(
                db=db,
                connector_id=conn.id,
                company_identifier="Demo Website Company",
                entity_type="LEDGER",
                records=records
            )
            self.assertEqual(inserted, 2)

        comp_res = client.get("/api/v1/website/companies")
        self.assertEqual(comp_res.status_code, 200)
        self.assertTrue(comp_res.json()["success"])
        comps = comp_res.json()["data"]["companies"]
        self.assertGreater(len(comps), 0)

        stat_res = client.get("/api/v1/website/dashboard/summary")
        self.assertEqual(stat_res.status_code, 200)
        self.assertTrue(stat_res.json()["success"])
        stats = stat_res.json()["data"]
        self.assertGreater(stats["total_records"], 0)
        self.assertGreater(stats["total_ledgers"], 0)

        entity_res = client.get("/api/v1/website/entities/LEDGER?page=1&page_size=10")
        self.assertEqual(entity_res.status_code, 200)
        items = entity_res.json()["data"]["items"]
        self.assertGreater(len(items), 0)

        search_res = client.get("/api/v1/website/entities/LEDGER?search=Cash")
        self.assertEqual(search_res.status_code, 200)
        s_items = search_res.json()["data"]["items"]
        self.assertGreaterEqual(len(s_items), 1)
        self.assertIn("Cash", s_items[0]["record_name"])

        target_id = items[0]["id"]
        detail_res = client.get(f"/api/v1/website/records/{target_id}")
        self.assertEqual(detail_res.status_code, 200)
        self.assertEqual(detail_res.json()["data"]["id"], target_id)

    def test_02_website_dashboard_html_view(self):
        res = client.get("/website")
        self.assertEqual(res.status_code, 200)
        self.assertIn("text/html", res.headers["content-type"])
        self.assertIn("CtrlBooks Web Connector Portal", res.text)

if __name__ == "__main__":
    unittest.main()
