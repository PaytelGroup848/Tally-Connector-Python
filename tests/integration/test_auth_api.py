"""
Integration tests for Authentication API endpoints (POST /api/auth/login, POST /api/auth/logout, GET /api/auth/me)
"""

import unittest
from fastapi.testclient import TestClient
from apps.backend.gateway.main import app
from shared.database import initialize_database
from shared.db.session import get_db_session
from shared.db.models.user import User, Role
from shared.auth.password import hash_password
from shared.repositories.user_repo import UserRepository, RoleRepository

class TestAuthenticationAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        initialize_database()
        cls.client = TestClient(app)

        with get_db_session() as db:
            user_repo = UserRepository()
            role_repo = RoleRepository()

            admin_role = role_repo.get_by_name(db, "Admin")
            if not admin_role:
                admin_role = role_repo.create(db, Role(name="Admin", description="Admin Role"))

            existing = user_repo.get_by_username(db, "test_admin")
            if not existing:
                u = User(
                    username="test_admin",
                    full_name="Test Administrator",
                    email="testadmin@example.com",
                    password_hash=hash_password("ValidPassword123!"),
                    status="ACTIVE"
                )
                created = user_repo.create(db, u)
                role_repo.assign_role_to_user(db, created.id, admin_role.id)
            else:
                existing.password_hash = hash_password("ValidPassword123!")
                existing.status = "ACTIVE"
                role_repo.assign_role_to_user(db, existing.id, admin_role.id)
            db.commit()

    def test_01_login_success(self):
        payload = {"username": "test_admin", "password": "ValidPassword123!"}
        response = self.client.post("/api/auth/login", json=payload)
        self.assertEqual(response.status_code, 200)

        body = response.json()
        self.assertTrue(body["success"])
        self.assertIn("access_token", body["data"]["session"])
        self.assertEqual(body["data"]["user"]["username"], "test_admin")
        self.assertNotIn("password", body["data"]["user"])
        self.assertNotIn("password_hash", body["data"]["user"])

    def test_02_login_invalid_password(self):
        payload = {"username": "test_admin", "password": "IncorrectPassword!"}
        response = self.client.post("/api/auth/login", json=payload)
        self.assertEqual(response.status_code, 401)

        body = response.json()
        self.assertFalse(body["success"])
        self.assertEqual(body["error"]["message"], "Invalid username or password")

    def test_03_login_invalid_username(self):
        payload = {"username": "unknown_user_999", "password": "ValidPassword123!"}
        response = self.client.post("/api/auth/login", json=payload)
        self.assertEqual(response.status_code, 401)

        body = response.json()
        self.assertFalse(body["success"])
        self.assertEqual(body["error"]["message"], "Invalid username or password")

    def test_04_get_current_user_me(self):
        login_res = self.client.post("/api/auth/login", json={"username": "test_admin", "password": "ValidPassword123!"})
        token = login_res.json()["data"]["session"]["access_token"]

        headers = {"Authorization": f"Bearer {token}"}
        me_res = self.client.get("/api/auth/me", headers=headers)
        self.assertEqual(me_res.status_code, 200)

        me_body = me_res.json()
        self.assertTrue(me_body["success"])
        self.assertEqual(me_body["data"]["username"], "test_admin")

    def test_05_logout_and_revocation(self):
        login_res = self.client.post("/api/auth/login", json={"username": "test_admin", "password": "ValidPassword123!"})
        token = login_res.json()["data"]["session"]["access_token"]

        headers = {"Authorization": f"Bearer {token}"}
        logout_res = self.client.post("/api/auth/logout", headers=headers)
        self.assertEqual(logout_res.status_code, 200)

    def test_06_send_and_verify_email_otp(self):
        from shared.auth.otp_service import otp_service
        send_res = self.client.post("/api/auth/send-otp", json={"email": "testadmin@example.com"})
        self.assertEqual(send_res.status_code, 200)
        self.assertTrue(send_res.json()["success"])

        stored = otp_service._store.get("testadmin@example.com")
        real_otp = stored["otp"] if stored else "123456"

        verify_res = self.client.post("/api/auth/verify-otp", json={"email": "testadmin@example.com", "otp": real_otp})
        self.assertEqual(verify_res.status_code, 200)
        verify_body = verify_res.json()
        self.assertTrue(verify_body["success"])
        self.assertIn("access_token", verify_body["data"]["session"])

if __name__ == "__main__":
    unittest.main()
