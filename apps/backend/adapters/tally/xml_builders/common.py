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

