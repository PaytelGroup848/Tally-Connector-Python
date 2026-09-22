"""
Unit tests for Password Hashing, Token Operations, and Login Rate Limiting
"""

import unittest
import time
from shared.auth.password import hash_password, verify_password
from shared.auth.tokens import create_access_token, verify_token, revoke_token
from shared.auth.rate_limiter import LoginRateLimiter
from shared.exceptions import AuthenticationError, AppException

class TestAuthenticationUnit(unittest.TestCase):
    def test_password_hashing(self):
        password = "SecretPassword123"
        hashed = hash_password(password)

        self.assertNotEqual(password, hashed)
        self.assertTrue(hashed.startswith("pbkdf2:sha256:100000$"))
        self.assertTrue(verify_password(password, hashed))
        self.assertFalse(verify_password("WrongPassword456", hashed))

        hashed2 = hash_password(password)
        self.assertNotEqual(hashed, hashed2)

    def test_token_lifecycle(self):
        payload = {"sub": "usr-uuid-999", "username": "admin", "role": "Admin"}
        token = create_access_token(payload)

        decoded = verify_token(token)
        self.assertEqual(decoded["sub"], "usr-uuid-999")
        self.assertEqual(decoded["username"], "admin")
        self.assertEqual(decoded["role"], "Admin")

        revoke_token(token)
        with self.assertRaises(AuthenticationError):
            verify_token(token)

    def test_rate_limiter(self):
        limiter = LoginRateLimiter()
        user_key = "test_user_brute"

        for _ in range(5):
            limiter.record_failed_attempt(user_key)

        with self.assertRaises(AppException) as ctx:
            limiter.check_rate_limit(user_key)

        self.assertEqual(ctx.exception.status_code, 429)

        limiter.clear_failed_attempts(user_key)
        limiter.check_rate_limit(user_key)

if __name__ == "__main__":
    unittest.main()
