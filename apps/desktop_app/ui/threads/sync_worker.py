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



def find_matching_tally_company(

    target_name: str,

    open_companies: List[Dict[str, Any]]

) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:

    """

    Identifies the open Tally company matching target_name.

    1. Exact match (case-insensitive & stripped).

    2. If no exact match, normalized match (ignoring whitespace and punctuation).

    Returns (matched_company_dict, error_message).

    If ambiguous (multiple open companies match under normalization), returns (None, error_message).

    If no match, returns (None, None).

    """

    if not open_companies:

        return None, "No companies are currently open in Tally Prime."



    clean_target = (target_name or "").strip()

    target_lower = clean_target.lower()



    # 1. Exact match (case-insensitive & whitespace-trimmed)

    exact_matches = [

        oc for oc in open_companies

        if str(oc.get("name") or "").strip().lower() == target_lower

    ]

    if len(exact_matches) == 1:

        return exact_matches[0], None

    elif len(exact_matches) > 1:

        names = [str(oc.get("name") or "") for oc in exact_matches]

        return None, f"Ambiguous company match: Multiple exact open companies in Tally match '{clean_target}': {names}"



    # 2. Normalized match (punctuation and whitespace tolerant)

    import re

    def _norm(s: str) -> str:

        return re.sub(r'[\s\.\(\)\-_]+', '', s or "").lower()



    norm_target = _norm(clean_target)

    if not norm_target:

        return None, f"Invalid target company name: '{clean_target}'"



    norm_matches = [

        oc for oc in open_companies

        if _norm(str(oc.get("name") or "")) == norm_target

    ]

    if len(norm_matches) == 1:

        return norm_matches[0], None

    elif len(norm_matches) > 1:

        names = [str(oc.get("name") or "") for oc in norm_matches]

        return None, f"Ambiguous company match: Multiple open companies in Tally match '{clean_target}': {names}"



    return None, None





class BackgroundSyncWorker(QThread):

    progress_changed = Signal(int, str)

    company_synced = Signal(str, dict)

    sync_completed = Signal(str)

    sync_failed = Signal(str)



    def __init__(self, target_company: str = "", source: str = "TALLY", is_full_sync: bool = False, is_periodic: bool = False, from_date: Optional[str] = None, to_date: Optional[str] = None, parent=None):

        super().__init__(parent)

        self.target_company = target_company

        self.source = source.upper()

        self.is_full_sync = is_full_sync

        self.is_periodic = is_periodic

        self.from_date = from_date

        self.to_date = to_date

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

        from shared.config import get_settings

        c_oid = None

        org_oid = None



        if get_settings().direct_mongo_sync_enabled:

            try:

                comp_doc = get_collection("companies").find_one({

                    "$or": [

                        {"name": c_name},

                        {"company_name": c_name},

                        {"tallyCompanyName": c_name}

                    ]

                })

                if comp_doc:

                    cloud_cid = comp_doc.get("cloud_company_id")

                    if cloud_cid and ObjectId.is_valid(cloud_cid):

                        c_oid = ObjectId(cloud_cid)

                    elif comp_doc.get("_id"):

                        c_oid = comp_doc.get("_id")

                    org_oid = comp_doc.get("organizationId")

            except Exception:

                pass



        if not c_oid:

            try:

                import re

                def _norm(s):

                    return re.sub(r'[\s\.\(\)\-_]+', '', str(s or '')).lower()



                ok_c, c_list = cloud_auth_service.get_cloud_companies()

                if ok_c and c_list:

                    for c in c_list:

                        c_n = c.get("tallyCompanyName") or c.get("companyName") or c.get("name") or ""

                        if c_n.strip().lower() == c_name.strip().lower() or _norm(c_n) == _norm(c_name):

                            cid = c.get("id") or c.get("_id")

                            if cid and ObjectId.is_valid(cid):

                                c_oid = ObjectId(cid)

                            c_org = c.get("organizationId") or c.get("organization_id")

                            if c_org and not org_oid and ObjectId.is_valid(str(c_org)):

                                org_oid = ObjectId(str(c_org))

                            break

            except Exception:

                pass



        if not org_oid and get_settings().direct_mongo_sync_enabled:

            try:

                org_doc = get_collection("organizations").find_one()

                if org_doc:

                    org_oid = org_doc.get("_id")

            except Exception:

                pass



        if not org_oid:

            org_val = getattr(cloud_auth_service, "organization_id", None)

            if not org_val and isinstance(getattr(cloud_auth_service, "current_user", None), dict):

                org_val = cloud_auth_service.current_user.get("organizationId") or cloud_auth_service.current_user.get("organization_id")

            if org_val and ObjectId.is_valid(str(org_val)):

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

        total_companies: int = 1,

        from_date: Optional[str] = None,

        to_date: Optional[str] = None

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

            total_companies=total_companies,

            from_date=from_date or self.from_date,

            to_date=to_date or self.to_date

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

        is_incremental: bool = False,

        company_id: Optional[str] = None,

        start_date: Optional[str] = None,

        end_date: Optional[str] = None,

        is_full_replace: Optional[bool] = None,

        extracted_pl_accounts: Optional[list] = None

    ) -> Tuple[bool, str]:

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

            is_incremental=is_incremental,

            company_id=company_id,

            start_date=start_date,

            end_date=end_date,

            is_full_replace=is_full_replace,

            extracted_pl_accounts=extracted_pl_accounts

        )

    def _sync_pl_accounts(
        self,
        c_name: str,
        port: int,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        from apps.desktop_app.ui.threads.sync_handlers.pl_syncer import sync_pl_accounts
        return sync_pl_accounts(
            self.tally_client,
            self.tally_host,
            port,
            c_name,
            from_date=from_date,
            to_date=to_date
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

        cloud_cid: Optional[str] = comp.get("cloud_company_id") or comp.get("id")

        if not cloud_cid or not isinstance(cloud_cid, str) or len(str(cloud_cid).strip()) != 24:

            from shared.cloud.helpers import get_local_checkpoint

            local_cp = get_local_checkpoint(c_name)

            if local_cp and local_cp.get("cloud_company_id"):

                cloud_cid = str(local_cp["cloud_company_id"]).strip()

        base_pct = int(((idx - 1) / total_companies) * 100)



        self.progress_changed.emit(base_pct + 10, f"[{idx}/{total_companies}] Checking Tally Prime for '{c_name}'...")

        matched_oc, match_err = find_matching_tally_company(c_name, open_companies)

        if not matched_oc and not match_err:

            open_companies = self._get_open_tally_companies(tally_port)

            matched_oc, match_err = find_matching_tally_company(c_name, open_companies)



        if match_err:

            logger.warning(f"Sync validation error for '{c_name}': {match_err}")

            self.progress_changed.emit(base_pct + 15, f"⚠️ '{c_name}': {match_err}")

            return False, f"{c_name}: {match_err}"



        if not matched_oc:

            val_error = f"Target company '{c_name}' is not currently open in Tally Prime." if open_companies else f"Tally Prime is offline. Ensure Tally is running on Port {tally_port}."

            logger.warning(f"Sync validation failed for '{c_name}': {val_error}")

            self.progress_changed.emit(base_pct + 15, f"⚠️ '{c_name}': {val_error}")

            return False, f"{c_name}: {val_error}"



        # Exact original open company name in Tally (strictly used for Tally XML queries)

        tally_c_name: str = str(matched_oc.get("name") or "").strip() or c_name

        if matched_oc.get("guid"):

            c_guid = str(matched_oc.get("guid") or "")



        if not c_guid or len(c_guid) < 16 or c_guid.lower() in ("none", "null", "undefined"):

            import uuid

            c_guid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"ctrlbooks.tally.{c_name.strip().lower()}"))



        org_oid, c_oid = self._resolve_ids(c_name)

        now_iso = datetime.now(timezone.utc).isoformat()

        now_dt = datetime.now(timezone.utc)



        self.progress_changed.emit(base_pct + 16, f"[{idx}/{total_companies}] Extracting Groups...")

        self._sync_groups(tally_c_name, tally_port, now_iso, org_oid, c_oid)



        self.progress_changed.emit(base_pct + 18, f"[{idx}/{total_companies}] Extracting Godowns...")

        self._sync_godowns(tally_c_name, tally_port, now_iso, org_oid, c_oid)



        self.progress_changed.emit(base_pct + 20, f"[{idx}/{total_companies}] Extracting Units of Measure...")

        self._sync_units(tally_c_name, tally_port, now_iso, org_oid, c_oid)



        self._sync_stock_groups(tally_c_name, tally_port, now_iso, org_oid, c_oid)



        self.progress_changed.emit(base_pct + 22, f"[{idx}/{total_companies}] Extracting Voucher Types...")

        self._sync_voucher_types(tally_c_name, tally_port, now_iso, org_oid, c_oid)



        if self._is_cancelled:

            return False, "Cancelled"



        self.progress_changed.emit(base_pct + 25, f"[{idx}/{total_companies}] Extracting '{tally_c_name}' Ledgers & Accounts...")

        extracted_ledgers, max_ledger_alter = self._sync_ledgers(tally_c_name, tally_port, now_iso, now_dt, org_oid, c_oid)



        if self._is_cancelled:

            return False, "Cancelled"



        self.progress_changed.emit(base_pct + 45, f"[{idx}/{total_companies}] Extracting '{tally_c_name}' Stock Items & Inventory...")

        extracted_stock_items, max_stock_alter = self._sync_stock_items(tally_c_name, tally_port, now_iso, org_oid, c_oid)



        if self._is_cancelled:

            return False, "Cancelled"



        # Determine if incremental sync can be used for vouchers

        from_alter_id: Optional[int] = None

        if not self.is_full_sync:

            # 1. Primary: Persistent local checkpoint (pure cloud mode)

            # CRITICAL: Vouchers have an independent ALTERID counter in Tally from Masters (Ledgers/Stock).

            # NEVER fall back to last_alter_id, which would filter out vouchers with lower alter IDs.

            from shared.cloud.helpers import get_local_checkpoint

            local_cp = get_local_checkpoint(cloud_cid or c_name) or get_local_checkpoint(tally_c_name)

            if local_cp:

                raw_alt = local_cp.get("last_voucher_alter_id")

                if raw_alt is not None:

                    try:

                        from_alter_id = int(raw_alt)

                    except (ValueError, TypeError):

                        from_alter_id = None



            # 2. Secondary: Fallback to MongoDB if direct_mongo_sync_enabled and no local checkpoint

            if from_alter_id is None:

                from shared.config import get_settings

                if get_settings().direct_mongo_sync_enabled:

                    try:

                        comp_doc = get_collection("companies").find_one({

                            "$or": [{"company_name": c_name}, {"name": c_name}, {"tallyCompanyName": c_name}, {"company_name": tally_c_name}]

                        })

                        if comp_doc:

                            raw_alt = comp_doc.get("last_voucher_alter_id")

                            if raw_alt is not None:

                                try:

                                    from_alter_id = int(raw_alt)

                                except (ValueError, TypeError):

                                    from_alter_id = None

                    except Exception as e_alt:

                        logger.debug(f"Could not load last_voucher_alter_id for '{c_name}': {e_alt}")



        comp_from_date = self.from_date
        comp_to_date = self.to_date
        is_date_filtered = False
        from shared.cloud.helpers import get_company_sync_dates, format_tally_date
        if not comp_from_date or not comp_to_date:
            f_d, t_d, is_c = get_company_sync_dates(cloud_cid or c_name)
            if not is_c and tally_c_name != c_name:
                f_d, t_d, is_c = get_company_sync_dates(tally_c_name)
            if is_c and f_d and t_d:
                comp_from_date = f_d
                comp_to_date = t_d
                is_date_filtered = True
        else:
            is_date_filtered = True

        fmt_comp_from = format_tally_date(comp_from_date) if comp_from_date else None
        fmt_comp_to = format_tally_date(comp_to_date) if comp_to_date else None

        # Check if date range has changed since the last successful sync
        last_synced_from = local_cp.get("last_synced_from_date") if local_cp else None
        last_synced_to = local_cp.get("last_synced_to_date") if local_cp else None

        is_date_changed = False
        if fmt_comp_from and last_synced_from and fmt_comp_from != last_synced_from:
            is_date_changed = True
        elif fmt_comp_to and last_synced_to and fmt_comp_to != last_synced_to:
            is_date_changed = True

        if is_date_changed:
            logger.info(f"Sync date range changed for '{c_name}' ({last_synced_from}..{last_synced_to} -> {fmt_comp_from}..{fmt_comp_to}). Forcing INITIAL sync with full replace.")
            from_alter_id = None

        sync_label = f"Delta > {from_alter_id}" if from_alter_id else "Full"
        self.progress_changed.emit(base_pct + 60, f"[{idx}/{total_companies}] Extracting '{tally_c_name}' Vouchers ({sync_label})...")
        extracted_vouchers, max_voucher_alter = self._sync_vouchers(
            tally_c_name, tally_port, now_iso, org_oid, c_oid,
            from_alter_id=from_alter_id, base_pct=base_pct, idx=idx, total_companies=total_companies,
            from_date=comp_from_date, to_date=comp_to_date
        )

        self.progress_changed.emit(base_pct + 68, f"[{idx}/{total_companies}] Extracting '{tally_c_name}' Profit & Loss Accounts...")
        extracted_pl_accounts = self._sync_pl_accounts(
            tally_c_name, tally_port, from_date=comp_from_date, to_date=comp_to_date
        )

        last_alter_id = max(max_ledger_alter, max_stock_alter, max_voucher_alter, from_alter_id or 0)
        is_incremental = bool(from_alter_id and from_alter_id > 0 and not is_date_changed)
        is_full_replace = not is_incremental

        push_ok, push_msg = self._push_cloud_sync(
            c_name, c_guid, extracted_ledgers, extracted_stock_items,
            extracted_vouchers, last_alter_id, base_pct, idx, total_companies,
            is_incremental=is_incremental,
            company_id=cloud_cid,
            start_date=fmt_comp_from,
            end_date=fmt_comp_to,
            is_full_replace=is_full_replace,
            extracted_pl_accounts=extracted_pl_accounts
        )

        if not push_ok:

            logger.warning(f"Cloud sync incomplete for '{c_name}': {push_msg}")

            if "no subscription" in str(push_msg).lower():

                push_msg = "This company is already registered with a different email address."

            self.progress_changed.emit(base_pct + 95, f"⚠️ '{c_name}': {push_msg}")

            return False, f"{c_name}: {push_msg}"



        # Auto-reconcile pending 'SENT' commands for parties/items/vouchers already confirmed in Tally

        self._reconcile_pending_commands(

            c_name, org_oid, c_oid, extracted_ledgers, extracted_stock_items, extracted_vouchers

        )



        # Retrieve total truthful counts from Tally Prime statistics report (live source of truth)

        total_voucher_count = len(extracted_vouchers)
        total_ledger_count = len(extracted_ledgers)
        total_item_count = len(extracted_stock_items)

        if not is_date_filtered:
            try:
                from apps.desktop_app.ui.threads.company_fetch_worker import fetch_tally_company_statistics
                t_stats = fetch_tally_company_statistics(tally_c_name, host=self.tally_host, port=tally_port, timeout=2.0)
                if t_stats and isinstance(t_stats, dict):
                    if t_stats.get("vouchers") is not None and t_stats["vouchers"] > 0:
                        total_voucher_count = t_stats["vouchers"]
                    if t_stats.get("ledgers") is not None and t_stats["ledgers"] > 0:
                        total_ledger_count = t_stats["ledgers"]
                    if t_stats.get("items") is not None and t_stats["items"] > 0:
                        total_item_count = t_stats["items"]
            except Exception:
                pass

            pass



        stats_dict = {

            "ledgers": total_ledger_count,

            "vouchers": total_voucher_count,

            "items": total_item_count

        }

        # Persist checkpoint to local json file (pure cloud mode)

        from shared.cloud.helpers import set_local_checkpoint

        set_local_checkpoint(

            company_key=cloud_cid or c_name,

            last_alter_id=last_alter_id,

            last_voucher_alter_id=max_voucher_alter,

            status="SYNCED",

            stats=stats_dict,

            company_name=c_name,

            cloud_company_id=str(cloud_cid) if cloud_cid else "",

            last_synced_from_date=fmt_comp_from,

            last_synced_to_date=fmt_comp_to

        )



        from shared.config import get_settings

        if get_settings().direct_mongo_sync_enabled:

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

            import re

            def _norm(s: str) -> str:

                return re.sub(r'[\s\.\(\)\-_]+', '', str(s or '')).lower()



            configs_map = {}

            for c in configs:

                cn = str(c.get("company_name") or c.get("name") or "")

                if cn:

                    configs_map[cn.lower()] = c

                    configs_map[_norm(cn)] = c



            if self.target_company:

                target_norm = _norm(self.target_company)

                target_cfg = configs_map.get(self.target_company.lower()) or configs_map.get(target_norm)

                if target_cfg:

                    enabled_companies = [target_cfg]

                else:

                    from shared.cloud.helpers import get_local_checkpoint

                    cp = get_local_checkpoint(self.target_company) or {}

                    enabled_companies = [{

                        "company_name": self.target_company,

                        "source_type": self.source,

                        "cloud_company_id": cp.get("cloud_company_id"),

                        "company_guid": cp.get("company_guid"),

                        "last_alter_id": cp.get("last_alter_id", 0),

                        "last_voucher_alter_id": cp.get("last_voucher_alter_id", 0)

                    }]

            else:

                # Prioritize currently open companies in Tally Prime!

                enabled_companies = []

                for oc in open_companies:

                    oc_name = oc.get("name")

                    if not oc_name:

                        continue

                    oc_norm = _norm(oc_name)

                    matched_cfg = configs_map.get(oc_name.lower()) or configs_map.get(oc_norm)

                    if matched_cfg:

                        comp_dict = dict(matched_cfg)

                        comp_dict["company_name"] = oc_name

                        comp_dict["company_guid"] = oc.get("guid") or comp_dict.get("company_guid")

                        enabled_companies.append(comp_dict)

                    else:

                        from shared.cloud.helpers import get_local_checkpoint

                        cp = get_local_checkpoint(oc_name) or {}

                        enabled_companies.append({

                            "company_name": oc_name,

                            "source_type": self.source,

                            "company_guid": oc.get("guid"),

                            "cloud_company_id": cp.get("cloud_company_id"),

                            "last_alter_id": cp.get("last_alter_id", 0),

                            "last_voucher_alter_id": cp.get("last_voucher_alter_id", 0),

                        })



                # Fallback if no open_companies detected

                if not enabled_companies and not getattr(self, "is_periodic", False):

                    enabled_companies = [

                        c for c in configs

                        if c.get("is_sync_enabled", True) and c.get("source_type", "").upper() == self.source

                    ]



            if not enabled_companies:

                if getattr(self, "is_periodic", False):

                    logger.debug("Periodic auto-sync idle: No active company currently open in Tally Prime.")

                    return

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

                if getattr(self, "is_periodic", False):

                    logger.debug("Periodic auto-sync completed with 0 companies synced.")

                    return

                err_summary = "; ".join(failed_reasons) if failed_reasons else "Tally Prime is offline or no company is open."

                self.sync_failed.emit(err_summary)



        except Exception as exc:

            logger.error(f"Sync worker unexpected error: {exc}")

            self.sync_failed.emit(f"Sync failed: {exc}")

