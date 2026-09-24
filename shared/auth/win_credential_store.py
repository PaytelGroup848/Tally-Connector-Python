"""
CtrlBooks - Windows Credential Manager Storage
--------------------------------------------------------------
Provides hardware-backed, DPAPI-encrypted credential and session storage
via native Windows Credential Manager API (advapi32.dll).

Features:
- Stores session tokens and user data securely inside Windows Credential Manager.
- Enforces 24-hour (1 day) session Time-To-Live (TTL).
- Automatically clears expired credentials.
- Works natively with zero external Python dependencies using ctypes.
"""

import sys
import os
import time
import json
from typing import Optional, Dict, Any, Tuple
from shared.logging_config import get_logger

logger = get_logger("app.auth.win_cred")

CRED_TARGET_NAME = "CtrlBooks:UserSession"
SESSION_LIFETIME_SECONDS = 86400  # 1 day / 24 hours


# ---------------------------------------------------------------------------
# Native Windows advapi32.dll C-Types Bindings
# ---------------------------------------------------------------------------
if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    advapi32 = ctypes.windll.advapi32
    kernel32 = ctypes.windll.kernel32

    CRED_TYPE_GENERIC = 1
    CRED_PERSIST_LOCAL_MACHINE = 2

    class CREDENTIALW(ctypes.Structure):
        _fields_ = [
            ("Flags", wintypes.DWORD),
            ("Type", wintypes.DWORD),
            ("TargetName", wintypes.LPWSTR),
            ("Comment", wintypes.LPWSTR),
            ("LastWritten", wintypes.FILETIME),
            ("CredentialBlobSize", wintypes.DWORD),
            ("CredentialBlob", ctypes.POINTER(ctypes.c_byte)),
            ("Persist", wintypes.DWORD),
            ("AttributeCount", wintypes.DWORD),
            ("Attributes", ctypes.c_void_p),
            ("TargetAlias", wintypes.LPWSTR),
            ("UserName", wintypes.LPWSTR),
        ]

    PCREDENTIALW = ctypes.POINTER(CREDENTIALW)

    # CredWriteW
    CredWriteW = advapi32.CredWriteW
    CredWriteW.argtypes = [PCREDENTIALW, wintypes.DWORD]
    CredWriteW.restype = wintypes.BOOL

    # CredReadW
    CredReadW = advapi32.CredReadW
    CredReadW.argtypes = [wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(PCREDENTIALW)]
    CredReadW.restype = wintypes.BOOL

    # CredDeleteW
    CredDeleteW = advapi32.CredDeleteW
    CredDeleteW.argtypes = [wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
    CredDeleteW.restype = wintypes.BOOL

    # CredFree
    CredFree = advapi32.CredFree
    CredFree.argtypes = [ctypes.c_void_p]
    CredFree.restype = None


def win_cred_write(target_name: str, username: str, secret: str) -> bool:
    """Writes a generic credential to Windows Credential Manager."""
    if sys.platform != "win32":
        return False

    try:
        secret_bytes = secret.encode("utf-8")
        blob = (ctypes.c_byte * len(secret_bytes))(*secret_bytes)

        cred = CREDENTIALW()
        cred.Flags = 0
        cred.Type = CRED_TYPE_GENERIC
        cred.TargetName = target_name
        cred.Comment = "CtrlBooks Encrypted Session Token (24h TTL)"
        cred.CredentialBlobSize = len(secret_bytes)
        cred.CredentialBlob = ctypes.cast(blob, ctypes.POINTER(ctypes.c_byte))
        cred.Persist = CRED_PERSIST_LOCAL_MACHINE
        cred.AttributeCount = 0
        cred.Attributes = None
        cred.TargetAlias = None
        cred.UserName = username

        ret = CredWriteW(ctypes.byref(cred), 0)
        return bool(ret)
    except Exception as exc:
        logger.error(f"Failed to write Windows Credential '{target_name}': {exc}")
        return False


def win_cred_read(target_name: str) -> Optional[Tuple[str, str]]:
    """Reads a generic credential from Windows Credential Manager. Returns (username, secret)."""
    if sys.platform != "win32":
        return None

    pcred = PCREDENTIALW()
    try:
        ret = CredReadW(target_name, CRED_TYPE_GENERIC, 0, ctypes.byref(pcred))
        if not ret or not pcred:
            return None

        cred = pcred.contents
        username = cred.UserName or ""
        blob_size = cred.CredentialBlobSize
        blob_ptr = cred.CredentialBlob

        raw_bytes = bytes(blob_ptr[:blob_size])
        secret = raw_bytes.decode("utf-8", errors="replace")

        CredFree(pcred)
        return username, secret
    except Exception as exc:
        logger.warning(f"Error reading Windows Credential '{target_name}': {exc}")
        if pcred:
            try:
                CredFree(pcred)
            except Exception:
                pass
        return None


def win_cred_delete(target_name: str) -> bool:
    """Deletes a credential from Windows Credential Manager."""
    if sys.platform != "win32":
        return False

    try:
        ret = CredDeleteW(target_name, CRED_TYPE_GENERIC, 0)
        return bool(ret)
    except Exception as exc:
        logger.warning(f"Failed to delete Windows Credential '{target_name}': {exc}")
        return False


# ---------------------------------------------------------------------------
# High-Level 24-Hour Session Management API
# ---------------------------------------------------------------------------

def save_persisted_session(
    username: str,
    access_token: str,
    refresh_token: Optional[str] = None,
    user_dict: Optional[Dict[str, Any]] = None,
    ttl_seconds: int = SESSION_LIFETIME_SECONDS,
) -> bool:
    """
    Saves authenticated user session to Windows Credential Manager with a 24-hour expiration.
    """
    now = int(time.time())
    expires_at = now + ttl_seconds

    payload = {
        "username": username,
        "access_token": access_token,
        "refresh_token": refresh_token or "",
        "user": user_dict or {},
        "logged_in_at": now,
        "expires_at": expires_at,
    }

    raw_json = json.dumps(payload, ensure_ascii=False)
    ok = win_cred_write(CRED_TARGET_NAME, username, raw_json)
    if ok:
        logger.info(f"Saved session for '{username}' to Windows Credential Manager (Valid for 24 hours until {expires_at})")
    return ok


def load_persisted_session() -> Optional[Dict[str, Any]]:
    """
    Retrieves the persisted session from Windows Credential Manager.
    If the session has exceeded 24 hours (expired), it is purged automatically and returns None.
    """
    res = win_cred_read(CRED_TARGET_NAME)
    if not res:
        return None

    username, raw_json = res
    try:
        data = json.loads(raw_json)
        expires_at = data.get("expires_at", 0)
        now = int(time.time())

        # Enforce 24-Hour (1 day) Expiry Check
        if now >= expires_at:
            logger.info(f"Session in Windows Credential Manager has expired (now={now} >= expires_at={expires_at}). Purging session...")
            clear_persisted_session()
            return None

        remaining_hours = round((expires_at - now) / 3600.0, 1)
        logger.info(f"Loaded valid session for '{username}' from Windows Credential Manager ({remaining_hours} hours remaining)")
        return data
    except Exception as exc:
        logger.warning(f"Failed to decode session payload from Windows Credential Manager: {exc}")
        return None


def clear_persisted_session() -> bool:
    """Clears the session from Windows Credential Manager on logout."""
    ok = win_cred_delete(CRED_TARGET_NAME)
    if ok:
        logger.info(f"Cleared session '{CRED_TARGET_NAME}' from Windows Credential Manager")
    return ok

