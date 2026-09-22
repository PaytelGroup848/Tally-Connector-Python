"""
Integration tests for User & Role Management API Endpoints (/api/users, /api/roles, /api/permissions)
"""

import unittest
from fastapi.testclient import TestClient
from apps.backend.gateway.main import app
from shared.database import initialize_database
from shared.db.session import get_db_session
from shared.db.models.user import User, Role
from shared.auth.password import hash_password
from shared.repositories.user_repo import UserRepository, RoleRepository
from scripts.seed_rbac import seed_rbac

class TestUserRoleAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        initialize_database()
        seed_rbac()
        cls.client = TestClient(app)

        with get_db_session() as db:
            user_repo = UserRepository()
            role_repo = RoleRepository()
            admin_role = role_repo.get_by_code(db, "ADMIN")

            admin_user = user_repo.get_by_username(db, "api_admin")
            if not admin_user:
                u = User(
                    username="api_admin",
                    full_name="API Admin",
                    email="apiadmin@example.com",
                    password_hash=hash_password("ApiAdminPass123!"),
                    status="ACTIVE"
                )
                created = user_repo.create(db, u)
                role_repo.assign_role_to_user(db, created.id, admin_role.id)
            else:
                admin_user.password_hash = hash_password("ApiAdminPass123!")
                admin_user.status = "ACTIVE"
                role_repo.assign_role_to_user(db, admin_user.id, admin_role.id)
            db.commit()

        login_res = cls.client.post("/api/auth/login", json={"username": "api_admin", "password": "ApiAdminPass123!"})
        cls.token = login_res.json()["data"]["session"]["access_token"]
        cls.headers = {"Authorization": f"Bearer {cls.token}"}

    def test_01_list_users(self):
        res = self.client.get("/api/users?page=1&page_size=10", headers=self.headers)
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body["success"])
        self.assertIn("items", body["data"])
        self.assertIn("pagination", body["data"])

    def test_02_create_user(self):
        with get_db_session() as db:
            user_repo = UserRepository()
            existing = user_repo.get_by_username(db, "api_new_user")
            if existing:
                user_repo.delete(db, existing.id, hard=True)
                db.commit()

        payload = {
            "username": "api_new_user",
            "full_name": "API New User",
            "password": "NewUserPass123!",
            "role": "OPERATOR",
            "email": "newuser@example.com"
        }
        res = self.client.post("/api/users", json=payload, headers=self.headers)
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["data"]["username"], "api_new_user")
        self.assertNotIn("password", body["data"])
        self.assertNotIn("password_hash", body["data"])

    def test_03_reset_password(self):
        users_res = self.client.get("/api/users?search=api_new_user", headers=self.headers)
        user_id = users_res.json()["data"]["items"][0]["id"]

        reset_res = self.client.post(f"/api/users/{user_id}/reset-password", json={"new_password": "ResetPass123!"}, headers=self.headers)
        self.assertEqual(reset_res.status_code, 200)
        self.assertTrue(reset_res.json()["data"]["password_reset"])

    def test_04_list_roles_and_permissions(self):
        roles_res = self.client.get("/api/roles", headers=self.headers)
        self.assertEqual(roles_res.status_code, 200)
        self.assertTrue(roles_res.json()["success"])

        perms_res = self.client.get("/api/permissions", headers=self.headers)
        self.assertEqual(perms_res.status_code, 200)
        self.assertTrue(perms_res.json()["success"])

    def test_05_create_and_delete_custom_role(self):
        payload = {
            "name": "Audit Manager",
            "code": "AUDIT_MANAGER",
            "description": "Custom audit manager role",
            "permissions": ["logs.view", "users.view"]
        }
        create_res = self.client.post("/api/roles", json=payload, headers=self.headers)
        self.assertEqual(create_res.status_code, 200)
        role_id = create_res.json()["data"]["id"]

        delete_res = self.client.delete(f"/api/roles/{role_id}", headers=self.headers)
        self.assertEqual(delete_res.status_code, 200)
        self.assertTrue(delete_res.json()["data"]["deleted"])

    def test_06_unauthenticated_request_rejected(self):
        res = self.client.get("/api/users")
        self.assertEqual(res.status_code, 401)

if __name__ == "__main__":
    unittest.main()
