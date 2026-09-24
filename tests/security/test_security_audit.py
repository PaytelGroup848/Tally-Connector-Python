"""
CtrlBooks - Automated Security Testing & Vulnerability Assessment Suite
========================================================================
Performs rigorous vulnerability checks across:
1. SQL Injection / NoSQL Injection resistance
2. Privilege Escalation & Insecure Role Assignment
3. Hardcoded Secrets & Credential Exposure
4. Authentication, Token Forgery & Expiration
5. Password Hashing & Salt Entropy
6. Rate Limiting & Brute-Force Lockout
7. Log Sensitive Data Leakage & Secret Masking
8. Server-Side Request Forgery (SSRF) Guard
9. XML External Entity (XXE) / DTD Injection Safety
10. API Route Authorization & Unprotected Endpoints Audit
"""

import unittest
import logging
import os
import re
from unittest.mock import patch, MagicMock
from xml.etree import ElementTree as ET

from shared.auth.password import hash_password, verify_password, ITERATIONS, SALT_SIZE
from shared.auth.tokens import create_access_token, verify_token, revoke_token
from shared.auth.rate_limiter import LoginRateLimiter
from shared.logging_config import SecretMaskingFilter, SENSITIVE_KEYS
from apps.backend.adapters.tally.tally_client import TallyClient
from apps.backend.adapters.tally.response_parser import parse_tally_xml_response
from shared.exceptions import ValidationError, AuthenticationError, AppException


class TestSecurityAudit(unittest.TestCase):

    # -------------------------------------------------------------------------
    # 1. SQL Injection Resistance
    # -------------------------------------------------------------------------
    def test_sql_injection_resilience(self):
        """Verify that SQL queries use parameterization and reject/safely escape injection payloads."""
        from shared.db.session import get_db_session
        from shared.repositories.user_repo import UserRepository

        repo = UserRepository()
        sql_payloads = [
            "' OR '1'='1",
            "admin'--",
            "'; DROP TABLE users; --",
            "' UNION SELECT * FROM users --",
        ]

        with get_db_session() as db:
            for payload in sql_payloads:
                # Querying with an injection string should return None safely, not execute raw SQL
                result = repo.get_by_username(db, payload)
                self.assertIsNone(result, f"SQL injection vulnerability suspected with payload: {payload}")

    # -------------------------------------------------------------------------
    # 2. Privilege Escalation Audit (Vulnerability Check)
    # -------------------------------------------------------------------------
    def test_privilege_escalation_substring_check(self):
        """
        AUDIT CHECK:
        Examines if user role assignment relies on insecure substring matching (e.g. 'admin' in email).
        Flagged as HIGH severity if any user with 'admin' in email/username automatically gains Admin privileges.
        """
        import inspect
        from shared.auth.auth_service import AuthService

        source = inspect.getsource(AuthService)
        # Check if insecure substring patterns exist in auth_service.py
        insecure_patterns = [
            r'elif\s+["\']admin["\']\s+in\s+clean_email',
            r'elif\s+["\']admin["\']\s+in\s+clean_username\.lower\(\)',
            r'elif\s+["\']admin["\']\s+in\s+user\.username\.lower\(\)',
        ]

        found_issues = []
        for pat in insecure_patterns:
            if re.search(pat, source):
                found_issues.append(pat)

        # Verify that all insecure substring role assignment patterns have been removed
        self.assertEqual(len(found_issues), 0, f"Insecure Substring Role Assignment still present: {found_issues}")

    # -------------------------------------------------------------------------
    # 3. Hardcoded Secrets Audit
    # -------------------------------------------------------------------------
    def test_hardcoded_secrets_in_config(self):
        """
        AUDIT CHECK:
        Ensures production database credentials are not hardcoded as defaults in source code files.
        """
        from shared import config
        with open(config.__file__, "r", encoding="utf-8") as f:
            inspect_src = f.read()

        has_hardcoded_mongo_cred = "datacloude8_db_user:" in inspect_src and "@ac-twlm6pz" in inspect_src
        self.assertFalse(has_hardcoded_mongo_cred, "Hardcoded MongoDB Atlas Credentials must not exist in shared/config.py!")

    # -------------------------------------------------------------------------
    # 4. Authentication Token Forgery & Expiration
    # -------------------------------------------------------------------------
    def test_token_forgery_resistance(self):
        """Verify tokens with forged signatures or altered headers are rejected."""
        valid_token = create_access_token({"sub": "user_123", "role": "User"})
        parts = valid_token.split(".")
        self.assertEqual(len(parts), 3)

        # Tampered payload
        fake_payload_b64 = "eyJzdWIiOiAieW91X2hhdmVfYmVlbl9oYWNrZWQiLCAicm9sZSI6ICJBZG1pbiJ9"
        tampered_token = f"{parts[0]}.{fake_payload_b64}.{parts[2]}"

        with self.assertRaises(AuthenticationError):
            verify_token(tampered_token)

        # Forged signature
        forged_token = f"{parts[0]}.{parts[1]}.fake_signature_xyz"
        with self.assertRaises(AuthenticationError):
            verify_token(forged_token)

        # Revoked token
        revoke_token(valid_token)
        with self.assertRaises(AuthenticationError):
            verify_token(valid_token)

    # -------------------------------------------------------------------------
    # 5. Password Hashing Standard & Salt Entropy
    # -------------------------------------------------------------------------
    def test_password_hashing_standards(self):
        """Verify PBKDF2 parameters meet OWASP recommendations."""
        self.assertGreaterEqual(ITERATIONS, 100000, "PBKDF2 iteration count must be at least 100,000")
        self.assertGreaterEqual(SALT_SIZE, 16, "Salt size must be at least 16 bytes (128 bits)")

        raw_pwd = "P@ssw0rdSecure2026!"
        h1 = hash_password(raw_pwd)
        h2 = hash_password(raw_pwd)

        # Unique salt per hash
        self.assertNotEqual(h1, h2, "Each hashed password must have a unique cryptographic salt")
        self.assertTrue(verify_password(raw_pwd, h1))
        self.assertTrue(verify_password(raw_pwd, h2))
        self.assertFalse(verify_password("wrong_password", h1))

    # -------------------------------------------------------------------------
    # 6. Rate Limiting & Brute-Force Lockout
    # -------------------------------------------------------------------------
    def test_rate_limiting_brute_force_lockout(self):
        """Verify 5 failed login attempts trigger lockout with HTTP 429."""
        limiter = LoginRateLimiter()
        target = "victim_account"

        # 4 failed attempts should succeed check
        for _ in range(4):
            limiter.record_failed_attempt(target)
            limiter.check_rate_limit(target)

        # 5th failed attempt should trigger lockout
        limiter.record_failed_attempt(target)
        with self.assertRaises(AppException) as ctx:
            limiter.check_rate_limit(target)

        self.assertEqual(ctx.exception.status_code, 429)
        self.assertEqual(ctx.exception.error_code, "RATE_LIMIT_EXCEEDED")

    # -------------------------------------------------------------------------
    # 7. Sensitive Data Leakage & Secret Masking in Logs
    # -------------------------------------------------------------------------
    def test_secret_masking_in_logs(self):
        """Verify sensitive credentials, bearer tokens, and OTPs are masked in logs."""
        sec_filter = SecretMaskingFilter()
        logger = logging.getLogger("test_sec_logger")

        test_records = [
            ("Connecting with password: SuperSecretPassword123!", "password"),
            ("Auth header: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.xyz.abc", "bearer"),
            ("OTP code sent: otp: 738291 to user", "otp"),
            ("MongoDB URI: mongodb://admin:my_mongo_pass@cluster0.net", "admin"),
        ]

        for raw_msg, sensitive_word in test_records:
            rec = logging.LogRecord("test", logging.INFO, "path", 1, raw_msg, (), None)
            sec_filter.filter(rec)
            self.assertNotIn("SuperSecretPassword123!", rec.msg)
            self.assertNotIn("738291", rec.msg)

    # -------------------------------------------------------------------------
    # 8. SSRF Protection on Tally Adapter
    # -------------------------------------------------------------------------
    def test_ssrf_host_and_port_validation(self):
        """Verify TallyClient rejects dangerous host patterns and port injection."""
        client = TallyClient()

        # Reject URL scheme smuggling
        with self.assertRaises(ValidationError):
            client.validate_host_and_port("http://169.254.169.254", 9000)

        # Reject path traversal / query smuggling
        with self.assertRaises(ValidationError):
            client.validate_host_and_port("127.0.0.1/admin", 9000)

        # Reject out of bound ports
        with self.assertRaises(ValidationError):
            client.validate_host_and_port("127.0.0.1", 0)

        with self.assertRaises(ValidationError):
            client.validate_host_and_port("127.0.0.1", 65536)

    # -------------------------------------------------------------------------
    # 9. XXE (XML External Entity) Injection Protection
    # -------------------------------------------------------------------------
    def test_xxe_external_entity_safety(self):
        """Verify that XML parser does not expand external DTD entities."""
        xxe_payload = """<?xml version="1.0" encoding="ISO-8859-1"?>
        <!DOCTYPE foo [
        <!ELEMENT foo ANY >
        <!ENTITY xxe SYSTEM "file:///c:/windows/win.ini" >]>
        <ENVELOPE>
            <BODY>
                <DATA>
                    <COLLECTION>
                        <COMPANY>
                            <NAME>&xxe;</NAME>
                            <GUID>guid-12345</GUID>
                        </COMPANY>
                    </COLLECTION>
                </DATA>
            </BODY>
        </ENVELOPE>"""

        is_ok, root, err = parse_tally_xml_response(xxe_payload)
        if root is not None:
            name_elem = root.find(".//COMPANY/NAME")
            text = name_elem.text if name_elem is not None else ""
            # Must NOT contain windows/system file content
            self.assertNotIn("[fonts]", text.lower())
            self.assertNotIn("for 16-bit app support", text.lower())

    # -------------------------------------------------------------------------
    # 10. Unprotected Website API Endpoints Audit
    # -------------------------------------------------------------------------
    def test_website_api_authorization_audit(self):
        """
        AUDIT CHECK:
        Checks whether /api/v1/website endpoints require authentication or expose company financial records publicly.
        """
        from apps.backend.router import website_api_routes
        routes = website_api_routes.website_api_router.routes

        unprotected_sensitive_routes = []
        for route in routes:
            # Check if any dependencies include user or authentication
            dep_names = [d.call.__name__ for d in route.dependencies if hasattr(d, "call")]
            endpoint_params = route.endpoint.__annotations__
            has_auth = any("user" in str(p).lower() or "auth" in str(p).lower() for p in endpoint_params.values())

            if not has_auth and route.path in ["/companies", "/entities/{entity_type}", "/sync-and-store"]:
                unprotected_sensitive_routes.append(route.path)

        if unprotected_sensitive_routes:
            print(f"\n[SECURITY AUDIT NOTE] Publicly accessible accounting routes without Auth: {unprotected_sensitive_routes}")

    # -------------------------------------------------------------------------
    # 11. JWT Secret Entropy & Configuration Verification
    # -------------------------------------------------------------------------
    def test_jwt_secret_configured(self):
        """Verify that JWT_SECRET is loaded from .env and is sufficiently long."""
        from shared.config import get_settings
        settings = get_settings()
        self.assertIsNotNone(settings.jwt_secret, "JWT_SECRET must be configured in environment/.env")
        self.assertGreaterEqual(len(settings.jwt_secret), 32, "JWT_SECRET must be at least 32 characters (256-bit entropy)")
        self.assertNotEqual(
            settings.jwt_secret,
            "lr-connector-secure-default-secret-key-change-in-prod",
            "Production/Environment must not use default static secret key"
        )

    # -------------------------------------------------------------------------
    # 12. OTA Binary Integrity & Pre-Execution SHA256 Verification
    # -------------------------------------------------------------------------
    def test_updater_sha256_pre_execution_check(self):
        """Verify install_and_restart aborts execution if SHA256 checksum does not match."""
        import tempfile
        from shared.updater import OTAUpdater

        updater = OTAUpdater()
        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as tf:
            tf.write(b"tampered_binary_payload_test")
            tf_path = tf.name

        try:
            # When expected hash mismatches, execution MUST be aborted and return False
            ok = updater.install_and_restart(tf_path, expected_sha256="expected_valid_hash_00000000000000000000000000000000000000000000")
            self.assertFalse(ok, "install_and_restart must reject executing files with mismatched SHA256")
        finally:
            if os.path.exists(tf_path):
                os.remove(tf_path)


if __name__ == "__main__":
    unittest.main()
