

import re
from datetime import datetime, timedelta
from xml.etree import ElementTree as ET
from typing import List, Dict, Any, Tuple, Optional
from shared.logging_config import get_logger

logger = get_logger("app.adapters.tally.parser")

def parse_tally_xml_response(xml_text: str) -> Tuple[bool, Optional[ET.Element], Optional[str]]:
    if not xml_text or not xml_text.strip():
        return False, None, "Empty response from Tally server."

    clean_xml = re.sub(r'&#(0?[0-8]|1[124-9]|2[0-9]|3[01]);', '', xml_text)
    clean_xml = re.sub(r'&#\d+;', '', clean_xml)
    clean_xml = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F]', '', clean_xml)

    try:
        root = ET.fromstring(clean_xml)
    except ET.ParseError as pe:
        return False, None, f"Malformed XML response from Tally: {pe}"

    line_err = root.find(".//LINEERROR")
    if line_err is not None and line_err.text:
        return False, root, f"Tally XML Line Error: {line_err.text}"

    return True, root, None

def parse_company_list(xml_text: str) -> List[Dict[str, Any]]:
    is_ok, root, err = parse_tally_xml_response(xml_text)
    if not is_ok or root is None:
        return []

    companies = []
    for comp in root.findall(".//COMPANY"):
        c_name = comp.get("NAME")
        if not c_name:
            name_tag = comp.find("NAME")
            if name_tag is None:
                name_tag = comp.find("NAME.LIST/NAME")
            if name_tag is not None and name_tag.text:
                c_name = name_tag.text.strip()

        guid_tag = comp.find("GUID")
        books_tag = comp.find("BOOKSFROM")
        if books_tag is None:
            books_tag = comp.find("STARTINGFROM")

        if c_name:
            companies.append({
                "name": c_name.strip(),
                "guid": guid_tag.text.strip() if guid_tag is not None and guid_tag.text else f"guid-{c_name.lower().replace(' ', '-')}",
                "financial_year_from": books_tag.text.strip() if books_tag is not None and books_tag.text else "01-Apr-2025",
                "status": "CONNECTED"
            })
    return companies

def classify_ledger_type(parent: Optional[str], raw_type: Optional[str] = None) -> str:
    """Classifies ledger type into CUSTOMER, VENDOR, BANK, CASH, EXPENSE, INCOME, TAX, ASSET, LIABILITY, or GENERAL."""
    if raw_type and raw_type.strip():
        return raw_type.strip().upper()
    if not parent:
        return "GENERAL"
    p = parent.strip().lower()
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

def format_tally_date(d_str: Optional[str]) -> Optional[str]:
    """Formats Tally date string (YYYYMMDD, DD-Mon-YYYY, etc.) to YYYY-MM-DD."""
    if not d_str or not str(d_str).strip():
        return None
    s = str(d_str).strip()
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    if len(s) == 10 and s[4] == '-' and s[7] == '-':
        return s
    for fmt in ("%d-%b-%Y", "%d-%b-%y", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            from datetime import datetime
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except Exception:
            pass
    return s

def clean_numeric(val: Any, default: float = 0.0) -> float:
    """Extracts numeric float value from string or number safely."""
    if val is None:
        return default
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    if not s:
        return default
    m = re.search(r'[-+]?\d+(?:\.\d+)?', s)
    if m:
        try:
            return float(m.group(0))
        except ValueError:
            return default
    return default

def parse_metadata_response(xml_text: str, tag_name: str) -> List[Dict[str, Any]]:
    is_ok, root, err = parse_tally_xml_response(xml_text)
    if not is_ok or root is None:
        return []

    items = []
    xml_tag = tag_name.upper().replace(" ", "").replace("_", "")

    if xml_tag in ("LEDGER", "LEDGERS"):
        for elem in root.findall(".//LEDGER"):
            item_name = elem.get("NAME") or elem.get("RESERVEDNAME")
            if not item_name:
                name_elem = elem.find("NAME") or elem.find("LEDGER.LIST/NAME")
                if name_elem is not None and name_elem.text:
                    item_name = name_elem.text.strip()

            guid_elem = elem.find("GUID")
            if not item_name and guid_elem is not None and guid_elem.text:
                item_name = f"LEDGER_{guid_elem.text.strip()[:8]}"

            if not item_name:
                continue

            parent_elem = elem.find("PARENT")
            bal_elem = elem.find("CLOSINGBALANCE")
            op_bal_elem = elem.find("OPENINGBALANCE")
            
            gstin_elem = elem.find("PARTYGSTIN")
            if gstin_elem is None or not gstin_elem.text:
                gstin_elem = elem.find("GSTIN")
            if gstin_elem is None or not gstin_elem.text:
                gstin_elem = elem.find(".//PARTYGSTIN")
            if gstin_elem is None or not gstin_elem.text:
                gstin_elem = elem.find(".//GSTIN")

            ltype_elem = elem.find("LEDGERCLASSIFICATION") or elem.find("LEDGERTYPE")
            alter_elem = elem.find("ALTERID")

            c_bal = 0.0
            if bal_elem is not None and bal_elem.text:
                try:
                    c_bal = float(bal_elem.text.strip())
                except ValueError:
                    c_bal = 0.0

            op_bal = 0.0
            if op_bal_elem is not None and op_bal_elem.text:
                try:
                    op_bal = float(op_bal_elem.text.strip())
                except ValueError:
                    op_bal = 0.0

            parent_val = parent_elem.text.strip() if parent_elem is not None and parent_elem.text else ""
            gstin_val = gstin_elem.text.strip() if gstin_elem is not None and gstin_elem.text and gstin_elem.text.strip() else None
            raw_ltype = ltype_elem.text.strip() if ltype_elem is not None and ltype_elem.text else None
            computed_ltype = classify_ledger_type(parent_val, raw_ltype)
            guid_val = guid_elem.text.strip() if guid_elem is not None and guid_elem.text else None
            alt_id = int(alter_elem.text.strip()) if alter_elem is not None and alter_elem.text and alter_elem.text.strip().isdigit() else 0

            email_elem = elem.find("EMAIL")
            email_val = email_elem.text.strip() if email_elem is not None and email_elem.text else ""

            phone_elem = elem.find("LEDGERPHONE")
            if phone_elem is None or not phone_elem.text:
                phone_elem = elem.find("LEDGERMOBILE")
            if phone_elem is None or not phone_elem.text:
                phone_elem = elem.find("LEDGERCONTACT")
            phone_val = phone_elem.text.strip() if phone_elem is not None and phone_elem.text else ""

            addr_nodes = elem.findall(".//ADDRESS.LIST/ADDRESS") + elem.findall(".//ADDRESS")
            addr_lines = [a.text.strip() for a in addr_nodes if a.text and a.text.strip()]
            addr_val = ", ".join(dict.fromkeys(addr_lines))

            d_elem = elem.find("STARTINGFROM")
            if d_elem is None:
                d_elem = elem.find("ACTIVEFROM")
            if d_elem is None:
                d_elem = elem.find("APPLICABLEFROM")
            if d_elem is None:
                d_elem = elem.find("OPENINGBALANCEDATE")
            raw_d = d_elem.text.strip() if d_elem is not None and d_elem.text else None
            parsed_date = format_tally_date(raw_d) or "2022-04-01"

            # Parse Credit Limit
            cl_elem = elem.find("CREDITLIMIT")
            credit_limit = 0.0
            if cl_elem is not None and cl_elem.text and cl_elem.text.strip():
                clean_cl = re.sub(r'[^\d.-]', '', cl_elem.text.strip())
                try:
                    credit_limit = float(clean_cl) if clean_cl else 0.0
                except (ValueError, TypeError):
                    credit_limit = 0.0

            # Parse Bill Credit Period / Credit Days
            cp_elem = elem.find("BILLCREDITPERIOD")
            if cp_elem is None or not cp_elem.text:
                cp_elem = elem.find("CREDITPERIOD")
            credit_period_str = cp_elem.text.strip() if cp_elem is not None and cp_elem.text else ""
            credit_days = 0
            if credit_period_str:
                m_days = re.search(r'\d+', credit_period_str)
                if m_days:
                    try:
                        credit_days = int(m_days.group())
                    except (ValueError, TypeError):
                        credit_days = 0

            items.append({
                "tallyExternalId": guid_val or item_name.strip(),
                "name": item_name.strip(),
                "parent": parent_val,
                "group": parent_val,
                "ledgerType": computed_ltype,
                "date": parsed_date,
                "email": email_val,
                "phone": phone_val,
                "address": addr_val,
                "openingBalance": op_bal,
                "closingBalance": c_bal,
                "creditLimit": credit_limit,
                "creditDays": credit_days,
                "creditPeriod": credit_period_str,
                "billCreditPeriod": credit_period_str,
                "gstin": gstin_val,
                "guid": guid_val,
                "alterid": alt_id,
                "raw": {
                    "name": item_name.strip(),
                    "parent": parent_val,
                    "group": parent_val,
                    "guid": guid_val,
                    "tallyExternalId": guid_val or item_name.strip(),
                    "date": parsed_date,
                    "email": email_val,
                    "phone": phone_val,
                    "address": addr_val,
                    "openingBalance": op_bal,
                    "closingBalance": c_bal,
                    "creditLimit": credit_limit,
                    "creditDays": credit_days,
                    "creditPeriod": credit_period_str,
                    "billCreditPeriod": credit_period_str,
                    "ledgerType": computed_ltype,
                    "gstin": gstin_val,
                    "alterid": alt_id
                }
            })

    elif xml_tag in ("VOUCHER", "VOUCHERS"):
        for elem in root.findall(".//VOUCHER"):
            v_num = elem.get("VCHNUM") or elem.get("NAME")
            if not v_num:
                v_num_elem = elem.find("VOUCHERNUMBER")
                if v_num_elem is not None and v_num_elem.text:
                    v_num = v_num_elem.text.strip()

            v_type_elem = elem.find("VOUCHERTYPENAME")
            if v_type_elem is None:
                v_type_elem = elem.find("VOUCHERTYPE")
            if v_type_elem is None:
                v_type_elem = elem.find("PARENT")
            v_type = v_type_elem.text.strip() if v_type_elem is not None and v_type_elem.text else (elem.get("VCHTYPE") or elem.get("VOUCHERTYPENAME") or "")

            guid_elem = elem.find("GUID")
            guid_val = guid_elem.text.strip() if guid_elem is not None and guid_elem.text else None

            if not v_num and guid_val:
                v_num = f"VCH_{guid_val[:8]}"

            date_elem = elem.find("DATE")
            if date_elem is None:
                date_elem = elem.find("EFFECTIVEDATE")
            if date_elem is None:
                date_elem = elem.find("VOUCHERDATE")
            if date_elem is None:
                date_elem = elem.find("REFERENCEDATE")
            raw_date = date_elem.text.strip() if date_elem is not None and date_elem.text else (elem.get("DATE") or elem.get("EFFECTIVEDATE"))
            parsed_date = format_tally_date(raw_date)

            eff_elem = elem.find("EFFECTIVEDATE") or elem.find("DATE")
            eff_raw = eff_elem.text.strip() if eff_elem is not None and eff_elem.text else elem.get("EFFECTIVEDATE")
            eff_date = format_tally_date(eff_raw) or parsed_date or "2023-04-01"
            if not parsed_date:
                parsed_date = eff_date

            ref_elem = elem.find("REFERENCE")
            ref_num = ref_elem.text.strip() if ref_elem is not None and ref_elem.text else ""
            ref_date_elem = elem.find("REFERENCEDATE")
            ref_date = format_tally_date(ref_date_elem.text.strip()) if ref_date_elem is not None and ref_date_elem.text else parsed_date

            pos_elem = elem.find("PLACEOFSUPPLY") or elem.find("STATENAME")
            place_of_supply = pos_elem.text.strip() if pos_elem is not None and pos_elem.text else ""

            opt_elem = elem.find("ISOPTIONAL")
            is_optional = (opt_elem.text.strip().lower() == "yes") if opt_elem is not None and opt_elem.text else False
            canc_elem = elem.find("ISCANCELLED")
            is_cancelled = (canc_elem.text.strip().lower() == "yes") if canc_elem is not None and canc_elem.text else False
            post_elem = elem.find("ISPOSTDATED")
            is_post_dated = (post_elem.text.strip().lower() == "yes") if post_elem is not None and post_elem.text else False

            party_elem = elem.find("PARTYLEDGERNAME")
            if party_elem is None:
                party_elem = elem.find("PARTYNAME")
            if party_elem is None:
                party_elem = elem.find("BASICBUYERNAME")
            party_val = party_elem.text.strip() if party_elem is not None and party_elem.text else ""

            ledger_entries = elem.findall(".//ALLLEDGERENTRIES.LIST") or elem.findall(".//LEDGERENTRIES.LIST")
            entries_total_amt = 0.0
            first_entry_name = ""
            parsed_ledger_entries = []
            all_bill_allocations = []
            all_bank_allocations = []

            for l_entry in ledger_entries:
                l_name_elem = l_entry.find("LEDGERNAME")
                l_amt_elem = l_entry.find("AMOUNT")
                l_deemed_elem = l_entry.find("ISDEEMEDPOSITIVE")
                l_party_elem = l_entry.find("ISPARTYLEDGER")
                
                entry_amt = 0.0
                if l_amt_elem is not None and l_amt_elem.text:
                    try:
                        entry_amt = float(l_amt_elem.text.strip())
                        entries_total_amt += abs(entry_amt)
                    except ValueError:
                        pass

                l_entry_name = l_name_elem.text.strip() if l_name_elem is not None and l_name_elem.text else ""
                if l_entry_name:
                    if not first_entry_name:
                        first_entry_name = l_entry_name
                    if not party_val:
                        lower_l = l_entry_name.lower()
                        if not any(k in lower_l for k in ["sales", "purchase", "cgst", "sgst", "igst", "round off", "discount"]):
                            party_val = l_entry_name

                bill_nodes = l_entry.findall(".//BILLALLOCATIONS.LIST")
                entry_bills = []
                for b in bill_nodes:
                    b_name_elem = b.find("NAME")
                    b_type_elem = b.find("BILLTYPE")
                    b_amt_elem = b.find("AMOUNT")
                    b_credit_elem = b.find("BILLCREDITPERIOD")
                    b_due_elem = b.find("DUEDATEOFTOTALAMOUNT") or b.find("DUEDATE")

                    b_amt_val = 0.0
                    if b_amt_elem is not None and b_amt_elem.text:
                        try:
                            b_amt_val = float(b_amt_elem.text.strip())
                        except ValueError:
                            pass

                    # Skip zero-amount allocations (from non-bill lines)
                    if abs(b_amt_val) < 0.001:
                        continue

                    b_name_str = b_name_elem.text.strip() if b_name_elem is not None and b_name_elem.text else ""
                    if not b_name_str:
                        b_name_str = v_num or str(guid_val or "")

                    raw_type = b_type_elem.text.strip() if b_type_elem is not None and b_type_elem.text else ""
                    if not raw_type or "agst" in raw_type.lower() or "against" in raw_type.lower():
                        b_type_str = "Against Ref"
                    elif "new" in raw_type.lower():
                        b_type_str = "New Ref"
                    elif "adv" in raw_type.lower():
                        b_type_str = "Advance"
                    elif "account" in raw_type.lower():
                        b_type_str = "On Account"
                    else:
                        b_type_str = raw_type

                    # Signed amount rule:
                    # Invoices (Sales, Purchase) positive; Settlements (Receipt, Payment) negative
                    upper_vtype = v_type.upper()
                    if any(k in upper_vtype for k in ["RECEIPT", "PAYMENT", "CREDIT NOTE"]):
                        final_amt = -abs(b_amt_val)
                    elif any(k in upper_vtype for k in ["SALES", "PURCHASE", "DEBIT NOTE"]):
                        final_amt = abs(b_amt_val)
                    else:
                        final_amt = -abs(b_amt_val) if b_type_str == "Against Ref" else abs(b_amt_val)

                    # Due date calculation
                    due_date_str = None
                    if b_due_elem is not None and b_due_elem.text and b_due_elem.text.strip():
                        due_date_str = format_tally_date(b_due_elem.text.strip())
                    elif b_credit_elem is not None and b_credit_elem.text and b_credit_elem.text.strip():
                        cp_raw = b_credit_elem.text.strip()
                        parsed_cp = format_tally_date(cp_raw)
                        if parsed_cp and parsed_cp != "2022-04-01" and re.match(r'^\d{4}-\d{2}-\d{2}$', parsed_cp):
                            due_date_str = parsed_cp
                        else:
                            m_days = re.search(r'\d+', cp_raw)
                            if m_days and parsed_date:
                                try:
                                    base_d = datetime.strptime(parsed_date, "%Y-%m-%d")
                                    due_date_str = (base_d + timedelta(days=int(m_days.group()))).strftime("%Y-%m-%d")
                                except Exception:
                                    due_date_str = None

                    bill_ext_id = f"{guid_val or v_num}:bill:{len(all_bill_allocations)}"
                    b_data = {
                        "tallyExternalId": bill_ext_id,
                        "billName": b_name_str,
                        "billType": b_type_str,
                        "amount": final_amt
                    }
                    if due_date_str:
                        b_data["dueDate"] = due_date_str

                    entry_bills.append(b_data)
                    all_bill_allocations.append({
                        "party": l_entry_name or party_val,
                        "voucherNumber": v_num,
                        "date": parsed_date,
                        **b_data
                    })

                bank_nodes = l_entry.findall(".//BANKALLOCATIONS.LIST")
                entry_bank = []
                for bn in bank_nodes:
                    inst_num = bn.find("INSTRUMENTNUMBER")
                    inst_date = bn.find("INSTRUMENTDATE")
                    bank_n = bn.find("BANKNAME")
                    bn_amt = bn.find("AMOUNT")
                    bn_amt_val = 0.0
                    if bn_amt is not None and bn_amt.text:
                        try:
                            bn_amt_val = float(bn_amt.text.strip())
                        except ValueError:
                            pass
                    bank_info = {
                        "instrumentNumber": inst_num.text.strip() if inst_num is not None and inst_num.text else "",
                        "instrumentDate": format_tally_date(inst_date.text.strip()) if inst_date is not None and inst_date.text else parsed_date,
                        "bankName": bank_n.text.strip() if bank_n is not None and bank_n.text else "",
                        "amount": abs(bn_amt_val)
                    }
                    entry_bank.append(bank_info)
                    all_bank_allocations.append({
                        "voucherNumber": v_num,
                        "date": parsed_date,
                        "party": party_val,
                        "ledger": l_entry_name,
                        **bank_info
                    })

                parsed_ledger_entries.append({
                    "ledgerName": l_entry_name,
                    "amount": entry_amt,
                    "isDeemedPositive": (l_deemed_elem.text.strip().lower() == "yes") if l_deemed_elem is not None and l_deemed_elem.text else False,
                    "isPartyLedger": (l_party_elem.text.strip().lower() == "yes") if l_party_elem is not None and l_party_elem.text else False,
                    "billAllocations": entry_bills,
                    "bankAllocations": entry_bank
                })

            if not party_val and first_entry_name:
                party_val = first_entry_name

            inv_nodes = elem.findall(".//ALLINVENTORYENTRIES.LIST") + elem.findall(".//INVENTORYENTRIES.LIST")
            parsed_inventory_entries = []
            for inv in inv_nodes:
                i_name_elem = inv.find("STOCKITEMNAME") or inv.find("ITEMNAME")
                i_rate_elem = inv.find("RATE")
                i_qty_elem = inv.find("ACTUALQTY") or inv.find("BILLEDQTY")
                i_amt_elem = inv.find("AMOUNT")
                i_disc_elem = inv.find("DISCOUNT")
                i_godown_elem = inv.find(".//GODOWNNAME") or inv.find("GODOWNNAME")
                i_batch_elem = inv.find(".//BATCHNAME") or inv.find("BATCHNAME")
                i_hsn_elem = inv.find(".//HSNCODE") or inv.find("HSNCODE")

                i_amt_val = 0.0
                if i_amt_elem is not None and i_amt_elem.text:
                    try:
                        i_amt_val = abs(float(i_amt_elem.text.strip()))
                    except ValueError:
                        pass

                i_qty_str = i_qty_elem.text.strip() if i_qty_elem is not None and i_qty_elem.text else ""
                i_unit_elem = inv.find(".//UNIT") or inv.find("UNIT") or inv.find(".//BASEUNITS") or inv.find("BASEUNITS") or inv.find(".//GSTREPUOM")
                i_unit = i_unit_elem.text.strip() if i_unit_elem is not None and i_unit_elem.text else ""
                if not i_unit and i_qty_str:
                    u_match = re.findall(r'[a-zA-Z]+', i_qty_str)
                    if u_match:
                        i_unit = u_match[-1].strip()

                parsed_inventory_entries.append({
                    "itemName": i_name_elem.text.strip() if i_name_elem is not None and i_name_elem.text else "",
                    "rate": i_rate_elem.text.strip() if i_rate_elem is not None and i_rate_elem.text else "",
                    "quantity": i_qty_str,
                    "unit": i_unit,
                    "amount": i_amt_val,
                    "discount": i_disc_elem.text.strip() if i_disc_elem is not None and i_disc_elem.text else "0",
                    "godown": i_godown_elem.text.strip() if i_godown_elem is not None and i_godown_elem.text else "",
                    "batch": i_batch_elem.text.strip() if i_batch_elem is not None and i_batch_elem.text else "",
                    "hsnCode": i_hsn_elem.text.strip() if i_hsn_elem is not None and i_hsn_elem.text else ""
                })

            amt_elem = elem.find("AMOUNT")
            if amt_elem is None:
                amt_elem = elem.find("CLOSINGBALANCE")
            amt_val = 0.0
            if amt_elem is not None and amt_elem.text:
                try:
                    amt_val = abs(float(amt_elem.text.strip()))
                except ValueError:
                    amt_val = 0.0
            elif entries_total_amt > 0:
                amt_val = entries_total_amt / 2.0 if len(ledger_entries) > 1 else entries_total_amt

            narr_elem = elem.find("NARRATION") or elem.find("NARRATION.LIST/NARRATION") or elem.find(".//NARRATION")
            narr_val = narr_elem.text.strip() if narr_elem is not None and narr_elem.text and narr_elem.text.strip() != "None" else ""
            if not narr_val:
                for le in parsed_ledger_entries:
                    pass

            alter_elem = elem.find("ALTERID")
            alt_id = int(alter_elem.text.strip()) if alter_elem is not None and alter_elem.text and alter_elem.text.strip().isdigit() else 0

            ext_vch_id = str(guid_val or v_num)
            items.append({
                "voucherId": ext_vch_id,
                "tallyExternalId": ext_vch_id,
                "voucherNumber": str(v_num or ""),
                "voucherType": str(v_type or "Sales"),
                "date": str(parsed_date or eff_date or "2023-04-01"),
                "effectiveDate": str(eff_date or parsed_date or "2023-04-01"),
                "reference": str(ref_num or ""),
                "referenceDate": str(ref_date or parsed_date or "2023-04-01"),
                "placeOfSupply": str(place_of_supply or ""),
                "partyLedger": str(party_val or "Cash"),
                "amount": float(amt_val or 0.0),
                "narration": str(narr_val or ""),
                "isOptional": bool(is_optional),
                "isCancelled": bool(is_cancelled),
                "isPostDated": bool(is_post_dated),
                "guid": str(guid_val or ext_vch_id),
                "alterid": int(alt_id or 0),
                "ledgerEntries": parsed_ledger_entries,
                "inventoryEntries": parsed_inventory_entries,
                "billAllocations": all_bill_allocations,
                "bankAllocations": all_bank_allocations,
                "raw": {
                    "voucherId": ext_vch_id,
                    "name": str(v_num or ""),
                    "parent": str(v_type or "Sales"),
                    "party": str(party_val or "Cash"),
                    "alterid": int(alt_id or 0)
                }
            })

    elif xml_tag in ("STOCKITEM", "STOCKITEMS", "STOCK_ITEM", "STOCK_ITEMS"):
        for elem in root.findall(".//STOCKITEM"):
            item_name = elem.get("NAME") or elem.get("RESERVEDNAME")
            if not item_name:
                name_elem = elem.find("NAME") or elem.find("STOCKITEM.LIST/NAME")
                if name_elem is not None and name_elem.text:
                    item_name = name_elem.text.strip()

            guid_elem = elem.find("GUID")
            if not item_name and guid_elem is not None and guid_elem.text:
                item_name = f"ITEM_{guid_elem.text.strip()[:8]}"

            if not item_name:
                continue

            parent_elem = elem.find("PARENT")
            cat_elem = elem.find("CATEGORY")
            unit_elem = elem.find("BASEUNITS") or elem.find("UNIT") or elem.find("GSTREPUOM") or elem.find(".//BASEUNITS") or elem.find(".//UNIT")
            alt_unit_elem = elem.find("ADDITIONALUNITS") or elem.find(".//ADDITIONALUNITS")
            bal_elem = elem.find("CLOSINGBALANCE")
            op_bal_elem = elem.find("OPENINGBALANCE")
            rate_elem = elem.find("CLOSINGRATE")
            val_elem = elem.find("CLOSINGVALUE")
            op_rate_elem = elem.find("OPENINGRATE")
            op_val_elem = elem.find("OPENINGVALUE")
            hsn_nodes = (
                elem.findall(".//HSNCODE") + 
                elem.findall("HSNCODE") + 
                elem.findall(".//HSNDETAILS.LIST/HSNCODE") + 
                elem.findall(".//GSTDETAILS.LIST/HSNCODE") +
                elem.findall(".//HSN") +
                elem.findall("HSN")
            )
            hsn_val = ""
            for hn in reversed(hsn_nodes):
                if hn is not None and hn.text and hn.text.strip():
                    txt = hn.text.strip()
                    if any(c.isdigit() for c in txt):
                        hsn_val = txt
                        break
                    elif not hsn_val:
                        hsn_val = txt

            gst_app_elem = elem.find("GSTAPPLICABLE")
            reorder_elem = elem.find("REORDERLEVEL")
            alter_elem = elem.find("ALTERID")

            parent_val = parent_elem.text.strip() if parent_elem is not None and parent_elem.text else ""
            cat_val = cat_elem.text.strip() if cat_elem is not None and cat_elem.text else ""
            unit_val = unit_elem.text.strip() if unit_elem is not None and unit_elem.text else ""
            alt_unit_val = alt_unit_elem.text.strip() if alt_unit_elem is not None and alt_unit_elem.text else ""
            c_bal_raw = bal_elem.text.strip() if bal_elem is not None and bal_elem.text else "0"
            op_bal_raw = op_bal_elem.text.strip() if op_bal_elem is not None and op_bal_elem.text else "0"

            if not unit_val:
                match_u = re.findall(r'[a-zA-Z]+', c_bal_raw) or re.findall(r'[a-zA-Z]+', op_bal_raw)
                if match_u:
                    unit_val = match_u[-1].strip()

            c_rate_raw = rate_elem.text.strip() if rate_elem is not None and rate_elem.text else "0"
            c_val_raw = val_elem.text.strip() if val_elem is not None and val_elem.text else "0"
            op_rate_raw = op_rate_elem.text.strip() if op_rate_elem is not None and op_rate_elem.text else "0"
            op_val_raw = op_val_elem.text.strip() if op_val_elem is not None and op_val_elem.text else "0"
            gst_app_val = gst_app_elem.text.strip() if gst_app_elem is not None and gst_app_elem.text else "Applicable"
            reorder_val = reorder_elem.text.strip() if reorder_elem is not None and reorder_elem.text else "0"
            guid_val = guid_elem.text.strip() if guid_elem is not None and guid_elem.text else None
            alt_id = int(alter_elem.text.strip()) if alter_elem is not None and alter_elem.text and alter_elem.text.strip().isdigit() else 0

            c_qty = clean_numeric(c_bal_raw)
            op_qty = clean_numeric(op_bal_raw)
            c_rate = clean_numeric(c_rate_raw)
            c_val = clean_numeric(c_val_raw)
            op_rate = clean_numeric(op_rate_raw)
            op_val = clean_numeric(op_val_raw)
            if c_val == 0.0 and c_qty != 0.0 and c_rate != 0.0:
                c_val = round(c_qty * c_rate, 2)
            if op_val == 0.0 and op_qty != 0.0 and op_rate != 0.0:
                op_val = round(op_qty * op_rate, 2)

            d_elem = elem.find("STARTINGFROM") or elem.find("ACTIVEFROM") or elem.find("APPLICABLEFROM")
            raw_d = d_elem.text.strip() if d_elem is not None and d_elem.text else None
            parsed_date = format_tally_date(raw_d) or "2022-04-01"

            # Godown and Batch extraction
            batch_val = ""
            for bn_elem in (elem.findall(".//BATCHNAME") + elem.findall(".//BATCHALLOCATIONS.LIST/BATCHNAME") + elem.findall("BATCHNAME")):
                if bn_elem is not None and bn_elem.text and bn_elem.text.strip():
                    batch_val = bn_elem.text.strip()
                    break
            if not batch_val:
                batch_val = "Primary Batch"

            godown_val = ""
            for gn_elem in (elem.findall(".//GODOWNNAME") + elem.findall(".//BATCHALLOCATIONS.LIST/GODOWNNAME") + elem.findall(".//GODOWNALLOCATIONS.LIST/GODOWNNAME") + elem.findall("GODOWNNAME")):
                if gn_elem is not None and gn_elem.text and gn_elem.text.strip():
                    godown_val = gn_elem.text.strip()
                    break
            if not godown_val:
                godown_val = "Main Location"

            ext_id = guid_val or item_name.strip()

            items.append({
                "tallyExternalId": ext_id,
                "name": item_name.strip(),
                "itemName": item_name.strip(),
                "itemTallyExternalId": guid_val or ext_id,
                "godown": godown_val,
                "batch": batch_val,
                "quantity": c_qty,
                "rate": c_rate,
                "value": c_val,
                "parent": parent_val,
                "group": parent_val,
                "category": cat_val,
                "unit": unit_val,
                "alternateUnit": alt_unit_val,
                "date": parsed_date,
                "openingBalance": op_qty,
                "openingRate": op_rate,
                "openingValue": op_val,
                "closingBalance": c_qty,
                "closingRate": c_rate,
                "closingValue": c_val,
                "hsnCode": hsn_val,
                "gstApplicable": gst_app_val,
                "reorderLevel": reorder_val,
                "guid": guid_val,
                "alterid": alt_id,
                "raw": {
                    "tallyExternalId": ext_id,
                    "name": item_name.strip(),
                    "itemName": item_name.strip(),
                    "itemTallyExternalId": guid_val or ext_id,
                    "godown": godown_val,
                    "batch": batch_val,
                    "parent": parent_val,
                    "category": cat_val,
                    "unit": unit_val,
                    "date": parsed_date,
                    "openingBalance": op_qty,
                    "closingBalance": c_qty,
                    "closingRate": c_rate,
                    "closingValue": c_val,
                    "hsnCode": hsn_val,
                    "guid": guid_val,
                    "alterid": alt_id
                }
            })

    elif xml_tag in ("GROUP", "GROUPS"):
        for elem in root.findall(".//GROUP"):
            g_name = elem.get("NAME") or elem.get("RESERVEDNAME")
            if not g_name:
                name_elem = elem.find("NAME")
                if name_elem is not None and name_elem.text:
                    g_name = name_elem.text.strip()
            guid_elem = elem.find("GUID")
            if not g_name and guid_elem is not None and guid_elem.text:
                g_name = f"GRP_{guid_elem.text.strip()[:8]}"
            if not g_name:
                continue

            parent_elem = elem.find("PARENT")
            parent_val = parent_elem.text.strip() if parent_elem is not None and parent_elem.text else ""
            is_addable = elem.find("ISADDABLE")
            is_sub = elem.find("ISSUBLEDGER")
            nature_elem = elem.find("NATUREOFGROUP")
            alter_elem = elem.find("ALTERID")
            guid_val = guid_elem.text.strip() if guid_elem is not None and guid_elem.text else None
            alt_id = int(alter_elem.text.strip()) if alter_elem is not None and alter_elem.text and alter_elem.text.strip().isdigit() else 0

            items.append({
                "tallyExternalId": guid_val or g_name.strip(),
                "name": g_name.strip(),
                "parent": parent_val,
                "isPrimary": not bool(parent_val),
                "isAddable": (is_addable.text.strip().lower() == "yes") if is_addable is not None and is_addable.text else True,
                "isSubLedger": (is_sub.text.strip().lower() == "yes") if is_sub is not None and is_sub.text else False,
                "natureOfGroup": nature_elem.text.strip() if nature_elem is not None and nature_elem.text else "",
                "guid": guid_val,
                "alterid": alt_id,
                "raw": {
                    "name": g_name.strip(),
                    "parent": parent_val,
                    "guid": guid_val,
                    "alterid": alt_id
                }
            })

    elif xml_tag in ("GODOWN", "GODOWNS"):
        for elem in root.findall(".//GODOWN"):
            gd_name = elem.get("NAME") or elem.get("RESERVEDNAME")
            if not gd_name:
                name_elem = elem.find("NAME")
                if name_elem is not None and name_elem.text:
                    gd_name = name_elem.text.strip()
            guid_elem = elem.find("GUID")
            if not gd_name and guid_elem is not None and guid_elem.text:
                gd_name = f"GD_{guid_elem.text.strip()[:8]}"
            if not gd_name:
                continue

            parent_elem = elem.find("PARENT")
            parent_val = parent_elem.text.strip() if parent_elem is not None and parent_elem.text else ""
            addr_nodes = elem.findall(".//ADDRESS.LIST/ADDRESS") + elem.findall(".//ADDRESS")
            addr_lines = [a.text.strip() for a in addr_nodes if a.text and a.text.strip()]
            addr_val = ", ".join(dict.fromkeys(addr_lines))
            alter_elem = elem.find("ALTERID")
            guid_val = guid_elem.text.strip() if guid_elem is not None and guid_elem.text else None
            alt_id = int(alter_elem.text.strip()) if alter_elem is not None and alter_elem.text and alter_elem.text.strip().isdigit() else 0

            items.append({
                "tallyExternalId": guid_val or gd_name.strip(),
                "name": gd_name.strip(),
                "parent": parent_val,
                "address": addr_val,
                "guid": guid_val,
                "alterid": alt_id,
                "raw": {
                    "name": gd_name.strip(),
                    "parent": parent_val,
                    "address": addr_val,
                    "guid": guid_val,
                    "alterid": alt_id
                }
            })

    elif xml_tag in ("UNIT", "UNITS"):
        for elem in root.findall(".//UNIT"):
            u_name = elem.get("NAME") or elem.get("RESERVEDNAME")
            if not u_name:
                name_elem = elem.find("NAME") or elem.find("ORIGINALNAME")
                if name_elem is not None and name_elem.text:
                    u_name = name_elem.text.strip()
            guid_elem = elem.find("GUID")
            if not u_name and guid_elem is not None and guid_elem.text:
                u_name = f"UNIT_{guid_elem.text.strip()[:8]}"
            if not u_name:
                continue

            symbol_elem = elem.find("SYMBOL") or elem.find("NAME")
            symbol_val = symbol_elem.text.strip() if symbol_elem is not None and symbol_elem.text else u_name
            orig_elem = elem.find("ORIGINALNAME")
            orig_val = orig_elem.text.strip() if orig_elem is not None and orig_elem.text else u_name
            dec_elem = elem.find("DECIMALPLACES")
            dec_val = int(dec_elem.text.strip()) if dec_elem is not None and dec_elem.text and dec_elem.text.strip().isdigit() else 0
            alter_elem = elem.find("ALTERID")
            guid_val = guid_elem.text.strip() if guid_elem is not None and guid_elem.text else None
            alt_id = int(alter_elem.text.strip()) if alter_elem is not None and alter_elem.text and alter_elem.text.strip().isdigit() else 0

            items.append({
                "tallyExternalId": guid_val or u_name.strip(),
                "name": u_name.strip(),
                "symbol": symbol_val,
                "originalName": orig_val,
                "decimalPlaces": dec_val,
                "guid": guid_val,
                "alterid": alt_id,
                "raw": {
                    "name": u_name.strip(),
                    "symbol": symbol_val,
                    "guid": guid_val,
                    "alterid": alt_id
                }
            })

    elif xml_tag in ("COSTCENTRE", "COSTCENTRES", "COST_CENTRE", "COST_CENTRES"):
        for elem in root.findall(".//COSTCENTRE"):
            cc_name = elem.get("NAME") or elem.get("RESERVEDNAME")
            if not cc_name:
                name_elem = elem.find("NAME")
                if name_elem is not None and name_elem.text:
                    cc_name = name_elem.text.strip()
            guid_elem = elem.find("GUID")
            if not cc_name and guid_elem is not None and guid_elem.text:
                cc_name = f"CC_{guid_elem.text.strip()[:8]}"
            if not cc_name:
                continue

            cat_elem = elem.find("CATEGORY")
            cat_val = cat_elem.text.strip() if cat_elem is not None and cat_elem.text else "Primary Cost Category"
            alter_elem = elem.find("ALTERID")
            guid_val = guid_elem.text.strip() if guid_elem is not None and guid_elem.text else None
            alt_id = int(alter_elem.text.strip()) if alter_elem is not None and alter_elem.text and alter_elem.text.strip().isdigit() else 0

            items.append({
                "tallyExternalId": guid_val or cc_name.strip(),
                "name": cc_name.strip(),
                "category": cat_val,
                "guid": guid_val,
                "alterid": alt_id,
                "raw": {
                    "name": cc_name.strip(),
                    "category": cat_val,
                    "guid": guid_val,
                    "alterid": alt_id
                }
            })

    elif xml_tag in ("STOCKGROUP", "STOCKGROUPS", "STOCK_GROUP", "STOCK_GROUPS"):
        for elem in root.findall(".//STOCKGROUP"):
            sg_name = elem.get("NAME") or elem.get("RESERVEDNAME")
            if not sg_name:
                name_elem = elem.find("NAME")
                if name_elem is not None and name_elem.text:
                    sg_name = name_elem.text.strip()
            guid_elem = elem.find("GUID")
            if not sg_name and guid_elem is not None and guid_elem.text:
                sg_name = f"SG_{guid_elem.text.strip()[:8]}"
            if not sg_name:
                continue

            parent_elem = elem.find("PARENT")
            parent_val = parent_elem.text.strip() if parent_elem is not None and parent_elem.text else ""
            alter_elem = elem.find("ALTERID")
            guid_val = guid_elem.text.strip() if guid_elem is not None and guid_elem.text else None
            alt_id = int(alter_elem.text.strip()) if alter_elem is not None and alter_elem.text and alter_elem.text.strip().isdigit() else 0

            items.append({
                "tallyExternalId": guid_val or sg_name.strip(),
                "name": sg_name.strip(),
                "parent": parent_val,
                "guid": guid_val,
                "alterid": alt_id,
                "raw": {
                    "name": sg_name.strip(),
                    "parent": parent_val,
                    "guid": guid_val,
                    "alterid": alt_id
                }
            })

    elif xml_tag in ("STOCKCATEGORY", "STOCKCATEGORIES", "STOCK_CATEGORY", "STOCK_CATEGORIES"):
        for elem in root.findall(".//STOCKCATEGORY"):
            sc_name = elem.get("NAME") or elem.get("RESERVEDNAME")
            if not sc_name:
                name_elem = elem.find("NAME")
                if name_elem is not None and name_elem.text:
                    sc_name = name_elem.text.strip()
            guid_elem = elem.find("GUID")
            if not sc_name and guid_elem is not None and guid_elem.text:
                sc_name = f"SC_{guid_elem.text.strip()[:8]}"
            if not sc_name:
                continue

            parent_elem = elem.find("PARENT")
            parent_val = parent_elem.text.strip() if parent_elem is not None and parent_elem.text else ""
            alter_elem = elem.find("ALTERID")
            guid_val = guid_elem.text.strip() if guid_elem is not None and guid_elem.text else None
            alt_id = int(alter_elem.text.strip()) if alter_elem is not None and alter_elem.text and alter_elem.text.strip().isdigit() else 0

            items.append({
                "tallyExternalId": guid_val or sc_name.strip(),
                "name": sc_name.strip(),
                "parent": parent_val,
                "guid": guid_val,
                "alterid": alt_id,
                "raw": {
                    "name": sc_name.strip(),
                    "parent": parent_val,
                    "guid": guid_val,
                    "alterid": alt_id
                }
            })

    else:
        for elem in root.findall(f".//{xml_tag}"):
            item_name = elem.get("NAME") or elem.get("RESERVEDNAME")
            if not item_name:
                name_elem = elem.find("NAME") or elem.find(f"{xml_tag}.LIST/NAME")
                if name_elem is not None and name_elem.text:
                    item_name = name_elem.text.strip()

            guid_elem = elem.find("GUID")
            if not item_name and guid_elem is not None and guid_elem.text:
                item_name = f"{xml_tag}_{guid_elem.text.strip()[:8]}"

            if not item_name:
                continue

            parent_elem = elem.find("PARENT")
            alter_elem = elem.find("ALTERID")
            parent_val = parent_elem.text.strip() if parent_elem is not None and parent_elem.text else None
            guid_val = guid_elem.text.strip() if guid_elem is not None and guid_elem.text else None
            alt_id = int(alter_elem.text.strip()) if alter_elem is not None and alter_elem.text and alter_elem.text.strip().isdigit() else 0

            items.append({
                "name": item_name.strip(),
                "parent": parent_val,
                "guid": guid_val,
                "tallyExternalId": guid_val or item_name.strip(),
                "alterid": alt_id,
                "raw": {
                    "name": item_name.strip(),
                    "parent": parent_val,
                    "guid": guid_val,
                    "alterid": alt_id
                }
            })

    return items

