"""
CtrlBooks - Smart Voucher Queue Repository
------------------------------------------------------
Durable local queue for incoming cloud vouchers and commands that cannot be
immediately posted to Tally Prime because Tally is closed or the target company
is not currently opened.

Persists to MongoDB Atlas collection 'pending_voucher_queue' with an automatic
local JSON file fallback so no voucher is ever lost even across application restarts.
"""

import json
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from bson import ObjectId

from shared.db.mongo_client import get_collection
from shared.logging_config import get_logger

logger = get_logger("app.repositories.voucher_queue")

def _get_queue_cache_file() -> Path:
    p = Path("data/pending_vouchers.json")
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        return p
    except Exception:
        fallback = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "CtrlBooks" / "data" / "pending_vouchers.json"
        fallback.parent.mkdir(parents=True, exist_ok=True)
        return fallback

QUEUE_CACHE_FILE = _get_queue_cache_file()


class VoucherQueueRepository:
    """Manages the pending voucher queue across MongoDB Atlas and local disk fallback."""

    def _read_local_queue(self) -> List[Dict[str, Any]]:
        try:
            if QUEUE_CACHE_FILE.exists():
                with open(QUEUE_CACHE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data
        except Exception as exc:
            logger.debug(f"Error reading local pending queue file: {exc}")
        return []

    def _write_local_queue(self, items: List[Dict[str, Any]]):
        try:
            QUEUE_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(QUEUE_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(items, f, indent=2, default=str)
        except Exception as exc:
            logger.debug(f"Error writing local pending queue file: {exc}")

    def enqueue_pending_voucher(
        self,
        cmd_id: str,
        cmd_type: str,
        payload: Dict[str, Any],
        target_company: str,
        user_email: Optional[str] = None,
        organization_id: Optional[str] = None,
        reason: Optional[str] = None
    ) -> str:
        """
        Stores an incoming voucher into the pending queue.
        Idempotent by cmd_id.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        queue_id = f"queue_{cmd_id}"

        doc = {
            "queue_id": queue_id,
            "cmd_id": str(cmd_id),
            "cmd_type": cmd_type,
            "target_company": target_company.strip() if target_company else "",
            "user_email": (user_email or "").strip().lower(),
            "organization_id": str(organization_id or ""),
            "payload": payload,
            "status": "PENDING_TALLY",
            "reason": reason or "Tally Prime is offline or company is not opened.",
            "attempts": 0,
            "created_at": now_iso,
            "last_attempt_at": now_iso,
        }

        # 1. Persist to MongoDB
        try:
            col = get_collection("pending_voucher_queue")
            col.update_one(
                {"cmd_id": str(cmd_id)},
                {"$set": doc},
                upsert=True
            )
        except Exception as exc:
            logger.debug(f"MongoDB pending queue enqueue error: {exc}")

        # 2. Persist to local JSON cache
        local_items = self._read_local_queue()
        updated = False
        for i, item in enumerate(local_items):
            if str(item.get("cmd_id")) == str(cmd_id):
                local_items[i] = doc
                updated = True
                break
        if not updated:
            local_items.append(doc)
        self._write_local_queue(local_items)

        logger.info(f"Enqueued voucher for company '{target_company}' (cmd_id={cmd_id}, queue_id={queue_id})")
        return queue_id

    def get_pending_vouchers(
        self,
        organization_id: Optional[str] = None,
        user_email: Optional[str] = None,
        company_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieves active pending vouchers filtered by tenant and optionally by company.
        """
        pending_list: List[Dict[str, Any]] = []

        try:
            col = get_collection("pending_voucher_queue")
            query: Dict[str, Any] = {"status": "PENDING_TALLY"}
            if organization_id:
                query["$or"] = [
                    {"organization_id": str(organization_id)},
                    {"organization_id": ""},
                    {"organization_id": {"$exists": False}}
                ]
            if user_email:
                query["user_email"] = str(user_email).strip().lower()
            if company_name:
                query["target_company"] = {"$regex": f"^{company_name.strip()}$", "$options": "i"}

            docs = list(col.find(query).sort("created_at", 1))
            if docs:
                for d in docs:
                    d["id"] = str(d.get("_id", d.get("queue_id", "")))
                    pending_list.append(d)
                return pending_list
        except Exception as exc:
            logger.debug(f"MongoDB pending queue lookup error: {exc}")

        # Fallback to local queue file
        local_items = self._read_local_queue()
        matched = []
        for item in local_items:
            if item.get("status") != "PENDING_TALLY":
                continue
            if organization_id and item.get("organization_id") and str(item.get("organization_id")) != str(organization_id):
                continue
            if user_email and item.get("user_email") and str(item.get("user_email")).lower() != str(user_email).strip().lower():
                continue
            if company_name and str(item.get("target_company")).strip().lower() != str(company_name).strip().lower():
                continue
            matched.append(item)
        return matched

    def mark_voucher_completed(self, cmd_id: str, tally_voucher_number: Optional[str] = None) -> bool:
        """Marks a voucher in the pending queue as successfully posted into Tally."""
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            col = get_collection("pending_voucher_queue")
            col.update_one(
                {"cmd_id": str(cmd_id)},
                {"$set": {
                    "status": "COMPLETED",
                    "tally_voucher_number": tally_voucher_number,
                    "completed_at": now_iso
                }}
            )
        except Exception as exc:
            logger.debug(f"MongoDB queue completion update error: {exc}")

        local_items = self._read_local_queue()
        for item in local_items:
            if str(item.get("cmd_id")) == str(cmd_id):
                item["status"] = "COMPLETED"
                item["tally_voucher_number"] = tally_voucher_number
                item["completed_at"] = now_iso
        self._write_local_queue(local_items)
        logger.info(f"Marked pending voucher cmd_id={cmd_id} as COMPLETED (Voucher #{tally_voucher_number})")
        return True

    def mark_voucher_attempt(self, cmd_id: str, error_reason: str) -> bool:
        """Records a failed attempt or retry on a pending voucher."""
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            col = get_collection("pending_voucher_queue")
            col.update_one(
                {"cmd_id": str(cmd_id)},
                {
                    "$inc": {"attempts": 1},
                    "$set": {"last_attempt_at": now_iso, "reason": error_reason}
                }
            )
        except Exception:
            pass

        local_items = self._read_local_queue()
        for item in local_items:
            if str(item.get("cmd_id")) == str(cmd_id):
                item["attempts"] = item.get("attempts", 0) + 1
                item["last_attempt_at"] = now_iso
                item["reason"] = error_reason
        self._write_local_queue(local_items)
        return True

    def delete_pending_voucher(self, cmd_id: str) -> bool:
        """Removes a voucher from the pending queue."""
        try:
            col = get_collection("pending_voucher_queue")
            col.delete_one({"cmd_id": str(cmd_id)})
        except Exception:
            pass

        local_items = self._read_local_queue()
        local_items = [it for it in local_items if str(it.get("cmd_id")) != str(cmd_id)]
        self._write_local_queue(local_items)
        return True


voucher_queue_repo = VoucherQueueRepository()

