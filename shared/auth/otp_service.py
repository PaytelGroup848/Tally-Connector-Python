"""
CtrlBooks - OTP Management Service
-----------------------------------------------
Generates, stores, expires, and verifies 6-digit OTP codes for Email authentication.
"""

import random
import time
from typing import Dict, Any, Tuple
from shared.logging_config import get_logger

logger = get_logger("app.auth.otp")

class OTPService:
    def __init__(self, expiry_seconds: int = 300):
        self.expiry_seconds = expiry_seconds
        self._store: Dict[str, Dict[str, Any]] = {}

    def generate_otp(self, email: str) -> str:
       
        clean_email = email.strip().lower()
        code = str(random.randint(100000, 999999))

        now = time.time()
        self._store[clean_email] = {
            "otp": code,
            "expires_at": now + self.expiry_seconds,
            "attempts": 0
        }
        logger.info(f"Generated new OTP for {clean_email} (Expires in {self.expiry_seconds}s)")
        return code

    def verify_otp(self, email: str, code: str) -> Tuple[bool, str]:
        """
        Verifies provided OTP for given email address.
        Returns (is_valid, message).
        """
        clean_email = email.strip().lower()
        clean_code = code.strip()

        record = self._store.get(clean_email)
        if not record:
            return False, "OTP not requested or expired for this email address"

        now = time.time()
        if now > record["expires_at"]:
            del self._store[clean_email]
            return False, "OTP has expired. Please request a new OTP"

        record["attempts"] += 1
        if record["attempts"] > 5:
            del self._store[clean_email]
            return False, "Too many invalid OTP attempts. Please request a new OTP"

        if clean_code == record["otp"]:
            del self._store[clean_email]
            return True, "OTP verified successfully"

        return False, "Invalid OTP code. Please enter the correct 6-digit code"

otp_service = OTPService()
