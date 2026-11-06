from typing import Dict, Any, List, Optional


def build_pl_ledger_group_map(
    extracted_pl_accounts: Optional[List[Dict[str, Any]]] = None,
    extracted_ledgers: Optional[List[Dict[str, Any]]] = None,
    pl_data: Optional[Dict[str, Any]] = None
) -> Dict[str, str]:
    """
    Builds a case-insensitive lookup: lowercase ledger_name -> P&L group name.
    Supported P&L groups:
      - 'Sales Accounts'
      - 'Purchase Accounts'
      - 'Direct Expenses'
      - 'Indirect Expenses'
      - 'Direct Incomes'
      - 'Indirect Incomes'
    """
    mapping: Dict[str, str] = {}

    cat_to_group = {
        "SALES_ACCOUNTS": "Sales Accounts",
        "PURCHASE_ACCOUNTS": "Purchase Accounts",
        "DIRECT_EXPENSES": "Direct Expenses",
        "INDIRECT_EXPENSES": "Indirect Expenses",
        "DIRECT_INCOMES": "Direct Incomes",
        "INDIRECT_INCOMES": "Indirect Incomes"
    }

    # 1. Inspect pl_data dictionary (attached during cloud sync)
    if isinstance(pl_data, dict):
        for key, g_name in [
            ("salesAccounts", "Sales Accounts"),
            ("purchaseAccounts", "Purchase Accounts"),
            ("directExpenses", "Direct Expenses"),
            ("indirectExpenses", "Indirect Expenses"),
            ("directIncomes", "Direct Incomes"),
            ("indirectIncomes", "Indirect Incomes")
        ]:
            grp_obj = pl_data.get(key)
            if isinstance(grp_obj, dict):
                for led in grp_obj.get("ledgers", []):
                    if isinstance(led, dict) and led.get("ledgerName"):
                        mapping[str(led["ledgerName"]).strip().lower()] = g_name

        pl_accs = pl_data.get("plAccounts")
        if isinstance(pl_accs, list):
            for grp in pl_accs:
                if isinstance(grp, dict):
                    cat = grp.get("category", "")
                    g_name = cat_to_group.get(cat)
                    if g_name:
                        for led in grp.get("ledgers", []):
                            if isinstance(led, dict) and led.get("ledgerName"):
                                mapping[str(led["ledgerName"]).strip().lower()] = g_name

    # 2. Inspect extracted_pl_accounts list
    if isinstance(extracted_pl_accounts, list):
        for grp in extracted_pl_accounts:
            if not isinstance(grp, dict):
                continue
            cat = grp.get("category", "")
            g_name = cat_to_group.get(cat) or grp.get("groupName")
            if not g_name or cat == "PL_SUMMARY":
                continue
            for led in grp.get("ledgers", []):
                if isinstance(led, dict) and led.get("ledgerName"):
                    mapping[str(led["ledgerName"]).strip().lower()] = g_name

    # 3. Inspect extracted_ledgers list from Tally
    if isinstance(extracted_ledgers, list):
        for l in extracted_ledgers:
            if not isinstance(l, dict):
                continue
            l_name = str(l.get("name") or "").strip().lower()
            if not l_name or l_name in mapping:
                continue
            parent = str(l.get("parent") or "").strip().lower()
            if not parent:
                continue
            if parent == "sales accounts" or "sales account" in parent:
                mapping[l_name] = "Sales Accounts"
            elif parent == "purchase accounts" or "purchase account" in parent:
                mapping[l_name] = "Purchase Accounts"
            elif "indirect exp" in parent:
                mapping[l_name] = "Indirect Expenses"
            elif "direct exp" in parent:
                mapping[l_name] = "Direct Expenses"
            elif "indirect inc" in parent:
                mapping[l_name] = "Indirect Incomes"
            elif "direct inc" in parent:
                mapping[l_name] = "Direct Incomes"

    return mapping


def resolve_voucher_group(
    voucher: Dict[str, Any],
    pl_ledger_map: Optional[Dict[str, str]] = None,
    voucher_type_parent_map: Optional[Dict[str, str]] = None
) -> str:
    """
    Determines the voucherGroup for a voucher:
    1. Checks if any non-party ledger line belongs to a P&L group (Sales, Purchase, Expenses, Incomes).
    2. Checks VoucherType parent hierarchy (e.g. Tax Invoice -> Sales).
    3. Fallback to base voucherType name pattern matching.
    """
    if not isinstance(voucher, dict):
        return "Sales Accounts"

    raw_dict = voucher.get("raw") if isinstance(voucher.get("raw"), dict) else {}

    # Step 1: Check lines / ledgerEntries
    lines = voucher.get("lines") or voucher.get("ledgerEntries")
    if not lines and raw_dict:
        lines = raw_dict.get("lines") or raw_dict.get("ledgerEntries")

    if pl_ledger_map and isinstance(lines, list) and len(lines) > 0:
        party_lower = str(
            voucher.get("partyLedger") or
            voucher.get("partyName") or
            voucher.get("customer") or
            voucher.get("customerName") or
            raw_dict.get("party") or
            raw_dict.get("partyLedger") or
            ""
        ).strip().lower()

        # Priority check: look for non-party ledgers
        matched_groups: List[str] = []
        for entry in lines:
            if not isinstance(entry, dict):
                continue
            ln = str(entry.get("ledgerName") or entry.get("name") or "").strip().lower()
            if not ln:
                continue
            if party_lower and ln == party_lower:
                continue
            grp = pl_ledger_map.get(ln)
            if grp:
                matched_groups.append(grp)

        if matched_groups:
            for target_grp in [
                "Sales Accounts",
                "Purchase Accounts",
                "Direct Expenses",
                "Indirect Expenses",
                "Direct Incomes",
                "Indirect Incomes"
            ]:
                if target_grp in matched_groups:
                    return target_grp
            return matched_groups[0]

        # If all lines were party or no non-party matched, check every line
        for entry in lines:
            if not isinstance(entry, dict):
                continue
            ln = str(entry.get("ledgerName") or entry.get("name") or "").strip().lower()
            grp = pl_ledger_map.get(ln)
            if grp:
                return grp

    # Step 2: Check VoucherType parent mapping (if provided)
    v_type = str(
        voucher.get("voucherType") or
        voucher.get("voucher_type") or
        raw_dict.get("parent") or
        raw_dict.get("vouchertypename") or
        ""
    ).strip()
    vt_lower = v_type.lower()

    if voucher_type_parent_map and vt_lower in voucher_type_parent_map:
        vt_parent = voucher_type_parent_map[vt_lower].lower()
        if "sale" in vt_parent or "credit note" in vt_parent:
            return "Sales Accounts"
        elif "purchase" in vt_parent or "debit note" in vt_parent:
            return "Purchase Accounts"
        elif "receipt" in vt_parent:
            return "Receipt"
        elif "payment" in vt_parent:
            return "Payment"
        elif "contra" in vt_parent:
            return "Contra"
        elif "journal" in vt_parent:
            return "Journal"

    # Step 3: Base name string matching
    rp_lower = str(raw_dict.get("parent") or "").lower()
    comb = f"{vt_lower} {rp_lower}"
    if "sale" in comb or "credit note" in comb:
        return "Sales Accounts"
    elif "purchase" in comb or "debit note" in comb:
        return "Purchase Accounts"
    elif "indirect exp" in comb:
        return "Indirect Expenses"
    elif "direct exp" in comb:
        return "Direct Expenses"
    elif "indirect inc" in comb:
        return "Indirect Incomes"
    elif "direct inc" in comb:
        return "Direct Incomes"
    elif "receipt" in comb:
        return "Receipt"
    elif "payment" in comb:
        return "Payment"
    elif "contra" in comb:
        return "Contra"
    elif "journal" in comb:
        return "Journal"

    return v_type if v_type else "Sales Accounts"
