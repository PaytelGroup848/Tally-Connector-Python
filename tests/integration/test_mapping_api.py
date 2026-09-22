"""
CtrlBooks - Integration Test Suite for Data Mapping & Field Mapping APIs
--------------------------------------------------------------------------------------
Tests all Module 9 API endpoints: CRUD, field rules, suggestions, validation, preview, activation, deactivation, and archiving.
"""

import unittest
import uuid
from fastapi.testclient import TestClient
from apps.backend.gateway.main import app
from shared.database import initialize_database
from shared.db.session import get_db_session
from shared.db.models.connector import Connector
from shared.db.models.user import User
from shared.auth.password import hash_password
from shared.repositories.user_repo import UserRepository, RoleRepository
from scripts.seed_rbac import seed_rbac

class TestMappingAPIIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        initialize_database()
        seed_rbac()
        cls.client = TestClient(app)

        with get_db_session() as db:
            user_repo = UserRepository()
            role_repo = RoleRepository()
            admin_role = role_repo.get_by_code(db, "ADMIN")

            admin_user = user_repo.get_by_username(db, "mapping_api_admin")
            if not admin_user:
                u = User(
                    username="mapping_api_admin",
                    full_name="Mapping API Admin",
                    email="mappingadmin@example.com",
                    password_hash=hash_password("MapAdminPass123!"),
                    status="ACTIVE"
                )
                created = user_repo.create(db, u)
                role_repo.assign_role_to_user(db, created.id, admin_role.id)
            else:
                admin_user.password_hash = hash_password("MapAdminPass123!")
                admin_user.status = "ACTIVE"
                role_repo.assign_role_to_user(db, admin_user.id, admin_role.id)
            db.commit()

        login_res = cls.client.post("/api/auth/login", json={"username": "mapping_api_admin", "password": "MapAdminPass123!"})
        cls.token = login_res.json()["data"]["session"]["access_token"]
        cls.headers = {"Authorization": f"Bearer {cls.token}"}

        unique_suffix = uuid.uuid4().hex[:6]
        with get_db_session() as db:
            src_conn = Connector(
                name=f"Source Tally {unique_suffix}",
                connector_type="TALLY",
                configuration_status="CONFIGURED",
                connection_status="CONNECTED",
                is_active=True,
                configuration_json='{"company_name": "Tally Comp A"}'
            )
            tgt_conn = Connector(
                name=f"Target Tally {unique_suffix}",
                connector_type="TALLY",
                configuration_status="CONFIGURED",
                connection_status="CONNECTED",
                is_active=True,
                configuration_json='{"company_name": "Tally Comp B"}'
            )
            db.add_all([src_conn, tgt_conn])
            db.commit()
            cls.src_connector_id = src_conn.id
            cls.tgt_connector_id = tgt_conn.id

    def test_01_create_and_get_mapping(self):
        payload = {
            "name": "Integration Test Mapping",
            "source_connector_id": self.src_connector_id,
            "source_company_identifier": "Tally Comp A",
            "target_connector_id": self.tgt_connector_id,
            "target_company_identifier": "Tally Comp B",
            "canonical_entity_type": "LEDGER",
            "description": "Integration test mapping definition"
        }
        res = self.client.post("/api/mappings", json=payload, headers=self.headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()["data"]
        self.assertIn("id", data)
        self.assertEqual(data["name"], "Integration Test Mapping")
        self.assertEqual(data["status"], "DRAFT")

        mapping_id = data["id"]
        TestMappingAPIIntegration.mapping_id = mapping_id

        get_res = self.client.get(f"/api/mappings/{mapping_id}", headers=self.headers)
        self.assertEqual(get_res.status_code, 200)
        self.assertEqual(get_res.json()["data"]["id"], mapping_id)

    def test_02_field_rules_crud(self):
        mapping_id = getattr(TestMappingAPIIntegration, "mapping_id", None)
        self.assertIsNotNone(mapping_id)

        rule_payload = {
            "source_field": "LedgerName",
            "target_field": "name",
            "source_data_type": "STRING",
            "target_data_type": "STRING",
            "is_required": True,
            "transformation_type": "NONE"
        }
        add_res = self.client.post(f"/api/mappings/{mapping_id}/fields", json=rule_payload, headers=self.headers)
        self.assertEqual(add_res.status_code, 200)
        rule_data = add_res.json()["data"]
        self.assertEqual(rule_data["source_field"], "LedgerName")
        rule_id = rule_data["id"]

        list_res = self.client.get(f"/api/mappings/{mapping_id}/fields", headers=self.headers)
        self.assertEqual(list_res.status_code, 200)
        self.assertTrue(len(list_res.json()["data"]) >= 1)

        upd_res = self.client.put(f"/api/mappings/{mapping_id}/fields/{rule_id}", json={"transformation_type": "TRIM"}, headers=self.headers)
        self.assertEqual(upd_res.status_code, 200)
        self.assertEqual(upd_res.json()["data"]["transformation_type"], "TRIM")

    def test_03_field_suggestions(self):
        mapping_id = getattr(TestMappingAPIIntegration, "mapping_id", None)
        res = self.client.get(f"/api/mappings/{mapping_id}/field-suggestions", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()["data"]
        self.assertIn("suggestions", data)

    def test_04_validate_and_preview(self):
        mapping_id = getattr(TestMappingAPIIntegration, "mapping_id", None)

        val_res = self.client.post(f"/api/mappings/{mapping_id}/validate", json={}, headers=self.headers)
        self.assertEqual(val_res.status_code, 200)
        self.assertIn("status", val_res.json()["data"])

        sample_src = {"LedgerName": "  Sales Account  ", "Phone": "9876543210"}
        prev_res = self.client.post(f"/api/mappings/{mapping_id}/preview", json=sample_src, headers=self.headers)
        self.assertEqual(prev_res.status_code, 200)
        p_data = prev_res.json()["data"]
        self.assertTrue(p_data["is_preview"])
        self.assertEqual(p_data["target_preview"]["name"], "Sales Account")

    def test_05_activate_deactivate_archive(self):
        mapping_id = getattr(TestMappingAPIIntegration, "mapping_id", None)

        act_res = self.client.post(f"/api/mappings/{mapping_id}/activate", json={}, headers=self.headers)
        self.assertEqual(act_res.status_code, 200)
        self.assertEqual(act_res.json()["data"]["status"], "ACTIVE")

        deact_res = self.client.post(f"/api/mappings/{mapping_id}/deactivate", json={}, headers=self.headers)
        self.assertEqual(deact_res.status_code, 200)
        self.assertEqual(deact_res.json()["data"]["status"], "INACTIVE")

        arch_res = self.client.delete(f"/api/mappings/{mapping_id}", headers=self.headers)
        self.assertEqual(arch_res.status_code, 200)
        self.assertEqual(arch_res.json()["data"]["status"], "ARCHIVED")

if __name__ == "__main__":
    unittest.main()
