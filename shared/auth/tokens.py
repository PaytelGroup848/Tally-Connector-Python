"""
CtrlBooks - Authentication Token Management
-------------------------------------------------------
Handles token creation, HMAC-SHA256 signing, expiration validation, and revocation.
"""

import hmac
import hashlib
import json
import base64
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, Set
from shared.config import get_settings
from shared.exceptions import AuthenticationError
from shared.logging_config import get_logger

logger = get_logger("app.auth.tokens")

REVOKED_TOKENS: Set[str] = set()

def base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")

def base64url_decode(data_str: str) -> bytes:
    padding = "=" * (4 - (len(data_str) % 4))
    return base64.urlsafe_b64decode((data_str + padding).encode("utf-8"))

def get_token_secret() -> bytes:
    settings = get_settings()
    secret = settings.jwt_secret
    if not secret:
        from shared.config import Environment
        if settings.app_environment == Environment.PRODUCTION:
            raise AuthenticationError("JWT_SECRET must be configured in environment for production mode.")
        logger.warning("SECURITY WARNING: JWT_SECRET not configured in environment. Using temporary fallback.")
        secret = "lr-connector-secure-default-secret-key-change-in-prod"
    return secret.encode("utf-8")

def create_access_token(payload_data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Creates a signed HMAC-SHA256 token with payload and expiration."""
    now = datetime.now(timezone.utc)
    delta = expires_delta or timedelta(hours=24)
    exp = int((now + delta).timestamp())
    iat = int(now.timestamp())

    header = {"alg": "HS256", "typ": "JWT"}
    payload = dict(payload_data)
    payload["iat"] = iat
    payload["exp"] = exp

    header_b64 = base64url_encode(json.dumps(header).encode("utf-8"))
    payload_b64 = base64url_encode(json.dumps(payload, default=str).encode("utf-8"))

    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
    signature = hmac.new(get_token_secret(), signing_input, hashlib.sha256).digest()
    sig_b64 = base64url_encode(signature)

    return f"{header_b64}.{payload_b64}.{sig_b64}"

def verify_token(token: str) -> Dict[str, Any]:
    """Verifies token signature, expiration, and revocation status."""
    if not token or token in REVOKED_TOKENS:
        raise AuthenticationError("Session token is invalid or has been logged out")

    parts = token.split(".")
    if len(parts) != 3:
        raise AuthenticationError("Malformed authentication token")

    header_b64, payload_b64, sig_b64 = parts

    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
    expected_sig = hmac.new(get_token_secret(), signing_input, hashlib.sha256).digest()
    expected_sig_b64 = base64url_encode(expected_sig)

    if not hmac.compare_digest(sig_b64, expected_sig_b64):
        raise AuthenticationError("Invalid token signature")

    try:
        payload_bytes = base64url_decode(payload_b64)
        payload = json.loads(payload_bytes.decode("utf-8"))
    except Exception:
        raise AuthenticationError("Unable to parse token payload")

    exp = payload.get("exp")
    if not exp or datetime.now(timezone.utc).timestamp() > exp:
        raise AuthenticationError("Session token has expired. Please sign in again.")

    return payload

def revoke_token(token: str) -> None:
    """Blacklists a token upon user logout."""
    if token:
        REVOKED_TOKENS.add(token)
