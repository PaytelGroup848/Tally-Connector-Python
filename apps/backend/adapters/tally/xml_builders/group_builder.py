from typing import Dict, Any
from apps.backend.adapters.tally.xml_builders.common import (
    escape_xml,
    _clean_str,
    canonicalize_tally_group_name,
)

STANDARD_GROUP_PARENTS: Dict[str, str] = {
    "sundry debtors": "Current Assets",
    "sundry creditors": "Current Liabilities",
    "bank accounts": "Current Assets",
    "bank od a/c": "Loans (Liability)",
    "bank occ a/c": "Loans (Liability)",
    "cash-in-hand": "Current Assets",
    "duties & taxes": "Current Liabilities",
    "direct expenses": "Primary",
    "indirect expenses": "Primary",
    "direct incomes": "Primary",
    "indirect incomes": "Primary",
    "sales accounts": "Primary",
    "purchase accounts": "Primary",
    "fixed assets": "Primary",
    "current assets": "Primary",
    "current liabilities": "Primary",
    "capital account": "Primary",
    "loans (liability)": "Primary",
    "investments": "Primary",
    "stock-in-hand": "Current Assets",
    "provisions": "Current Liabilities",
    "reserves & surplus": "Primary",
    "deposits (asset)": "Current Assets",
    "loans & advances (asset)": "Current Assets",
}


def determine_group_parent(group_name: str) -> str:
    """Determines the standard Tally parent group for a given group name."""
    g_low = (group_name or "").strip().lower()
    if g_low in STANDARD_GROUP_PARENTS:
        return STANDARD_GROUP_PARENTS[g_low]
    for k, v in STANDARD_GROUP_PARENTS.items():
        if k in g_low or g_low in k:
            return v
    return "Current Assets"


def build_group_import_xml(group_data: Dict[str, Any], action: str = "Create") -> str:
    """
    Constructs a valid Tally XML Master Import envelope with Action='Create' or 'Alter'
    to insert or update an accounting GROUP (e.g. Sundry Debtors, Sundry Creditors) into Tally Prime.
    """
    company_name = escape_xml(group_data.get("company_name", ""))
    company_tag = f"<SVCURRENTCOMPANY>{company_name}</SVCURRENTCOMPANY>" if company_name else ""
    raw_name = _clean_str(group_data.get("name") or group_data.get("group_name") or "")
    group_name = escape_xml(canonicalize_tally_group_name(raw_name) or raw_name)
    raw_parent = _clean_str(group_data.get("parent") or "")
    parent = escape_xml(raw_parent or determine_group_parent(raw_name))

    action_attr = escape_xml(action or "Create")

    # In Tally Prime, Sundry Debtors and Creditors are subledgers and billwise
    is_debtor_or_creditor = any(k in group_name.lower() for k in ("debtor", "creditor"))
    is_subledger = "Yes" if is_debtor_or_creditor else "No"
    is_billwise = "Yes" if is_debtor_or_creditor else "No"

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
                    <GROUP ACTION="{action_attr}" NAME="{group_name}">
                        <NAME.LIST TYPE="String">
                            <NAME>{group_name}</NAME>
                        </NAME.LIST>
                        <PARENT>{parent}</PARENT>
                        <ISSUBLEDGER>{is_subledger}</ISSUBLEDGER>
                        <ISBILLWISEON>{is_billwise}</ISBILLWISEON>
                    </GROUP>
                </TALLYMESSAGE>
            </REQUESTDATA>
        </IMPORTDATA>
    </BODY>
</ENVELOPE>"""
    return xml_envelope
