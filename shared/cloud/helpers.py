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

SYNC_CHECKPOINTS_FILE = _get_writable_data_file("sync_checkpoints.json")



def _normalize_checkpoint_key(key: str) -> str:

    import re

    return re.sub(r'[\s\.\(\)\-_]+', '', str(key or '')).lower()



def get_all_local_checkpoints() -> Dict[str, Any]:

    """Retrieves all persisted local sync checkpoints without touching MongoDB."""

    target = SYNC_CHECKPOINTS_FILE

    if not target.exists() and Path("data/sync_checkpoints.json").exists():

        target = Path("data/sync_checkpoints.json")

    if target.exists():

        try:

            with open(target, "r", encoding="utf-8") as f:

                data = json.load(f)

                if isinstance(data, dict):

                    return data

        except Exception as exc:

            logger.debug(f"Error reading sync checkpoints file: {exc}")

    return {}


def clear_all_local_checkpoints() -> None:
    """Removes and clears all sync checkpoint files from disk across all candidate paths."""
    for p in (SYNC_CHECKPOINTS_FILE, Path("data/sync_checkpoints.json"), Path("data") / "sync_checkpoints.json"):
        try:
            if p.exists():
                p.unlink()
                logger.info(f"Unlinked sync checkpoints file: {p}")
        except Exception as exc:
            logger.debug(f"Error unlinking checkpoint file {p}: {exc}")



def get_local_checkpoint(company_key: str) -> Optional[Dict[str, Any]]:

    """

    Retrieves sync checkpoint for a company (by ObjectId, company name, or normalized name).

    Works in pure cloud mode without requiring MongoDB.

    """

    if not company_key:

        return None

    raw_key = str(company_key).strip()

    norm_key = _normalize_checkpoint_key(raw_key)

    all_cps = get_all_local_checkpoints()



    # 1. Direct exact key match (ObjectId or exact name)

    if raw_key in all_cps and isinstance(all_cps[raw_key], dict):

        return all_cps[raw_key]



    # 2. Check normalized keys and inner company_name / cloud_company_id

    for k, val in all_cps.items():

        if not isinstance(val, dict):

            continue

        if _normalize_checkpoint_key(k) == norm_key:

            return val

        c_name = val.get("company_name") or val.get("tallyCompanyName") or val.get("name")

        if c_name and _normalize_checkpoint_key(str(c_name)) == norm_key:

            return val

        c_id = val.get("cloud_company_id") or val.get("id")

        if c_id and str(c_id).strip() == raw_key:

            return val

    return None



def set_local_checkpoint(
    company_key: str,
    last_alter_id: int = 0,
    last_voucher_alter_id: int = 0,
    status: str = "SYNCED",
    stats: Optional[Dict[str, Any]] = None,
    company_name: str = "",
    cloud_company_id: str = "",
    force_voucher_alter_reset: bool = False,
    last_synced_from_date: Optional[str] = None,
    last_synced_to_date: Optional[str] = None,
) -> None:
    """
    Persists sync checkpoint (alter IDs, sync status, stats) locally.
    Enables incremental sync in pure cloud mode with zero MongoDB dependency.
    """
    if not company_key and not company_name and not cloud_company_id:
        return
    primary_key = str(cloud_company_id or company_key or company_name).strip()
    all_cps = get_all_local_checkpoints()

    # Collect all candidate keys that represent this company
    candidate_keys = [k for k in [
        primary_key,
        str(company_key).strip() if company_key else None,
        str(company_name).strip() if company_name else None,
        str(cloud_company_id).strip() if cloud_company_id else None
    ] if k]

    existing = get_local_checkpoint(primary_key) or {}
    if not existing:
        for ck in candidate_keys:
            cand = get_local_checkpoint(ck)
            if cand:
                existing = cand
                break
    updated_cp = dict(existing)

    # CRITICAL: Preserve date configuration fields from ANY candidate entry in all_cps
    # This prevents set_local_checkpoint from erasing user-configured sync dates when sync finishes!
    for ck in candidate_keys:
        cand = all_cps.get(ck)
        if isinstance(cand, dict):
            for field in ("sync_from_date", "sync_to_date", "financial_year", "date_configured", "last_synced_from_date", "last_synced_to_date"):
                if field in cand and cand[field] is not None and not updated_cp.get(field):
                    updated_cp[field] = cand[field]

    # If date_configured is still not found, search all_cps by company_name
    if not updated_cp.get("date_configured") and company_name:
        for k, v in all_cps.items():
            if isinstance(v, dict) and v.get("date_configured"):
                c_name = str(v.get("company_name", "")).strip().lower()
                if c_name == company_name.strip().lower():
                    for field in ("sync_from_date", "sync_to_date", "financial_year", "date_configured", "last_synced_from_date", "last_synced_to_date"):
                        if field in v and v[field] is not None and not updated_cp.get(field):
                            updated_cp[field] = v[field]
                    break

    now_iso = datetime.now(timezone.utc).isoformat()
    updated_cp["updated_at"] = now_iso
    updated_cp["status"] = status
    if last_alter_id > 0 or "last_alter_id" not in updated_cp:
        updated_cp["last_alter_id"] = max(last_alter_id, updated_cp.get("last_alter_id", 0))
    if force_voucher_alter_reset:
        updated_cp["last_voucher_alter_id"] = 0
    elif last_voucher_alter_id > 0 or "last_voucher_alter_id" not in updated_cp:
        updated_cp["last_voucher_alter_id"] = max(last_voucher_alter_id, updated_cp.get("last_voucher_alter_id", 0))
    if stats:
        updated_cp["stats"] = stats
    if company_name:
        updated_cp["company_name"] = company_name
    if cloud_company_id:
        updated_cp["cloud_company_id"] = cloud_company_id
    if last_synced_from_date:
        updated_cp["last_synced_from_date"] = str(last_synced_from_date)
    if last_synced_to_date:
        updated_cp["last_synced_to_date"] = str(last_synced_to_date)

    all_cps[primary_key] = updated_cp
    if company_name and company_name != primary_key:
        all_cps[company_name] = updated_cp
    if cloud_company_id and cloud_company_id != primary_key:
        all_cps[cloud_company_id] = updated_cp

    try:
        SYNC_CHECKPOINTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(SYNC_CHECKPOINTS_FILE, "w", encoding="utf-8") as f:
            json.dump(all_cps, f, indent=2)
    except Exception as exc:
        logger.warning(f"Could not persist sync checkpoint: {exc}")


def get_company_sync_dates(company_key: str) -> Tuple[Optional[str], Optional[str], bool]:
    """Returns (from_date, to_date, is_configured) for a company from persistent checkpoints."""
    if not company_key:
        return None, None, False
    clean_key = str(company_key).strip()
    all_cps = get_all_local_checkpoints()

    # 1. Direct checkpoint lookup
    cp = get_local_checkpoint(clean_key) or {}

    # 2. If not configured or dates missing, search all_cps for matching company_name or cloud_company_id
    if not (cp.get("date_configured") and cp.get("sync_from_date") and cp.get("sync_to_date")):
        for k, v in all_cps.items():
            if isinstance(v, dict):
                c_name = str(v.get("company_name", "")).strip().lower()
                c_cid = str(v.get("cloud_company_id", "")).strip().lower()
                if clean_key.lower() in (k.lower(), c_name, c_cid):
                    if v.get("date_configured") and v.get("sync_from_date") and v.get("sync_to_date"):
                        cp = v
                        break

    f_date = cp.get("sync_from_date")
    t_date = cp.get("sync_to_date")
    is_conf = bool(cp.get("date_configured", False) and f_date and t_date)
    return f_date, t_date, is_conf


def save_company_sync_dates(
    company_key: str,
    from_date: str,
    to_date: str,
    fy_label: str = "",
    company_name: str = "",
    reset_voucher_checkpoint: bool = False,
    cloud_company_id: str = ""
) -> None:
    """Persists sync date range (from_date, to_date) into company checkpoint."""
    if not company_key and not company_name:
        return
    primary_key = str(company_key or company_name).strip()
    all_cps = get_all_local_checkpoints()

    # Look up existing checkpoint across candidate keys
    candidate_keys = [k for k in [
        primary_key,
        str(company_key).strip() if company_key else None,
        str(company_name).strip() if company_name else None,
        str(cloud_company_id).strip() if cloud_company_id else None
    ] if k]

    existing = {}
    for ck in candidate_keys:
        cand = all_cps.get(ck)
        if isinstance(cand, dict) and cand:
            existing = dict(cand)
            break
    if not existing:
        existing = get_local_checkpoint(primary_key) or {}
    updated_cp = dict(existing)

    updated_cp["sync_from_date"] = from_date
    updated_cp["sync_to_date"] = to_date
    if fy_label:
        updated_cp["financial_year"] = fy_label
    updated_cp["date_configured"] = True
    if company_name:
        updated_cp["company_name"] = company_name

    # Try to resolve cloud_company_id if not explicitly provided
    resolved_cloud_id = cloud_company_id or updated_cp.get("cloud_company_id") or ""
    if not resolved_cloud_id:
        for ck in candidate_keys:
            cand = all_cps.get(ck)
            if isinstance(cand, dict) and cand.get("cloud_company_id"):
                resolved_cloud_id = str(cand["cloud_company_id"]).strip()
                break
    if resolved_cloud_id:
        updated_cp["cloud_company_id"] = resolved_cloud_id

    # Reset voucher alter id checkpoint so vouchers for the newly selected date range are fully extracted
    if reset_voucher_checkpoint:
        updated_cp["last_voucher_alter_id"] = 0

    all_cps[primary_key] = updated_cp
    if company_name and company_name != primary_key:
        all_cps[company_name] = updated_cp
    if resolved_cloud_id and resolved_cloud_id != primary_key:
        all_cps[resolved_cloud_id] = updated_cp

    try:
        SYNC_CHECKPOINTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(SYNC_CHECKPOINTS_FILE, "w", encoding="utf-8") as f:
            json.dump(all_cps, f, indent=2)
        logger.info(f"Saved sync dates for '{primary_key}': {from_date} -> {to_date} ({fy_label})")
    except Exception as exc:
        logger.error(f"Failed to persist company sync dates: {exc}")

def format_to_tally_date(date_str: Optional[str]) -> str:

    """Converts any date string (YYYY-MM-DD, DD-MM-YYYY, etc.) to Tally's YYYYMMDD format."""

    if not date_str:

        return ""

    clean = str(date_str).strip()

    import re

    from datetime import datetime

    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%Y%m%d", "%d/%m/%Y", "%d-%b-%Y"):

        try:

            dt = datetime.strptime(clean, fmt)

            return dt.strftime("%Y%m%d")

        except ValueError:

            pass

    digits = re.sub(r'[^0-9]', '', clean)

    return digits if len(digits) == 8 else clean



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

