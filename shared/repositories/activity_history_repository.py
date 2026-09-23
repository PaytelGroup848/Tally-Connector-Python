import os
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from shared.logging_config import get_logger

logger = get_logger("app.repositories.activity_history")

LOCAL_HISTORY_FILE = Path.home() / ".ctrlbooks" / "activity_history.json"

class ActivityHistoryRepository:
    def __init__(self):
        LOCAL_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)

    def record_activity(self, activity: Dict[str, Any]) -> None:
        """Records an incoming cloud/web sync command activity to MongoDB and local cache."""
        now_dt = datetime.now()

        from shared.config import get_settings
        from shared.auth.cloud_auth_service import cloud_auth_service
        settings = get_settings()

        org_id = str(
            activity.get("organization_id")
            or activity.get("organizationId")
            or cloud_auth_service.organization_id
            or getattr(settings, "organization_id", "")
            or ""
        ).strip()

        user_email = str(
            activity.get("user_email")
            or activity.get("email")
            or cloud_auth_service.email
            or getattr(settings, "user_email", "")
            or ""
        ).strip().lower()

        device_id = str(
            activity.get("device_id")
            or activity.get("deviceId")
            or cloud_auth_service.device_id
            or getattr(settings, "device_id", "")
            or ""
        ).strip()

        raw_amt = activity.get("amount")
        try:
            parsed_amt = float(raw_amt) if raw_amt is not None else 0.0
        except (ValueError, TypeError):
            parsed_amt = 0.0

        doc = {
            "command_id": str(activity.get("command_id", "")),
            "organization_id": org_id,
            "organizationId": org_id,
            "user_email": user_email,
            "email": user_email,
            "device_id": device_id,
            "time": activity.get("time") or now_dt.strftime("%I:%M %p"),
            "date": activity.get("date") or now_dt.strftime("%d-%b-%Y"),
            "voucher_date": activity.get("voucher_date") or activity.get("date") or now_dt.strftime("%d-%b-%Y"),
            "timestamp": activity.get("timestamp") or now_dt.isoformat(),
            "voucher_type": activity.get("voucher_type") or activity.get("type", "Sales Bill"),
            "party": activity.get("party") or activity.get("party_ledger", "Unknown Party"),
            "amount": parsed_amt,
            "company": activity.get("company") or activity.get("company_name", ""),
            "status": activity.get("status", "SUCCESS").upper(),
            "voucher_number": activity.get("voucher_number"),
            "error": activity.get("error"),
        }

        try:
            from shared.db.mongo_client import get_collection
            col = get_collection("incoming_commands_history")
            col.insert_one(dict(doc))
        except Exception as exc:
            logger.debug(f"MongoDB activity record skipped: {exc}")

        try:
            history = self._load_local_history()
            history.insert(0, doc)
            history = history[:200]
            with open(LOCAL_HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=2, default=str)
        except Exception as exc:
            logger.error(f"Failed to persist activity locally: {exc}")

    def get_recent_activities(
        self,
        limit: int = 50,
        organization_id: Optional[str] = None,
        user_email: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Fetches recent activities isolated by organization / user email."""
        from shared.config import get_settings
        from shared.auth.cloud_auth_service import cloud_auth_service
        settings = get_settings()

        target_org = str(
            organization_id
            or cloud_auth_service.organization_id
            or getattr(settings, "organization_id", "")
            or ""
        ).strip()

        target_email = str(
            user_email
            or cloud_auth_service.email
            or getattr(settings, "user_email", "")
            or ""
        ).strip().lower()

        # Build isolation query
        and_clauses = []
        if target_org:
            and_clauses.append({"$or": [{"organization_id": target_org}, {"organizationId": target_org}]})
        if target_email:
            and_clauses.append({"$or": [{"user_email": target_email}, {"email": target_email}]})

        if and_clauses:
            query_filter: Dict[str, Any] = {"$and": and_clauses} if len(and_clauses) > 1 else and_clauses[0]
        else:
            query_filter = {}

        try:
            from shared.db.mongo_client import get_collection
            col = get_collection("incoming_commands_history")
            docs = list(col.find(query_filter, {"_id": 0}).sort("timestamp", -1).limit(limit))
            if docs:
                return docs
        except Exception as exc:
            logger.debug(f"MongoDB get_recent_activities failed: {exc}")

        return self._load_local_history(organization_id=target_org, user_email=target_email)[:limit]

    def clear_activities(
        self,
        organization_id: Optional[str] = None,
        user_email: Optional[str] = None
    ) -> None:
        """Clears local and MongoDB activity logs strictly scoped to user/org."""
        from shared.config import get_settings
        settings = get_settings()

        from shared.auth.cloud_auth_service import cloud_auth_service
        target_org = str(
            organization_id
            or cloud_auth_service.organization_id
            or getattr(settings, "organization_id", "")
            or ""
        ).strip()

        target_email = str(
            user_email
            or cloud_auth_service.email
            or getattr(settings, "user_email", "")
            or ""
        ).strip().lower()

        and_clauses = []
        if target_org:
            and_clauses.append({"$or": [{"organization_id": target_org}, {"organizationId": target_org}]})
        if target_email:
            and_clauses.append({"$or": [{"user_email": target_email}, {"email": target_email}]})

        # Allow dropping scoped user entries AND local untagged legacy entries
        legacy_clause = {
            "$and": [
                {"$or": [{"organization_id": None}, {"organization_id": ""}, {"organization_id": {"$exists": False}}]},
                {"$or": [{"user_email": None}, {"user_email": ""}, {"user_email": {"$exists": False}}]}
            ]
        }
        if and_clauses:
            user_clause = {"$and": and_clauses} if len(and_clauses) > 1 else and_clauses[0]
            delete_query = {"$or": [user_clause, legacy_clause]}
        else:
            delete_query = legacy_clause

        try:
            from shared.db.mongo_client import get_collection
            col = get_collection("incoming_commands_history")
            col.delete_many(delete_query)
        except Exception as exc:
            logger.debug(f"MongoDB clear_activities failed: {exc}")

        try:
            if not LOCAL_HISTORY_FILE.exists():
                return
            with open(LOCAL_HISTORY_FILE, "r", encoding="utf-8") as f:
                records = json.load(f)
            if not isinstance(records, list):
                records = []

            kept = []
            for item in records:
                item_org = str(item.get("organization_id") or item.get("organizationId") or "").strip()
                item_email = str(item.get("user_email") or item.get("email") or "").strip().lower()

                match_org = bool(target_org and (item_org == target_org))
                match_email = bool(target_email and (item_email == target_email))

                # If matches criteria, drop it; otherwise keep
                if match_org or match_email or (not item_org and not item_email):
                    continue
                kept.append(item)

            with open(LOCAL_HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(kept, f, indent=2, default=str)
        except Exception as exc:
            logger.error(f"Failed to clear local history: {exc}")

    def _load_local_history(
        self,
        organization_id: Optional[str] = None,
        user_email: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        if not LOCAL_HISTORY_FILE.exists():
            legacy_file = Path.home() / ".lr_connector" / "activity_history.json"
            if legacy_file.exists():
                try:
                    import shutil
                    LOCAL_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(legacy_file, LOCAL_HISTORY_FILE)
                except Exception:
                    pass
            if not LOCAL_HISTORY_FILE.exists():
                return []
        try:
            with open(LOCAL_HISTORY_FILE, "r", encoding="utf-8") as f:
                records = json.load(f)
            if not isinstance(records, list):
                return []

            clean_org = organization_id.strip() if organization_id else ""
            clean_email = user_email.strip().lower() if user_email else ""

            filtered = []
            for item in records:
                item_org = str(item.get("organization_id") or item.get("organizationId") or "").strip()
                item_email = str(item.get("user_email") or item.get("email") or "").strip().lower()

                # If filter criteria specified, enforce strict isolation
                if clean_org and item_org and item_org != clean_org:
                    continue
                if clean_email and item_email and item_email != clean_email:
                    continue
                # If record has neither org nor email, skip to prevent legacy cross-tenant leakage
                if (clean_org or clean_email) and not item_org and not item_email:
                    continue

                filtered.append(item)
            return filtered
        except Exception:
            return []

activity_history_repo = ActivityHistoryRepository()

