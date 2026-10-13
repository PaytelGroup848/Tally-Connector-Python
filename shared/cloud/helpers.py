import uuid
import json
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from shared.logging_config import get_logger

logger = get_logger("app.cloud.helpers")

def _safe_get_collection(name: str):
    """Lazily and safely retrieves MongoDB collection without failing at import time."""
    try:
        from shared.db.mongo_client import get_collection
        return get_collection(name)
    except Exception as exc:
        logger.debug(f"MongoDB collection '{name}' access notice: {exc}")
        return None

def _get_writable_data_file(filename: str) -> Path:
    """Returns a writable Path for app data storage across all environments."""
    local_path = Path("data") / filename
    try:
        local_path.parent.mkdir(parents=True, exist_ok=True)
        test_file = local_path.parent / ".perm_check"
        test_file.touch(exist_ok=True)
        test_file.unlink(missing_ok=True)
        return local_path
    except Exception:
        pass

    import os
    local_app_data = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    fallback = Path(local_app_data) / "CtrlBooks" / "data" / filename
    try:
        fallback.parent.mkdir(parents=True, exist_ok=True)
        return fallback
    except Exception:
        import tempfile
        tmp = Path(tempfile.gettempdir()) / "CtrlBooks" / "data" / filename
        tmp.parent.mkdir(parents=True, exist_ok=True)
        return tmp

AUTH_SESSION_FILE = _get_writable_data_file("auth_session.json")
DEVICE_CONFIG_FILE = _get_writable_data_file("device_id.json")

def get_or_create_device_id() -> str:
    """Returns persistent unique hardware device identifier."""
    target_file = DEVICE_CONFIG_FILE
    if not target_file.exists() and Path("data/device_id.json").exists():
        target_file = Path("data/device_id.json")

    if target_file.exists():
        try:
            with open(target_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                dev_id = data.get("deviceId") or data.get("device_id")
                if dev_id:
                    return str(dev_id)
        except Exception:
            pass

    new_device_id = str(uuid.uuid4())
    try:
        DEVICE_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(DEVICE_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({"deviceId": new_device_id, "created_at": datetime.now(timezone.utc).isoformat()}, f, indent=2)
    except Exception as exc:
        logger.warning(f"Could not persist device ID file: {exc}")

    return new_device_id

def format_tally_date(d_str: Optional[str]) -> str:
    """Formats Tally date string (YYYYMMDD, DD-Mon-YYYY, etc.) to YYYY-MM-DD."""
    if not d_str or not str(d_str).strip():
        return "2022-04-01"
    s = str(d_str).strip()
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    if len(s) == 10 and s[4] == '-' and s[7] == '-':
        return s
    for fmt in ("%d-%b-%Y", "%d-%b-%y", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except Exception:
            pass
    return s

def classify_ledger_type(parent: Optional[str], raw_type: Optional[str] = None) -> str:
    """Classifies ledger type into CUSTOMER, VENDOR, BANK, CASH, EXPENSE, INCOME, TAX, ASSET, LIABILITY, or GENERAL."""
    if raw_type and str(raw_type).strip():
        return str(raw_type).strip().upper()
    if not parent:
        return "GENERAL"
    p = str(parent).strip().lower()
    if "debtor" in p or "customer" in p:
        return "CUSTOMER"
    elif "creditor" in p or "supplier" in p or "vendor" in p:
        return "VENDOR"
    elif "bank" in p:
        return "BANK"
    elif "cash" in p:
        return "CASH"
    elif "sales" in p:
        return "SALES"
    elif "purchase" in p:
        return "PURCHASE"
    elif "expense" in p:
        return "EXPENSE"
    elif "income" in p or "revenue" in p:
        return "INCOME"
    elif "tax" in p or "duties" in p or "gst" in p or "vat" in p or "tds" in p:
        return "TAX"
    elif "asset" in p or "stock" in p or "deposit" in p or "investment" in p:
        return "ASSET"
    elif "liabilit" in p or "loan" in p or "capital" in p or "provision" in p:
        return "LIABILITY"
    return "GENERAL"

