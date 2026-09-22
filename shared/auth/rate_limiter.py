"""
CtrlBooks - Login Rate Limiter
-----------------------------------------
Tracks failed login attempts per username and IP address to prevent brute-force attacks.
"""

import time
from typing import Dict, List
from shared.exceptions import AppException
from shared.logging_config import get_logger

logger = get_logger("app.auth.rate_limiter")

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_DURATION_SECONDS = 300

class LoginRateLimiter:
    """In-memory rate limiter tracking failed login attempts."""
    def __init__(self):
        self._failed_attempts: Dict[str, List[float]] = {}

    def check_rate_limit(self, identifier: str) -> None:
        """Checks if identifier is locked out due to excessive failed attempts."""
        key = identifier.lower().strip()
        now = time.time()
        timestamps = self._failed_attempts.get(key, [])

        valid_timestamps = [ts for ts in timestamps if now - ts < LOCKOUT_DURATION_SECONDS]
        self._failed_attempts[key] = valid_timestamps

        if len(valid_timestamps) >= MAX_FAILED_ATTEMPTS:
            time_remaining = int(LOCKOUT_DURATION_SECONDS - (now - valid_timestamps[0]))
            logger.warning(f"Rate limit exceeded for '{key}'. Locked out for {time_remaining}s")
            raise AppException(
                message=f"Too many failed login attempts. Please try again in {max(time_remaining, 1)} seconds.",
                status_code=429,
                error_code="RATE_LIMIT_EXCEEDED"
            )

    def record_failed_attempt(self, identifier: str) -> None:
        """Records a failed login attempt for the identifier."""
        key = identifier.lower().strip()
        now = time.time()
        if key not in self._failed_attempts:
            self._failed_attempts[key] = []
        self._failed_attempts[key].append(now)

    def clear_failed_attempts(self, identifier: str) -> None:
        """Clears failed attempts for an identifier upon successful login."""
        key = identifier.lower().strip()
        if key in self._failed_attempts:
            del self._failed_attempts[key]

rate_limiter = LoginRateLimiter()
