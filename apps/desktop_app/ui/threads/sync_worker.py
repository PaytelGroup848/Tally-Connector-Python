import time
import uuid
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime, timezone
from PySide6.QtCore import QThread, Signal
try:
    from pymongo import UpdateOne, UpdateMany
except Exception:
    UpdateOne = None
    UpdateMany = None

try:
    from bson import ObjectId
except Exception:
    ObjectId = None

from shared.repositories.company_repository import get_all_company_configs, upsert_company_config
from shared.auth.cloud_auth_service import cloud_auth_service
from shared.logging_config import get_logger

def get_collection(name: str):
    try:
        from shared.db.mongo_client import get_collection as _gc
        return _gc(name)
    except Exception as exc:
        logger.debug(f"MongoDB collection '{name}' access notice: {exc}")
        return None
from apps.backend.adapters.tally.tally_client import TallyClient
from apps.backend.adapters.tally.request_builder import build_company_list_xml, build_collection_xml
from apps.backend.adapters.tally.response_parser import parse_company_list, parse_metadata_response

logger = get_logger("app.threads.sync_worker")

def chunk_list(lst: list, chunk_size: int = 101):
    for i in range(0, len(lst), chunk_size):
        yield lst[i:i + chunk_size]

class BackgroundSyncWorker(QThread):
    progress_changed = Signal(int, str)
    company_synced = Signal(str, dict)
    sync_completed = Signal(str)
    sync_failed = Signal(str)

    def __init__(self, target_company: str = "", source: str = "TALLY", parent=None):
        super().__init__(parent)
        self.target_company = target_company
        self.source = source.upper()
        self._is_cancelled = False
        self.tally_client = TallyClient(connect_timeout=5.0, read_timeout=120.0)

    def cancel(self):
        self._is_cancelled = True

    def _discover_tally_ports(self) -> int:
        from shared.config import get_settings
        from shared.connection_config import load_connection_config
        cfg = load_connection_config()
        configured_port = int(cfg.get("tally_port") or get_settings().tally_port or 9000)
        auto_connect = bool(cfg.get("auto_connect", True))
        t_host = str(cfg.get("tally_host") or "127.0.0.1").strip()
        if t_host.lower() == "localhost":
            t_host = "127.0.0.1"

        if not auto_connect or configured_port != 9000:
            candidate_ports = [configured_port]
        else:
            candidate_ports = [configured_port, 9000, 9001, 9002, 9003, 9004]
            seen = set()
            candidate_ports = [p for p in candidate_ports if not (p in seen or seen.add(p))]

        for port in candidate_ports:
            try:
                ok, code, _, _ = self.tally_client.send_xml_request(t_host, port, build_company_list_xml(), timeout=2.0)
                if ok and code == 200:
                    return port
            except Exception:
                continue
        return configured_port

    def _get_open_tally_companies(self, port: int) -> List[Dict[str, Any]]:
        try:
            ok, code, text, _ = self.tally_client.send_xml_request("127.0.0.1", port, build_company_list_xml(), timeout=3.0)
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
        c_oid = comp_doc.get("_id") if comp_doc else None
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
        try:
            grp_xml = build_collection_xml("Group", ["NAME", "PARENT", "GUID", "ALTERID", "ISADDABLE", "ISSUBLEDGER", "NATUREOFGROUP"], company_name=c_name)
            ok_g, code_g, text_g, _ = self.tally_client.send_xml_request("127.0.0.1", port, grp_xml, timeout=30.0)
            if ok_g and code_g == 200:
                grp_items = parse_metadata_response(text_g, tag_name="Group")
                grp_col = get_collection("groups")
                grp_ops = []
                for g in grp_items:
                    g_doc = {
                        "source": "TALLY",
                        "company_name": c_name,
                        "tallyExternalId": g.get("tallyExternalId") or g.get("name"),
                        "name": g.get("name"),
                        "parent": g.get("parent"),
                        "isPrimary": g.get("isPrimary", False),
                        "isAddable": g.get("isAddable", True),
                        "isSubLedger": g.get("isSubLedger", False),
                        "natureOfGroup": g.get("natureOfGroup", ""),
                        "guid": g.get("guid"),
                        "alter_id": int(g.get("alterid", 0) or 0),
                        "raw": g.get("raw") or g,
                        "updated_at": now_iso
                    }
                    if org_oid:
                        g_doc["organizationId"] = org_oid
                    if c_oid:
                        g_doc["companyId"] = c_oid
                    grp_ops.append(UpdateOne({"name": g.get("name"), "company_name": c_name}, {"$set": g_doc}, upsert=True))
                if grp_ops:
                    for chunk in chunk_list(grp_ops, 500):
                        grp_col.bulk_write(chunk, ordered=False)
        except Exception as exc:
            logger.warning(f"Groups extraction error for '{c_name}': {exc}")

    def _sync_godowns(self, c_name: str, port: int, now_iso: str, org_oid, c_oid):
        try:
            gd_xml = build_collection_xml("Godown", ["NAME", "PARENT", "GUID", "ALTERID", "ADDRESS.LIST"], company_name=c_name)
            ok_gd, code_gd, text_gd, _ = self.tally_client.send_xml_request("127.0.0.1", port, gd_xml, timeout=30.0)
            if ok_gd and code_gd == 200:
                gd_items = parse_metadata_response(text_gd, tag_name="Godown")
                gd_col = get_collection("godowns")
                gd_ops = []
                for gd in gd_items:
                    gd_doc = {
                        "source": "TALLY",
                        "company_name": c_name,
                        "tallyExternalId": gd.get("tallyExternalId") or gd.get("name"),
                        "name": gd.get("name"),
                        "parent": gd.get("parent"),
                        "address": gd.get("address", ""),
                        "guid": gd.get("guid"),
                        "alter_id": int(gd.get("alterid", 0) or 0),
                        "raw": gd.get("raw") or gd,
                        "updated_at": now_iso
                    }
                    if org_oid:
                        gd_doc["organizationId"] = org_oid
                    if c_oid:
                        gd_doc["companyId"] = c_oid
                    gd_ops.append(UpdateOne({"name": gd.get("name"), "company_name": c_name}, {"$set": gd_doc}, upsert=True))
                if gd_ops:
                    for chunk in chunk_list(gd_ops, 500):
                        gd_col.bulk_write(chunk, ordered=False)
        except Exception as exc:
            logger.warning(f"Godowns extraction error for '{c_name}': {exc}")

    def _sync_units(self, c_name: str, port: int, now_iso: str, org_oid, c_oid):
        try:
            u_xml = build_collection_xml("Unit", ["NAME", "SYMBOL", "ORIGINALNAME", "DECIMALPLACES", "GUID", "ALTERID"], company_name=c_name)
            ok_u, code_u, text_u, _ = self.tally_client.send_xml_request("127.0.0.1", port, u_xml, timeout=30.0)
            if ok_u and code_u == 200:
                u_items = parse_metadata_response(text_u, tag_name="Unit")
                u_col = get_collection("units")
                u_ops = []
                for u in u_items:
                    u_doc = {
                        "source": "TALLY",
                        "company_name": c_name,
                        "tallyExternalId": u.get("tallyExternalId") or u.get("name"),
                        "name": u.get("name"),
                        "symbol": u.get("symbol"),
                        "originalName": u.get("originalName"),
                        "decimalPlaces": u.get("decimalPlaces", 0),
                        "guid": u.get("guid"),
                        "alter_id": int(u.get("alterid", 0) or 0),
                        "raw": u.get("raw") or u,
                        "updated_at": now_iso
                    }
                    if org_oid:
                        u_doc["organizationId"] = org_oid
                    if c_oid:
                        u_doc["companyId"] = c_oid
                    u_ops.append(UpdateOne({"name": u.get("name"), "company_name": c_name}, {"$set": u_doc}, upsert=True))
                if u_ops:
                    for chunk in chunk_list(u_ops, 500):
                        u_col.bulk_write(chunk, ordered=False)
        except Exception as exc:
            logger.warning(f"Units extraction error for '{c_name}': {exc}")

    def _sync_stock_groups(self, c_name: str, port: int, now_iso: str, org_oid, c_oid):
        try:
            sg_xml = build_collection_xml("StockGroup", ["NAME", "PARENT", "GUID", "ALTERID"], company_name=c_name)
            ok_sg, code_sg, text_sg, _ = self.tally_client.send_xml_request("127.0.0.1", port, sg_xml, timeout=30.0)
            if ok_sg and code_sg == 200:
                sg_items = parse_metadata_response(text_sg, tag_name="StockGroup")
                sg_col = get_collection("stock_groups")
                sg_ops = []
                for sg in sg_items:
                    sg_doc = {
                        "source": "TALLY",
                        "company_name": c_name,
                        "tallyExternalId": sg.get("tallyExternalId") or sg.get("name"),
                        "name": sg.get("name"),
                        "parent": sg.get("parent"),
                        "guid": sg.get("guid"),
                        "alter_id": int(sg.get("alterid", 0) or 0),
                        "raw": sg.get("raw") or sg,
                        "updated_at": now_iso
                    }
                    if org_oid:
                        sg_doc["organizationId"] = org_oid
                    if c_oid:
                        sg_doc["companyId"] = c_oid
                    sg_ops.append(UpdateOne({"name": sg.get("name"), "company_name": c_name}, {"$set": sg_doc}, upsert=True))
                if sg_ops:
                    for chunk in chunk_list(sg_ops, 500):
                        sg_col.bulk_write(chunk, ordered=False)
        except Exception as exc:
            logger.warning(f"Stock groups extraction notice: {exc}")

    def _sync_ledgers(self, c_name: str, port: int, now_iso: str, now_dt: datetime, org_oid, c_oid) -> Tuple[List[Dict[str, Any]], int]:
        extracted_ledgers: List[Dict[str, Any]] = []
        max_ledger_alter = 0
        try:
            l_xml = build_collection_xml(
                "Ledger",
                ["NAME", "PARENT", "CLOSINGBALANCE", "OPENINGBALANCE", "STARTINGFROM", "ACTIVEFROM", "APPLICABLEFROM", "OPENINGBALANCEDATE", "PARTYGSTIN", "GSTIN", "LEDGERCLASSIFICATION", "GUID", "ALTERID", "EMAIL", "LEDGERPHONE", "LEDGERMOBILE", "ADDRESS.LIST", "BILLCREDITPERIOD", "CREDITLIMIT", "ISBILLWISEON", "LEDGERGSTREGISTRATIONDETAILS.LIST"],
                company_name=c_name
            )
            ok_l, code_l, text_l, err_l = self.tally_client.send_xml_request("127.0.0.1", port, l_xml, timeout=60.0)
            if ok_l and code_l == 200:
                extracted_ledgers = parse_metadata_response(text_l, tag_name="Ledger")
                for l in extracted_ledgers:
                    alt = int(l.get("alterid", 0) or 0)
                    if alt > max_ledger_alter:
                        max_ledger_alter = alt
            else:
                logger.warning(f"Ledger extraction failed: {err_l}")
        except Exception as exc:
            logger.warning(f"Ledger extraction error for '{c_name}': {exc}")

        if extracted_ledgers:
            try:
                l_col = get_collection("ledgers")
                cust_col = get_collection("customers")
                supp_col = get_collection("suppliers")
                v_col = get_collection("vouchers")

                latest_vouchers_by_party: Dict[str, str] = {}
                try:
                    pipeline = [
                        {"$match": {"company_name": c_name}},
                        {"$sort": {"alter_id": -1, "_id": -1}},
                        {"$group": {
                            "_id": "$partyLedger",
                            "voucherId": {"$first": "$tallyExternalId"},
                            "voucherNumber": {"$first": "$voucherNumber"}
                        }}
                    ]
                    for doc in v_col.aggregate(pipeline):
                        p_key = str(doc.get("_id") or "")
                        if p_key:
                            latest_vouchers_by_party[p_key] = str(doc.get("voucherId") or doc.get("voucherNumber") or "")
                except Exception:
                    pass

                l_ops = []
                cust_ops = []
                supp_ops = []

                for l in extracted_ledgers:
                    ext_id = str(l.get("tallyExternalId") or l.get("guid") or l.get("name"))
                    alt_id = int(l.get("alterid", 0) or 0)
                    c_bal = l.get("closingBalance", l.get("closing_balance", 0.0)) or 0.0
                    op_bal = l.get("openingBalance", l.get("opening_balance", 0.0)) or 0.0
                    credit_limit_val = float(l.get("creditLimit", 0.0) or 0.0)
                    credit_days_val = int(l.get("creditDays", 0) or 0)
                    credit_period_val = str(l.get("creditPeriod") or l.get("billCreditPeriod") or "")
                    
                    l_doc = {
                        "source": "TALLY",
                        "company_name": c_name,
                        "tallyExternalId": ext_id,
                        "name": l.get("name"),
                        "parent": l.get("parent"),
                        "group": l.get("group") or l.get("parent"),
                        "ledgerType": l.get("ledgerType") or l.get("ledger_type") or "GENERAL",
                        "date": str(l.get("date") or "2022-04-01"),
                        "openingBalance": float(op_bal),
                        "closingBalance": float(c_bal),
                        "creditLimit": credit_limit_val,
                        "creditDays": credit_days_val,
                        "creditPeriod": credit_period_val,
                        "billCreditPeriod": credit_period_val,
                        "gstin": l.get("gstin"),
                        "guid": l.get("guid"),
                        "alter_id": alt_id,
                        "raw": l.get("raw") or l,
                        "updated_at": now_iso
                    }
                    if org_oid:
                        l_doc["organizationId"] = org_oid
                    if c_oid:
                        l_doc["companyId"] = c_oid
                    l_filter: Dict[str, Any] = {"tallyExternalId": ext_id}
                    if org_oid:
                        l_filter["organizationId"] = org_oid
                    if c_oid:
                        l_filter["companyId"] = c_oid
                    l_ops.append(UpdateOne(l_filter, {"$set": l_doc}, upsert=True))

                    party_name = str(l.get("name") or "")
                    latest_v_id = latest_vouchers_by_party.get(party_name) or ext_id

                    is_customer = (l.get("ledgerType") == "CUSTOMER" or "debtor" in (l.get("parent") or "").lower() or "customer" in (l.get("parent") or "").lower())
                    if is_customer:
                        cust_doc = {
                            "tallyExternalId": ext_id,
                            "__v": 0,
                            "name": party_name,
                            "gstin": l.get("gstin") or "",
                            "email": l.get("email") or "",
                            "phone": l.get("phone") or "",
                            "address": l.get("address") or "",
                            "openingBalance": float(op_bal),
                            "closingBalance": float(c_bal),
                            "creditLimit": credit_limit_val,
                            "creditDays": credit_days_val,
                            "creditPeriod": credit_period_val,
                            "billCreditPeriod": credit_period_val,
                            "company_name": c_name,
                            "voucherId": latest_v_id,
                            "raw": {
                                "tallyExternalId": ext_id,
                                "name": party_name,
                                "gstin": l.get("gstin") or "",
                                "email": l.get("email") or "",
                                "phone": l.get("phone") or "",
                                "address": l.get("address") or "",
                                "openingBalance": float(op_bal),
                                "closingBalance": float(c_bal),
                                "creditLimit": credit_limit_val,
                                "creditDays": credit_days_val,
                                "creditPeriod": credit_period_val,
                                "billCreditPeriod": credit_period_val,
                                "voucherId": latest_v_id
                            },
                            "updatedAt": now_dt
                        }
                        if org_oid:
                            cust_doc["organizationId"] = org_oid
                        if c_oid:
                            cust_doc["companyId"] = c_oid
                        cust_filter: Dict[str, Any] = {"tallyExternalId": ext_id}
                        if org_oid:
                            cust_filter["organizationId"] = org_oid
                        if c_oid:
                            cust_filter["companyId"] = c_oid
                        cust_ops.append(UpdateOne(
                            cust_filter,
                            {"$set": cust_doc, "$setOnInsert": {"createdAt": now_dt}},
                            upsert=True
                        ))

                    is_supplier = (l.get("ledgerType") in ("VENDOR", "LIABILITY") or "creditor" in (l.get("parent") or "").lower() or "supplier" in (l.get("parent") or "").lower() or "vendor" in (l.get("parent") or "").lower())
                    if is_supplier:
                        supp_ext_id = str(l.get("tallyExternalId") or l.get("guid") or l.get("name"))
                        supp_doc = {
                            "tallyExternalId": supp_ext_id,
                            "__v": 0,
                            "name": party_name,
                            "parent": l.get("parent") or "Sundry Creditors",
                            "group": l.get("group") or l.get("parent") or "Sundry Creditors",
                            "gstin": l.get("gstin") or "",
                            "email": l.get("email") or "",
                            "phone": l.get("phone") or "",
                            "address": l.get("address") or "",
                            "openingBalance": float(op_bal),
                            "closingBalance": float(c_bal),
                            "creditLimit": credit_limit_val,
                            "creditDays": credit_days_val,
                            "creditPeriod": credit_period_val,
                            "billCreditPeriod": credit_period_val,
                            "ledgerType": "LIABILITY",
                            "alterId": alt_id,
                            "company_name": c_name,
                            "voucherId": latest_v_id,
                            "raw": {
                                "tallyExternalId": supp_ext_id,
                                "name": party_name,
                                "parent": l.get("parent") or "Sundry Creditors",
                                "group": l.get("group") or l.get("parent") or "Sundry Creditors",
                                "gstin": l.get("gstin") or "",
                                "email": l.get("email") or "",
                                "phone": l.get("phone") or "",
                                "address": l.get("address") or "",
                                "openingBalance": float(op_bal),
                                "closingBalance": float(c_bal),
                                "creditLimit": credit_limit_val,
                                "creditDays": credit_days_val,
                                "creditPeriod": credit_period_val,
                                "billCreditPeriod": credit_period_val,
                                "ledgerType": "LIABILITY",
                                "alterId": alt_id,
                                "voucherId": latest_v_id
                            },
                            "updatedAt": now_dt
                        }
                        if org_oid:
                            supp_doc["organizationId"] = org_oid
                        if c_oid:
                            supp_doc["companyId"] = c_oid
                        supp_filter: Dict[str, Any] = {"tallyExternalId": supp_ext_id}
                        if org_oid:
                            supp_filter["organizationId"] = org_oid
                        if c_oid:
                            supp_filter["companyId"] = c_oid
                        supp_ops.append(UpdateOne(
                            supp_filter,
                            {"$set": supp_doc, "$setOnInsert": {"createdAt": now_dt}},
                            upsert=True
                        ))

                for ops, col in [(l_ops, l_col), (cust_ops, cust_col), (supp_ops, supp_col)]:
                    if ops:
                        for chunk in chunk_list(ops, 500):
                            col.bulk_write(chunk, ordered=False)
            except Exception as m_exc:
                logger.warning(f"MongoDB ledger persistence notice: {m_exc}")

        return extracted_ledgers, max_ledger_alter

    def _sync_stock_items(self, c_name: str, port: int, now_iso: str, org_oid, c_oid) -> Tuple[List[Dict[str, Any]], int]:
        extracted_stock_items: List[Dict[str, Any]] = []
        max_stock_alter = 0
        try:
            s_xml = build_collection_xml(
                "StockItem",
                ["NAME", "PARENT", "CATEGORY", "BASEUNITS", "ADDITIONALUNITS", "GSTREPUOM", "CLOSINGBALANCE", "OPENINGBALANCE", "STARTINGFROM", "ACTIVEFROM", "APPLICABLEFROM", "CLOSINGRATE", "CLOSINGVALUE", "OPENINGRATE", "OPENINGVALUE", "HSNCODE", "GSTAPPLICABLE", "HSNDETAILS.LIST", "GSTDETAILS.LIST", "BATCHNAME", "BATCHALLOCATIONS.LIST", "GODOWNALLOCATIONS.LIST", "GUID", "ALTERID", "REORDERLEVEL"],
                company_name=c_name
            )
            ok_s, code_s, text_s, err_s = self.tally_client.send_xml_request("127.0.0.1", port, s_xml, timeout=60.0)
            if ok_s and code_s == 200:
                extracted_stock_items = parse_metadata_response(text_s, tag_name="StockItem")
                for s in extracted_stock_items:
                    alt = int(s.get("alterid", 0) or 0)
                    if alt > max_stock_alter:
                        max_stock_alter = alt
            else:
                logger.warning(f"Stock items extraction failed: {err_s}")
        except Exception as exc:
            logger.warning(f"Stock items extraction error for '{c_name}': {exc}")

        if extracted_stock_items:
            try:
                s_col = get_collection("stock_items")
                stocks_col = get_collection("stocks")
                stockbal_col = get_collection("stockbalances")
                items_col = get_collection("items")
                units_col = get_collection("units")

                units_lookup: Dict[str, Dict[str, Any]] = {}
                try:
                    for u_doc in units_col.find({"company_name": c_name}):
                        u_name = str(u_doc.get("name") or "").strip()
                        u_sym = str(u_doc.get("symbol") or "").strip()
                        raw_u = u_doc.get("raw") or {}
                        u_info = {
                            "name": u_name or u_sym,
                            "symbol": u_sym or u_name,
                            "guid": str(u_doc.get("guid") or raw_u.get("guid") or ""),
                            "alterid": int(u_doc.get("alter_id") or raw_u.get("alterid") or 0)
                        }
                        if u_name:
                            units_lookup[u_name.lower()] = u_info
                        if u_sym:
                            units_lookup[u_sym.lower()] = u_info
                except Exception as u_exc:
                    logger.debug(f"Units lookup notice: {u_exc}")

                now_utc = datetime.now(timezone.utc)
                s_ops = []
                items_ops = []
                stocks_ops = []
                stockbal_ops = []

                for s_idx, s in enumerate(extracted_stock_items, start=1):
                    alt_id = int(s.get("alterid", 0) or 0)
                    ext_id = str(s.get("tallyExternalId") or s.get("guid") or s.get("name") or f"STOCK-{s_idx:03d}")
                    item_name = str(s.get("name") or s.get("itemName") or "")
                    item_ext_id = str(s.get("guid") or s.get("itemTallyExternalId") or ext_id)
                    godown_name = str(s.get("godown") or "Main Location")
                    batch_val = str(s.get("batch") or s.get("batchName") or s.get("batch_name") or "Primary Batch").strip()
                    unit_val = str(s.get("unit") or "").strip()
                    hsn_val = str(s.get("hsnCode") or "").strip()

                    unit_obj = units_lookup.get(unit_val.lower())
                    if not unit_obj and unit_val:
                        unit_obj = {
                            "name": unit_val,
                            "symbol": unit_val,
                            "guid": "",
                            "alterid": 0
                        }

                    try:
                        qty = float(s.get("quantity", 0.0) or s.get("closingBalance", 0.0) or 0.0)
                    except (ValueError, TypeError):
                        qty = 0.0
                    try:
                        rate = float(s.get("rate", 0.0) or s.get("closingRate", 0.0) or 0.0)
                    except (ValueError, TypeError):
                        rate = 0.0
                    try:
                        val = float(s.get("value", 0.0) or s.get("closingValue", 0.0) or 0.0)
                    except (ValueError, TypeError):
                        val = 0.0
                    if val == 0.0 and qty != 0.0 and rate != 0.0:
                        val = round(qty * rate, 2)

                    s_doc = {
                        "source": "TALLY",
                        "company_name": c_name,
                        "tallyExternalId": ext_id,
                        "name": item_name,
                        "itemName": item_name,
                        "itemTallyExternalId": item_ext_id,
                        "godown": godown_name,
                        "batch": batch_val,
                        "quantity": qty,
                        "rate": rate,
                        "value": val,
                        "parent": s.get("parent"),
                        "group": s.get("group") or s.get("parent"),
                        "category": s.get("category", ""),
                        "unit": unit_val,
                        "unit_details": unit_obj,
                        "alternateUnit": s.get("alternateUnit", ""),
                        "hsnCode": hsn_val,
                        "gstApplicable": s.get("gstApplicable", "Applicable"),
                        "reorderLevel": s.get("reorderLevel", "0"),
                        "date": str(s.get("date") or "2022-04-01"),
                        "openingBalance": s.get("openingBalance", 0.0),
                        "openingRate": s.get("openingRate", 0.0),
                        "openingValue": s.get("openingValue", 0.0),
                        "closingBalance": qty,
                        "closingRate": rate,
                        "closingValue": val,
                        "guid": s.get("guid"),
                        "alter_id": alt_id,
                        "raw": s.get("raw") or s,
                        "updated_at": now_iso
                    }
                    if org_oid:
                        s_doc["organizationId"] = org_oid
                    if c_oid:
                        s_doc["companyId"] = c_oid
                    item_filter: Dict[str, Any] = {"tallyExternalId": ext_id}
                    if org_oid:
                        item_filter["organizationId"] = org_oid
                    if c_oid:
                        item_filter["companyId"] = c_oid
                    s_ops.append(UpdateOne(item_filter, {"$set": s_doc}, upsert=True))
                    items_ops.append(UpdateOne(item_filter, {"$set": s_doc}, upsert=True))

                    stock_record_doc = {
                        "tallyExternalId": ext_id,
                        "itemName": item_name,
                        "itemTallyExternalId": item_ext_id,
                        "unit": unit_val,
                        "unit_details": unit_obj,
                        "hsnCode": hsn_val,
                        "godown": godown_name,
                        "batch": batch_val,
                        "quantity": qty,
                        "rate": rate,
                        "value": val,
                        "company_name": c_name,
                        "source": "TALLY",
                        "updated_at": now_iso
                    }
                    if org_oid:
                        stock_record_doc["organizationId"] = org_oid
                    if c_oid:
                        stock_record_doc["companyId"] = c_oid
                    stocks_filter: Dict[str, Any] = {"tallyExternalId": ext_id}
                    if org_oid:
                        stocks_filter["organizationId"] = org_oid
                    if c_oid:
                        stocks_filter["companyId"] = c_oid
                    stocks_ops.append(UpdateOne(
                        stocks_filter,
                        {"$set": stock_record_doc},
                        upsert=True
                    ))

                    stockbal_doc = {
                        "tallyExternalId": ext_id,
                        "itemName": item_name,
                        "itemTallyExternalId": item_ext_id,
                        "unit": unit_val,
                        "hsnCode": hsn_val,
                        "godown": godown_name,
                        "batch": batch_val,
                        "quantity": qty,
                        "rate": rate,
                        "value": val,
                        "company_name": c_name,
                        "source": "TALLY",
                        "raw": {
                            "tallyExternalId": ext_id,
                            "itemName": item_name,
                            "itemTallyExternalId": item_ext_id,
                            "unit": unit_obj if unit_obj else unit_val,
                            "hsnCode": hsn_val,
                            "godown": godown_name,
                            "batch": batch_val,
                            "quantity": qty,
                            "rate": rate,
                            "value": val,
                            "voucherId": s.get("voucherId"),
                        },
                        "updatedAt": now_utc
                    }
                    stockbal_filter = {"tallyExternalId": ext_id}
                    if org_oid:
                        stockbal_filter["organizationId"] = org_oid
                        stockbal_doc["organizationId"] = org_oid
                    if c_oid:
                        stockbal_filter["companyId"] = c_oid
                        stockbal_doc["companyId"] = c_oid

                    stockbal_ops.append(UpdateOne(
                        stockbal_filter,
                        {"$set": stockbal_doc, "$setOnInsert": {"createdAt": now_utc, "__v": 0}},
                        upsert=True
                    ))

                for ops, col in [(s_ops, s_col), (items_ops, items_col), (stocks_ops, stocks_col), (stockbal_ops, stockbal_col)]:
                    if ops:
                        for chunk in chunk_list(ops, 500):
                            col.bulk_write(chunk, ordered=False)
            except Exception as m_exc:
                logger.warning(f"MongoDB stock item persistence notice: {m_exc}")

        return extracted_stock_items, max_stock_alter

    def _sync_vouchers(self, c_name: str, port: int, now_iso: str, org_oid, c_oid) -> Tuple[List[Dict[str, Any]], int]:
        extracted_vouchers: List[Dict[str, Any]] = []
        max_voucher_alter = 0
        try:
            v_xml = build_collection_xml(
                "Voucher",
                [
                    "DATE", "EFFECTIVEDATE", "VOUCHERTYPENAME", "VOUCHERNUMBER", "REFERENCE", "REFERENCEDATE",
                    "PARTYLEDGERNAME", "PARTYNAME", "BASICBUYERNAME", "PLACEOFSUPPLY", "AMOUNT", "NARRATION",
                    "GUID", "ALTERID", "ISOPTIONAL", "ISCANCELLED", "ISPOSTDATED",
                    "ALLLEDGERENTRIES.LIST",
                    "ALLLEDGERENTRIES.BILLALLOCATIONS.LIST",
                    "ALLLEDGERENTRIES.BILLALLOCATIONS.NAME",
                    "ALLLEDGERENTRIES.BILLALLOCATIONS.BILLTYPE",
                    "ALLLEDGERENTRIES.BILLALLOCATIONS.AMOUNT",
                    "ALLLEDGERENTRIES.BILLALLOCATIONS.BILLCREDITPERIOD",
                    "ALLLEDGERENTRIES.BILLALLOCATIONS.DUEDATEOFTOTALAMOUNT",
                    "ALLINVENTORYENTRIES.LIST",
                    "LEDGERENTRIES.LIST",
                    "LEDGERENTRIES.BILLALLOCATIONS.LIST",
                    "LEDGERENTRIES.BILLALLOCATIONS.NAME",
                    "LEDGERENTRIES.BILLALLOCATIONS.BILLTYPE",
                    "LEDGERENTRIES.BILLALLOCATIONS.AMOUNT",
                    "LEDGERENTRIES.BILLALLOCATIONS.BILLCREDITPERIOD",
                    "LEDGERENTRIES.BILLALLOCATIONS.DUEDATEOFTOTALAMOUNT"
                ],
                company_name=c_name
            )
            ok_v, code_v, text_v, err_v = self.tally_client.send_xml_request("127.0.0.1", port, v_xml, timeout=300.0)
            if ok_v and code_v == 200:
                extracted_vouchers = parse_metadata_response(text_v, tag_name="Voucher")
                for v in extracted_vouchers:
                    alt = int(v.get("alterid", 0) or 0)
                    if alt > max_voucher_alter:
                        max_voucher_alter = alt
            else:
                logger.warning(f"Voucher extraction failed: {err_v}")
        except Exception as exc:
            logger.warning(f"Voucher extraction error for '{c_name}': {exc}")

        if extracted_vouchers:
            try:
                now_dt = datetime.now(timezone.utc)
                v_col = get_collection("vouchers")
                sales_col = get_collection("sales_invoices")
                purch_col = get_collection("purchase_invoices")
                bank_col = get_collection("bank_transactions")
                bills_col = get_collection("bills_outstanding")

                v_ops, sales_ops, purch_ops, bank_ops, bills_ops = [], [], [], [], []

                for v in extracted_vouchers:
                    alt_id = int(v.get("alterid", 0) or 0)
                    v_num = str(v.get("voucherNumber") or v.get("voucher_number") or v.get("name") or "")
                    v_type = str(v.get("voucherType") or v.get("voucher_type") or v.get("parent") or "")
                    v_party = str(v.get("partyLedger") or v.get("party_ledger") or v.get("party") or "")
                    raw_amt = v.get("amount") if v.get("amount") is not None else v.get("closing_balance")
                    try:
                        amt_val = abs(float(raw_amt)) if raw_amt is not None else 0.0
                    except (ValueError, TypeError):
                        amt_val = 0.0
                    narr_val = str(v.get("narration") or "")
                    guid_val = str(v.get("guid") or "")
                    ext_id = str(v.get("tallyExternalId") or guid_val or v_num)
                    if not guid_val:
                        guid_val = ext_id
                    v_date = str(v.get("date") or v.get("effectiveDate") or "2023-04-01")
                    eff_date = str(v.get("effectiveDate") or v_date)
                    ref_val = str(v.get("reference") or "")
                    ref_date_val = str(v.get("referenceDate") or v_date)
                    place_val = str(v.get("placeOfSupply") or "")
                    inv_entries = v.get("inventoryEntries") or []
                    led_entries = v.get("ledgerEntries") or []
                    bill_allocs = v.get("billAllocations") or []
                    bank_allocs = v.get("bankAllocations") or []

                    v_doc = {
                        "source": "TALLY",
                        "company_name": c_name,
                        "voucherId": ext_id,
                        "tallyExternalId": ext_id,
                        "voucherNumber": v_num,
                        "voucher_number": v_num,
                        "voucherType": v_type,
                        "voucher_type": v_type,
                        "partyLedger": v_party,
                        "party_ledger": v_party,
                        "date": v_date,
                        "effectiveDate": eff_date,
                        "reference": ref_val,
                        "referenceDate": ref_date_val,
                        "placeOfSupply": place_val,
                        "amount": amt_val,
                        "narration": narr_val,
                        "isOptional": bool(v.get("isOptional", False)),
                        "isCancelled": bool(v.get("isCancelled", False)),
                        "isPostDated": bool(v.get("isPostDated", False)),
                        "ledgerEntries": led_entries,
                        "lines": led_entries,
                        "inventoryEntries": inv_entries,
                        "billAllocations": bill_allocs,
                        "guid": guid_val,
                        "alter_id": alt_id,
                        "raw": {
                            "voucherId": ext_id,
                            "name": v_num,
                            "parent": v_type,
                            "party": v_party,
                            "date": v_date,
                            "alterid": alt_id
                        }
                    }
                    if org_oid:
                        v_doc["organizationId"] = org_oid
                    if c_oid:
                        v_doc["companyId"] = c_oid
                    v_filter: Dict[str, Any] = {"tallyExternalId": ext_id}
                    if org_oid:
                        v_filter["organizationId"] = org_oid
                    if c_oid:
                        v_filter["companyId"] = c_oid
                    v_ops.append(UpdateOne(v_filter, {"$set": v_doc, "$unset": {"updated_at": "", "updatedAt": ""}}, upsert=True))

                    lower_type = v_type.lower()
                    if any(k in lower_type for k in ["sales", "credit note"]):
                        sales_doc = {
                            "source": "TALLY",
                            "company_name": c_name,
                            "voucherId": ext_id,
                            "tallyExternalId": ext_id,
                            "invoiceNumber": v_num,
                            "invoiceType": v_type,
                            "invoiceDate": v_date,
                            "customer": v_party,
                            "placeOfSupply": place_val,
                            "amount": amt_val,
                            "items": inv_entries,
                            "ledgerEntries": led_entries,
                            "lines": led_entries,
                            "billAllocations": bill_allocs,
                            "narration": narr_val,
                            "guid": guid_val,
                            "updated_at": now_iso
                        }
                        if org_oid:
                            sales_doc["organizationId"] = org_oid
                        if c_oid:
                            sales_doc["companyId"] = c_oid
                        sales_filter: Dict[str, Any] = {"tallyExternalId": ext_id}
                        if org_oid:
                            sales_filter["organizationId"] = org_oid
                        if c_oid:
                            sales_filter["companyId"] = c_oid
                        sales_ops.append(UpdateOne(sales_filter, {"$set": sales_doc}, upsert=True))

                    elif any(k in lower_type for k in ["purchase", "debit note"]):
                        purch_doc = {
                            "source": "TALLY",
                            "company_name": c_name,
                            "voucherId": ext_id,
                            "tallyExternalId": ext_id,
                            "invoiceNumber": v_num,
                            "invoiceType": v_type,
                            "invoiceDate": v_date,
                            "supplier": v_party,
                            "supplierInvoiceNumber": ref_val,
                            "supplierInvoiceDate": ref_date_val,
                            "amount": amt_val,
                            "items": inv_entries,
                            "ledgerEntries": led_entries,
                            "lines": led_entries,
                            "billAllocations": bill_allocs,
                            "narration": narr_val,
                            "guid": guid_val,
                            "updated_at": now_iso
                        }
                        if org_oid:
                            purch_doc["organizationId"] = org_oid
                        if c_oid:
                            purch_doc["companyId"] = c_oid
                        purch_filter: Dict[str, Any] = {"tallyExternalId": ext_id}
                        if org_oid:
                            purch_filter["organizationId"] = org_oid
                        if c_oid:
                            purch_filter["companyId"] = c_oid
                        purch_ops.append(UpdateOne(purch_filter, {"$set": purch_doc}, upsert=True))

                    elif any(k in lower_type for k in ["receipt", "payment", "contra"]):
                        bank_doc = {
                            "source": "TALLY",
                            "company_name": c_name,
                            "voucherId": ext_id,
                            "tallyExternalId": ext_id,
                            "voucherNumber": v_num,
                            "voucherType": v_type,
                            "date": v_date,
                            "party": v_party,
                            "amount": amt_val,
                            "narration": narr_val,
                            "ledgerEntries": led_entries,
                            "lines": led_entries,
                            "billAllocations": bill_allocs,
                            "bankAllocations": bank_allocs,
                            "guid": guid_val,
                            "updated_at": now_iso
                        }
                        if org_oid:
                            bank_doc["organizationId"] = org_oid
                        if c_oid:
                            bank_doc["companyId"] = c_oid
                        bank_filter: Dict[str, Any] = {"tallyExternalId": ext_id}
                        if org_oid:
                            bank_filter["organizationId"] = org_oid
                        if c_oid:
                            bank_filter["companyId"] = c_oid
                        bank_ops.append(UpdateOne(bank_filter, {"$set": bank_doc}, upsert=True))

                    for b in bill_allocs:
                        b_name = str(b.get("billName") or v_num or "")
                        b_party = str(b.get("party") or v_party or "")
                        bill_doc = {
                            "source": "TALLY",
                            "company_name": c_name,
                            "voucherId": ext_id,
                            "party": b_party,
                            "billName": b_name,
                            "billType": str(b.get("billType") or "Agst Ref"),
                            "voucherNumber": v_num,
                            "billDate": v_date,
                            "dueDate": str(b.get("dueDate") or ""),
                            "amount": float(b.get("amount", 0.0) or 0.0),
                            "updated_at": now_iso
                        }
                        if org_oid:
                            bill_doc["organizationId"] = org_oid
                        if c_oid:
                            bill_doc["companyId"] = c_oid
                        bills_ops.append(UpdateOne(
                            {"billName": b_name, "party": b_party, "voucherNumber": v_num, "company_name": c_name},
                            {"$set": bill_doc},
                            upsert=True
                        ))

                for ops, col in [(v_ops, v_col), (sales_ops, sales_col), (purch_ops, purch_col), (bank_ops, bank_col), (bills_ops, bills_col)]:
                    if ops:
                        for chunk in chunk_list(ops, 500):
                            col.bulk_write(chunk, ordered=False)

                party_latest_voucher: Dict[str, str] = {}
                for v in extracted_vouchers:
                    p = str(v.get("partyLedger") or v.get("party_ledger") or v.get("party") or "").strip()
                    g = str(v.get("tallyExternalId") or v.get("guid") or v.get("voucherNumber") or "")
                    if p and g:
                        party_latest_voucher[p] = g

                if party_latest_voucher:
                    try:
                        cust_col = get_collection("customers")
                        supp_col = get_collection("suppliers")
                        c_updates = []
                        s_updates = []
                        for p_name, v_id in party_latest_voucher.items():
                            c_updates.append(UpdateMany({"name": p_name}, {"$set": {"voucherId": v_id, "raw.voucherId": v_id, "updatedAt": now_dt}}))
                            s_updates.append(UpdateMany({"name": p_name}, {"$set": {"voucherId": v_id, "raw.voucherId": v_id, "updatedAt": now_dt}}))
                        if c_updates:
                            for chunk in chunk_list(c_updates, 500):
                                cust_col.bulk_write(chunk, ordered=False)
                        if s_updates:
                            for chunk in chunk_list(s_updates, 500):
                                supp_col.bulk_write(chunk, ordered=False)
                    except Exception as c_err:
                        logger.debug(f"Customer/Supplier voucherId update notice: {c_err}")

            except Exception as m_exc:
                logger.warning(f"MongoDB voucher persistence notice: {m_exc}")

        return extracted_vouchers, max_voucher_alter

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
        total_companies: int
    ):
        if not cloud_auth_service.access_token:
            return

        total_records = len(extracted_ledgers) + len(extracted_stock_items) + len(extracted_vouchers)
        self.progress_changed.emit(base_pct + 70, f"[{idx}/{total_companies}] Initiating Cloud Sync Session...")
        sync_ok, _, s_data = cloud_auth_service.sync_start(
            company_name=c_name,
            company_guid=c_guid,
            sync_type="FULL",
            total_records=total_records,
            metadata={
                "totalLedgers": len(extracted_ledgers),
                "totalStockItems": len(extracted_stock_items),
                "totalVouchers": len(extracted_vouchers),
                "lastAlterId": last_alter_id
            }
        )
        sync_id = (s_data.get("syncJobId") or s_data.get("syncId") or s_data.get("id") or str(uuid.uuid4())) if sync_ok else str(uuid.uuid4())

        if extracted_ledgers:
            ledger_chunks = list(chunk_list(extracted_ledgers, 101))
            total_l = len(ledger_chunks)
            for b_idx, chunk in enumerate(ledger_chunks, start=1):
                if self._is_cancelled:
                    return
                is_last = (b_idx == total_l and not extracted_stock_items and not extracted_vouchers)
                self.progress_changed.emit(base_pct + 75, f"Pushing Ledgers Batch #{b_idx}/{total_l} ({len(chunk)} items)...")
                cloud_auth_service.sync_batch(sync_id, c_name, "LEDGER", chunk, b_idx, is_last)

        if extracted_stock_items:
            stock_chunks = list(chunk_list(extracted_stock_items, 101))
            total_s = len(stock_chunks)
            for b_idx, chunk in enumerate(stock_chunks, start=1):
                if self._is_cancelled:
                    return
                is_last = (b_idx == total_s and not extracted_vouchers)
                self.progress_changed.emit(base_pct + 80, f"Pushing Stock Batch #{b_idx}/{total_s} ({len(chunk)} items)...")
                cloud_auth_service.sync_batch(sync_id, c_name, "STOCK", chunk, b_idx, is_last)

        if extracted_vouchers:
            voucher_chunks = list(chunk_list(extracted_vouchers, 101))
            total_v = len(voucher_chunks)
            for b_idx, chunk in enumerate(voucher_chunks, start=1):
                if self._is_cancelled:
                    return
                is_last = (b_idx == total_v)
                self.progress_changed.emit(base_pct + 85, f"Pushing Vouchers Batch #{b_idx}/{total_v} ({len(chunk)} items)...")
                cloud_auth_service.sync_batch(sync_id, c_name, "VOUCHER", chunk, b_idx, is_last)

        cloud_auth_service.sync_complete(
            sync_id=sync_id,
            company_name=c_name,
            status="COMPLETED",
            total_synced=total_records,
            last_alter_id=last_alter_id,
            summary={
                "ledgersSynced": len(extracted_ledgers),
                "stockItemsSynced": len(extracted_stock_items),
                "vouchersSynced": len(extracted_vouchers)
            }
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
            val_error = f"Target company '{c_name}' is not currently open in Tally Prime." if open_companies else "Tally Prime is offline. Ensure Tally is running on Port 9000."
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

        self.progress_changed.emit(base_pct + 60, f"[{idx}/{total_companies}] Extracting '{c_name}' Vouchers & Invoices...")
        extracted_vouchers, max_voucher_alter = self._sync_vouchers(c_name, tally_port, now_iso, org_oid, c_oid)

        last_alter_id = max(max_ledger_alter, max_stock_alter, max_voucher_alter)

        self._push_cloud_sync(
            c_name, c_guid, extracted_ledgers, extracted_stock_items,
            extracted_vouchers, last_alter_id, base_pct, idx, total_companies
        )

        # Immediately persist stats to MongoDB 'companies' collection so UI and DB read it instantly
        stats_dict = {
            "ledgers": len(extracted_ledgers),
            "vouchers": len(extracted_vouchers),
            "items": len(extracted_stock_items)
        }
        try:
            col = get_collection("companies")
            col.update_one(
                {"$or": [{"company_name": c_name}, {"name": c_name}, {"tallyCompanyName": c_name}]},
                {"$set": {
                    "status": "SYNCED",
                    "last_sync_at": now_iso,
                    "stats": stats_dict
                }},
                upsert=True
            )
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
