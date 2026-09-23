

import re
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Dict, Any, Tuple, Optional, List, Set, Union
from shared.logging_config import get_logger
from apps.backend.adapters.tally.tally_client import TallyClient

logger = get_logger("app.adapters.tally.importer")

__all__ = [
    "format_tally_date",
    "escape_xml",
    "build_ledger_import_xml",
    "build_unit_import_xml",
    "build_stock_item_import_xml",
    "build_voucher_type_import_xml",
    "determine_voucher_type_parent",
    "build_voucher_import_xml",
    "parse_tally_import_response",
    "diagnose_voucher_rejection",
    "TallyImporter",
]

def format_tally_date(date_str: str) -> str:
    """Converts YYYY-MM-DD or DD-MM-YYYY or similar date strings to Tally YYYYMMDD format."""
    if not date_str:
        return datetime.now().strftime("%Y%m%d")

    clean_str = date_str.strip()
    if len(clean_str) == 8 and clean_str.isdigit():
        return clean_str

    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            dt = datetime.strptime(clean_str, fmt)
            return dt.strftime("%Y%m%d")
        except ValueError:
            continue

    return clean_str.replace("-", "").replace("/", "").replace(" ", "")

def escape_xml(value: Optional[str]) -> str:
    """Escapes special characters for XML safely."""
    if not value:
        return ""
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )

def build_ledger_import_xml(ledger_data: Dict[str, Any]) -> str:
    """
    Constructs a valid Tally XML Master Import envelope with ACTION="Create" to insert a LEDGER
    (Customer / Sundry Debtors / Vendor / Sales Account / Duties & Taxes / Bank Account) into Tally Prime.
    (Customer / Sundry Debtors / Vendor / Sales Account) into Tally Prime.
    """
    company_name = escape_xml(ledger_data.get("company_name", ""))
    company_tag = f"<SVCURRENTCOMPANY>{company_name}</SVCURRENTCOMPANY>" if company_name else ""

    ledger_name = escape_xml(
        ledger_data.get("name")
        or ledger_data.get("party_ledger")
        or ledger_data.get("partyName")
        or ledger_data.get("party_name")
        or ""
    )
    p_type = str(ledger_data.get("partyType") or ledger_data.get("party_type") or "").strip().upper()
    default_p = "Sundry Creditors" if "SUPPLIER" in p_type or "VENDOR" in p_type else "Sundry Debtors"
    parent = escape_xml(ledger_data.get("parent") or default_p)
    opening_bal = float(ledger_data.get("opening_balance") or ledger_data.get("openingBalance") or 0.0)
    state = escape_xml(ledger_data.get("state") or "")
    gstin = escape_xml(ledger_data.get("gstin") or ledger_data.get("party_gstin") or ledger_data.get("gstNumber") or "")
    mobile = escape_xml(ledger_data.get("mobile") or ledger_data.get("phone") or ledger_data.get("contactNumber") or "")
    email = escape_xml(ledger_data.get("email") or "")
    address = escape_xml(ledger_data.get("address") or "")

    state_tag = f"<STATENAME>{state}</STATENAME>" if state else ""
    gstin_tag = f"<PARTYGSTIN>{gstin}</PARTYGSTIN>" if gstin else ""
    mobile_tag = f"<LEDGERMOBILE>{mobile}</LEDGERMOBILE>" if mobile else ""
    email_tag = f"<EMAIL>{email}</EMAIL>" if email else ""
    address_tag = f"<ADDRESS.LIST><ADDRESS>{address}</ADDRESS></ADDRESS.LIST>" if address else ""

    duty_head = escape_xml(ledger_data.get("duty_head") or ledger_data.get("tax_head") or "")
    tax_tags = ""
    if "duties" in parent.lower() or duty_head:
        head_val = duty_head or ("CGST" if "cgst" in ledger_name.lower() else "SGST" if "sgst" in ledger_name.lower() else "IGST" if "igst" in ledger_name.lower() else "Others")
        tax_tags = f"""
                        <TAXTYPE>GST</TAXTYPE>
                        <GSTDUTYHEAD>{head_val}</GSTDUTYHEAD>"""

    xml_envelope = f"""<ENVELOPE>
    <HEADER>
        <TALLYREQUEST>Import Data</TALLYREQUEST>
    </HEADER>
    <BODY>
        <IMPORTDATA>
            <REQUESTDESC>
                <REPORTNAME>All Masters</REPORTNAME>
                <STATICVARIABLES>
                    {company_tag}
                </STATICVARIABLES>
            </REQUESTDESC>
            <REQUESTDATA>
                <TALLYMESSAGE xmlns:UDF="TallyUDF">
                    <LEDGER ACTION="Create" NAME="{ledger_name}">
                        <NAME>{ledger_name}</NAME>
                        <PARENT>{parent}</PARENT>
                        <OPENINGBALANCE>{opening_bal:.2f}</OPENINGBALANCE>
                        <ISBILLWISEON>Yes</ISBILLWISEON>
                        {state_tag}
                        {gstin_tag}
                        {mobile_tag}
                        {email_tag}
                        {address_tag}{tax_tags}
                    </LEDGER>
                </TALLYMESSAGE>
            </REQUESTDATA>
        </IMPORTDATA>
    </BODY>
</ENVELOPE>"""
    return xml_envelope

def build_unit_import_xml(unit_data: Dict[str, Any]) -> str:
    """
    Constructs a valid Tally XML Master Import envelope with ACTION="Create" to insert a UNIT OF MEASURE
    (e.g., Pcs, Nos, KGS, BOX, LTR, MTR) into Tally Prime.
    """
    company_name = escape_xml(unit_data.get("company_name", ""))
    company_tag = f"<SVCURRENTCOMPANY>{company_name}</SVCURRENTCOMPANY>" if company_name else ""
    unit_name = escape_xml(_clean_str(unit_data.get("name") or unit_data.get("symbol") or "Pcs"))
    decimal_places = int(unit_data.get("decimal_places") or unit_data.get("decimalPlaces") or 0)

    xml_envelope = f"""<ENVELOPE>
    <HEADER>
        <TALLYREQUEST>Import Data</TALLYREQUEST>
    </HEADER>
    <BODY>
        <IMPORTDATA>
            <REQUESTDESC>
                <REPORTNAME>All Masters</REPORTNAME>
                <STATICVARIABLES>
                    {company_tag}
                </STATICVARIABLES>
            </REQUESTDESC>
            <REQUESTDATA>
                <TALLYMESSAGE xmlns:UDF="TallyUDF">
                    <UNIT ACTION="Create" NAME="{unit_name}">
                        <NAME>{unit_name}</NAME>
                        <ISSIMPLEUNIT>Yes</ISSIMPLEUNIT>
                        <DECIMALPLACES>{decimal_places}</DECIMALPLACES>
                    </UNIT>
                </TALLYMESSAGE>
            </REQUESTDATA>
        </IMPORTDATA>
    </BODY>
</ENVELOPE>"""
    return xml_envelope

def build_stock_item_import_xml(item_data: Dict[str, Any]) -> str:
    """
    Constructs a valid Tally XML Master Import envelope with ACTION="Create" to insert a STOCK ITEM
    (with Base Unit, HSN Code, Opening Balance) into Tally Prime.
    """
    company_name = escape_xml(item_data.get("company_name", ""))
    company_tag = f"<SVCURRENTCOMPANY>{company_name}</SVCURRENTCOMPANY>" if company_name else ""
    item_name = escape_xml(_clean_str(item_data.get("name") or item_data.get("itemName") or ""))
    base_unit = escape_xml(_clean_str(item_data.get("unit") or item_data.get("units") or item_data.get("base_units") or "Pcs"))
    hsn_code = escape_xml(_clean_str(item_data.get("hsn_code") or item_data.get("hsnCode") or ""))
    hsn_tag = f"\n                        <HSNCODE>{hsn_code}</HSNCODE>" if hsn_code else ""

    xml_envelope = f"""<ENVELOPE>
    <HEADER>
        <TALLYREQUEST>Import Data</TALLYREQUEST>
    </HEADER>
    <BODY>
        <IMPORTDATA>
            <REQUESTDESC>
                <REPORTNAME>All Masters</REPORTNAME>
                <STATICVARIABLES>
                    {company_tag}
                </STATICVARIABLES>
            </REQUESTDESC>
            <REQUESTDATA>
                <TALLYMESSAGE xmlns:UDF="TallyUDF">
                    <STOCKITEM ACTION="Create" NAME="{item_name}">
                        <NAME>{item_name}</NAME>
                        <BASEUNITS>{base_unit}</BASEUNITS>
                        <OPENINGBALANCE>0</OPENINGBALANCE>
                        <GSTAPPLICABLE>&#4; Applicable</GSTAPPLICABLE>{hsn_tag}
                    </STOCKITEM>
                </TALLYMESSAGE>
            </REQUESTDATA>
        </IMPORTDATA>
    </BODY>
</ENVELOPE>"""
    return xml_envelope

def build_voucher_type_import_xml(vtype_data: Dict[str, Any]) -> str:
    """
    Constructs a valid Tally XML Master Import envelope with Action="Create" to insert a VOUCHERTYPE
    into Tally Prime with ISACTIVE=Yes, NUMBERINGMETHOD=Manual, and USEZEROENTRIES=Yes.
    """
    company_name = escape_xml(vtype_data.get("company_name", ""))
    company_tag = f"<SVCURRENTCOMPANY>{company_name}</SVCURRENTCOMPANY>" if company_name else ""
    vtype_name = escape_xml(_clean_str(vtype_data.get("name") or vtype_data.get("voucher_type") or ""))
    parent = escape_xml(_clean_str(vtype_data.get("parent") or "Sales"))

    xml_envelope = f"""<ENVELOPE>
    <HEADER>
        <TALLYREQUEST>Import Data</TALLYREQUEST>
    </HEADER>
    <BODY>
        <IMPORTDATA>
            <REQUESTDESC>
                <REPORTNAME>All Masters</REPORTNAME>
                <STATICVARIABLES>
                    {company_tag}
                </STATICVARIABLES>
            </REQUESTDESC>
            <REQUESTDATA>
                <TALLYMESSAGE xmlns:UDF="TallyUDF">
                    <VOUCHERTYPE Action="Create">
                        <NAME>{vtype_name}</NAME>
                        <PARENT>{parent}</PARENT>
                        <ISACTIVE>Yes</ISACTIVE>
                        <NUMBERINGMETHOD>Manual</NUMBERINGMETHOD>
                        <USEZEROENTRIES>Yes</USEZEROENTRIES>
                        <COMMONNARRATION>Yes</COMMONNARRATION>
                    </VOUCHERTYPE>
                </TALLYMESSAGE>
            </REQUESTDATA>
        </IMPORTDATA>
    </BODY>
</ENVELOPE>"""
    return xml_envelope

def determine_voucher_type_parent(vtype_name: str) -> str:
    """Determines the most appropriate Tally standard parent voucher type."""
    v = (vtype_name or "").strip().lower()
    if any(k in v for k in ("quote", "quotation", "estimate", "proforma", "sale", "order")):
        return "Sales"
    elif "purchase" in v:
        return "Purchase"
    elif "receipt" in v:
        return "Receipt"
    elif "payment" in v:
        return "Payment"
    elif "contra" in v:
        return "Contra"
    elif "journal" in v:
        return "Journal"
    elif "credit note" in v:
        return "Credit Note"
    elif "debit note" in v:
        return "Debit Note"
    return "Sales"

def _clean_str(value: Any) -> str:
    """Cleans a string value, returning empty string if None, 'none', 'null', 'undefined'."""
    if value is None:
        return ""
    s = str(value).strip()
    if s.lower() in ("none", "null", "undefined"):
        return ""
    return s

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

_ITEM_MASTER_UNIT_CACHE: Dict[Tuple[str, str], Optional[str]] = {}

def _lookup_item_master_unit(company_name: str, item_name: str) -> Optional[str]:
    """
    Looks up the registered Base Unit of Measure (UOM) for the Stock Item from MongoDB.
    Ensures that Tally receives the exact unit expected by its master database,
    preventing Tally from blanking out Quantity and Rate fields on unit mismatch.
    """
    if not item_name:
        return None
    key = (company_name or "", item_name)
    if key in _ITEM_MASTER_UNIT_CACHE:
        return _ITEM_MASTER_UNIT_CACHE[key]

    try:
        from shared.db.mongo_client import get_mongo_db
        db = get_mongo_db()
        q: Dict[str, Any] = {"itemName": item_name}
        if company_name:
            q["company_name"] = company_name
        doc = db.stocks.find_one(q) or db.stockbalances.find_one(q)
        if not doc and company_name:
            doc = db.stocks.find_one({"itemName": item_name}) or db.stockbalances.find_one({"itemName": item_name})

        if doc and doc.get("unit"):
            u = str(doc.get("unit")).strip()
            if u:
                _ITEM_MASTER_UNIT_CACHE[key] = u
                return u
    except Exception as exc:
        logger.debug(f"Master unit lookup error for '{item_name}': {exc}")

    _ITEM_MASTER_UNIT_CACHE[key] = None
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

            ledger_entries_xml.append(f"""                <{round_off_tag}>
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

    total_amount = _parse_float(
        voucher_data.get("amount")
        or voucher_data.get("total_amount")
        or voucher_data.get("total"),
        0.0,
    )

    company_tag = f"<SVCURRENTCOMPANY>{company_name}</SVCURRENTCOMPANY>" if company_name else ""

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
    if "journal" in voucher_type.lower():
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
            if master_unit:
                i_unit = master_unit
            else:
                i_unit = _clean_str(
                    item.get("units")
                    or item.get("unit")
                    or item.get("uom")
                    or item.get("symbol")
                ) or "Pcs"

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
                    order_tags += f"\n                                <ORDERNO>{escape_xml(order_no_val)}</ORDERNO>"
                if order_due_date_val:
                    order_tags += f"\n                                <ORDERDUEDATE>{escape_xml(order_due_date_val)}</ORDERDUEDATE>"

                godown_tag = f"""
                        <BATCHALLOCATIONS.LIST>
                            <GODOWNNAME>{escape_xml(g_name)}</GODOWNNAME>
                            <BATCHNAME>{escape_xml(batch_val)}</BATCHNAME>
                            <AMOUNT>{alloc_amount:.2f}</AMOUNT>
                            <ACTUALQTY>{escape_xml(qty_str)}</ACTUALQTY>
                            <BILLEDQTY>{escape_xml(qty_str)}</BILLEDQTY>{order_tags}
                        </BATCHALLOCATIONS.LIST>"""

            discount_tag = f"\n                        <DISCOUNT>{disc_pct:g}%</DISCOUNT>" if disc_pct > 0 else ""

            accounting_alloc_tag = f"""
                        <ACCOUNTINGALLOCATIONS.LIST>
                            <LEDGERNAME>{item_alloc_ledger}</LEDGERNAME>
                            <ISDEEMEDPOSITIVE>{alloc_deemed_positive}</ISDEEMEDPOSITIVE>
                            <AMOUNT>{alloc_amount:.2f}</AMOUNT>
                        </ACCOUNTINGALLOCATIONS.LIST>"""

            inventory_entries_xml.append(f"""                <INVENTORYENTRIES.LIST>
                    <STOCKITEMNAME>{escape_xml(i_name)}</STOCKITEMNAME>
                    <ISDEEMEDPOSITIVE>{item_deemed_positive}</ISDEEMEDPOSITIVE>
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

            ledger_entries_xml.append(f"""                <ALLLEDGERENTRIES.LIST>
                    <LEDGERNAME>{l_name}</LEDGERNAME>
                    <ISDEEMEDPOSITIVE>{is_deemed_pos}</ISDEEMEDPOSITIVE>
                    <AMOUNT>{tally_amt:.2f}</AMOUNT>
                </ALLLEDGERENTRIES.LIST>""")
    elif has_valid_items:
        is_purchase_or_cn = "purchase" in voucher_type.lower() or "credit note" in voucher_type.lower() or "sales return" in voucher_type.lower()
        party_deemed_pos = "No" if is_purchase_or_cn else "Yes"
        party_amt = abs(total_amount) if is_purchase_or_cn else -abs(total_amount)
        tax_deemed_pos = "Yes" if is_purchase_or_cn else "No"

        ledger_entries_xml.append(f"""                <LEDGERENTRIES.LIST>
                    <LEDGERNAME>{party_ledger}</LEDGERNAME>
                    <ISDEEMEDPOSITIVE>{party_deemed_pos}</ISDEEMEDPOSITIVE>
                    <ISPARTYLEDGER>Yes</ISPARTYLEDGER>
                    <AMOUNT>{party_amt:.2f}</AMOUNT>
                </LEDGERENTRIES.LIST>""")
        for tax in tax_entries:
            t_amt = -abs(tax['amount']) if is_purchase_or_cn else abs(tax['amount'])
            ledger_entries_xml.append(f"""                <LEDGERENTRIES.LIST>
                    <LEDGERNAME>{escape_xml(tax['name'])}</LEDGERNAME>
                    <ISDEEMEDPOSITIVE>{tax_deemed_pos}</ISDEEMEDPOSITIVE>
                    <AMOUNT>{t_amt:.2f}</AMOUNT>
                </LEDGERENTRIES.LIST>""")
    else:
        if "sale" in voucher_type.lower():
            ledger_entries_xml.append(f"""                <ALLLEDGERENTRIES.LIST>
                    <LEDGERNAME>{party_ledger}</LEDGERNAME>
                    <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
                    <AMOUNT>-{abs(total_amount):.2f}</AMOUNT>
                </ALLLEDGERENTRIES.LIST>""")
            ledger_entries_xml.append(f"""                <ALLLEDGERENTRIES.LIST>
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

            ledger_entries_xml.append(f"""                <ALLLEDGERENTRIES.LIST>
                    <LEDGERNAME>{bank_ledger}</LEDGERNAME>
                    <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
                    <AMOUNT>-{abs(total_amount):.2f}</AMOUNT>
                </ALLLEDGERENTRIES.LIST>""")
            ledger_entries_xml.append(f"""                <ALLLEDGERENTRIES.LIST>
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

            ledger_entries_xml.append(f"""                <ALLLEDGERENTRIES.LIST>
                    <LEDGERNAME>{party_ledger}</LEDGERNAME>
                    <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
                    <AMOUNT>-{abs(total_amount):.2f}</AMOUNT>{bill_alloc_xml}
                </ALLLEDGERENTRIES.LIST>""")
            ledger_entries_xml.append(f"""                <ALLLEDGERENTRIES.LIST>
                    <LEDGERNAME>{bank_ledger}</LEDGERNAME>
                    <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
                    <AMOUNT>{abs(total_amount):.2f}</AMOUNT>
                </ALLLEDGERENTRIES.LIST>""")
        elif "credit note" in voucher_type.lower() or "sales return" in voucher_type.lower():
            credit_note_ledger = escape_xml(_clean_str(voucher_data.get("credit_note_ledger") or voucher_data.get("sales_return_ledger")) or "Sales Return")
            ledger_entries_xml.append(f"""                <ALLLEDGERENTRIES.LIST>
                    <LEDGERNAME>{party_ledger}</LEDGERNAME>
                    <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
                    <AMOUNT>{abs(total_amount):.2f}</AMOUNT>
                </ALLLEDGERENTRIES.LIST>""")
            if not has_valid_items:
                ledger_entries_xml.append(f"""                <ALLLEDGERENTRIES.LIST>
                    <LEDGERNAME>{credit_note_ledger}</LEDGERNAME>
                    <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
                    <AMOUNT>-{abs(total_amount):.2f}</AMOUNT>
                </ALLLEDGERENTRIES.LIST>""")
        elif "debit note" in voucher_type.lower() or "purchase return" in voucher_type.lower():
            debit_note_ledger = escape_xml(_clean_str(voucher_data.get("debit_note_ledger") or voucher_data.get("purchase_return_ledger")) or "Purchase Return")
            ledger_entries_xml.append(f"""                <ALLLEDGERENTRIES.LIST>
                    <LEDGERNAME>{party_ledger}</LEDGERNAME>
                    <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
                    <AMOUNT>-{abs(total_amount):.2f}</AMOUNT>
                </ALLLEDGERENTRIES.LIST>""")
            if not has_valid_items:
                ledger_entries_xml.append(f"""                <ALLLEDGERENTRIES.LIST>
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
                ledger_entries_xml.append(f"""                <LEDGERENTRIES.LIST>
                    <LEDGERNAME>{party_ledger}</LEDGERNAME>
                    <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
                    <ISPARTYLEDGER>Yes</ISPARTYLEDGER>
                    <AMOUNT>-{abs(total_amount):.2f}</AMOUNT>
                </LEDGERENTRIES.LIST>""")
            else:
                ledger_entries_xml.append(f"""                <ALLLEDGERENTRIES.LIST>
                    <LEDGERNAME>{party_ledger}</LEDGERNAME>
                    <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
                    <AMOUNT>{abs(total_amount):.2f}</AMOUNT>
                </ALLLEDGERENTRIES.LIST>""")
                ledger_entries_xml.append(f"""                <ALLLEDGERENTRIES.LIST>
                    <LEDGERNAME>{purchase_ledger}</LEDGERNAME>
                    <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
                    <AMOUNT>-{abs(total_amount):.2f}</AMOUNT>
                </ALLLEDGERENTRIES.LIST>""")
        elif "contra" in voucher_type.lower():
            to_acc = escape_xml(_clean_str(voucher_data.get("to_account") or voucher_data.get("toAccount") or voucher_data.get("bank_ledger") or party_ledger))
            from_acc = escape_xml(_clean_str(voucher_data.get("from_account") or voucher_data.get("fromAccount") or voucher_data.get("cash_ledger") or "Cash"))
            ledger_entries_xml.append(f"""                <ALLLEDGERENTRIES.LIST>
                    <LEDGERNAME>{to_acc}</LEDGERNAME>
                    <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
                    <AMOUNT>-{abs(total_amount):.2f}</AMOUNT>
                </ALLLEDGERENTRIES.LIST>""")
            ledger_entries_xml.append(f"""                <ALLLEDGERENTRIES.LIST>
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
                        ledger_entries_xml.append(f"""                <ALLLEDGERENTRIES.LIST>
                    <LEDGERNAME>{jp_name}</LEDGERNAME>
                    <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
                    <AMOUNT>-{j_amt:.2f}</AMOUNT>
                </ALLLEDGERENTRIES.LIST>""")
                    else:
                        ledger_entries_xml.append(f"""                <ALLLEDGERENTRIES.LIST>
                    <LEDGERNAME>{jp_name}</LEDGERNAME>
                    <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
                    <AMOUNT>{j_amt:.2f}</AMOUNT>
                </ALLLEDGERENTRIES.LIST>""")
            else:
                ledger_entries_xml.append(f"""                <ALLLEDGERENTRIES.LIST>
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
            ledger_entries_xml.append(f"""                <ALLLEDGERENTRIES.LIST>
                    <LEDGERNAME>{party_ledger}</LEDGERNAME>
                    <ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE>
                    <AMOUNT>-{abs(total_amount):.2f}</AMOUNT>
                </ALLLEDGERENTRIES.LIST>""")
            if other_ledger and other_ledger.lower() != party_ledger.lower():
                ledger_entries_xml.append(f"""                <ALLLEDGERENTRIES.LIST>
                    <LEDGERNAME>{other_ledger}</LEDGERNAME>
                    <ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE>
                    <AMOUNT>{abs(total_amount):.2f}</AMOUNT>
                </ALLLEDGERENTRIES.LIST>""")

    # Enforce exact penny double-entry accounting balance
    _balance_double_entry_accounting(ledger_entries_xml, inventory_entries_xml, has_valid_items, voucher_data)

    ledgers_block = "\n".join(ledger_entries_xml)
    inventory_block = ("\n" + "\n".join(inventory_entries_xml)) if inventory_entries_xml else ""
    isinvoice_tag = "\n                        <ISINVOICE>Yes</ISINVOICE>" if has_valid_items else ""

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
                        <VOUCHERTYPENAME>{voucher_type}</VOUCHERTYPENAME>
                        <VOUCHERNUMBER>{voucher_number}</VOUCHERNUMBER>
                        <REFERENCE>{reference}</REFERENCE>
                        <NARRATION>{narration}</NARRATION>
                        <PARTYLEDGERNAME>{party_ledger}</PARTYLEDGERNAME>
{ledgers_block}{inventory_block}
                    </VOUCHER>
                </TALLYMESSAGE>
            </REQUESTDATA>
        </IMPORTDATA>
    </BODY>
</ENVELOPE>"""
    return xml_envelope

def parse_tally_import_response(xml_text: str, default_voucher_number: Optional[str] = None) -> Tuple[bool, Optional[str], Optional[str]]:
  
    if not xml_text or not xml_text.strip():
        return False, None, "Empty response received from Tally Prime server."

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as pe:
        return False, None, f"Malformed XML response from Tally Prime: {pe}"

    line_errors = []
    for line_err in root.findall(".//LINEERROR"):
        if line_err.text and line_err.text.strip():
            line_errors.append(line_err.text.strip())

    if line_errors:
        clean_error = "; ".join(line_errors)
        logger.warning(f"Tally Import LINEERROR: {clean_error}")
        return False, None, f"Tally XML Line Error: {clean_error}"

    errors_elem = root.find(".//ERRORS")
    if errors_elem is not None and errors_elem.text:
        try:
            err_count = int(errors_elem.text.strip())
            if err_count > 0 and not line_errors:
                return False, None, f"Tally reported {err_count} import error(s)."
        except ValueError:
            pass

    exceptions_elem = root.find(".//EXCEPTIONS")
    if exceptions_elem is not None and exceptions_elem.text:
        try:
            exc_count = int(exceptions_elem.text.strip())
            if exc_count > 0 and not line_errors:
                return False, None, f"Tally reported {exc_count} exception(s) during voucher creation."
        except ValueError:
            pass

    voucher_num = default_voucher_number
    vnum_elem = root.find(".//VOUCHERNUMBER")
    if vnum_elem is not None and vnum_elem.text and vnum_elem.text.strip():
        voucher_num = vnum_elem.text.strip()
    else:
        last_id_elem = root.find(".//LASTVOUCHERID")
        if last_id_elem is None:
            last_id_elem = root.find(".//LASTVCHID")
        if last_id_elem is not None and last_id_elem.text and last_id_elem.text.strip():
            v_text = last_id_elem.text.strip()
            if v_text not in ("0", ""):
                voucher_num = voucher_num or f"VCH-{v_text}"

    altered_elem = root.find(".//ALTERED")
    alt_count = 0
    if altered_elem is not None and altered_elem.text:
        try:
            alt_count = int(altered_elem.text.strip())
        except ValueError:
            pass

    created_elem = root.find(".//CREATED")
    if created_elem is not None and created_elem.text:
        try:
            c_count = int(created_elem.text.strip())
            if c_count > 0:
                return True, voucher_num or "CREATED", None
            elif alt_count > 0:
                return True, voucher_num or "ALTERED", None
            else:
                return False, None, "Tally rejected creation (CREATED: 0, ALTERED: 0)."
        except ValueError:
            pass

    return True, voucher_num or "SUCCESS", None

def diagnose_voucher_rejection(
    voucher_data: Dict[str, Any],
    tally_response_text: str = "",
    parse_error: Optional[str] = ""
) -> Dict[str, Any]:
    """
    Intelligently diagnoses why Tally Prime rejected a voucher import request
    and provides human-readable English explanations (Root Cause) and Actionable Steps.
    """
    company_name = str(voucher_data.get("company_name") or voucher_data.get("companyName") or voucher_data.get("company") or "")
    v_date = str(voucher_data.get("date") or voucher_data.get("voucherDate") or "")
    v_type = str(voucher_data.get("voucher_type") or voucher_data.get("voucherType") or "Sales")
    raw_amt = voucher_data.get("amount")
    items = voucher_data.get("items") or voucher_data.get("inventory_entries") or []

    reasons = []
    actions = []

    if tally_response_text and "<LINEERROR>" in tally_response_text:
        line_errs = re.findall(r"<LINEERROR>(.*?)</LINEERROR>", tally_response_text, re.IGNORECASE)
        for le in line_errs:
            clean_le = le.replace("&apos;", "'").replace("&quot;", '"').replace("&amp;", "&").strip()
            if clean_le:
                reasons.append(f"Tally Master Error: {clean_le}")
                if "svcurrentcompany" in clean_le.lower() or "currentcompany" in clean_le.lower():
                    actions.append(
                        f"Company '{company_name}' is not open in Tally Prime. Please open '{company_name}' inside Tally Prime (Gateway of Tally) and retry the entry from the web app."
                    )
                elif "ledger" in clean_le.lower():
                    actions.append("Ensure the required ledger accounts exist and are active in Tally.")
                elif "item" in clean_le.lower() or "unit" in clean_le.lower():
                    actions.append("Ensure the stock item and its unit of measure are created in Tally.")

    v_year = None
    if v_date:
        clean_d = v_date.replace("-", "").replace("/", "").strip()
        if len(clean_d) >= 4 and clean_d[:4].isdigit():
            v_year = int(clean_d[:4])
        elif len(clean_d) == 8 and clean_d[-4:].isdigit():
            v_year = int(clean_d[-4:])

    fy_match = re.search(r"(20\d\d)\s*-\s*(20\d\d)", company_name)
    if fy_match and v_year:
        start_y = int(fy_match.group(1))
        end_y = int(fy_match.group(2))
        if v_year < start_y or v_year > end_y:
            reasons.append(
                f"Financial Year Mismatch: Voucher date '{v_date}' (Year {v_year}) is outside company '{company_name}' financial year ({start_y}-{end_y}). Tally rejects vouchers posted into a closed or future financial period."
            )
            actions.append(
                f"Select the active company for the current financial year on the Web App (e.g. 'Tarun Enterprise (25-26)'), or change the voucher date to be within {start_y}-{end_y}."
            )
    else:
        fy2_match = re.search(r"\(?(\d{2})\s*-\s*(\d{2})\)?", company_name)
        if fy2_match and v_year:
            start_y = 2000 + int(fy2_match.group(1))
            end_y = 2000 + int(fy2_match.group(2))
            if v_year < start_y or v_year > end_y:
                reasons.append(
                    f"Financial Year Mismatch: Voucher date '{v_date}' is outside company '{company_name}' financial year ({start_y}-{end_y})."
                )
                actions.append(
                    f"Ensure the voucher date matches the active company's financial year ({start_y}-{end_y})."
                )

    try:
        amt_val = float(raw_amt or 0.0)
    except (ValueError, TypeError):
        amt_val = 0.0

    all_items_zero = False
    if isinstance(items, list) and len(items) > 0:
        total_item_amt = 0.0
        for it in items:
            try:
                q = float(it.get("quantity") if it.get("quantity") is not None else it.get("qty", 0.0))
                r = float(it.get("rate") if it.get("rate") is not None else it.get("price", 0.0))
                total_item_amt += (q * r)
            except (ValueError, TypeError):
                pass
        if total_item_amt <= 0.0:
            all_items_zero = True

    if amt_val <= 0.0 and (all_items_zero or len(items) == 0):
        reasons.append(
            "Zero-Value Invoice: Total voucher amount is Rs. 0.00 (item quantity or rate is 0). Tally Prime standard settings do not allow zero-value invoices without explicit configuration."
        )
        actions.append(
            "Enter a valid positive Quantity, Rate, and Amount for your items on the Web App before creating the invoice."
        )

    party_input = voucher_data.get("partyLedger") or voucher_data.get("party_ledger") or voucher_data.get("party") or ""
    if not party_input or str(party_input).strip() == "":
        reasons.append(
            "Missing Customer / Party Ledger: No customer or debtor was selected in the web request (defaulted to Cash)."
        )
        actions.append(
            "Select a valid Customer / Debtor ledger from the customer dropdown on the Web App."
        )

    if not reasons:
        reasons.append(
            f"Tally rejected voucher creation ({parse_error or 'Validation exception'})."
        )
        actions.append(
            "Check that Tally Prime is running, the company is open, and all ledger accounts (Sales, Party, Tax) exist in Tally."
        )

    combined_reason = " | ".join(reasons)
    combined_action = " ".join(actions)

    return {
        "reason": combined_reason,
        "action": combined_action,
        "reasons": reasons,
        "actions": actions,
        "technical_error": parse_error or "Tally reported an exception during voucher creation.",
        "voucher_type": v_type,
        "voucher_number": str(voucher_data.get("voucher_number") or voucher_data.get("voucherNumber") or "N/A"),
        "company_name": company_name or "N/A",
        "party": str(party_input or voucher_data.get("party_ledger") or "Cash"),
        "amount": amt_val,
        "date": v_date or "N/A"
    }

class TallyImporter:
    def __init__(self, client: Optional[TallyClient] = None):
        self.client = client or TallyClient()
        self._voucher_types_cache: Dict[str, Dict[str, str]] = {}
        self._known_ledgers: Dict[str, set] = {}
        self._known_units: Dict[str, set] = {}
        self._known_stock_items: Dict[str, set] = {}

    async def check_tally_company_status(
        self, host: str, port: int, company_name: str
    ) -> Tuple[bool, bool, List[str]]:
        """
        Checks if Tally Prime is running and if company_name is currently opened in Tally.
        Returns (is_tally_online: bool, is_company_loaded: bool, open_companies: List[str]).
        """
        try:
            from apps.backend.adapters.tally.request_builder import build_company_list_xml
            from apps.backend.adapters.tally.response_parser import parse_company_list
            xml_req = build_company_list_xml()
            ok, status, resp_txt, err = await self.client.send_xml_request_async(
                host=host, port=port, xml_content=xml_req, timeout=4.0
            )
            if not ok or status != 200:
                return False, False, []

            companies = parse_company_list(resp_txt)
            open_names = [str(c.get("name") or c.get("company_name", "")).strip() for c in companies if c.get("name") or c.get("company_name")]
            if not company_name or not company_name.strip():
                return True, len(open_names) > 0, open_names

            target = company_name.strip().lower()
            loaded = any(target == name.lower() or target in name.lower() or name.lower() in target for name in open_names)
            return True, loaded, open_names
        except Exception as exc:
            logger.debug(f"Error checking Tally company status: {exc}")
            return False, False, []

    async def ensure_ledger(
        self,
        host: str,
        port: int,
        company_name: str,
        ledger_name: str,
        parent: str = "Sundry Debtors",
        extra_info: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Auto-Creates the ledger in Tally if it does not already exist.
        Runs safely on-the-fly before voucher posting.
        """
        if not ledger_name or not ledger_name.strip():
            return False

        clean_name = ledger_name.strip()
        if clean_name.lower() in ("cash", "profit & loss a/c", "profit &amp; loss a/c"):
            return True

        comp_key = (company_name or "").strip().lower()
        if comp_key not in self._known_ledgers:
            self._known_ledgers[comp_key] = set()
        if clean_name.lower() in self._known_ledgers[comp_key]:
            return True

        ledger_payload = {
            "company_name": company_name,
            "name": clean_name,
            "parent": parent,
            **(extra_info or {})
        }
        xml_envelope = build_ledger_import_xml(ledger_payload)

        try:
            ok, status, res_text, _ = await self.client.send_xml_request_async(
                host=host, port=port, xml_content=xml_envelope, serialize_company=company_name
            )
            if ok and status == 200:
                self._known_ledgers[comp_key].add(clean_name.lower())
                logger.info(f"Auto-Ensured Ledger '{clean_name}' under '{parent}' in Tally (Company: '{company_name}')")
                return True
        except Exception as exc:
            logger.warning(f"Auto-ensure ledger '{clean_name}' encountered error: {exc}")

        return False

    async def ensure_unit(
        self, host: str, port: int, company_name: str, unit_name: str, decimal_places: int = 0
    ) -> bool:
        """
        Auto-Creates the Unit of Measure in Tally if it does not already exist.
        """
        if not unit_name or not unit_name.strip():
            return False
        clean_name = unit_name.strip()
        comp_key = (company_name or "").strip().lower()
        if comp_key not in self._known_units:
            self._known_units[comp_key] = set()
        if clean_name.lower() in self._known_units[comp_key]:
            return True

        xml = build_unit_import_xml({
            "company_name": company_name,
            "name": clean_name,
            "decimal_places": decimal_places,
        })
        try:
            ok, status, res_text, _ = await self.client.send_xml_request_async(
                host=host, port=port, xml_content=xml, serialize_company=company_name
            )
            if ok and status == 200:
                self._known_units[comp_key].add(clean_name.lower())
                logger.info(f"Auto-Ensured Unit '{clean_name}' in Tally (Company: '{company_name}')")
                return True
        except Exception as exc:
            logger.debug(f"Auto-ensure unit '{clean_name}' error: {exc}")
        return False

    async def ensure_stock_item(
        self, host: str, port: int, company_name: str, item_name: str, unit_name: str = "Pcs", hsn_code: str = ""
    ) -> bool:
        """
        Auto-Creates the Stock Item in Tally if it does not already exist.
        Ensures the Unit exists in Tally first, then inserts the Stock Item.
        """
        if not item_name or not item_name.strip():
            return False
        clean_name = item_name.strip()
        comp_key = (company_name or "").strip().lower()
        if comp_key not in self._known_stock_items:
            self._known_stock_items[comp_key] = set()
        if clean_name.lower() in self._known_stock_items[comp_key]:
            return True

        clean_unit = unit_name.strip() if unit_name else "Pcs"

        await self.ensure_unit(host=host, port=port, company_name=company_name, unit_name=clean_unit)

        item_xml = build_stock_item_import_xml({
            "company_name": company_name,
            "name": clean_name,
            "unit": clean_unit,
            "hsn_code": hsn_code
        })
        try:
            ok, status, res_text, _ = await self.client.send_xml_request_async(
                host=host, port=port, xml_content=item_xml, serialize_company=company_name
            )
            if ok and status == 200:
                self._known_stock_items[comp_key].add(clean_name.lower())
                logger.info(f"Auto-Ensured Stock Item '{clean_name}' with Unit '{clean_unit}' in Tally (Company: '{company_name}')")
                return True
        except Exception as exc:
            logger.warning(f"Auto-ensure stock item '{clean_name}' error: {exc}")
        return False

    async def ensure_voucher_type(
        self, host: str, port: int, company_name: str, voucher_type_name: str, parent: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Auto-Checks if the Voucher Type exists in Tally Prime.
        If it does not exist, searches for smart aliases (e.g. 'Quotation' -> 'Quotation Voucher' / 'Sales Quotation')
        or automatically creates the custom Voucher Type in Tally with Active=Yes.
        Returns (success: bool, resolved_voucher_type_name: str).
        """
        if not voucher_type_name or not voucher_type_name.strip():
            return True, "Sales"

        comp_key = (company_name or "").strip()
        v_clean = voucher_type_name.strip()
        v_lower = v_clean.lower()

        if comp_key not in self._voucher_types_cache:
            self._voucher_types_cache[comp_key] = {}

        cached = self._voucher_types_cache[comp_key]
        if v_lower in cached:
            return True, cached[v_lower]

        # Query existing voucher types from Tally
        try:
            from apps.backend.adapters.tally.request_builder import build_collection_xml
            xml_q = build_collection_xml(
                collection_type="VoucherType",
                fetch_fields=["NAME", "PARENT", "ISACTIVE"],
                company_name=comp_key if comp_key else None
            )
            ok, status, txt, _ = await self.client.send_xml_request_async(host=host, port=port, xml_content=xml_q)
            if ok and status == 200 and txt:
                clean_txt = re.sub(r"&#\d+;", "", txt)
                try:
                    root = ET.fromstring(clean_txt)
                    for vt in root.findall(".//VOUCHERTYPE"):
                        t_name = vt.get("NAME") or ""
                        name_elem = vt.find("NAME")
                        if not t_name and name_elem is not None and name_elem.text:
                            t_name = name_elem.text or ""
                        t_name = t_name.strip()
                        if t_name:
                            cached[t_name.lower()] = t_name
                except Exception:
                    matches = re.findall(r'<VOUCHERTYPE [^>]*NAME="([^"]+)"', clean_txt)
                    for m in matches:
                        m_str = m.strip()
                        if m_str:
                            cached[m_str.lower()] = m_str
        except Exception as exc:
            logger.warning(f"Failed to query VoucherType collection from Tally: {exc}")

        # Check in refreshed cache
        if v_lower in cached:
            return True, cached[v_lower]

        # Smart alias check for Quotation
        if v_lower in ("quotation", "quote", "estimates", "estimate"):
            for alias in ("quotation voucher", "sales quotation", "quote", "estimate", "proforma invoice"):
                if alias in cached:
                    resolved = cached[alias]
                    cached[v_lower] = resolved
                    logger.info(f"Smart-mapped voucher type '{voucher_type_name}' to existing '{resolved}' in Tally")
                    return True, resolved

        # Try to auto-create custom voucher type in Tally
        resolved_parent = parent or determine_voucher_type_parent(v_clean)
        candidates = ["Quotation Voucher", "Sales Quotation"] if v_lower == "quotation" else [v_clean]

        for cand in candidates:
            cand_lower = cand.lower()
            if cand_lower in cached:
                cached[v_lower] = cached[cand_lower]
                return True, cached[cand_lower]

            vt_xml = build_voucher_type_import_xml({
                "company_name": comp_key,
                "name": cand,
                "parent": resolved_parent,
            })
            try:
                ok, status, res_txt, _ = await self.client.send_xml_request_async(
                    host=host, port=port, xml_content=vt_xml
                )
                if ok and status == 200 and ("<CREATED>1</CREATED>" in res_txt or "<ALTERED>1</ALTERED>" in res_txt):
                    if "<EXCEPTIONS>0</EXCEPTIONS>" in res_txt and "<ERRORS>0</ERRORS>" in res_txt:
                        logger.info(f"Auto-Created Voucher Type '{cand}' under '{resolved_parent}' in Tally (Company: '{comp_key}')")
                        cached[cand_lower] = cand
                        cached[v_lower] = cand
                        return True, cand
            except Exception as e:
                logger.warning(f"Failed to auto-create voucher type '{cand}': {e}")

        logger.warning(f"Voucher type '{voucher_type_name}' not found and could not be created; falling back to '{resolved_parent}'")
        cached[v_lower] = resolved_parent
        return True, resolved_parent

    async def import_ledger(self, host: str, port: int, ledger_data: Dict[str, Any]) -> Dict[str, Any]:
        """Explicitly creates a Ledger in Tally Prime."""
        xml_payload = build_ledger_import_xml(ledger_data)
        ok, status_code, res_text, err_msg = await self.client.send_xml_request_async(
            host=host, port=port, xml_content=xml_payload
        )

        if not ok or status_code != 200:
            return {
                "success": False,
                "message": "Failed to post ledger XML to Tally Prime HTTP interface.",
                "error": err_msg or f"HTTP status code {status_code}",
            }

        success, _, parse_err = parse_tally_import_response(res_text, default_voucher_number="LEDGER_CREATED")
        if not success:
            return {
                "success": False,
                "message": "Tally Prime rejected the ledger creation.",
                "error": parse_err,
            }

        return {
            "success": True,
            "message": f"Ledger '{ledger_data.get('name')}' successfully created in Tally Prime.",
            "error": None,
        }

    async def import_voucher(self, host: str, port: int, voucher_data: Dict[str, Any]) -> Dict[str, Any]:
        company_name = voucher_data.get("company_name", "")

        # Guard: Check Tally connectivity & verify if target company is open in Tally Prime
        is_online, is_loaded, open_comps = await self.check_tally_company_status(host, port, company_name)
        if not is_online:
            logger.info(f"Tally Prime is offline at {host}:{port}. Queueing voucher.")
            return {
                "success": False,
                "should_queue": True,
                "status": "TALLY_OFFLINE",
                "voucher_number": None,
                "company_name": company_name,
                "message": f"Tally Prime is offline at {host}:{port}.",
                "reason": "Tally Prime is not running or HTTP port 9000 is closed.",
                "action": "Ensure Tally Prime is running. Voucher will auto-post once connected.",
            }
        if company_name and not is_loaded:
            logger.info(f"Target company '{company_name}' is not open in Tally. Queueing voucher.")
            return {
                "success": False,
                "should_queue": True,
                "status": "COMPANY_NOT_LOADED",
                "voucher_number": None,
                "company_name": company_name,
                "message": f"Company '{company_name}' is not currently open in Tally.",
                "reason": f"Company '{company_name}' is not open in Tally Prime (Active: {', '.join(open_comps) or 'None'}).",
                "action": f"Open '{company_name}' inside Tally Prime (Gateway of Tally). Voucher will auto-post.",
            }

        raw_vtype = _clean_str(
            voucher_data.get("voucher_type")
            or voucher_data.get("voucherType")
            or voucher_data.get("vtype")
            or voucher_data.get("type")
            or "Sales"
        )
        ok_vt, resolved_vtype = await self.ensure_voucher_type(
            host=host, port=port, company_name=company_name, voucher_type_name=raw_vtype
        )
        if resolved_vtype:
            voucher_data["voucher_type"] = resolved_vtype
            voucher_data["voucherType"] = resolved_vtype
            v_type = resolved_vtype.lower()
        else:
            v_type = (voucher_data.get("voucher_type") or "Sales").lower()

        party_ledger = voucher_data.get("party_ledger") or voucher_data.get("party_name", "")
        explicit_parent = (
            voucher_data.get("party_parent")
            or voucher_data.get("partyParent")
            or voucher_data.get("parent")
            or voucher_data.get("group")
        )
        if explicit_parent:
            party_parent = explicit_parent
        else:
            party_type_hint = str(voucher_data.get("partyType") or voucher_data.get("party_type") or "").strip().upper()
            if "DEBTOR" in party_type_hint or "CUSTOMER" in party_type_hint or "CLIENT" in party_type_hint:
                party_parent = "Sundry Debtors"
            elif "CREDITOR" in party_type_hint or "SUPPLIER" in party_type_hint or "VENDOR" in party_type_hint:
                party_parent = "Sundry Creditors"
            elif any(k in v_type for k in ("sales", "receipt", "quotation", "quote", "estimate", "proforma")):
                party_parent = "Sundry Debtors"
            else:
                party_parent = "Sundry Creditors"

        if party_ledger and party_ledger.lower() not in ("cash", "bank"):
            await self.ensure_ledger(
                host=host,
                port=port,
                company_name=company_name,
                ledger_name=party_ledger,
                parent=party_parent,
                extra_info={
                    "state": voucher_data.get("state"),
                    "gstin": voucher_data.get("gstin") or voucher_data.get("party_gstin"),
                    "mobile": voucher_data.get("mobile") or voucher_data.get("phone"),
                    "address": voucher_data.get("address"),
                }
            )

        items = _extract_items_list(voucher_data)
        if items and isinstance(items, list):
            for it in items:
                i_name = _extract_item_name(it)
                if i_name:
                    i_unit = _clean_str(it.get("units") or it.get("unit") or it.get("uom")) or "Pcs"
                    i_hsn = _clean_str(it.get("hsn_code") or it.get("hsnCode") or it.get("hsn"))
                    await self.ensure_stock_item(
                        host=host, port=port, company_name=company_name, item_name=i_name, unit_name=i_unit, hsn_code=i_hsn
                    )

        if "sales" in v_type or "quotation" in v_type or "quote" in v_type:
            sales_ledger = _clean_str(voucher_data.get("sales_ledger") or voucher_data.get("salesLedger") or "Sales")
            await self.ensure_ledger(
                host=host,
                port=port,
                company_name=company_name,
                ledger_name=sales_ledger,
                parent="Sales Accounts"
            )
        elif "purchase" in v_type:
            purchase_ledger = _clean_str(voucher_data.get("purchase_ledger") or voucher_data.get("purchaseLedger") or "Purchase")
            await self.ensure_ledger(
                host=host,
                port=port,
                company_name=company_name,
                ledger_name=purchase_ledger,
                parent="Purchase Accounts"
            )
        elif "receipt" in v_type or "payment" in v_type:
            bank_ledger = _clean_str(
                voucher_data.get("bank_ledger")
                or voucher_data.get("bankLedger")
                or voucher_data.get("cash_bank_ledger")
                or voucher_data.get("account")
                or voucher_data.get("bank_account")
                or "Cash"
            )
            if bank_ledger.lower() not in ("cash",):
                bank_parent = voucher_data.get("bank_parent") or voucher_data.get("bankParent") or "Bank Accounts"
                await self.ensure_ledger(
                    host=host,
                    port=port,
                    company_name=company_name,
                    ledger_name=bank_ledger,
                    parent=bank_parent
                )

        xml_payload = build_voucher_import_xml(voucher_data)

        for tax in voucher_data.get("_calculated_tax_entries", []):
            tax_name = tax.get("name")
            if tax_name:
                await self.ensure_ledger(
                    host=host,
                    port=port,
                    company_name=company_name,
                    ledger_name=tax_name,
                    parent="Duties & Taxes"
                )

        if voucher_data.get("_has_round_off"):
            await self.ensure_ledger(
                host=host,
                port=port,
                company_name=company_name,
                ledger_name="Round Off",
                parent="Indirect Expenses"
            )

        ok, status_code, res_text, err_msg = await self.client.send_xml_request_async(
            host=host, port=port, xml_content=xml_payload, serialize_company=company_name
        )

        if not ok or status_code != 200:
            return {
                "success": False,
                "voucher_number": None,
                "message": "Failed to post voucher XML to Tally Prime HTTP interface.",
                "error": err_msg or f"HTTP status code {status_code}",
            }

        success, v_num, parse_err = parse_tally_import_response(
            res_text, default_voucher_number=voucher_data.get("voucher_number") or voucher_data.get("_generated_voucher_number")
        )

        if not success:
            logger.warning(f"Tally Import Failed. Error: {parse_err}. Response:\n{res_text}\nPayload Sent:\n{xml_payload}")
            diagnostic = diagnose_voucher_rejection(voucher_data, res_text, parse_err or "")
            is_company_err = "svcurrentcompany" in str(parse_err or "").lower() or "svcurrentcompany" in str(res_text or "").lower()
            return {
                "success": False,
                "should_queue": is_company_err,
                "status": "COMPANY_NOT_LOADED" if is_company_err else "FAILED",
                "voucher_number": None,
                "message": "Tally Prime rejected the voucher import.",
                "error": parse_err,
                "reason": diagnostic.get("reason"),
                "action": diagnostic.get("action"),
                "diagnostic": diagnostic,
            }

        return {
            "success": True,
            "voucher_number": v_num,
            "amount": float(voucher_data.get("amount", 0.0)),
            "company_name": company_name or voucher_data.get("company_name", ""),
            "message": f"Voucher '{v_num}' successfully created in Tally Prime.",
            "error": None,
        }
