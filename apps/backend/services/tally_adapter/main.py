from fastapi import FastAPI, HTTPException
from typing import Optional, Dict, Any
from shared.config import get_settings
from shared.logging_config import setup_logging, get_logger
from shared.exceptions import register_exception_handlers
from shared.middleware import add_request_id_middleware
from apps.backend.adapters.tally.tally_client import TallyClient
from apps.backend.adapters.tally.request_builder import build_company_list_xml, build_collection_xml
from apps.backend.adapters.tally.response_parser import parse_company_list, parse_metadata_response
from apps.backend.adapters.tally.tally_importer import TallyImporter
from shared.repositories.company_repository import upsert_company_config
from shared.database import initialize_database
from pymongo import UpdateOne, UpdateMany

setup_logging("tally_adapter")
logger = get_logger("app.tally_adapter")
settings = get_settings()

app = FastAPI(title="CtrlBooks Tally Adapter", description="Microservice adapter for Tally XML interface")
add_request_id_middleware(app)
register_exception_handlers(app)

CONFIG = {"host": settings.tally_host, "port": settings.tally_port}
client = TallyClient(connect_timeout=10.0, read_timeout=60.0)
tally_importer = TallyImporter(client=client)

@app.on_event("startup")
def startup_event():
    initialize_database()

@app.get("/health")
async def health():
    return {"service": "tally_adapter", "status": "ok", "config": CONFIG}

@app.post("/configure")
async def configure(payload: dict):
    h, p = payload.get("host", CONFIG["host"]), int(payload.get("port", CONFIG["port"]))
    client.validate_host_and_port(h, p)
    CONFIG["host"], CONFIG["port"] = h, p
    return {"configured": True, "tally_config": CONFIG}

@app.get("/validate/company")
async def validate_company(target_company: Optional[str] = None):
    """Validates if Tally is running and targeted company is currently open."""
    xml_req = build_company_list_xml()
    ok, code, res_text, err_msg = await client.send_xml_request_async(CONFIG["host"], CONFIG["port"], xml_req, timeout=5.0)
    if not ok or code != 200:
        return {"valid": False, "reason": err_msg or "Tally Prime server unreachable"}
    open_companies = [c.get("name", "").strip().lower() for c in parse_company_list(res_text)]
    if not open_companies:
        return {"valid": False, "reason": "No company is currently open in Tally Prime"}
    if target_company and target_company.strip().lower() not in open_companies:
        return {"valid": False, "reason": f"Target company '{target_company}' is not open in Tally Prime"}
    return {"valid": True, "open_companies": open_companies}

@app.get("/extract/companies")
async def extract_companies():
    xml_req = build_company_list_xml()
    ok, code, res_text, err_msg = await client.send_xml_request_async(CONFIG["host"], CONFIG["port"], xml_req, timeout=5.0)
    if not ok or code != 200:
        raise HTTPException(503, err_msg or "Failed to connect to Tally server to extract companies.")
    companies = parse_company_list(res_text)

    for c in companies:
        c_name = c.get("name")
        if c_name:
            try:
                upsert_company_config("TALLY", c_name)
            except Exception as e:
                logger.warning(f"Failed to upsert company '{c_name}': {e}")

    return {"status": "success", "count": len(companies), "companies": companies}

@app.get("/extract/ledgers")
async def extract_ledgers(company_name: Optional[str] = None, from_alter_id: Optional[int] = None):
    xml_req = build_collection_xml(
        "Ledger",
        ["NAME", "PARENT", "CLOSINGBALANCE", "OPENINGBALANCE", "STARTINGFROM", "ACTIVEFROM", "APPLICABLEFROM", "OPENINGBALANCEDATE", "PARTYGSTIN", "GSTIN", "LEDGERCLASSIFICATION", "GUID", "ALTERID", "EMAIL", "LEDGERPHONE", "LEDGERMOBILE", "ADDRESS.LIST", "BILLCREDITPERIOD", "CREDITLIMIT", "ISBILLWISEON", "LEDGERGSTREGISTRATIONDETAILS.LIST"],
        company_name=company_name,
        from_alter_id=from_alter_id
    )
    ok, code, res_text, err_msg = await client.send_xml_request_async(CONFIG["host"], CONFIG["port"], xml_req, timeout=60.0)
    if not ok or code != 200:
        raise HTTPException(503, err_msg or "Failed to connect to Tally server to extract ledgers.")
    ledgers = parse_metadata_response(res_text, tag_name="Ledger")

    target_comp = company_name or (ledgers[0].get("company") if ledgers else "Tally Prime Company") or "Tally Prime Company"
    if ledgers:
        try:
            from shared.db.mongo_client import get_collection
            from datetime import datetime, timezone
            from bson import ObjectId
            now_iso = datetime.now(timezone.utc).isoformat()
            now_dt = datetime.now(timezone.utc)
            l_col = get_collection("ledgers")
            cust_col = get_collection("customers")
            norm_col = get_collection("normalized_records")

            comp_doc = get_collection("companies").find_one({
                "$or": [
                    {"name": target_comp},
                    {"company_name": target_comp},
                    {"tallyCompanyName": target_comp}
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

            max_alter_id = 0
            v_col = get_collection("vouchers")
            latest_vouchers_by_party = {}
            try:
                pipeline = [
                    {"$match": {"company_name": target_comp}},
                    {"$sort": {"alter_id": -1, "_id": -1}},
                    {"$group": {
                        "_id": "$partyLedger",
                        "voucherId": {"$first": "$tallyExternalId"},
                        "voucherNumber": {"$first": "$voucherNumber"}
                    }}
                ]
                for d in v_col.aggregate(pipeline):
                    if d.get("_id"):
                        latest_vouchers_by_party[str(d["_id"])] = str(d.get("voucherId") or d.get("voucherNumber") or "")
            except Exception:
                pass

            l_ops = []
            norm_ops = []
            cust_ops = []

            for l in ledgers:
                ext_id = str(l.get("guid") or l.get("name") or "led_0")
                alt_id = int(l.get("alterid", 0) or 0)
                if alt_id > max_alter_id:
                    max_alter_id = alt_id

                c_bal = l.get("closingBalance")
                if c_bal is None:
                    c_bal = l.get("closing_balance")
                if c_bal is None:
                    c_bal = 0.0
                op_bal = l.get("openingBalance")
                if op_bal is None:
                    op_bal = l.get("opening_balance")
                if op_bal is None:
                    op_bal = 0.0

                credit_limit_val = float(l.get("creditLimit", 0.0) or 0.0)
                credit_days_val = int(l.get("creditDays", 0) or 0)
                credit_period_val = str(l.get("creditPeriod") or l.get("billCreditPeriod") or "")

                doc = {
                    "source": "TALLY",
                    "company_name": target_comp,
                    "tallyExternalId": l.get("tallyExternalId") or l.get("guid") or l.get("name"),
                    "name": l.get("name"),
                    "parent": l.get("parent"),
                    "group": l.get("group") or l.get("parent"),
                    "ledgerType": l.get("ledgerType") or l.get("ledger_type") or "GENERAL",
                    "date": l.get("date") or "2022-04-01",
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
                    doc["organizationId"] = org_oid
                if c_oid:
                    doc["companyId"] = c_oid
                l_filter: Dict[str, Any] = {"tallyExternalId": ext_id}
                if org_oid:
                    l_filter["organizationId"] = org_oid
                if c_oid:
                    l_filter["companyId"] = c_oid
                l_ops.append(UpdateOne(l_filter, {"$set": doc}, upsert=True))
                norm_ops.append(UpdateOne(
                    {"source": "TALLY", "record_type": "ledger", "external_id": ext_id, "company_name": target_comp},
                    {"$set": {
                        "source": "TALLY", "record_type": "ledger", "external_id": ext_id, "company_name": target_comp,
                        "canonical": l, "fingerprint": str(alt_id), "normalized_at": now_iso, "updated_at": now_iso
                    }},
                    upsert=True
                ))

                is_customer = (l.get("ledgerType") == "CUSTOMER" or "debtor" in (l.get("parent") or "").lower() or "customer" in (l.get("parent") or "").lower())
                party_name = str(l.get("name") or "")
                cust_ext_id = str(l.get("tallyExternalId") or l.get("guid") or party_name)
                latest_v_id = latest_vouchers_by_party.get(party_name) or cust_ext_id

                if is_customer:
                    cust_raw = {
                        "tallyExternalId": cust_ext_id,
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
                    }
                    cust_doc = {
                        "tallyExternalId": cust_ext_id,
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
                        "voucherId": latest_v_id,
                        "raw": cust_raw,
                        "updatedAt": now_dt
                    }
                    if org_oid:
                        cust_doc["organizationId"] = org_oid
                    if c_oid:
                        cust_doc["companyId"] = c_oid

                    cust_filter: Dict[str, Any] = {"tallyExternalId": cust_ext_id}
                    if org_oid:
                        cust_filter["organizationId"] = org_oid
                    if c_oid:
                        cust_filter["companyId"] = c_oid

                    cust_ops.append(UpdateOne(
                        cust_filter,
                        {
                            "$set": cust_doc,
                            "$setOnInsert": {"createdAt": now_dt}
                        },
                        upsert=True
                    ))

            if l_ops:
                l_col.bulk_write(l_ops, ordered=False)
            if norm_ops:
                norm_col.bulk_write(norm_ops, ordered=False)
            if cust_ops:
                cust_col.bulk_write(cust_ops, ordered=False)

            if max_alter_id > 0:
                c_filter = {"_id": c_oid} if c_oid else {"company_name": target_comp}
                get_collection("companies").update_one(
                    c_filter,
                    {"$max": {"last_alter_id": max_alter_id}, "$set": {"last_sync_at": now_iso}}
                )

            logger.info(f"Persisted {len(ledgers)} ledgers for '{target_comp}' into MongoDB Atlas.")
        except Exception as exc:
            logger.warning(f"MongoDB persistence for ledgers failed: {exc}")

    return {"status": "success", "count": len(ledgers), "company": company_name, "from_alter_id": from_alter_id, "ledgers": ledgers}

@app.get("/extract/customers")
async def extract_customers(company_name: Optional[str] = None, from_alter_id: Optional[int] = None):
    """Extracts customer ledgers (Sundry Debtors) and returns customer list."""
    res = await extract_ledgers(company_name=company_name, from_alter_id=from_alter_id)
    all_ledgers = res.get("ledgers", [])
    customers = [
        l for l in all_ledgers
        if l.get("ledgerType") == "CUSTOMER" or "debtor" in (l.get("parent") or "").lower() or "customer" in (l.get("parent") or "").lower()
    ]
    return {"status": "success", "count": len(customers), "company": company_name, "customers": customers}

@app.get("/extract/vouchers")
async def extract_vouchers(company_name: Optional[str] = None, from_alter_id: Optional[int] = None):
    xml_req = build_collection_xml(
        "Voucher",
        [
            "DATE", "EFFECTIVEDATE", "VOUCHERTYPENAME", "VOUCHERNUMBER", "PARTYLEDGERNAME", "PARTYNAME", "BASICBUYERNAME",
            "AMOUNT", "NARRATION", "GUID", "ALTERID",
            "ALLLEDGERENTRIES.LIST",
            "ALLLEDGERENTRIES.BILLALLOCATIONS.LIST",
            "ALLLEDGERENTRIES.BILLALLOCATIONS.NAME",
            "ALLLEDGERENTRIES.BILLALLOCATIONS.BILLTYPE",
            "ALLLEDGERENTRIES.BILLALLOCATIONS.AMOUNT",
            "ALLLEDGERENTRIES.BILLALLOCATIONS.BILLCREDITPERIOD",
            "ALLLEDGERENTRIES.BILLALLOCATIONS.DUEDATEOFTOTALAMOUNT",
            "LEDGERENTRIES.LIST",
            "LEDGERENTRIES.BILLALLOCATIONS.LIST",
            "LEDGERENTRIES.BILLALLOCATIONS.NAME",
            "LEDGERENTRIES.BILLALLOCATIONS.BILLTYPE",
            "LEDGERENTRIES.BILLALLOCATIONS.AMOUNT",
            "LEDGERENTRIES.BILLALLOCATIONS.BILLCREDITPERIOD",
            "LEDGERENTRIES.BILLALLOCATIONS.DUEDATEOFTOTALAMOUNT",
        ],
        company_name=company_name,
        from_alter_id=from_alter_id
    )
    ok, code, res_text, err_msg = await client.send_xml_request_async(CONFIG["host"], CONFIG["port"], xml_req, timeout=180.0)
    if not ok or code != 200:
        raise HTTPException(503, err_msg or "Failed to connect to Tally server to extract vouchers.")
    vouchers = parse_metadata_response(res_text, tag_name="Voucher")

    target_comp = company_name or (vouchers[0].get("company") if vouchers else "Tally Prime Company") or "Tally Prime Company"
    if vouchers:
        try:
            from shared.db.mongo_client import get_collection
            from datetime import datetime, timezone
            now_iso = datetime.now(timezone.utc).isoformat()
            now_dt = datetime.now(timezone.utc)
            v_col = get_collection("vouchers")
            norm_col = get_collection("normalized_records")

            max_alter_id = 0
            v_ops = []
            norm_ops = []

            for v in vouchers:
                v_num = str(v.get("voucherNumber") or v.get("voucher_number") or v.get("name") or "")
                v_type = str(v.get("voucherType") or v.get("voucher_type") or v.get("parent") or "")
                v_party = str(v.get("partyLedger") or v.get("party_ledger") or v.get("party") or "")
                raw_amt = v.get("amount") if v.get("amount") is not None else v.get("closing_balance")
                try:
                    amt_val = abs(float(raw_amt)) if raw_amt is not None else 0.0
                except (ValueError, TypeError):
                    amt_val = 0.0
                narr_val = str(v.get("narration") or "")
                guid_val = v.get("guid")
                alt_id = int(v.get("alterid", 0) or 0)
                ext_id = str(guid_val or v_num)

                if alt_id > max_alter_id:
                    max_alter_id = alt_id

                v_date = str(v.get("date") or v.get("effectiveDate") or "2023-04-01")
                doc = {
                    "source": "TALLY",
                    "company_name": target_comp,
                    "voucherId": ext_id,
                    "tallyExternalId": ext_id,
                    "voucherNumber": v_num,
                    "voucher_number": v_num,
                    "voucherType": v_type,
                    "voucher_type": v_type,
                    "partyLedger": v_party,
                    "party_ledger": v_party,
                    "date": v_date,
                    "effectiveDate": str(v.get("effectiveDate") or v_date),
                    "reference": str(v.get("reference") or ""),
                    "referenceDate": str(v.get("referenceDate") or v_date),
                    "placeOfSupply": str(v.get("placeOfSupply") or ""),
                    "amount": amt_val,
                    "narration": narr_val,
                    "ledgerEntries": v.get("ledgerEntries", []),
                    "lines": v.get("ledgerEntries", []),
                    "inventoryEntries": v.get("inventoryEntries", []),
                    "billAllocations": v.get("billAllocations", []),
                    "guid": str(guid_val or ext_id),
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
                v_ops.append(UpdateOne(
                    {"tallyExternalId": ext_id, "company_name": target_comp},
                    {"$set": doc, "$unset": {"updated_at": "", "updatedAt": ""}},
                    upsert=True
                ))
                norm_ops.append(UpdateOne(
                    {"source": "TALLY", "record_type": "voucher", "external_id": ext_id, "company_name": target_comp},
                    {"$set": {
                        "source": "TALLY", "record_type": "voucher", "external_id": ext_id, "company_name": target_comp,
                        "canonical": v, "fingerprint": str(alt_id)
                    }},
                    upsert=True
                ))

            if v_ops:
                v_col.bulk_write(v_ops, ordered=False)
            if norm_ops:
                norm_col.bulk_write(norm_ops, ordered=False)

            if max_alter_id > 0:
                get_collection("companies").update_one(
                    {"company_name": target_comp},
                    {"$max": {"last_alter_id": max_alter_id}},
                    upsert=True
                )

            try:
                cust_col = get_collection("customers")
                supp_col = get_collection("suppliers")
                party_latest_v = {}
                for v in vouchers:
                    p = str(v.get("partyLedger") or v.get("party_ledger") or v.get("party") or "").strip()
                    g = str(v.get("tallyExternalId") or v.get("guid") or v.get("voucherNumber") or "")
                    if p and g:
                        party_latest_v[p] = g
                c_up = []
                s_up = []
                for p_name, v_id in party_latest_v.items():
                    c_up.append(UpdateMany({"name": p_name}, {"$set": {"voucherId": v_id, "raw.voucherId": v_id, "updatedAt": now_dt}}))
                    s_up.append(UpdateMany({"name": p_name}, {"$set": {"voucherId": v_id, "raw.voucherId": v_id, "updatedAt": now_dt}}))
                if c_up:
                    cust_col.bulk_write(c_up, ordered=False)
                if s_up:
                    supp_col.bulk_write(s_up, ordered=False)
            except Exception:
                pass

            logger.info(f"Persisted {len(vouchers)} vouchers for '{target_comp}' into MongoDB Atlas.")
        except Exception as exc:
            logger.warning(f"MongoDB persistence for vouchers failed: {exc}")

    return {"status": "success", "count": len(vouchers), "company": company_name, "from_alter_id": from_alter_id, "vouchers": vouchers}

@app.get("/extract/stock")
@app.get("/extract/stocks")
@app.get("/extract/stock_items")
async def extract_stock_items(company_name: Optional[str] = None, from_alter_id: Optional[int] = None):
    import uuid
    xml_req = build_collection_xml(
        "StockItem",
        ["NAME", "PARENT", "CATEGORY", "BASEUNITS", "ADDITIONALUNITS", "CLOSINGBALANCE", "OPENINGBALANCE", "STARTINGFROM", "ACTIVEFROM", "APPLICABLEFROM", "CLOSINGRATE", "CLOSINGVALUE", "OPENINGRATE", "OPENINGVALUE", "HSNCODE", "GSTAPPLICABLE", "BATCHNAME", "BATCHALLOCATIONS.LIST", "GODOWNALLOCATIONS.LIST", "GUID", "ALTERID", "REORDERLEVEL"],
        company_name=company_name,
        from_alter_id=from_alter_id
    )
    ok, code, res_text, err_msg = await client.send_xml_request_async(CONFIG["host"], CONFIG["port"], xml_req, timeout=60.0)
    if not ok or code != 200:
        raise HTTPException(503, err_msg or "Failed to connect to Tally server to extract stock items.")
    stock_items = parse_metadata_response(res_text, tag_name="StockItem")

    mapped_records = []
    for s_idx, s in enumerate(stock_items, start=1):
        ext_id = str(s.get("tallyExternalId") or s.get("guid") or s.get("name") or f"STOCK-{s_idx:03d}")
        item_name = str(s.get("name") or s.get("itemName") or "")
        item_ext_id = str(s.get("guid") or s.get("itemTallyExternalId") or ext_id)
        godown_name = str(s.get("godown") or "Main Location")
        batch_val = str(s.get("batch") or s.get("batchName") or s.get("batch_name") or "Primary Batch").strip()
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

        mapped_records.append({
            "tallyExternalId": ext_id,
            "itemName": item_name,
            "itemTallyExternalId": item_ext_id,
            "godown": godown_name,
            "batch": batch_val,
            "quantity": qty,
            "rate": rate,
            "value": val
        })

    return {
        "syncJobId": f"job-{uuid.uuid4().hex[:12]}",
        "entityType": "STOCK",
        "status": "success",
        "count": len(mapped_records),
        "company": company_name,
        "from_alter_id": from_alter_id,
        "records": mapped_records,
        "stock_items": stock_items
    }

@app.get("/extract/groups")
async def extract_groups(company_name: Optional[str] = None):
    xml_req = build_collection_xml("Group", ["NAME", "PARENT", "GUID", "ALTERID", "ISADDABLE", "ISSUBLEDGER", "NATUREOFGROUP"], company_name=company_name)
    ok, code, res_text, err_msg = await client.send_xml_request_async(CONFIG["host"], CONFIG["port"], xml_req, timeout=30.0)
    if not ok or code != 200:
        raise HTTPException(503, err_msg or "Failed to extract groups from Tally.")
    groups = parse_metadata_response(res_text, tag_name="Group")
    return {"status": "success", "count": len(groups), "company": company_name, "groups": groups}

@app.get("/extract/godowns")
async def extract_godowns(company_name: Optional[str] = None):
    xml_req = build_collection_xml("Godown", ["NAME", "PARENT", "GUID", "ALTERID", "ADDRESS.LIST"], company_name=company_name)
    ok, code, res_text, err_msg = await client.send_xml_request_async(CONFIG["host"], CONFIG["port"], xml_req, timeout=30.0)
    if not ok or code != 200:
        raise HTTPException(503, err_msg or "Failed to extract godowns from Tally.")
    godowns = parse_metadata_response(res_text, tag_name="Godown")
    return {"status": "success", "count": len(godowns), "company": company_name, "godowns": godowns}

@app.get("/extract/units")
async def extract_units(company_name: Optional[str] = None):
    xml_req = build_collection_xml("Unit", ["NAME", "SYMBOL", "ORIGINALNAME", "DECIMALPLACES", "GUID", "ALTERID"], company_name=company_name)
    ok, code, res_text, err_msg = await client.send_xml_request_async(CONFIG["host"], CONFIG["port"], xml_req, timeout=30.0)
    if not ok or code != 200:
        raise HTTPException(503, err_msg or "Failed to extract units from Tally.")
    units = parse_metadata_response(res_text, tag_name="Unit")
    return {"status": "success", "count": len(units), "company": company_name, "units": units}

@app.get("/extract/cost_centres")
async def extract_cost_centres(company_name: Optional[str] = None):
    xml_req = build_collection_xml("CostCentre", ["NAME", "CATEGORY", "GUID", "ALTERID"], company_name=company_name)
    ok, code, res_text, err_msg = await client.send_xml_request_async(CONFIG["host"], CONFIG["port"], xml_req, timeout=30.0)
    if not ok or code != 200:
        raise HTTPException(503, err_msg or "Failed to extract cost centres from Tally.")
    cost_centres = parse_metadata_response(res_text, tag_name="CostCentre")
    return {"status": "success", "count": len(cost_centres), "company": company_name, "cost_centres": cost_centres}

@app.get("/extract/supplier")
@app.get("/extract/suppliers")
async def extract_suppliers(company_name: Optional[str] = None, from_alter_id: Optional[int] = None):
    """Extracts supplier/vendor ledgers (Sundry Creditors) matching Web Developer Schema."""
    import uuid
    res = await extract_ledgers(company_name=company_name, from_alter_id=from_alter_id)
    all_ledgers = res.get("ledgers", [])
    suppliers = [
        l for l in all_ledgers
        if l.get("ledgerType") in ("VENDOR", "LIABILITY") or "creditor" in (l.get("parent") or "").lower() or "supplier" in (l.get("parent") or "").lower() or "vendor" in (l.get("parent") or "").lower()
    ]
    
    mapped_records = []
    for idx, s in enumerate(suppliers, start=1):
        alt = int(s.get("alterid", 0) or s.get("alter_id", 0) or 0)
        ext_id = str(s.get("tallyExternalId") or s.get("guid") or s.get("name") or f"SUPPLIER-{idx:03d}")
        mapped_records.append({
            "tallyExternalId": ext_id,
            "name": s.get("name") or "",
            "parent": s.get("parent") or "Sundry Creditors",
            "group": s.get("group") or s.get("parent") or "Sundry Creditors",
            "gstin": s.get("gstin") or "",
            "email": s.get("email") or "",
            "phone": s.get("phone") or "",
            "address": s.get("address") or "",
            "openingBalance": float(s.get("openingBalance", 0.0) or 0.0),
            "closingBalance": float(s.get("closingBalance", 0.0) or 0.0),
            "creditLimit": float(s.get("creditLimit", 0.0) or 0.0),
            "creditDays": int(s.get("creditDays", 0) or 0),
            "creditPeriod": str(s.get("creditPeriod") or s.get("billCreditPeriod") or ""),
            "billCreditPeriod": str(s.get("creditPeriod") or s.get("billCreditPeriod") or ""),
            "ledgerType": "LIABILITY",
            "alterId": alt
        })

    return {
        "syncJobId": f"job-{uuid.uuid4().hex[:12]}",
        "entityType": "SUPPLIER",
        "status": "success",
        "count": len(mapped_records),
        "company": company_name,
        "from_alter_id": from_alter_id,
        "records": mapped_records,
        "suppliers": suppliers
    }

@app.get("/extract/sales")
async def extract_sales_invoices(company_name: Optional[str] = None, from_alter_id: Optional[int] = None):
    """Extracts Sales Invoices with item lines."""
    res = await extract_vouchers(company_name=company_name, from_alter_id=from_alter_id)
    all_vouchers = res.get("vouchers", [])
    sales = [v for v in all_vouchers if any(k in (v.get("voucherType") or "").lower() for k in ["sales", "credit note"])]
    return {"status": "success", "count": len(sales), "company": company_name, "sales_invoices": sales}

@app.get("/extract/purchases")
async def extract_purchase_invoices(company_name: Optional[str] = None, from_alter_id: Optional[int] = None):
    """Extracts Purchase Invoices with item lines."""
    res = await extract_vouchers(company_name=company_name, from_alter_id=from_alter_id)
    all_vouchers = res.get("vouchers", [])
    purchases = [v for v in all_vouchers if any(k in (v.get("voucherType") or "").lower() for k in ["purchase", "debit note"])]
    return {"status": "success", "count": len(purchases), "company": company_name, "purchase_invoices": purchases}

@app.get("/extract/bank_transactions")
async def extract_bank_transactions(company_name: Optional[str] = None, from_alter_id: Optional[int] = None):
    """Extracts Receipts, Payments and Bank/Cash Contra."""
    res = await extract_vouchers(company_name=company_name, from_alter_id=from_alter_id)
    all_vouchers = res.get("vouchers", [])
    bank_txns = [v for v in all_vouchers if any(k in (v.get("voucherType") or "").lower() for k in ["receipt", "payment", "contra"])]
    return {"status": "success", "count": len(bank_txns), "company": company_name, "bank_transactions": bank_txns}

@app.get("/extract/outstanding")
async def extract_outstanding_bills(company_name: Optional[str] = None):
    """Extracts aggregated Bill-wise Outstanding from vouchers."""
    res = await extract_vouchers(company_name=company_name)
    all_vouchers = res.get("vouchers", [])
    all_bills = []
    for v in all_vouchers:
        for b in v.get("billAllocations", []):
            all_bills.append(b)
    return {"status": "success", "count": len(all_bills), "company": company_name, "bills_outstanding": all_bills}

@app.post("/import/voucher")
async def import_voucher_endpoint(payload: dict):
    """Imports an online voucher/invoice payload into Tally Prime."""
    host = payload.get("host", CONFIG["host"])
    port = int(payload.get("port", CONFIG["port"]))
    res = await tally_importer.import_voucher(host=host, port=port, voucher_data=payload)
    if not res.get("success"):
        raise HTTPException(400, res.get("error") or "Voucher import failed")
    return res
