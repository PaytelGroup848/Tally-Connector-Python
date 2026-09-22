

import hmac
import hashlib
import os

ALGORITHM = "sha256"
ITERATIONS = 100000
SALT_SIZE = 16

def hash_password(password: str) -> str:
    """Hashes a plain text password using PBKDF2-HMAC-SHA256 with random salt."""
    if not password:
        raise ValueError("Password cannot be empty.")
    salt_bytes = os.urandom(SALT_SIZE)
    salt_hex = salt_bytes.hex()
    hash_bytes = hashlib.pbkdf2_hmac(
        ALGORITHM,
        password.encode("utf-8"),
        salt_bytes,
        ITERATIONS
    )
    hash_hex = hash_bytes.hex()
    return f"pbkdf2:{ALGORITHM}:{ITERATIONS}${salt_hex}${hash_hex}"

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain text password against stored PBKDF2 hash using constant-time comparison."""
    if not plain_password or not hashed_password:
        return False

    try:
        parts = hashed_password.split("$")
        if len(parts) != 3:
            return False

        header, salt_hex, expected_hash_hex = parts
        header_parts = header.split(":")
        if len(header_parts) != 3 or header_parts[0] != "pbkdf2":
            return False

        algo = header_parts[1]
        iterations = int(header_parts[2])

        salt_bytes = bytes.fromhex(salt_hex)
        computed_bytes = hashlib.pbkdf2_hmac(
            algo,
            plain_password.encode("utf-8"),
            salt_bytes,
            iterations
        )
        computed_hash_hex = computed_bytes.hex()

        return hmac.compare_digest(computed_hash_hex, expected_hash_hex)
    except Exception:
        return False
