from datetime import datetime
from typing import List, Dict, Any, Tuple, Optional
from pymongo import UpdateOne
from shared.logging_config import get_logger
from shared.db.mongo_client import get_collection
from apps.backend.adapters.tally.request_builder import build_collection_xml
from apps.backend.adapters.tally.response_parser import parse_metadata_response
from apps.desktop_app.ui.threads.sync_handlers.common import chunk_list, safe_bulk_write

logger = get_logger("app.threads.sync_handlers.ledger")

def sync_ledgers(worker, c_name: str, port: int, now_iso: str, now_dt: datetime, org_oid, c_oid) -> Tuple[List[Dict[str, Any]], int]:
    extracted_ledgers: List[Dict[str, Any]] = []
    max_ledger_alter = 0
    try:
        l_xml = build_collection_xml(
            "Ledger",
            ["NAME", "PARENT", "CLOSINGBALANCE", "OPENINGBALANCE", "STARTINGFROM", "ACTIVEFROM", "APPLICABLEFROM", "OPENINGBALANCEDATE", "PARTYGSTIN", "GSTIN", "LEDGERCLASSIFICATION", "GUID", "ALTERID", "EMAIL", "LEDGERPHONE", "LEDGERMOBILE", "ADDRESS.LIST", "BILLCREDITPERIOD", "CREDITLIMIT", "ISBILLWISEON", "LEDGERGSTREGISTRATIONDETAILS.LIST", "LEDGSTREGDETAILS.*", "LEDMAILINGDETAILS.*", "STATENAME", "COUNTRYNAME", "PINCODE", "BANKDETAILS", "BANKACCOUNTNUMBER", "ACCOUNTNUMBER", "IFSCODE", "BANKNAME", "BRANCHNAME", "ACCOUNTHOLDERNAME", "SWIFTCODE", "PAYMENTDETAILS.*", "BANKDETAILS.*"],
            company_name=c_name
        )
        ok_l, code_l, text_l, err_l = worker.tally_client.send_xml_request(worker.tally_host, port, l_xml, timeout=60.0)
        if ok_l and code_l == 200:
            extracted_ledgers = parse_metadata_response(text_l, tag_name="Ledger")
            for l in extracted_ledgers:
                alt = int(l.get("alterid", 0) or 0)
                if alt > max_ledger_alter:
                    max_ledger_alter = alt
        else:
            logger.error(f"Ledger extraction failed for '{c_name}': {err_l or f'HTTP {code_l}'}")
    except Exception as exc:
        logger.warning(f"Ledger extraction error for '{c_name}': {exc}")

    from shared.config import get_settings
    if extracted_ledgers and get_settings().direct_mongo_sync_enabled:
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

            group_parent_map: Dict[str, str] = {}
            try:
                g_col = get_collection("groups")
                for g_doc in g_col.find({"company_name": c_name}):
                    gn = str(g_doc.get("name") or "").strip().lower()
                    gp = str(g_doc.get("parent") or "").strip().lower()
                    if gn:
                        group_parent_map[gn] = gp
            except Exception:
                pass

            def is_subgroup_of(curr_group: str, keywords: tuple) -> bool:
                curr = (curr_group or "").strip().lower()
                visited = set()
                while curr and curr not in visited:
                    visited.add(curr)
                    if any(k in curr for k in keywords):
                        return True
                    curr = group_parent_map.get(curr, "")
                return False

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
                    "address": l.get("address") or "",
                    "state": l.get("state") or "",
                    "country": l.get("country") or "",
                    "pincode": l.get("pincode") or "",
                    "registration_type": l.get("registration_type") or "",
                    "pan": l.get("pan") or "",
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
                if l.get("bankDetails"):
                    if not l["bankDetails"].get("accountHolderName") and c_name:
                        l["bankDetails"]["accountHolderName"] = c_name
                    l_doc["bankDetails"] = l["bankDetails"]
                if org_oid:
                    l_doc["organizationId"] = org_oid
                if c_oid:
                    l_doc["companyId"] = c_oid
                    l_doc["cloud_company_id"] = str(c_oid)
                l_filter: Dict[str, Any] = {"tallyExternalId": ext_id, "company_name": c_name}
                if org_oid:
                    l_filter["organizationId"] = org_oid
                if c_oid:
                    l_filter["companyId"] = c_oid
                l_ops.append(UpdateOne(l_filter, {"$set": l_doc}, upsert=True))

                party_name = str(l.get("name") or "")
                latest_v_id = latest_vouchers_by_party.get(party_name) or ext_id

                parent_str = str(l.get("parent") or "")
                is_customer = (
                    l.get("ledgerType") == "CUSTOMER"
                    or "debtor" in parent_str.lower()
                    or "customer" in parent_str.lower()
                    or is_subgroup_of(parent_str, ("debtor", "customer"))
                )
                if is_customer:
                    cust_doc = {
                        "tallyExternalId": ext_id,
                        "__v": 0,
                        "name": party_name,
                        "gstin": l.get("gstin") or "",
                        "pan": l.get("pan") or "",
                        "email": l.get("email") or "",
                        "phone": l.get("phone") or "",
                        "address": l.get("address") or "",
                        "state": l.get("state") or "",
                        "country": l.get("country") or "",
                        "pincode": l.get("pincode") or "",
                        "registration_type": l.get("registration_type") or "",
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
                            "pan": l.get("pan") or "",
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
                        cust_doc["cloud_company_id"] = str(c_oid)
                    cust_filter: Dict[str, Any] = {"tallyExternalId": ext_id, "company_name": c_name}
                    if org_oid:
                        cust_filter["organizationId"] = org_oid
                    if c_oid:
                        cust_filter["companyId"] = c_oid
                    cust_ops.append(UpdateOne(
                        cust_filter,
                        {"$set": cust_doc, "$setOnInsert": {"createdAt": now_dt}},
                        upsert=True
                    ))

                is_supplier = (
                    l.get("ledgerType") in ("VENDOR", "SUPPLIER")
                    or "creditor" in parent_str.lower()
                    or "supplier" in parent_str.lower()
                    or "vendor" in parent_str.lower()
                    or is_subgroup_of(parent_str, ("creditor", "supplier", "vendor"))
                )
                if is_supplier:
                    supp_ext_id = str(l.get("tallyExternalId") or l.get("guid") or l.get("name"))
                    supp_doc = {
                        "tallyExternalId": supp_ext_id,
                        "__v": 0,
                        "name": party_name,
                        "parent": l.get("parent") or "Sundry Creditors",
                        "group": l.get("group") or l.get("parent") or "Sundry Creditors",
                        "gstin": l.get("gstin") or "",
                        "pan": l.get("pan") or "",
                        "email": l.get("email") or "",
                        "phone": l.get("phone") or "",
                        "address": l.get("address") or "",
                        "state": l.get("state") or "",
                        "country": l.get("country") or "",
                        "pincode": l.get("pincode") or "",
                        "registration_type": l.get("registration_type") or "",
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
                            "pan": l.get("pan") or "",
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
                        supp_doc["cloud_company_id"] = str(c_oid)
                    supp_filter: Dict[str, Any] = {"tallyExternalId": supp_ext_id, "company_name": c_name}
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
                safe_bulk_write(col, ops, chunk_size=250)
        except Exception as m_exc:
            logger.warning(f"MongoDB ledger persistence notice: {m_exc}")

    return extracted_ledgers, max_ledger_alter

