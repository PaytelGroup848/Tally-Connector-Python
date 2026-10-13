from typing import Dict, Any
from apps.backend.adapters.tally.xml_builders.common import escape_xml, _clean_str



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

