# pyright: reportArgumentType=false
import time
import uuid
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime, timezone
from PySide6.QtCore import QThread, Signal
from bson import ObjectId
from shared.repositories.company_repository import get_all_company_configs, upsert_company_config
from shared.logging_config import get_logger
from shared.db.mongo_client import get_collection
from shared.auth.cloud_auth_service import cloud_auth_service
from apps.backend.adapters.tally.tally_client import TallyClient
from apps.backend.adapters.tally.request_builder import build_company_list_xml
from apps.backend.adapters.tally.response_parser import parse_company_list
from apps.desktop_app.ui.threads.sync_handlers import (
    chunk_list,
    safe_bulk_write,
    sync_groups,
    sync_godowns,
    sync_units,
    sync_stock_groups,
    sync_voucher_types,
    sync_ledgers,
    sync_stock_items,
    sync_vouchers,
    push_cloud_sync,
    reconcile_pending_commands,
)

logger = get_logger("app.threads.sync_worker")

__all__ = ["chunk_list", "safe_bulk_write", "BackgroundSyncWorker"]

class BackgroundSyncWorker(QThread):
    progress_changed = Signal(int, str)
    company_synced = Signal(str, dict)
    sync_completed = Signal(str)
    sync_failed = Signal(str)

    def __init__(self, target_company: str = "", source: str = "TALLY", is_full_sync: bool = False, parent=None):
        super().__init__(parent)
        self.target_company = target_company
        self.source = source.upper()
        self.is_full_sync = is_full_sync
        self._is_cancelled = False
        self.tally_client = TallyClient(connect_timeout=5.0, read_timeout=120.0)
        self.tally_host = "127.0.0.1"
        self.tally_port = 9000

    def cancel(self):
        self._is_cancelled = True

    def _discover_tally_ports(self) -> int:
        from shared.connection_config import resolve_active_tally_port
        active_host, active_port = resolve_active_tally_port()
        self.tally_host = active_host
        self.tally_port = active_port
        return active_port

    def _get_open_tally_companies(self, port: int) -> List[Dict[str, Any]]:
        try:
            ok, code, text, _ = self.tally_client.send_xml_request(self.tally_host, port, build_company_list_xml(), timeout=3.0)
            if ok and code == 200:
                return parse_company_list(text)
        except Exception as exc:
            logger.debug(f"Direct Tally company list probe failed: {exc}")
        return []

    def _resolve_ids(self, c_name: str) -> Tuple[Optional[ObjectId], Optional[ObjectId]]:
        comp_doc = get_collection("companies").find_one({
            "$or": [
                {"name": c_name},
                {"company_name": c_name},
                {"tallyCompanyName": c_name}
            ]
        })
        c_oid = None
        if comp_doc:
            cloud_cid = comp_doc.get("cloud_company_id")
            if cloud_cid and ObjectId.is_valid(cloud_cid):
                c_oid = ObjectId(cloud_cid)
            elif comp_doc.get("_id"):
                c_oid = comp_doc.get("_id")

        if not c_oid:
            try:
                ok_c, c_list = cloud_auth_service.get_cloud_companies()
                if ok_c and c_list:
                    for c in c_list:
                        c_n = c.get("tallyCompanyName") or c.get("companyName") or c.get("name") or ""
                        if c_n.strip().lower() == c_name.strip().lower():
                            cid = c.get("id") or c.get("_id")
                            if cid and ObjectId.is_valid(cid):
                                c_oid = ObjectId(cid)
                            break
            except Exception:
                pass

        org_oid = comp_doc.get("organizationId") if comp_doc else None

        if not org_oid:
            try:
                org_doc = get_collection("organizations").find_one()
                if org_doc:
                    org_oid = org_doc.get("_id")
            except Exception:
                pass

        if not org_oid:
            org_val = getattr(cloud_auth_service, "organization_id", None)
            if not org_val and isinstance(getattr(cloud_auth_service, "current_user", None), dict):
                org_val = cloud_auth_service.current_user.get("organizationId")
            if org_val:
                try:
                    org_oid = ObjectId(str(org_val))
                except Exception:
                    pass

        if isinstance(org_oid, str) and len(org_oid) == 24:
            try:
                org_oid = ObjectId(org_oid)
            except Exception:
                pass

        if isinstance(c_oid, str) and len(c_oid) == 24:
            try:
                c_oid = ObjectId(c_oid)
            except Exception:
                pass

        final_org: Optional[ObjectId] = org_oid if isinstance(org_oid, ObjectId) else None
        final_comp: Optional[ObjectId] = c_oid if isinstance(c_oid, ObjectId) else None
        return final_org, final_comp


    def _sync_groups(self, c_name: str, port: int, now_iso: str, org_oid, c_oid):
        return sync_groups(self, c_name, port, now_iso, org_oid, c_oid)

    def _sync_godowns(self, c_name: str, port: int, now_iso: str, org_oid, c_oid):
        return sync_godowns(self, c_name, port, now_iso, org_oid, c_oid)

    def _sync_units(self, c_name: str, port: int, now_iso: str, org_oid, c_oid):
        return sync_units(self, c_name, port, now_iso, org_oid, c_oid)

    def _sync_stock_groups(self, c_name: str, port: int, now_iso: str, org_oid, c_oid):
        return sync_stock_groups(self, c_name, port, now_iso, org_oid, c_oid)

    def _sync_voucher_types(self, c_name: str, port: int, now_iso: str, org_oid, c_oid):
        return sync_voucher_types(self, c_name, port, now_iso, org_oid, c_oid)

    def _sync_ledgers(self, c_name: str, port: int, now_iso: str, now_dt: datetime, org_oid, c_oid) -> Tuple[List[Dict[str, Any]], int]:
        return sync_ledgers(self, c_name, port, now_iso, now_dt, org_oid, c_oid)

    def _sync_stock_items(self, c_name: str, port: int, now_iso: str, org_oid, c_oid) -> Tuple[List[Dict[str, Any]], int]:
        return sync_stock_items(self, c_name, port, now_iso, org_oid, c_oid)

    def _sync_vouchers(
        self,
        c_name: str,
        port: int,
        now_iso: str,
        org_oid,
        c_oid,
        from_alter_id: Optional[int] = None,
        base_pct: int = 0,
        idx: int = 1,
        total_companies: int = 1
    ) -> Tuple[List[Dict[str, Any]], int]:
        return sync_vouchers(
            self,
            c_name,
            port,
            now_iso,
            org_oid,
            c_oid,
            from_alter_id=from_alter_id,
            base_pct=base_pct,
            idx=idx,
            total_companies=total_companies
        )

    def _push_cloud_sync(
        self,
        c_name: str,
        c_guid: str,
        extracted_ledgers: list,
        extracted_stock_items: list,
        extracted_vouchers: list,
        last_alter_id: int,
        base_pct: int,
        idx: int,
        total_companies: int,
        is_incremental: bool = False
    ):
        return push_cloud_sync(
            self,
            c_name,
            c_guid,
            extracted_ledgers,
            extracted_stock_items,
            extracted_vouchers,
            last_alter_id,
            base_pct,
            idx,
            total_companies,
            is_incremental=is_incremental
        )


    def _reconcile_pending_commands(
        self,
        c_name: str,
        org_oid,
        c_oid,
        extracted_ledgers: list,
        extracted_stock_items: list,
        extracted_vouchers: list
    ):
        return reconcile_pending_commands(
            self,
            c_name,
            org_oid,
            c_oid,
            extracted_ledgers,
            extracted_stock_items,
            extracted_vouchers
        )

    def _sync_single_company(
        self,
        comp: Dict[str, Any],
        idx: int,
        total_companies: int,
        tally_port: int,
        open_companies: List[Dict[str, Any]]
    ) -> Tuple[bool, str]:
        c_name: str = str(comp.get("company_name") or "")
        c_guid: str = str(comp.get("company_guid") or "")
        base_pct = int(((idx - 1) / total_companies) * 100)

        self.progress_changed.emit(base_pct + 10, f"[{idx}/{total_companies}] Checking Tally Prime for '{c_name}'...")
        open_comp_names = [c.get("name", "").strip().lower() for c in open_companies]
        is_valid = (c_name.strip().lower() in open_comp_names) if open_companies else False

        if not is_valid:
            open_companies = self._get_open_tally_companies(tally_port)
            open_comp_names = [c.get("name", "").strip().lower() for c in open_companies]
            is_valid = (c_name.strip().lower() in open_comp_names)

        if not is_valid:
            val_error = f"Target company '{c_name}' is not currently open in Tally Prime." if open_companies else f"Tally Prime is offline. Ensure Tally is running on Port {tally_port}."
            logger.warning(f"Sync validation failed for '{c_name}': {val_error}")
            self.progress_changed.emit(base_pct + 15, f"⚠️ '{c_name}': {val_error}")
            return False, f"{c_name}: {val_error}"

        for oc in open_companies:
            if oc.get("name", "").strip().lower() == c_name.strip().lower() and oc.get("guid"):
                c_guid = str(oc.get("guid") or "")

        org_oid, c_oid = self._resolve_ids(c_name)
        now_iso = datetime.now(timezone.utc).isoformat()
        now_dt = datetime.now(timezone.utc)

        self.progress_changed.emit(base_pct + 16, f"[{idx}/{total_companies}] Extracting Groups...")
        self._sync_groups(c_name, tally_port, now_iso, org_oid, c_oid)

        self.progress_changed.emit(base_pct + 18, f"[{idx}/{total_companies}] Extracting Godowns...")
        self._sync_godowns(c_name, tally_port, now_iso, org_oid, c_oid)

        self.progress_changed.emit(base_pct + 20, f"[{idx}/{total_companies}] Extracting Units of Measure...")
        self._sync_units(c_name, tally_port, now_iso, org_oid, c_oid)

        self._sync_stock_groups(c_name, tally_port, now_iso, org_oid, c_oid)

        self.progress_changed.emit(base_pct + 22, f"[{idx}/{total_companies}] Extracting Voucher Types...")
        self._sync_voucher_types(c_name, tally_port, now_iso, org_oid, c_oid)

        if self._is_cancelled:
            return False, "Cancelled"

        self.progress_changed.emit(base_pct + 25, f"[{idx}/{total_companies}] Extracting '{c_name}' Ledgers & Accounts...")
        extracted_ledgers, max_ledger_alter = self._sync_ledgers(c_name, tally_port, now_iso, now_dt, org_oid, c_oid)

        if self._is_cancelled:
            return False, "Cancelled"

        self.progress_changed.emit(base_pct + 45, f"[{idx}/{total_companies}] Extracting '{c_name}' Stock Items & Inventory...")
        extracted_stock_items, max_stock_alter = self._sync_stock_items(c_name, tally_port, now_iso, org_oid, c_oid)

        if self._is_cancelled:
            return False, "Cancelled"

        # Determine if incremental sync can be used
        from_alter_id: Optional[int] = None
        if not self.is_full_sync:
            try:
                comp_doc = get_collection("companies").find_one({
                    "$or": [{"company_name": c_name}, {"name": c_name}, {"tallyCompanyName": c_name}]
                })
                if comp_doc:
                    raw_alt = comp_doc.get("last_voucher_alter_id") or comp_doc.get("last_alter_id")
                    if raw_alt is not None:
                        try:
                            from_alter_id = int(raw_alt)
                        except (ValueError, TypeError):
                            from_alter_id = None
            except Exception as e_alt:
                logger.debug(f"Could not load last_alter_id for '{c_name}': {e_alt}")

        sync_label = f"Delta > {from_alter_id}" if from_alter_id else "Full"
        self.progress_changed.emit(base_pct + 60, f"[{idx}/{total_companies}] Extracting '{c_name}' Vouchers ({sync_label})...")
        extracted_vouchers, max_voucher_alter = self._sync_vouchers(
            c_name, tally_port, now_iso, org_oid, c_oid,
            from_alter_id=from_alter_id, base_pct=base_pct, idx=idx, total_companies=total_companies
        )

        last_alter_id = max(max_ledger_alter, max_stock_alter, max_voucher_alter, from_alter_id or 0)
        is_incremental = bool(from_alter_id and from_alter_id > 0)

        self._push_cloud_sync(
            c_name, c_guid, extracted_ledgers, extracted_stock_items,
            extracted_vouchers, last_alter_id, base_pct, idx, total_companies,
            is_incremental=is_incremental
        )

        # Auto-reconcile pending 'SENT' commands for parties/items/vouchers already confirmed in Tally
        self._reconcile_pending_commands(
            c_name, org_oid, c_oid, extracted_ledgers, extracted_stock_items, extracted_vouchers
        )

        # Count total vouchers in MongoDB so UI card chip displays total historical count
        total_voucher_count = len(extracted_vouchers)
        try:
            col_v = get_collection("vouchers")
            total_voucher_count = col_v.count_documents({"company_name": c_name})
        except Exception:
            pass

        stats_dict = {
            "ledgers": len(extracted_ledgers),
            "vouchers": total_voucher_count,
            "items": len(extracted_stock_items)
        }
        try:
            col = get_collection("companies")
            col.update_one(
                {"$or": [{"company_name": c_name}, {"name": c_name}, {"tallyCompanyName": c_name}]},
                {"$set": {
                    "status": "SYNCED",
                    "last_sync_at": now_iso,
                    "last_alter_id": last_alter_id,
                    "last_voucher_alter_id": max_voucher_alter,
                    "stats": stats_dict
                }},
                upsert=True
            )
            from shared.repositories.company_repository import update_company_last_alter_id
            update_company_last_alter_id("TALLY", c_name, last_alter_id)
        except Exception as e_s:
            logger.debug(f"Could not persist company stats to MongoDB: {e_s}")

        # Instantly notify Desktop UI to update company card chips in 0ms
        self.company_synced.emit(c_name, stats_dict)

        return True, ""


    def run(self):
        try:
            self.progress_changed.emit(5, f"Initializing {self.source} data sync...")
            time.sleep(0.1)

            tally_port = self._discover_tally_ports()
            open_companies = self._get_open_tally_companies(tally_port)

            for c in open_companies:
                c_name = c.get("name")
                if c_name:
                    upsert_company_config("TALLY", c_name, company_guid=c.get("guid"))

            if self._is_cancelled:
                return

            configs = get_all_company_configs()
            if self.target_company:
                enabled_companies = [{"company_name": self.target_company, "source_type": self.source}]
            else:
                enabled_companies = [
                    c for c in configs
                    if c.get("is_sync_enabled", True) and c.get("source_type", "").upper() == self.source
                ]

            if not enabled_companies and open_companies:
                enabled_companies = [{"company_name": c.get("name"), "source_type": "TALLY", "company_guid": c.get("guid")} for c in open_companies if c.get("name")]

            if not enabled_companies:
                self.sync_failed.emit(
                    f"No active {self.source} company found. Please launch Tally Prime and open your company."
                )
                return

            total_companies = len(enabled_companies)
            synced_count = 0
            failed_reasons = []

            for idx, comp in enumerate(enabled_companies, start=1):
                if self._is_cancelled:
                    return

                ok, reason = self._sync_single_company(comp, idx, total_companies, tally_port, open_companies)
                if ok:
                    synced_count += 1
                elif reason and reason != "Cancelled":
                    failed_reasons.append(reason)

            if synced_count > 0:
                self.progress_changed.emit(100, f"Successfully synced {synced_count} company(s)!")
                time.sleep(0.2)
                self.sync_completed.emit(f"Synced {synced_count} company(s) with Cloud & Database successfully.")
            else:
                err_summary = "; ".join(failed_reasons) if failed_reasons else "Tally Prime is offline or no company is open."
                self.sync_failed.emit(err_summary)

        except Exception as exc:
            logger.error(f"Sync worker unexpected error: {exc}")
            self.sync_failed.emit(f"Sync failed: {exc}")
