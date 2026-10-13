import re
import random
from datetime import datetime, date
from typing import Dict, Any, Tuple, Optional, List, Set, Union
from shared.logging_config import get_logger
from apps.backend.adapters.tally.xml_builders.common import (
    escape_xml,
    _clean_str,
    format_tally_date,
)

logger = get_logger("app.adapters.tally.voucher_builder")

__all__ = [
    "build_voucher_import_xml",
    "_lookup_party_master_gstin",
    "_lookup_item_master_unit",
    "_lookup_item_master_hsn",
    "_ITEM_MASTER_UNIT_CACHE",
    "_ITEM_MASTER_HSN_CACHE",
    "_PARTY_MASTER_GSTIN_CACHE",
    "_balance_double_entry_accounting",
]

def _parse_float(value: Any, default: float = 0.0) -> float:
    """Safely extracts a floating point number from various string or numeric representations."""
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().replace(",", "")
    match = re.search(r"[-+]?\d*\.?\d+", s)
    if match:
        try:
            return float(match.group(0))
        except ValueError:
            return default
    return default

def _extract_item_name(item: Any) -> str:
    """Extracts stock item name across all common web/JSON naming variations."""
    if not item:
        return ""
    if isinstance(item, str):
        return _clean_str(item)
    if isinstance(item, dict):
        for key in (
            "stockItemName", "stock_item_name", "stock_item", "stockItem",
            "itemName", "item_name", "name", "productName", "product_name",
            "product", "title", "description", "itemDescription"
        ):
            val = item.get(key)
            if isinstance(val, str) and _clean_str(val):
                return _clean_str(val)
            elif isinstance(val, dict):
                sub_name = val.get("name") or val.get("itemName") or val.get("stockItemName")
                if sub_name and _clean_str(sub_name):
                    return _clean_str(sub_name)

        raw_dict = item.get("raw")
        if isinstance(raw_dict, dict):
            for key in ("name", "stockItemName", "itemName", "stock_item_name", "stock_item"):
                val = raw_dict.get(key)
                if val and _clean_str(val):
                    return _clean_str(val)

    return ""

def _extract_items_list(voucher_data: Dict[str, Any]) -> list:
    """Finds the items list from various incoming payload keys."""
    for key in (
        "items", "inventory_entries", "inventoryEntries", "inventory",
        "stock_items", "stockItems", "line_items", "lineItems",
        "lines", "products", "itemsList"
    ):
        val = voucher_data.get(key)
        if isinstance(val, list) and len(val) > 0:
            return val

    raw = voucher_data.get("raw")
    if isinstance(raw, dict):
        for key in ("inventory_entries", "inventoryEntries", "items", "line_items"):
            val = raw.get(key)
            if isinstance(val, list) and len(val) > 0:
                return val

    return []

def _extract_party_ledger(voucher_data: Dict[str, Any]) -> str:
    """Extracts party ledger name from payload."""
    for key in (
        "party_ledger", "partyLedger", "party_name", "partyName",
        "party", "customer", "customer_name", "customerName",
        "ledger_name", "ledgerName", "party_ledger_name", "debtor"
    ):
        val = voucher_data.get(key)
        if isinstance(val, str) and _clean_str(val):
            return _clean_str(val)
        elif isinstance(val, dict):
            sub = val.get("name") or val.get("ledgerName") or val.get("customerName")
            if sub and _clean_str(sub):
                return _clean_str(sub)

    raw = voucher_data.get("raw")
    if isinstance(raw, dict):
        for key in ("partyLedger", "party_ledger", "party", "party_name"):
            val = raw.get(key)
            if isinstance(val, str) and _clean_str(val):
                return _clean_str(val)

    return "Cash"

def _extract_company_name(voucher_data: Dict[str, Any]) -> str:
    """Extracts cleaned company name from payload, with companyId database lookup fallback."""
    for key in ("company_name", "companyName", "company", "current_company"):
        val = voucher_data.get(key)
        cleaned = _clean_str(val)
        if cleaned:
            return cleaned

    comp_id = voucher_data.get("companyId") or voucher_data.get("company_id") or voucher_data.get("company_guid")
    if comp_id:
        try:
            from shared.db.mongo_client import get_mongo_db
            from bson import ObjectId
            db = get_mongo_db()
            c_doc = None
            if ObjectId.is_valid(str(comp_id)):
                c_doc = db.companies.find_one({"_id": ObjectId(str(comp_id))})
            if not c_doc:
                c_doc = db.companies.find_one({"cloud_company_id": str(comp_id)})
            if not c_doc:
                c_doc = db.companies.find_one({"id": str(comp_id)})
            if c_doc:
                return _clean_str(c_doc.get("company_name") or c_doc.get("name") or c_doc.get("tallyCompanyName"))
        except Exception as exc:
            logger.debug(f"Company ID lookup failed in _extract_company_name: {exc}")

    return ""

GST_STATE_CODES: Dict[str, str] = {
    "01": "Jammu and Kashmir", "02": "Himachal Pradesh", "03": "Punjab", "04": "Chandigarh",
    "05": "Uttarakhand", "06": "Haryana", "07": "Delhi", "08": "Rajasthan",
    "09": "Uttar Pradesh", "10": "Bihar", "11": "Sikkim", "12": "Arunachal Pradesh",
    "13": "Nagaland", "14": "Manipur", "15": "Mizoram", "16": "Tripura",
    "17": "Meghalaya", "18": "Assam", "19": "West Bengal", "20": "Jharkhand",
    "21": "Odisha", "22": "Chhattisgarh", "23": "Madhya Pradesh", "24": "Gujarat",
    "26": "Dadra and Nagar Haveli and Daman and Diu", "27": "Maharashtra", "28": "Andhra Pradesh",
    "29": "Karnataka", "30": "Goa", "31": "Lakshadweep", "32": "Kerala",
    "33": "Tamil Nadu", "34": "Puducherry", "35": "Andaman and Nicobar Islands",
    "36": "Telangana", "37": "Andhra Pradesh", "38": "Ladakh"
}

_PARTY_MASTER_GSTIN_CACHE: Dict[Tuple[str, str], Tuple[Optional[str], Optional[str], Optional[str]]] = {}

def _lookup_party_master_gstin(company_name: str, party_name: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Looks up the GSTIN, State, and Address for a Party from MongoDB customers, suppliers, or ledgers.
    """
    if not party_name:
        return None, None, None
    key = (company_name or "", party_name.strip().lower())
    if key in _PARTY_MASTER_GSTIN_CACHE:
        return _PARTY_MASTER_GSTIN_CACHE[key]
    try:
        from shared.db.mongo_client import get_mongo_db
        db = get_mongo_db()
        clean_name = party_name.strip()
        import re
        p_rgx = re.compile(f"^{re.escape(clean_name)}$", re.IGNORECASE)

        for col_name in ("customers", "suppliers", "ledgers"):
            col = db[col_name]
            doc = None
            if company_name:
                comp_rgx = re.compile(f"^{re.escape(company_name.strip())}$", re.IGNORECASE)
                doc = col.find_one({"company_name": comp_rgx, "name": p_rgx})
                if not doc:
                    doc = col.find_one({"company_name": comp_rgx, "name": clean_name})
            if not doc:
                doc = col.find_one({"name": p_rgx}) or col.find_one({"name": clean_name})
            if doc:
                g = _clean_str(doc.get("gstin") or doc.get("gstNumber") or doc.get("party_gstin") or (doc.get("raw") or {}).get("gstin"))
                s = _clean_str(doc.get("state") or doc.get("party_state") or (doc.get("raw") or {}).get("state"))
                a = _clean_str(doc.get("address") or (doc.get("raw") or {}).get("address"))
                if g or s or a:
                    res = (g or None, s or None, a or None)
                    _PARTY_MASTER_GSTIN_CACHE[key] = res
                    return res
    except Exception as exc:
        logger.debug(f"Party master lookup notice: {exc}")
    _PARTY_MASTER_GSTIN_CACHE[key] = (None, None, None)
    return None, None, None

_ITEM_MASTER_UNIT_CACHE: Dict[Tuple[str, str], Optional[str]] = {}

def _lookup_item_master_unit(company_name: str, item_name: str) -> Optional[str]:
    """
    Looks up the registered Base Unit of Measure (UOM) for the Stock Item from MongoDB.
    Ensures that Tally receives the exact unit expected by its master database,
    preventing Tally from blanking out Quantity and Rate fields on unit mismatch.
    """
    if not item_name:
        return None
    key = (company_name or "", item_name.strip().lower())
    if key in _ITEM_MASTER_UNIT_CACHE:
        return _ITEM_MASTER_UNIT_CACHE[key]

    try:
        from shared.db.mongo_client import get_mongo_db
        db = get_mongo_db()
        clean_name = item_name.strip()
        import re
        name_rgx = re.compile(f"^{re.escape(clean_name)}$", re.IGNORECASE)

        for col_name in ("stock_items", "stocks", "items", "stockbalances"):
            col = db[col_name]
            # Try with company first
            if company_name:
                comp_rgx = re.compile(f"^{re.escape(company_name.strip())}$", re.IGNORECASE)
                doc = col.find_one({"company_name": comp_rgx, "$or": [{"itemName": name_rgx}, {"name": name_rgx}]})
                if not doc:
                    doc = col.find_one({"company_name": comp_rgx, "$or": [{"itemName": clean_name}, {"name": clean_name}]})
                if doc:
                    u = _clean_str(doc.get("unit") or doc.get("baseUnits") or doc.get("base_units") or doc.get("uom") or doc.get("units") or (doc.get("unit_details") or {}).get("symbol") or (doc.get("unit_details") or {}).get("name"))
                    if u and not u.isdigit():
                        _ITEM_MASTER_UNIT_CACHE[key] = u
                        return u

            # Try without company
            doc = col.find_one({"$or": [{"itemName": name_rgx}, {"name": name_rgx}]})
            if not doc:
                doc = col.find_one({"$or": [{"itemName": clean_name}, {"name": clean_name}]})
            if doc:
                u = _clean_str(doc.get("unit") or doc.get("baseUnits") or doc.get("base_units") or doc.get("uom") or doc.get("units") or (doc.get("unit_details") or {}).get("symbol") or (doc.get("unit_details") or {}).get("name"))
                if u and not u.isdigit():
                    _ITEM_MASTER_UNIT_CACHE[key] = u
                    return u
    except Exception as exc:
        logger.debug(f"Master unit lookup error for '{item_name}': {exc}")

    _ITEM_MASTER_UNIT_CACHE[key] = None
    return None

_ITEM_MASTER_HSN_CACHE: Dict[Tuple[str, str], Optional[str]] = {}

def _lookup_item_master_hsn(company_name: str, item_name: str) -> Optional[str]:
    """
    Looks up the registered HSN/SAC Code for the Stock Item from MongoDB collections.
    Falls back to parent Stock Group's HSN if not on the item directly.
    """
    if not item_name:
        return None
    key = (company_name or "", item_name.strip().lower())
    if key in _ITEM_MASTER_HSN_CACHE:
        return _ITEM_MASTER_HSN_CACHE[key]

    try:
        from shared.db.mongo_client import get_mongo_db
        db = get_mongo_db()
        clean_name = item_name.strip()
        import re
        name_rgx = re.compile(f"^{re.escape(clean_name)}$", re.IGNORECASE)

        for col_name in ("stock_items", "stocks", "items", "stockbalances"):
            col = db[col_name]
            if company_name:
                comp_rgx = re.compile(f"^{re.escape(company_name.strip())}$", re.IGNORECASE)
                doc = col.find_one({"company_name": comp_rgx, "$or": [{"itemName": name_rgx}, {"name": name_rgx}]})
                if not doc:
                    doc = col.find_one({"company_name": comp_rgx, "$or": [{"itemName": clean_name}, {"name": clean_name}]})
                if doc:
                    h = _clean_str(doc.get("hsnCode") or doc.get("hsn_code") or doc.get("hsn"))
                    if h:
                        _ITEM_MASTER_HSN_CACHE[key] = h
                        return h
                    parent_grp = _clean_str(doc.get("parent") or doc.get("group"))
                    if parent_grp:
                        grp_doc = db.stock_groups.find_one({"name": re.compile(f"^{re.escape(parent_grp)}$", re.IGNORECASE)})
                        if grp_doc:
                            gh = _clean_str(grp_doc.get("hsnCode") or grp_doc.get("hsn_code") or grp_doc.get("hsn"))
                            if gh:
                                _ITEM_MASTER_HSN_CACHE[key] = gh
                                return gh

            doc = col.find_one({"$or": [{"itemName": name_rgx}, {"name": name_rgx}]})
            if not doc:
                doc = col.find_one({"$or": [{"itemName": clean_name}, {"name": clean_name}]})
            if doc:
                h = _clean_str(doc.get("hsnCode") or doc.get("hsn_code") or doc.get("hsn"))
                if h:
                    _ITEM_MASTER_HSN_CACHE[key] = h
                    return h
                parent_grp = _clean_str(doc.get("parent") or doc.get("group"))
                if parent_grp:
                    grp_doc = db.stock_groups.find_one({"name": re.compile(f"^{re.escape(parent_grp)}$", re.IGNORECASE)})
                    if grp_doc:
                        gh = _clean_str(grp_doc.get("hsnCode") or grp_doc.get("hsn_code") or grp_doc.get("hsn"))
                        if gh:
                            _ITEM_MASTER_HSN_CACHE[key] = gh
                            return gh
    except Exception as exc:
        logger.debug(f"Master HSN lookup error for '{item_name}': {exc}")

    _ITEM_MASTER_HSN_CACHE[key] = None
    return None

def _balance_double_entry_accounting(
    ledger_entries_xml: list,
    inventory_entries_xml: list,
    has_valid_items: bool,
    voucher_data: Dict[str, Any]
) -> None:
    """
    Guarantees that total Debits + total Credits sum to 0.00 down to the exact paisa.
    If a penny discrepancy (0 < |diff| <= 1.00) exists due to floating-point rounding
    of line items/taxes, automatically appends a balanced Round Off ledger line.
    """
    total_balance = 0.0

    for entry in ledger_entries_xml:
        m = re.search(r"<AMOUNT>([-+]?\d+\.?\d*)</AMOUNT>", entry)
        if m:
            try:
                total_balance += float(m.group(1))
            except ValueError:
                pass

    for inv_entry in inventory_entries_xml:
        allocs = re.findall(r"<ACCOUNTINGALLOCATIONS\.LIST>.*?</ACCOUNTINGALLOCATIONS\.LIST>", inv_entry, re.DOTALL)
        for alloc in allocs:
            m = re.search(r"<AMOUNT>([-+]?\d+\.?\d*)</AMOUNT>", alloc)
            if m:
                try:
                    total_balance += float(m.group(1))
                except ValueError:
                    pass

    diff = round(total_balance, 2)
    if diff != 0.0:
        if abs(diff) <= 1.00:
            round_off_tag = "LEDGERENTRIES.LIST" if has_valid_items else "ALLLEDGERENTRIES.LIST"
            if diff < 0:
                ro_amt = abs(diff)
                ro_deemed = "No"
            else:
                ro_amt = -abs(diff)
                ro_deemed = "Yes"

            ledger_entries_xml.append(f"""<{round_off_tag}>
                    <LEDGERNAME>Round Off</LEDGERNAME>
                    <ISDEEMEDPOSITIVE>{ro_deemed}</ISDEEMEDPOSITIVE>
                    <AMOUNT>{ro_amt:.2f}</AMOUNT>
                </{round_off_tag}>""")
            voucher_data["_has_round_off"] = True
            logger.info(f"Auto-balanced voucher #{voucher_data.get('voucher_number')} with Round Off of {ro_amt:.2f} (original imbalance: {diff:.2f})")
        else:
            logger.warning(f"Significant accounting imbalance of {diff:.2f} detected in voucher #{voucher_data.get('voucher_number')}")

def build_voucher_import_xml(voucher_data: Dict[str, Any]) -> str:
    """
    Constructs a valid Tally XML Import envelope with ACTION="Create" to insert a VOUCHER
    (Sales Invoice, Item Sales Invoice, Receipt, Payment, etc.) into Tally Prime via HTTP interface (port 9000).
    Robustly handles any JSON key variations and formats.
    """
    company_name = escape_xml(_extract_company_name(voucher_data))
    voucher_type = escape_xml(
        _clean_str(
            voucher_data.get("voucher_type")
            or voucher_data.get("voucherType")
            or voucher_data.get("vtype")
            or voucher_data.get("type")
        )
        or "Sales"
    )
    raw_date = str(
        voucher_data.get("date")
        or voucher_data.get("voucherDate")
        or voucher_data.get("effectiveDate")
        or voucher_data.get("invoice_date")
        or ""
    )
    tally_date = format_tally_date(raw_date)

    v_raw_num = (
        voucher_data.get("voucher_number")
        or voucher_data.get("voucherNumber")
        or voucher_data.get("invoice_number")
        or voucher_data.get("bill_no")
        or voucher_data.get("reference")
    )
    if not v_raw_num or not _clean_str(v_raw_num):
        import random
        v_raw_num = f"WEB-{datetime.now().strftime('%d%H%M%S')}-{random.randint(100, 999)}"
    voucher_data["_generated_voucher_number"] = str(v_raw_num)
    voucher_number = escape_xml(str(v_raw_num))
    reference = escape_xml(_clean_str(voucher_data.get("reference", voucher_number)) or voucher_number)
    narration = escape_xml(_clean_str(voucher_data.get("narration")) or "Imported from Cloud/Web 2-Way Sync")
    party_ledger = escape_xml(_extract_party_ledger(voucher_data))

    raw_party_gstin = _clean_str(
        voucher_data.get("gstin")
        or voucher_data.get("gstinUin")
        or voucher_data.get("gstNumber")
        or voucher_data.get("party_gstin")
        or voucher_data.get("partyGstin")
        or voucher_data.get("consigneeGstinUin")
        or voucher_data.get("buyerGstin")
        or voucher_data.get("supplierGstin")
    )
    raw_party_state = _clean_str(
        voucher_data.get("state")
        or voucher_data.get("party_state")
        or voucher_data.get("placeOfSupply")
        or voucher_data.get("place_of_supply")
        or voucher_data.get("supplierState")
    )
    raw_party_address = _clean_str(
        voucher_data.get("address")
        or voucher_data.get("party_address")
        or voucher_data.get("partyAddress")
        or voucher_data.get("consigneeAddress")
    )

    auto_gstin, auto_state, auto_addr = _lookup_party_master_gstin(company_name, party_ledger)
    party_gstin = raw_party_gstin or auto_gstin or ""
    party_address = raw_party_address or auto_addr or ""
    party_state = raw_party_state or auto_state or ""
    if not party_state and party_gstin and len(party_gstin) >= 2 and party_gstin[:2] in GST_STATE_CODES:
        party_state = GST_STATE_CODES[party_gstin[:2]]

    total_amount = _parse_float(
        voucher_data.get("amount")
        or voucher_data.get("total_amount")
        or voucher_data.get("total"),
        0.0,
    )

    company_tag = f"<SVCURRENTCOMPANY>{company_name}</SVCURRENTCOMPANY>" if company_name else ""

    v_type_lower = voucher_type.lower()
    is_stock_journal = "stock journal" in v_type_lower
    is_physical_stock = "physical stock" in v_type_lower

    if is_physical_stock:
        ps_items = _extract_items_list(voucher_data)
        ps_entries_xml = []
        for item in ps_items:
            i_name = _extract_item_name(item)
            if not i_name:
                continue
            i_qty = _parse_float(
                item.get("quantity") if item.get("quantity") is not None
                else item.get("qty", item.get("actualQty", item.get("billedQty", 1.0))),
                1.0,
            )
            if i_qty <= 0:
                i_qty = 1.0
            master_unit = _lookup_item_master_unit(company_name, i_name)
            i_unit = master_unit or _clean_str(item.get("units") or item.get("unit") or item.get("uom")) or "Pcs"
            qty_str = f"{int(i_qty)} {i_unit}" if float(i_qty).is_integer() else f"{i_qty:.3f}".rstrip("0").rstrip(".") + f" {i_unit}"
            godown = _clean_str(item.get("godown") or item.get("godown_name") or voucher_data.get("godown") or voucher_data.get("godown_name")) or "Main Location"
            batch = _clean_str(item.get("batch") or item.get("batch_name") or item.get("batch_no")) or "Primary Batch"

            ps_entries_xml.append(f""" <INVENTORYENTRIES.LIST>
                    <STOCKITEMNAME>{escape_xml(i_name)}</STOCKITEMNAME>
                    <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
                    <ACTUALQTY>{escape_xml(qty_str)}</ACTUALQTY>
                    <BILLEDQTY>{escape_xml(qty_str)}</BILLEDQTY>
                    <BATCHALLOCATIONS.LIST>
                        <GODOWNNAME>{escape_xml(godown)}</GODOWNNAME>
                        <BATCHNAME>{escape_xml(batch)}</BATCHNAME>
                        <ACTUALQTY>{escape_xml(qty_str)}</ACTUALQTY>
                        <BILLEDQTY>{escape_xml(qty_str)}</BILLEDQTY>
                    </BATCHALLOCATIONS.LIST>
                </INVENTORYENTRIES.LIST>""")

        inventory_block = ("\n" + "\n".join(ps_entries_xml)) if ps_entries_xml else ""
        return f"""<ENVELOPE>
    <HEADER>
        <TALLYREQUEST>Import Data</TALLYREQUEST>
    </HEADER>
    <BODY>
        <IMPORTDATA>
            <REQUESTDESC>
                <REPORTNAME>Vouchers</REPORTNAME>
                <STATICVARIABLES>
                    {company_tag}
                </STATICVARIABLES>
            </REQUESTDESC>
            <REQUESTDATA>
                <TALLYMESSAGE xmlns:UDF="TallyUDF">
                    <VOUCHER ACTION="Create" VCHTYPE="{voucher_type}">
                        <DATE>{tally_date}</DATE>
                        <EFFECTIVEDATE>{tally_date}</EFFECTIVEDATE>
                        <VOUCHERTYPENAME>{voucher_type}</VOUCHERTYPENAME>
                        <VOUCHERNUMBER>{voucher_number}</VOUCHERNUMBER>
                        <REFERENCE>{reference}</REFERENCE>
                        <NARRATION>{narration}</NARRATION>{inventory_block}
                    </VOUCHER>
                </TALLYMESSAGE>
            </REQUESTDATA>
        </IMPORTDATA>
    </BODY>
</ENVELOPE>"""

    if is_stock_journal:
        out_items_raw = list(voucher_data.get("source_items") or voucher_data.get("consumption_items") or voucher_data.get("items_out") or [])
        in_items_raw = list(voucher_data.get("destination_items") or voucher_data.get("production_items") or voucher_data.get("items_in") or [])
        gen_items = _extract_items_list(voucher_data)

        if not out_items_raw and not in_items_raw:
            for it in gen_items:
                itype = str(it.get("type", "")).lower()
                if itype in ("source", "consumption", "out", "outward", "issue"):
                    out_items_raw.append(it)
                elif itype in ("destination", "production", "in", "inward", "receipt"):
                    in_items_raw.append(it)

            if not out_items_raw and not in_items_raw:
                out_items_raw = list(gen_items)
                in_items_raw = list(gen_items)

        src_godown_default = _clean_str(voucher_data.get("source_godown") or voucher_data.get("from_godown") or voucher_data.get("godown")) or "Main Location"
        dest_godown_default = _clean_str(voucher_data.get("destination_godown") or voucher_data.get("to_godown") or voucher_data.get("dest_godown") or voucher_data.get("godown")) or "Main Location"

        sj_entries_xml = []

        for item in out_items_raw:
            i_name = _extract_item_name(item)
            if not i_name:
                continue
            i_qty = _parse_float(item.get("quantity") if item.get("quantity") is not None else item.get("qty", 1.0), 1.0)
            if i_qty <= 0:
                i_qty = 1.0
            master_unit = _lookup_item_master_unit(company_name, i_name)
            i_unit = master_unit or _clean_str(item.get("units") or item.get("unit") or item.get("uom")) or "Pcs"
            qty_str = f"{int(i_qty)} {i_unit}" if float(i_qty).is_integer() else f"{i_qty:.3f}".rstrip("0").rstrip(".") + f" {i_unit}"
            i_rate = _parse_float(item.get("rate") if item.get("rate") is not None else item.get("price", 0.0), 0.0)
            amt = abs(round(_parse_float(item.get("amount") or item.get("total"), i_qty * i_rate), 2))
            rate_str = f"{i_rate:.2f}/{i_unit}" if i_unit else f"{i_rate:.2f}"
            g_name = _clean_str(item.get("source_godown") or item.get("godown") or src_godown_default) or "Main Location"
            b_name = _clean_str(item.get("batch") or item.get("batch_name") or item.get("batch_no")) or "Primary Batch"

            sj_entries_xml.append(f"""<INVENTORYENTRIESOUT.LIST>
                    <STOCKITEMNAME>{escape_xml(i_name)}</STOCKITEMNAME>
                    <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
                    <RATE>{escape_xml(rate_str)}</RATE>
                    <AMOUNT>{amt:.2f}</AMOUNT>
                    <ACTUALQTY>-{escape_xml(qty_str)}</ACTUALQTY>
                    <BILLEDQTY>-{escape_xml(qty_str)}</BILLEDQTY>
                    <BATCHALLOCATIONS.LIST>
                        <GODOWNNAME>{escape_xml(g_name)}</GODOWNNAME>
                        <BATCHNAME>{escape_xml(b_name)}</BATCHNAME>
                        <AMOUNT>{amt:.2f}</AMOUNT>
                        <ACTUALQTY>-{escape_xml(qty_str)}</ACTUALQTY>
                        <BILLEDQTY>-{escape_xml(qty_str)}</BILLEDQTY>
                    </BATCHALLOCATIONS.LIST>
                </INVENTORYENTRIESOUT.LIST>""")

        for item in in_items_raw:
            i_name = _extract_item_name(item)
            if not i_name:
                continue
            i_qty = _parse_float(item.get("quantity") if item.get("quantity") is not None else item.get("qty", 1.0), 1.0)
            if i_qty <= 0:
                i_qty = 1.0
            master_unit = _lookup_item_master_unit(company_name, i_name)
            i_unit = master_unit or _clean_str(item.get("units") or item.get("unit") or item.get("uom")) or "Pcs"
            qty_str = f"{int(i_qty)} {i_unit}" if float(i_qty).is_integer() else f"{i_qty:.3f}".rstrip("0").rstrip(".") + f" {i_unit}"
            i_rate = _parse_float(item.get("rate") if item.get("rate") is not None else item.get("price", 0.0), 0.0)
            amt = abs(round(_parse_float(item.get("amount") or item.get("total"), i_qty * i_rate), 2))
            rate_str = f"{i_rate:.2f}/{i_unit}" if i_unit else f"{i_rate:.2f}"
            g_name = _clean_str(item.get("destination_godown") or item.get("godown") or dest_godown_default) or "Main Location"
            b_name = _clean_str(item.get("batch") or item.get("batch_name") or item.get("batch_no")) or "Primary Batch"

            sj_entries_xml.append(f"""<INVENTORYENTRIESIN.LIST>
                    <STOCKITEMNAME>{escape_xml(i_name)}</STOCKITEMNAME>
                    <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
                    <RATE>{escape_xml(rate_str)}</RATE>
                    <AMOUNT>-{amt:.2f}</AMOUNT>
                    <ACTUALQTY>{escape_xml(qty_str)}</ACTUALQTY>
                    <BILLEDQTY>{escape_xml(qty_str)}</BILLEDQTY>
                    <BATCHALLOCATIONS.LIST>
                        <GODOWNNAME>{escape_xml(g_name)}</GODOWNNAME>
                        <BATCHNAME>{escape_xml(b_name)}</BATCHNAME>
                        <AMOUNT>-{amt:.2f}</AMOUNT>
                        <ACTUALQTY>{escape_xml(qty_str)}</ACTUALQTY>
                        <BILLEDQTY>{escape_xml(qty_str)}</BILLEDQTY>
                    </BATCHALLOCATIONS.LIST>
                </INVENTORYENTRIESIN.LIST>""")

        inventory_block = ("\n" + "\n".join(sj_entries_xml)) if sj_entries_xml else ""
        return f"""<ENVELOPE>
    <HEADER>
        <TALLYREQUEST>Import Data</TALLYREQUEST>
    </HEADER>
    <BODY>
        <IMPORTDATA>
            <REQUESTDESC>
                <REPORTNAME>Vouchers</REPORTNAME>
                <STATICVARIABLES>
                    {company_tag}
                </STATICVARIABLES>
            </REQUESTDESC>
            <REQUESTDATA>
                <TALLYMESSAGE xmlns:UDF="TallyUDF">
                    <VOUCHER ACTION="Create" VCHTYPE="{voucher_type}">
                        <DATE>{tally_date}</DATE>
                        <EFFECTIVEDATE>{tally_date}</EFFECTIVEDATE>
                        <VOUCHERTYPENAME>{voucher_type}</VOUCHERTYPENAME>
                        <VOUCHERNUMBER>{voucher_number}</VOUCHERNUMBER>
                        <REFERENCE>{reference}</REFERENCE>
                        <NARRATION>{narration}</NARRATION>{inventory_block}
                    </VOUCHER>
                </TALLYMESSAGE>
            </REQUESTDATA>
        </IMPORTDATA>
    </BODY>
</ENVELOPE>"""

    sales_ledger = escape_xml(
        _clean_str(
            voucher_data.get("sales_ledger")
            or voucher_data.get("salesLedger")
            or voucher_data.get("sales_account")
            or voucher_data.get("salesAccount")
            or voucher_data.get("income_ledger")
        )
        or "Sales"
    )

    items = _extract_items_list(voucher_data)
    if "journal" in voucher_type.lower() and not is_stock_journal:
        items = []
    inventory_entries_xml = []
    calculated_items_total = 0.0

    if items and isinstance(items, list):
        for item in items:
            i_name = _extract_item_name(item)
            if not i_name:
                logger.warning(f"Skipping item entry with missing/empty item name in payload: {item}")
                continue

            i_qty = _parse_float(
                item.get("quantity")
                if item.get("quantity") is not None
                else item.get("qty", item.get("actualQty", item.get("billedQty", 1.0))),
                1.0,
            )
            if i_qty <= 0:
                i_qty = 1.0

            master_unit = _lookup_item_master_unit(company_name, i_name)
            raw_unit = _clean_str(
                item.get("units")
                or item.get("unit")
                or item.get("uom")
                or item.get("symbol")
                or item.get("baseUnits")
                or item.get("base_units")
            )
            # If incoming unit is purely numeric (e.g. "442" database ID), discard it
            if raw_unit and raw_unit.isdigit():
                raw_unit = ""

            unit_aliases = {
                "pcs": "Pcs", "piece": "Pcs", "pieces": "Pcs",
                "nos": "Nos", "no": "Nos", "number": "Nos", "numbers": "Nos",
                "box": "Box", "boxes": "Box",
                "kgs": "Kgs", "kg": "Kgs", "kilogram": "Kgs", "kilograms": "Kgs",
                "gms": "Gms", "gm": "Gms", "gram": "Gms", "grams": "Gms",
                "mtr": "Mtr", "meter": "Mtr", "meters": "Mtr", "mtrs": "Mtr",
                "ltr": "Ltr", "liter": "Ltr", "litre": "Ltr", "liters": "Ltr",
                "pkt": "Pkt", "packet": "Pkt", "packets": "Pkt",
                "bag": "Bag", "bags": "Bag",
                "set": "Set", "sets": "Set",
                "btl": "Btl", "bottle": "Btl", "bottles": "Btl",
                "can": "Can", "cans": "Can",
                "tin": "Tin", "tins": "Tin",
                "crt": "Crt", "carton": "Crt", "cartons": "Crt",
                "sqft": "Sqft", "sqm": "Sqm", "ton": "Ton", "tons": "Ton", "mt": "MT"
            }

            if master_unit:
                i_unit = master_unit
            elif raw_unit:
                i_unit = unit_aliases.get(raw_unit.lower(), raw_unit)
            else:
                i_unit = "Pcs"

            master_hsn = _lookup_item_master_hsn(company_name, i_name)
            raw_hsn = _clean_str(
                item.get("hsn_code")
                or item.get("hsnCode")
                or item.get("hsn")
                or item.get("hsnCodeValue")
                or item.get("hsn_code_value")
            )
            i_hsn = raw_hsn or master_hsn or ""

            i_rate = _parse_float(
                item.get("rate")
                if item.get("rate") is not None
                else item.get("price", item.get("unitPrice", item.get("unit_price", 0.0))),
                0.0,
            )

            disc_pct = _parse_float(
                item.get("discount")
                or item.get("discount_pct")
                or item.get("discountPct")
                or item.get("disc")
                or 0.0,
                0.0,
            )

            explicit_amt = item.get("amount") or item.get("net_amount") or item.get("netAmount") or item.get("total")
            if explicit_amt is not None:
                net_amt = round(_parse_float(explicit_amt, 0.0), 2)
                if i_rate == 0.0 and i_qty > 0 and net_amt > 0:
                    i_rate = round(net_amt / i_qty, 2)
            else:
                gross_amt = i_qty * i_rate
                disc_amt = round(gross_amt * (disc_pct / 100.0), 2) if disc_pct > 0 else 0.0
                net_amt = round(gross_amt - disc_amt, 2)

            calculated_items_total += net_amt

            if float(i_qty).is_integer():
                qty_str = f"{int(i_qty)} {i_unit}"
            else:
                qty_str = f"{i_qty:.3f}".rstrip("0").rstrip(".") + f" {i_unit}"

            rate_str = f"{i_rate:.2f}/{i_unit}" if i_unit else f"{i_rate:.2f}"

            order_no_val = _clean_str(
                item.get("order_no")
                or item.get("orderNo")
                or item.get("order_number")
                or item.get("orderNumber")
                or voucher_data.get("order_no")
                or voucher_data.get("orderNo")
                or voucher_data.get("order_number")
                or voucher_data.get("orderNumber")
                or (v_raw_num if "order" in voucher_type.lower() else "")
            )
            raw_due_date = (
                item.get("due_date")
                or item.get("dueDate")
                or item.get("order_due_date")
                or item.get("orderDueDate")
                or item.get("delivery_date")
                or item.get("deliveryDate")
                or voucher_data.get("due_date")
                or voucher_data.get("dueDate")
                or voucher_data.get("order_due_date")
                or voucher_data.get("orderDueDate")
                or voucher_data.get("delivery_date")
                or voucher_data.get("deliveryDate")
            )
            order_due_date_val = format_tally_date(str(raw_due_date)) if raw_due_date else (tally_date if "order" in voucher_type.lower() else "")

            godown_val = _clean_str(
                item.get("godown")
                or item.get("godown_name")
                or item.get("godownName")
                or item.get("location")
                or item.get("warehouse")
            )
            if godown_val and godown_val.strip().lower() in ("main", "default", "primary"):
                godown_val = "Main Location"

            batch_val = _clean_str(
                item.get("batch")
                or item.get("batch_name")
                or item.get("batchName")
                or item.get("batch_no")
                or item.get("batchNo")
            ) or "Primary Batch"

            is_order_voucher = "order" in voucher_type.lower()
            is_purchase = "purchase" in voucher_type.lower()
            is_credit_note = "credit note" in voucher_type.lower() or "sales return" in voucher_type.lower()
            is_debit_note = "debit note" in voucher_type.lower() or "purchase return" in voucher_type.lower()

            if is_purchase or is_credit_note:
                item_deemed_positive = "Yes"
                item_amount = -abs(net_amt)
                alloc_deemed_positive = "Yes"
                alloc_amount = -abs(net_amt)
                if is_purchase:
                    item_alloc_ledger = escape_xml(_clean_str(item.get("purchase_ledger") or item.get("purchaseLedger") or voucher_data.get("purchase_ledger") or voucher_data.get("purchaseLedger")) or "Purchase")
                else:
                    item_alloc_ledger = escape_xml(_clean_str(item.get("credit_note_ledger") or item.get("sales_return_ledger") or voucher_data.get("credit_note_ledger") or voucher_data.get("sales_return_ledger")) or "Sales Return")
            else:
                item_deemed_positive = "No"
                item_amount = abs(net_amt)
                alloc_deemed_positive = "No"
                alloc_amount = abs(net_amt)
                if is_debit_note:
                    item_alloc_ledger = escape_xml(_clean_str(item.get("debit_note_ledger") or item.get("purchase_return_ledger") or voucher_data.get("debit_note_ledger") or voucher_data.get("purchase_return_ledger")) or "Purchase Return")
                else:
                    item_alloc_ledger = escape_xml(_clean_str(item.get("sales_ledger") or item.get("salesLedger") or voucher_data.get("sales_ledger") or voucher_data.get("salesLedger")) or sales_ledger)

            godown_tag = ""
            if godown_val or is_order_voucher or order_no_val:
                g_name = godown_val or "Main Location"
                order_tags = ""
                if order_no_val:
                    order_tags += f"\n <ORDERNO>{escape_xml(order_no_val)}</ORDERNO>"
                if order_due_date_val:
                    order_tags += f"\n <ORDERDUEDATE>{escape_xml(order_due_date_val)}</ORDERDUEDATE>"

                godown_tag = f"""
                        <BATCHALLOCATIONS.LIST>
                            <GODOWNNAME>{escape_xml(g_name)}</GODOWNNAME>
                            <BATCHNAME>{escape_xml(batch_val)}</BATCHNAME>
                            <AMOUNT>{alloc_amount:.2f}</AMOUNT>
                            <ACTUALQTY>{escape_xml(qty_str)}</ACTUALQTY>
                            <BILLEDQTY>{escape_xml(qty_str)}</BILLEDQTY>{order_tags}
                        </BATCHALLOCATIONS.LIST>"""

            discount_tag = f"\n  <DISCOUNT>{disc_pct:g}%</DISCOUNT>" if disc_pct > 0 else ""
            hsn_tag = f"\n <GSTHSNNAME>{escape_xml(i_hsn)}</GSTHSNNAME>" if i_hsn else ""

            accounting_alloc_tag = f"""
                        <ACCOUNTINGALLOCATIONS.LIST>
                            <LEDGERNAME>{item_alloc_ledger}</LEDGERNAME>
                            <ISDEEMEDPOSITIVE>{alloc_deemed_positive}</ISDEEMEDPOSITIVE>
                            <AMOUNT>{alloc_amount:.2f}</AMOUNT>
                        </ACCOUNTINGALLOCATIONS.LIST>"""

            inventory_entries_xml.append(f""" <INVENTORYENTRIES.LIST>
                    <STOCKITEMNAME>{escape_xml(i_name)}</STOCKITEMNAME>
                    <ISDEEMEDPOSITIVE>{item_deemed_positive}</ISDEEMEDPOSITIVE>{hsn_tag}
                    <RATE>{escape_xml(rate_str)}</RATE>
                    <AMOUNT>{item_amount:.2f}</AMOUNT>
                    <ACTUALQTY>{escape_xml(qty_str)}</ACTUALQTY>
                    <BILLEDQTY>{escape_xml(qty_str)}</BILLEDQTY>{discount_tag}{godown_tag}{accounting_alloc_tag}
                </INVENTORYENTRIES.LIST>""")

    has_valid_items = len(inventory_entries_xml) > 0

    tax_entries = []
    explicit_taxes = voucher_data.get("taxes") or voucher_data.get("additional_ledgers")
    if explicit_taxes and isinstance(explicit_taxes, list):
        for extra in explicit_taxes:
            el_name = escape_xml(_clean_str(extra.get("ledger_name") or extra.get("name") or extra.get("tax_name")))
            el_amt = _parse_float(extra.get("amount") or extra.get("tax_amount"), 0.0)
            if el_name and el_amt != 0.0:
                tax_entries.append({"name": el_name, "amount": el_amt})
    else:
        gst_rate = _parse_float(voucher_data.get("gst_rate") or voucher_data.get("tax_rate") or voucher_data.get("gstRate") or voucher_data.get("taxRate"), 0.0)
        if gst_rate <= 0:
            for it in items:
                it_tax = _parse_float(it.get("gst_rate") or it.get("tax_rate") or it.get("gstRate"), 0.0)
                if it_tax > 0:
                    gst_rate = it_tax
                    break

        base_val = calculated_items_total if has_valid_items else total_amount
        if gst_rate > 0 and base_val > 0:
            party_state = _clean_str(voucher_data.get("state") or voucher_data.get("party_state")).lower()
            comp_state = _clean_str(voucher_data.get("company_state")).lower()
            is_inter_state = bool(party_state and comp_state and party_state != comp_state)
            
            total_tax = round(base_val * (gst_rate / 100.0), 2)
            if is_inter_state:
                tax_entries.append({"name": f"IGST {gst_rate:g}%" if f"{gst_rate:g}" not in "0" else "IGST", "amount": total_tax})
            else:
                half_rate = gst_rate / 2.0
                half_tax = round(total_tax / 2.0, 2)
                tax_entries.append({"name": f"CGST {half_rate:g}%" if f"{half_rate:g}" not in "0" else "CGST", "amount": half_tax})
                tax_entries.append({"name": f"SGST {half_rate:g}%" if f"{half_rate:g}" not in "0" else "SGST", "amount": half_tax})

    voucher_data["_calculated_tax_entries"] = tax_entries
    tax_total = sum(t["amount"] for t in tax_entries)

    if has_valid_items and (total_amount <= 0.0 or calculated_items_total > 0):
        total_amount = round(calculated_items_total + tax_total, 2)
    elif tax_total > 0 and total_amount > 0 and not has_valid_items:
        total_amount = round(total_amount + tax_total, 2)

    voucher_data["amount"] = total_amount
    if company_name:
        voucher_data["company_name"] = company_name

    ledger_entries_xml = []
    provided_entries = voucher_data.get("ledger_entries") or voucher_data.get("ledgerEntries")

    if provided_entries and isinstance(provided_entries, list) and not has_valid_items:
        for entry in provided_entries:
            l_name = escape_xml(_clean_str(entry.get("ledger_name") or entry.get("ledgerName") or entry.get("name")))
            if not l_name:
                continue
            amt = _parse_float(entry.get("amount", 0.0))
            is_debit = entry.get("is_debit", False) or entry.get("isDebit", False) or str(entry.get("type", "")).upper() in ("DR", "DEBIT") or (entry.get("isDeemedPositive") == "Yes")
            is_deemed_pos = "Yes" if is_debit else "No"
            tally_amt = -abs(amt) if is_debit else abs(amt)

            ledger_entries_xml.append(f"""<ALLLEDGERENTRIES.LIST>
                    <LEDGERNAME>{l_name}</LEDGERNAME>
                    <ISDEEMEDPOSITIVE>{is_deemed_pos}</ISDEEMEDPOSITIVE>
                    <AMOUNT>{tally_amt:.2f}</AMOUNT>
                </ALLLEDGERENTRIES.LIST>""")
    elif has_valid_items:
        is_purchase_or_cn = "purchase" in voucher_type.lower() or "credit note" in voucher_type.lower() or "sales return" in voucher_type.lower()
        party_deemed_pos = "No" if is_purchase_or_cn else "Yes"
        party_amt = abs(total_amount) if is_purchase_or_cn else -abs(total_amount)
        tax_deemed_pos = "Yes" if is_purchase_or_cn else "No"
        party_gstin_tag = f"\n                    <PARTYGSTIN>{party_gstin}</PARTYGSTIN>" if party_gstin else ""

        ledger_entries_xml.append(f""" <LEDGERENTRIES.LIST>
                    <LEDGERNAME>{party_ledger}</LEDGERNAME>
                    <ISDEEMEDPOSITIVE>{party_deemed_pos}</ISDEEMEDPOSITIVE>
                    <ISPARTYLEDGER>Yes</ISPARTYLEDGER>{party_gstin_tag}
                    <AMOUNT>{party_amt:.2f}</AMOUNT>
                </LEDGERENTRIES.LIST>""")
        for tax in tax_entries:
            t_amt = -abs(tax['amount']) if is_purchase_or_cn else abs(tax['amount'])
            ledger_entries_xml.append(f""" <LEDGERENTRIES.LIST>
                    <LEDGERNAME>{escape_xml(tax['name'])}</LEDGERNAME>
                    <ISDEEMEDPOSITIVE>{tax_deemed_pos}</ISDEEMEDPOSITIVE>
                    <AMOUNT>{t_amt:.2f}</AMOUNT>
                </LEDGERENTRIES.LIST>""")
    else:
        party_gstin_tag = f"\n PARTYGSTIN>{party_gstin}</PARTYGSTIN>" if party_gstin else ""
        if "sale" in voucher_type.lower():
            ledger_entries_xml.append(f"""<ALLLEDGERENTRIES.LIST>
                    <LEDGERNAME>{party_ledger}</LEDGERNAME>
                    <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>{party_gstin_tag}
                    <AMOUNT>-{abs(total_amount):.2f}</AMOUNT>
                </ALLLEDGERENTRIES.LIST>""")
            ledger_entries_xml.append(f""" <ALLLEDGERENTRIES.LIST>
                    <LEDGERNAME>{sales_ledger}</LEDGERNAME>
                    <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
                    <AMOUNT>{abs(total_amount):.2f}</AMOUNT>
                </ALLLEDGERENTRIES.LIST>""")
        elif "receipt" in voucher_type.lower():
            bank_ledger = escape_xml(
                _clean_str(
                    voucher_data.get("bank_ledger")
                    or voucher_data.get("bankLedger")
                    or voucher_data.get("cash_bank_ledger")
                    or voucher_data.get("account")
                    or voucher_data.get("bank_account")
                    or "Cash"
                )
            )
            bill_num = escape_xml(
                _clean_str(
                    voucher_data.get("bill_number")
                    or voucher_data.get("bill_no")
                    or voucher_data.get("invoice_number")
                    or voucher_data.get("billNo")
                )
            )
            bill_alloc_xml = ""
            if bill_num:
                bill_alloc_xml = f"""
                        <BILLALLOCATIONS.LIST>
                            <NAME>{bill_num}</NAME>
                            <BILLTYPE>Agst Ref</BILLTYPE>
                            <AMOUNT>{abs(total_amount):.2f}</AMOUNT>
                        </BILLALLOCATIONS.LIST>"""
            elif v_raw_num:
                bill_alloc_xml = f"""
                        <BILLALLOCATIONS.LIST>
                            <NAME>{v_raw_num}</NAME>
                            <BILLTYPE>On Account</BILLTYPE>
                            <AMOUNT>{abs(total_amount):.2f}</AMOUNT>
                        </BILLALLOCATIONS.LIST>"""

            ledger_entries_xml.append(f""" <ALLLEDGERENTRIES.LIST>
                    <LEDGERNAME>{bank_ledger}</LEDGERNAME>
                    <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
                    <AMOUNT>-{abs(total_amount):.2f}</AMOUNT>
                </ALLLEDGERENTRIES.LIST>""")
            ledger_entries_xml.append(f""" <ALLLEDGERENTRIES.LIST>
                    <LEDGERNAME>{party_ledger}</LEDGERNAME>
                    <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
                    <AMOUNT>{abs(total_amount):.2f}</AMOUNT>{bill_alloc_xml}
                </ALLLEDGERENTRIES.LIST>""")
        elif "payment" in voucher_type.lower():
            bank_ledger = escape_xml(
                _clean_str(
                    voucher_data.get("bank_ledger")
                    or voucher_data.get("bankLedger")
                    or voucher_data.get("cash_bank_ledger")
                    or voucher_data.get("account")
                    or voucher_data.get("bank_account")
                    or "Cash"
                )
            )
            bill_num = escape_xml(
                _clean_str(
                    voucher_data.get("bill_number")
                    or voucher_data.get("bill_no")
                    or voucher_data.get("invoice_number")
                    or voucher_data.get("billNo")
                )
            )
            bill_alloc_xml = ""
            if bill_num:
                bill_alloc_xml = f"""
                        <BILLALLOCATIONS.LIST>
                            <NAME>{bill_num}</NAME>
                            <BILLTYPE>Agst Ref</BILLTYPE>
                            <AMOUNT>-{abs(total_amount):.2f}</AMOUNT>
                        </BILLALLOCATIONS.LIST>"""
            elif v_raw_num:
                bill_alloc_xml = f"""
                        <BILLALLOCATIONS.LIST>
                            <NAME>{v_raw_num}</NAME>
                            <BILLTYPE>On Account</BILLTYPE>
                            <AMOUNT>-{abs(total_amount):.2f}</AMOUNT>
                        </BILLALLOCATIONS.LIST>"""

            ledger_entries_xml.append(f""" <ALLLEDGERENTRIES.LIST>
                    <LEDGERNAME>{party_ledger}</LEDGERNAME>
                    <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
                    <AMOUNT>-{abs(total_amount):.2f}</AMOUNT>{bill_alloc_xml}
                </ALLLEDGERENTRIES.LIST>""")
            ledger_entries_xml.append(f""" <ALLLEDGERENTRIES.LIST>
                    <LEDGERNAME>{bank_ledger}</LEDGERNAME>
                    <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
                    <AMOUNT>{abs(total_amount):.2f}</AMOUNT>
                </ALLLEDGERENTRIES.LIST>""")
        elif "credit note" in voucher_type.lower() or "sales return" in voucher_type.lower():
            credit_note_ledger = escape_xml(_clean_str(voucher_data.get("credit_note_ledger") or voucher_data.get("sales_return_ledger")) or "Sales Return")
            ledger_entries_xml.append(f"""<ALLLEDGERENTRIES.LIST>
                    <LEDGERNAME>{party_ledger}</LEDGERNAME>
                    <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
                    <AMOUNT>{abs(total_amount):.2f}</AMOUNT>
                </ALLLEDGERENTRIES.LIST>""")
            if not has_valid_items:
                ledger_entries_xml.append(f"""<ALLLEDGERENTRIES.LIST>
                    <LEDGERNAME>{credit_note_ledger}</LEDGERNAME>
                    <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
                    <AMOUNT>-{abs(total_amount):.2f}</AMOUNT>
                </ALLLEDGERENTRIES.LIST>""")
        elif "debit note" in voucher_type.lower() or "purchase return" in voucher_type.lower():
            debit_note_ledger = escape_xml(_clean_str(voucher_data.get("debit_note_ledger") or voucher_data.get("purchase_return_ledger")) or "Purchase Return")
            ledger_entries_xml.append(f""" <ALLLEDGERENTRIES.LIST>
                    <LEDGERNAME>{party_ledger}</LEDGERNAME>
                    <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
                    <AMOUNT>-{abs(total_amount):.2f}</AMOUNT>
                </ALLLEDGERENTRIES.LIST>""")
            if not has_valid_items:
                ledger_entries_xml.append(f"""<ALLLEDGERENTRIES.LIST>
                    <LEDGERNAME>{debit_note_ledger}</LEDGERNAME>
                    <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
                    <AMOUNT>{abs(total_amount):.2f}</AMOUNT>
                </ALLLEDGERENTRIES.LIST>""")
        elif "purchase" in voucher_type.lower():
            purchase_ledger = escape_xml(
                _clean_str(
                    voucher_data.get("purchase_ledger")
                    or voucher_data.get("purchaseLedger")
                    or "Purchase"
                )
            )
            if has_valid_items:
                ledger_entries_xml.append(f""" <LEDGERENTRIES.LIST>
                    <LEDGERNAME>{party_ledger}</LEDGERNAME>
                    <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
                    <ISPARTYLEDGER>Yes</ISPARTYLEDGER>
                    <AMOUNT>-{abs(total_amount):.2f}</AMOUNT>
                </LEDGERENTRIES.LIST>""")
            else:
                ledger_entries_xml.append(f""" <ALLLEDGERENTRIES.LIST>
                    <LEDGERNAME>{party_ledger}</LEDGERNAME>
                    <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
                    <AMOUNT>{abs(total_amount):.2f}</AMOUNT>
                </ALLLEDGERENTRIES.LIST>""")
                ledger_entries_xml.append(f""" <ALLLEDGERENTRIES.LIST>
                    <LEDGERNAME>{purchase_ledger}</LEDGERNAME>
                    <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
                    <AMOUNT>-{abs(total_amount):.2f}</AMOUNT>
                </ALLLEDGERENTRIES.LIST>""")
        elif "contra" in voucher_type.lower():
            to_acc = escape_xml(_clean_str(voucher_data.get("to_account") or voucher_data.get("toAccount") or voucher_data.get("bank_ledger") or party_ledger))
            from_acc = escape_xml(_clean_str(voucher_data.get("from_account") or voucher_data.get("fromAccount") or voucher_data.get("cash_ledger") or "Cash"))
            ledger_entries_xml.append(f"""<ALLLEDGERENTRIES.LIST>
                    <LEDGERNAME>{to_acc}</LEDGERNAME>
                    <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
                    <AMOUNT>-{abs(total_amount):.2f}</AMOUNT>
                </ALLLEDGERENTRIES.LIST>""")
            ledger_entries_xml.append(f"""<ALLLEDGERENTRIES.LIST>
                    <LEDGERNAME>{from_acc}</LEDGERNAME>
                    <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
                    <AMOUNT>{abs(total_amount):.2f}</AMOUNT>
                </ALLLEDGERENTRIES.LIST>""")
        elif "journal" in voucher_type.lower():
            raw_journal_items = voucher_data.get("items") or voucher_data.get("ledger_entries") or []
            if raw_journal_items and isinstance(raw_journal_items, list):
                for jit in raw_journal_items:
                    jp_name = escape_xml(_clean_str(jit.get("partyName") or jit.get("party_name") or jit.get("ledgerName") or jit.get("ledger_name") or jit.get("name") or jit.get("itemName")))
                    if not jp_name:
                        continue
                    j_type = str(jit.get("type") or jit.get("entry_type") or "Debit").strip().lower()
                    try:
                        j_amt = abs(float(jit.get("amount") or 0.0))
                    except (ValueError, TypeError):
                        j_amt = 0.0
                    if j_type == "debit":
                        ledger_entries_xml.append(f""" <ALLLEDGERENTRIES.LIST>
                    <LEDGERNAME>{jp_name}</LEDGERNAME>
                    <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
                    <AMOUNT>-{j_amt:.2f}</AMOUNT>
                </ALLLEDGERENTRIES.LIST>""")
                    else:
                        ledger_entries_xml.append(f""" <ALLLEDGERENTRIES.LIST>
                    <LEDGERNAME>{jp_name}</LEDGERNAME>
                    <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
                    <AMOUNT>{j_amt:.2f}</AMOUNT>
                </ALLLEDGERENTRIES.LIST>""")
            else:
                ledger_entries_xml.append(f""" <ALLLEDGERENTRIES.LIST>
                    <LEDGERNAME>{party_ledger}</LEDGERNAME>
                    <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
                    <AMOUNT>-{abs(total_amount):.2f}</AMOUNT>
                </ALLLEDGERENTRIES.LIST>""")
        else:
            other_ledger = escape_xml(
                _clean_str(
                    voucher_data.get("bank_ledger")
                    or voucher_data.get("bankLedger")
                    or voucher_data.get("cash_bank_ledger")
                    or voucher_data.get("account")
                    or voucher_data.get("sales_ledger")
                    or voucher_data.get("salesLedger")
                    or voucher_data.get("purchase_ledger")
                    or voucher_data.get("purchaseLedger")
                )
            )
            ledger_entries_xml.append(f"""  <ALLLEDGERENTRIES.LIST>
                    <LEDGERNAME>{party_ledger}</LEDGERNAME>
                    <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
                    <AMOUNT>-{abs(total_amount):.2f}</AMOUNT>
                </ALLLEDGERENTRIES.LIST>""")
            if other_ledger and other_ledger.lower() != party_ledger.lower():
                ledger_entries_xml.append(f""" <ALLLEDGERENTRIES.LIST>
                    <LEDGERNAME>{other_ledger}</LEDGERNAME>
                    <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
                    <AMOUNT>{abs(total_amount):.2f}</AMOUNT>
                </ALLLEDGERENTRIES.LIST>""")

    # Enforce exact penny double-entry accounting balance
    _balance_double_entry_accounting(ledger_entries_xml, inventory_entries_xml, has_valid_items, voucher_data)

    ledgers_block = "\n".join(ledger_entries_xml)
    inventory_block = ("\n" + "\n".join(inventory_entries_xml)) if inventory_entries_xml else ""
    isinvoice_tag = "\n  <ISINVOICE>Yes</ISINVOICE>" if has_valid_items else ""
    buyer_tags = []
    if party_ledger and party_ledger.lower() != "cash":
        buyer_tags.append(f"<BASICBUYERNAME>{party_ledger}</BASICBUYERNAME>")
        buyer_tags.append(f"<PARTYNAME>{party_ledger}</PARTYNAME>")
    if party_gstin:
        buyer_tags.append(f"<PARTYGSTIN>{party_gstin}</PARTYGSTIN>")
    if party_state:
        buyer_tags.append(f"<PLACEOFSUPPLY>{escape_xml(party_state)}</PLACEOFSUPPLY>")
        buyer_tags.append(f"<STATENAME>{escape_xml(party_state)}</STATENAME>")
    buyer_tags.append("<COUNTRYOFRESIDENCE>India</COUNTRYOFRESIDENCE>")
    if party_address:
        lines = [ln.strip() for ln in party_address.replace("\r", "").split("\n") if ln.strip()]
        if not lines:
            lines = [ln.strip() for ln in party_address.split(",") if ln.strip()]
        if not lines:
            lines = [party_address.strip()]
        b_lines = "".join(f"\n <BASICBUYERADDRESS>{escape_xml(l)}</BASICBUYERADDRESS>" for l in lines[:4])
        buyer_tags.append(f"<BASICBUYERADDRESS.LIST TYPE=\"String\">{b_lines}\n  </BASICBUYERADDRESS.LIST>")
        a_lines = "".join(f"\n <ADDRESS>{escape_xml(l)}</ADDRESS>" for l in lines[:4])
        buyer_tags.append(f"<ADDRESS.LIST TYPE=\"String\">{a_lines}\n </ADDRESS.LIST>")
    buyer_details_xml = ("\n" + "\n".join(buyer_tags)) if buyer_tags else ""

    xml_envelope = f"""<ENVELOPE>
    <HEADER>
        <TALLYREQUEST>Import Data</TALLYREQUEST>
    </HEADER>
    <BODY>
        <IMPORTDATA>
            <REQUESTDESC>
                <REPORTNAME>Vouchers</REPORTNAME>
                <STATICVARIABLES>
                    {company_tag}
                </STATICVARIABLES>
            </REQUESTDESC>
            <REQUESTDATA>
                <TALLYMESSAGE xmlns:UDF="TallyUDF">
                    <VOUCHER ACTION="Create" VCHTYPE="{voucher_type}">{isinvoice_tag}
                        <DATE>{tally_date}</DATE>
                        <EFFECTIVEDATE>{tally_date}</EFFECTIVEDATE>
                        <VOUCHERTYPENAME>{voucher_type}</VOUCHERTYPENAME>
                        <VOUCHERNUMBER>{voucher_number}</VOUCHERNUMBER>
                        <REFERENCE>{reference}</REFERENCE>
                        <NARRATION>{narration}</NARRATION>
                        <PARTYLEDGERNAME>{party_ledger}</PARTYLEDGERNAME>{buyer_details_xml}
{ledgers_block}{inventory_block}
                    </VOUCHER>
                </TALLYMESSAGE>
            </REQUESTDATA>
        </IMPORTDATA>
    </BODY>
</ENVELOPE>"""
    return xml_envelope
