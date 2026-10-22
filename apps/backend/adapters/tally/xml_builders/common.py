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
# Enterprise SaaS Safe Ledger Classification Helpers
# -------------------------------------------------------------------------

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
    are NEVER corrupted into Sundry Debtors or Sundry Creditors.
    """
    clean_n = str(ledger_name or "").strip()
    if not clean_n:
        return proposed_parent or "Sundry Debtors"

    prop_clean = str(proposed_parent or "").strip()
    prop_low = prop_clean.lower()

    # 1. Bank protection: If ledger is a bank, NEVER allow Debtors or Creditors
    if is_bank_ledger_name(clean_n):
        if not prop_clean or "debtor" in prop_low or "creditor" in prop_low or "customer" in prop_low or "supplier" in prop_low or "vendor" in prop_low:
            return "Bank Accounts"
        return prop_clean

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
        if not prop_clean or "debtor" in prop_low or "creditor" in prop_low or "customer" in prop_low:
            return "Indirect Expenses"
        return prop_clean

    return prop_clean or "Sundry Debtors"
