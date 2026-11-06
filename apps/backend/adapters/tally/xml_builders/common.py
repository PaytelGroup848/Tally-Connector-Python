import re
from datetime import datetime, date
from typing import Optional, Any


def format_tally_date(date_str: Any) -> str:
    """
    Converts ISO 8601 timestamps, dates, or date strings into Tally YYYYMMDD format.
    Handles:
      - datetime / date objects
      - ISO 8601 strings: "2026-09-25T10:30:00Z", "2026-09-25T10:30:00.000Z"
      - Standard dates: "2026-09-25", "25-09-2026", "25/09/2026", "2026/09/25"
      - Already formatted 8-digit strings: "20260925"
    """
    if not date_str:
        return datetime.now().strftime("%Y%m%d")

    if isinstance(date_str, datetime):
        return date_str.strftime("%Y%m%d")
    if isinstance(date_str, date):
        return date_str.strftime("%Y%m%d")

    clean_str = str(date_str).strip()
    if not clean_str or clean_str.lower() in ("none", "null", "undefined"):
        return datetime.now().strftime("%Y%m%d")

    # Already valid 8-digit YYYYMMDD
    if len(clean_str) == 8 and clean_str.isdigit():
        return clean_str

    # Extract date part if ISO string with 'T' or space separator
    date_part = clean_str
    if "T" in date_part:
        date_part = date_part.split("T")[0].strip()
    elif " " in date_part:
        date_part = date_part.split(" ")[0].strip()

    # Try common date formats on extracted date_part
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d", "%d.%m.%Y", "%Y.%m.%d"):
        try:
            dt = datetime.strptime(date_part, fmt)
            return dt.strftime("%Y%m%d")
        except ValueError:
            continue

    # Fallback: extract first 8 digits or clean punctuation
    digits = re.sub(r"\D", "", clean_str)
    if len(digits) >= 8:
        # If begins with reasonable year (19xx or 20xx)
        if digits[:4].isdigit() and 1900 <= int(digits[:4]) <= 2100:
            return digits[:8]
        # Or if DDMMYYYY
        if len(digits) == 8 and 1900 <= int(digits[4:]) <= 2100:
            return f"{digits[4:]}{digits[2:4]}{digits[:2]}"

    return datetime.now().strftime("%Y%m%d")



def escape_xml(value: Optional[str]) -> str:
    """Escapes special XML characters to prevent malformed XML payloads."""
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


def _clean_str(value: Any) -> str:
    """Cleans a string value, returning empty string if None, 'none', 'null', 'undefined'."""
    if value is None:
        return ""
    s = str(value).strip()
    if s.lower() in ("none", "null", "undefined"):
        return ""
    return s



# -------------------------------------------------------------------------
# Enterprise SaaS Safe Ledger & Group Classification Helpers
# -------------------------------------------------------------------------

TALLY_CANONICAL_STATES: dict[str, str] = {
    "01": "Jammu & Kashmir",
    "02": "Himachal Pradesh",
    "03": "Punjab",
    "04": "Chandigarh",
    "05": "Uttarakhand",
    "06": "Haryana",
    "07": "Delhi",
    "08": "Rajasthan",
    "09": "Uttar Pradesh",
    "10": "Bihar",
    "11": "Sikkim",
    "12": "Arunachal Pradesh",
    "13": "Nagaland",
    "14": "Manipur",
    "15": "Mizoram",
    "16": "Tripura",
    "17": "Meghalaya",
    "18": "Assam",
    "19": "West Bengal",
    "20": "Jharkhand",
    "21": "Odisha",
    "22": "Chhattisgarh",
    "23": "Madhya Pradesh",
    "24": "Gujarat",
    "25": "Daman and Diu",
    "26": "Dadra and Nagar Haveli",
    "27": "Maharashtra",
    "28": "Andhra Pradesh",
    "29": "Karnataka",
    "30": "Goa",
    "31": "Lakshadweep",
    "32": "Kerala",
    "33": "Tamil Nadu",
    "34": "Puducherry",
    "35": "Andaman and Nicobar Islands",
    "36": "Telangana",
    "37": "Andhra Pradesh",
    "38": "Ladakh",
    "97": "Other Territory",
    "99": "Centre Jurisdiction",
}

STATE_ALIAS_MAP: dict[str, str] = {
    "jammu and kashmir": "Jammu & Kashmir",
    "jammu & kashmir": "Jammu & Kashmir",
    "jammu kashmir": "Jammu & Kashmir",
    "jk": "Jammu & Kashmir",
    "j&k": "Jammu & Kashmir",
    "himachal pradesh": "Himachal Pradesh",
    "himachal": "Himachal Pradesh",
    "hp": "Himachal Pradesh",
    "punjab": "Punjab",
    "pb": "Punjab",
    "chandigarh": "Chandigarh",
    "ch": "Chandigarh",
    "uttarakhand": "Uttarakhand",
    "uttaranchal": "Uttarakhand",
    "uk": "Uttarakhand",
    "haryana": "Haryana",
    "hr": "Haryana",
    "delhi": "Delhi",
    "new delhi": "Delhi",
    "delhi ncr": "Delhi",
    "dl": "Delhi",
    "rajasthan": "Rajasthan",
    "raj": "Rajasthan",
    "rj": "Rajasthan",
    "uttar pradesh": "Uttar Pradesh",
    "up": "Uttar Pradesh",
    "bihar": "Bihar",
    "bih": "Bihar",
    "br": "Bihar",
    "sikkim": "Sikkim",
    "sk": "Sikkim",
    "arunachal pradesh": "Arunachal Pradesh",
    "arunachal": "Arunachal Pradesh",
    "ar": "Arunachal Pradesh",
    "nagaland": "Nagaland",
    "nl": "Nagaland",
    "manipur": "Manipur",
    "mn": "Manipur",
    "mizoram": "Mizoram",
    "mz": "Mizoram",
    "tripura": "Tripura",
    "tr": "Tripura",
    "meghalaya": "Meghalaya",
    "ml": "Meghalaya",
    "assam": "Assam",
    "as": "Assam",
    "west bengal": "West Bengal",
    "wb": "West Bengal",
    "bengal": "West Bengal",
    "jharkhand": "Jharkhand",
    "jh": "Jharkhand",
    "odisha": "Odisha",
    "orissa": "Odisha",
    "or": "Odisha",
    "od": "Odisha",
    "chhattisgarh": "Chhattisgarh",
    "chhatisgarh": "Chhattisgarh",
    "cg": "Chhattisgarh",
    "madhya pradesh": "Madhya Pradesh",
    "mp": "Madhya Pradesh",
    "gujarat": "Gujarat",
    "guj": "Gujarat",
    "gj": "Gujarat",
    "daman and diu": "Daman and Diu",
    "daman & diu": "Daman and Diu",
    "dd": "Daman and Diu",
    "dadra and nagar haveli": "Dadra and Nagar Haveli",
    "dadra & nagar haveli": "Dadra and Nagar Haveli",
    "dn": "Dadra and Nagar Haveli",
    "maharashtra": "Maharashtra",
    "mh": "Maharashtra",
    "andhra pradesh": "Andhra Pradesh",
    "ap": "Andhra Pradesh",
    "karnataka": "Karnataka",
    "ka": "Karnataka",
    "goa": "Goa",
    "ga": "Goa",
    "lakshadweep": "Lakshadweep",
    "ld": "Lakshadweep",
    "kerala": "Kerala",
    "kl": "Kerala",
    "tamil nadu": "Tamil Nadu",
    "tamilnadu": "Tamil Nadu",
    "tn": "Tamil Nadu",
    "puducherry": "Puducherry",
    "pondicherry": "Puducherry",
    "py": "Puducherry",
    "andaman and nicobar islands": "Andaman and Nicobar Islands",
    "andaman & nicobar islands": "Andaman and Nicobar Islands",
    "andaman": "Andaman and Nicobar Islands",
    "an": "Andaman and Nicobar Islands",
    "telangana": "Telangana",
    "ts": "Telangana",
    "tg": "Telangana",
    "ladakh": "Ladakh",
    "la": "Ladakh",
}


def normalize_tally_state(state_input: Any, gstin: Optional[str] = None) -> str:
    """
    Normalizes any state string (ALL CAPS, all lowercase, abbreviations, or codes)
    into Tally Prime's exact canonical State Master name.
    If state is missing or unrecognized, safely resolves state from GSTIN first 2 digits.
    """
    s_clean = str(state_input or "").strip()
    if s_clean:
        if s_clean in TALLY_CANONICAL_STATES:
            return TALLY_CANONICAL_STATES[s_clean]
        if len(s_clean) == 1 and f"0{s_clean}" in TALLY_CANONICAL_STATES:
            return TALLY_CANONICAL_STATES[f"0{s_clean}"]

        low = re.sub(r"[^a-zA-Z0-9\s&]", "", s_clean).strip().lower()
        low = re.sub(r"\s+", " ", low)
        if low in STATE_ALIAS_MAP:
            return STATE_ALIAS_MAP[low]
        for _, c_name in TALLY_CANONICAL_STATES.items():
            if low == c_name.lower():
                return c_name

    if gstin:
        clean_gst = str(gstin).strip().upper()
        if len(clean_gst) >= 2 and clean_gst[:2].isdigit():
            c = clean_gst[:2]
            if c in TALLY_CANONICAL_STATES:
                return TALLY_CANONICAL_STATES[c]

    if s_clean and s_clean.lower() not in ("none", "null", "undefined", "na", "n/a"):
        return s_clean.title()
    return ""


TALLY_STANDARD_GROUPS: dict[str, str] = {
    "sundry debtors": "Sundry Debtors",
    "sundry debtor": "Sundry Debtors",
    "debtors": "Sundry Debtors",
    "debtor": "Sundry Debtors",
    "customer": "Sundry Debtors",
    "customers": "Sundry Debtors",
    "sundry creditors": "Sundry Creditors",
    "sundry creditor": "Sundry Creditors",
    "creditors": "Sundry Creditors",
    "creditor": "Sundry Creditors",
    "supplier": "Sundry Creditors",
    "suppliers": "Sundry Creditors",
    "vendor": "Sundry Creditors",
    "vendors": "Sundry Creditors",
    "bank accounts": "Bank Accounts",
    "bank account": "Bank Accounts",
    "banks": "Bank Accounts",
    "bank": "Bank Accounts",
    "bank od a/c": "Bank OD A/c",
    "bank occ a/c": "Bank OCC A/c",
    "cash-in-hand": "Cash-in-hand",
    "cash in hand": "Cash-in-hand",
    "cash": "Cash-in-hand",
    "duties & taxes": "Duties & Taxes",
    "duties and taxes": "Duties & Taxes",
    "tax": "Duties & Taxes",
    "taxes": "Duties & Taxes",
    "sales accounts": "Sales Accounts",
    "sales account": "Sales Accounts",
    "sales": "Sales Accounts",
    "purchase accounts": "Purchase Accounts",
    "purchase account": "Purchase Accounts",
    "purchase": "Purchase Accounts",
    "direct expenses": "Direct Expenses",
    "direct expense": "Direct Expenses",
    "indirect expenses": "Indirect Expenses",
    "indirect expense": "Indirect Expenses",
    "direct incomes": "Direct Incomes",
    "direct income": "Direct Incomes",
    "indirect incomes": "Indirect Incomes",
    "indirect income": "Indirect Incomes",
    "fixed assets": "Fixed Assets",
    "current assets": "Current Assets",
    "current liabilities": "Current Liabilities",
    "capital account": "Capital Account",
    "loans (liability)": "Loans (Liability)",
    "secured loans": "Secured Loans",
    "unsecured loans": "Unsecured Loans",
    "investments": "Investments",
    "stock-in-hand": "Stock-in-hand",
    "provisions": "Provisions",
    "reserves & surplus": "Reserves & Surplus",
    "suspense a/c": "Suspense A/c",
    "branch / divisions": "Branch / Divisions",
}


def canonicalize_tally_group_name(group_name: str) -> str:
    """Normalizes any group name case-insensitively into Tally's canonical group string."""
    raw = str(group_name or "").strip()
    if not raw:
        return ""
    low = raw.lower()
    if low in TALLY_STANDARD_GROUPS:
        return TALLY_STANDARD_GROUPS[low]
    # Check partial matches
    for k, v in TALLY_STANDARD_GROUPS.items():
        if low == k or low.replace("-", " ") == k.replace("-", " "):
            return v
    return raw

BANK_KEYWORDS = (
    "bank", "banking", "sbi", "hdfc", "icici", "axis", "pnb", "bob", "canara", "kotak",
    "indusind", "yes bank", "union bank", "idfc", "citi", "standard chartered", "hsbc",
    "rbl", "bandhan", "federal bank", "uco", "central bank", "indian bank", "bank of india",
    "bank of baroda", "punjab national bank", "state bank of india"
)

CASH_KEYWORDS = (
    "cash", "cash in hand", "cash-in-hand", "petty cash", "office cash", "cash a/c",
    "cash account", "main cash", "cash balance"
)

DUTIES_TAXES_KEYWORDS = (
    "cgst", "sgst", "igst", "utgst", "cess", "gst", "tds", "tcs", "vat", "excise",
    "duties & taxes", "duties and taxes", "input tax", "output tax", "input cgst", "input sgst",
    "input igst", "output cgst", "output sgst", "output igst"
)

ROUND_OFF_KEYWORDS = ("round off", "roundoff", "rounding", "round-off")

EXPENSE_KEYWORDS = (
    "rent", "salary", "wages", "electricity", "freight", "cartage", "carriage",
    "courier", "postage", "telephone", "internet", "printing", "stationery", "fuel",
    "travelling", "traveling", "conveyance", "audit fee", "legal fee", "professional fee",
    "maintenance", "repairs", "commission", "brokerage", "interest paid", "bank charges"
)


def is_bank_ledger_name(name: Any) -> bool:
    """Returns True if the ledger name explicitly represents a bank account."""
    if not name:
        return False
    low = str(name).strip().lower()
    if low in ("bank", "bank account", "bank a/c", "bank accounts", "bank od a/c", "bank occ a/c"):
        return True
    tokens = [t for t in re.split(r"[\s\-_/.]+", low) if t]
    if "bank" in tokens or "banking" in tokens or "od" in tokens or "occ" in tokens:
        return True
    return any(k in low for k in ("sbi", "hdfc", "icici", "axis", "kotak", "pnb", "bob", "canara", "indusind", "idfc", "rbl", "yes bank", "union bank"))


def is_cash_ledger_name(name: Any) -> bool:
    """Returns True if the ledger represents cash-in-hand."""
    if not name:
        return False
    low = str(name).strip().lower()
    return any(low == k or low.startswith(k + " ") or low.endswith(" " + k) for k in CASH_KEYWORDS)


def is_tax_ledger_name(name: Any) -> bool:
    """Returns True if the ledger represents taxes or statutory duties."""
    if not name:
        return False
    low = str(name).strip().lower()
    tokens = [t for t in re.split(r"[\s\-_/.]+", low) if t]
    return any(k in tokens or low.startswith(k) for k in ("cgst", "sgst", "igst", "utgst", "cess", "tds", "tcs", "duties"))


def is_expense_ledger_name(name: Any) -> bool:
    """Returns True if the ledger clearly denotes an operating expense."""
    if not name:
        return False
    low = str(name).strip().lower()
    tokens = [t for t in re.split(r"[\s\-_/.]+", low) if t]
    return any(k in tokens for k in EXPENSE_KEYWORDS)


def classify_safe_ledger_parent(ledger_name: Any, proposed_parent: str = "") -> str:
    """
    Guarantees that protected accounting groups (Bank, Cash, Tax, Expense)
    are NEVER corrupted into Sundry Debtors or Sundry Creditors, and normalizes
    group names case-insensitively into Tally's canonical format.
    """
    clean_n = str(ledger_name or "").strip()
    prop_clean = str(proposed_parent or "").strip()
    prop_canon = canonicalize_tally_group_name(prop_clean)
    prop_low = prop_canon.lower()

    if not clean_n:
        return prop_canon or "Sundry Debtors"

    # 1. Bank protection: If ledger is a bank, NEVER allow Debtors or Creditors
    if is_bank_ledger_name(clean_n):
        if not prop_clean or any(k in prop_low for k in ("debtor", "creditor", "customer", "supplier", "vendor")):
            return "Bank Accounts"
        return prop_canon

    # 2. Cash protection: NEVER allow Debtors, Creditors, or Bank
    if is_cash_ledger_name(clean_n):
        return "Cash-in-hand"

    # 3. Tax / Duties protection:
    if is_tax_ledger_name(clean_n):
        return "Duties & Taxes"

    # 4. Round Off
    if any(k in clean_n.lower() for k in ROUND_OFF_KEYWORDS):
        return "Indirect Expenses"

    # 5. Expense protection: If name is clearly an expense, NEVER allow Debtors or Creditors
    if is_expense_ledger_name(clean_n):
        if not prop_clean or any(k in prop_low for k in ("debtor", "creditor", "customer")):
            return "Indirect Expenses"
        return prop_canon

    return prop_canon or "Sundry Debtors"
