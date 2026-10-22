from typing import Dict, Any
from apps.backend.adapters.tally.xml_builders.common import escape_xml, classify_safe_ledger_parent



def build_ledger_import_xml(ledger_data: Dict[str, Any], action: str = "Create") -> str:
    """
    Constructs an enterprise-grade Tally XML Master Import envelope with ACTION="Create" or "Alter"
    to insert or update a LEDGER (Customer / Sundry Debtors / Vendor / Sales Account / Duties & Taxes / Bank Account)
    into Tally Prime with full Mailing Details, Contact Details, and GST Statutory Registration.
    """
    company_name = escape_xml(ledger_data.get("company_name", ""))
    company_tag = f"<SVCURRENTCOMPANY>{company_name}</SVCURRENTCOMPANY>" if company_name else ""

    ledger_name = escape_xml(
        ledger_data.get("name")
        or ledger_data.get("ledgerName")
        or ledger_data.get("ledger_name")
        or ledger_data.get("party_ledger")
        or ledger_data.get("partyName")
        or ledger_data.get("party_name")
        or ""
    )
    p_type = str(ledger_data.get("partyType") or ledger_data.get("party_type") or "").strip().upper()
    raw_default = "Sundry Creditors" if "SUPPLIER" in p_type or "VENDOR" in p_type else "Sundry Debtors"
    chosen_parent = ledger_data.get("parent") or raw_default
    parent = escape_xml(classify_safe_ledger_parent(ledger_name, chosen_parent))
    opening_bal = float(ledger_data.get("opening_balance") or ledger_data.get("openingBalance") or 0.0)

    is_party = any(k in parent.lower() for k in ("debtors", "creditors")) or bool(ledger_data.get("is_billwise"))
    billwise_val = "Yes" if is_party else "No"

    # State & Country (Country required for Tally to bind State master)
    state = escape_xml(str(ledger_data.get("state") or ledger_data.get("state_name") or "").strip())
    raw_country = str(ledger_data.get("country") or "").strip()
    country = escape_xml(raw_country or ("India" if (state or is_party) else ""))

    # GST Details
    gstin = escape_xml(str(ledger_data.get("gstin") or ledger_data.get("party_gstin") or ledger_data.get("gstNumber") or ledger_data.get("gst_number") or "").strip().upper())
    raw_reg_type = str(ledger_data.get("registration_type") or ledger_data.get("registrationType") or ledger_data.get("gst_type") or "").strip()
    if raw_reg_type:
        reg_type = escape_xml(raw_reg_type)
    elif gstin:
        reg_type = "Regular"
    elif is_party:
        reg_type = "Unregistered"
    else:
        reg_type = ""

    # Contact Details
    mobile = escape_xml(str(ledger_data.get("mobile") or ledger_data.get("mobile_number") or ledger_data.get("contactNumber") or "").strip())
    phone = escape_xml(str(ledger_data.get("phone") or ledger_data.get("phoneNumber") or ledger_data.get("telephone") or "").strip())
    if not phone and mobile:
        phone = mobile
    if not mobile and phone:
        mobile = phone
    email = escape_xml(str(ledger_data.get("email") or ledger_data.get("email_id") or "").strip())

    # Pincode
    pincode = escape_xml(str(ledger_data.get("pincode") or ledger_data.get("pin") or ledger_data.get("postalCode") or ledger_data.get("zip") or "").strip())

    # Address (Split multi-lines cleanly into distinct <ADDRESS> elements)
    raw_address = str(ledger_data.get("address") or ledger_data.get("billingAddress") or ledger_data.get("party_address") or "").strip()
    address_lines = []
    if raw_address:
        for line in raw_address.replace("\r", "").split("\n"):
            line = line.strip()
            if line:
                address_lines.append(escape_xml(line))
        if not address_lines:
            address_lines.append(escape_xml(raw_address))

    # Assemble XML sub-blocks
    mailing_name_tag = f""" <MAILINGNAME.LIST TYPE="String">
                            <MAILINGNAME>{ledger_name}</MAILINGNAME>
                        </MAILINGNAME.LIST>""" if ledger_name and is_party else ""

    address_tag = ""
    if address_lines:
        inner_addrs = "\n".join([f" <ADDRESS>{l}</ADDRESS>" for l in address_lines])
        address_tag = f""" <ADDRESS.LIST TYPE="String">
{inner_addrs}
                        </ADDRESS.LIST>"""

    # TallyPrime 3.0+ / 4.0+ Multi-Address & Mailing Details List
    led_mailing_tag = ""
    if is_party and (address_lines or state or country or pincode or ledger_name):
        inner_m_addrs = "\n".join([f"<ADDRESS>{l}</ADDRESS>" for l in address_lines])
        m_addr_block = f"""\n  <ADDRESS.LIST TYPE="String">
{inner_m_addrs}
                            </ADDRESS.LIST>""" if address_lines else ""
        m_state = f"\n  <STATE>{state}</STATE>" if state else ""
        m_country = f"\n <COUNTRY>{country}</COUNTRY>" if country else ""
        m_pin = f"\n  <PINCODE>{pincode}</PINCODE>" if pincode else ""
        m_name = f"\n  <MAILINGNAME>{ledger_name}</MAILINGNAME>" if ledger_name else ""

        led_mailing_tag = f""" <LEDMAILINGDETAILS.LIST>
                            <APPLICABLEFROM>20200401</APPLICABLEFROM>{m_name}{m_addr_block}{m_state}{m_country}{m_pin}
                        </LEDMAILINGDETAILS.LIST>"""

    country_tag = f" <COUNTRYNAME>{country}</COUNTRYNAME>" if country else ""
    state_tag = f" <STATENAME>{state}</STATENAME>" if state else ""
    pincode_tag = f" <PINCODE>{pincode}</PINCODE>" if pincode else ""

    contact_tags = ""
    if mobile or phone or email:
        phone_elem = f"\n<LEDGERPHONE>{phone}</LEDGERPHONE>" if phone else ""
        mob_elem = f"\n <LEDGERMOBILE>{mobile}</LEDGERMOBILE>" if mobile else ""
        email_elem = f"\n <EMAIL>{email}</EMAIL>" if email else ""
        contact_tags = f"""{phone_elem}{mob_elem}{email_elem}
                        <ISCONTACTDETAILSAVAILABLE>Yes</ISCONTACTDETAILSAVAILABLE>"""

    gst_tags = ""
    if reg_type or gstin or is_party:
        reg_elem = f"\n  <GSTREGISTRATIONTYPE>{reg_type}</GSTREGISTRATIONTYPE>" if reg_type else ""
        gstin_elem = f"\n <PARTYGSTIN>{gstin}</PARTYGSTIN>" if gstin else ""
        pos_elem = f"\n <PLACEOFSUPPLY>{state}</PLACEOFSUPPLY>" if state else ""

        # Dual-Compatibility: TallyPrime 3.0+ / 4.0+ (LEDGSTREGDETAILS) & TallyPrime 2.x (LEDGERGSTREGISTRATIONDETAILS)
        multi_gst_list = ""
        reg_val_tally = reg_type or ("Regular" if gstin else "Unregistered")
        if gstin or reg_val_tally:
            pos_tag_tally = f"\n <PLACEOFSUPPLY>{state}</PLACEOFSUPPLY>" if state else ""
            state_tag_tally = f"\n <STATE>{state}</STATE>" if state else ""
            gstin_tag_tally = f"\n <GSTIN>{gstin}</GSTIN>" if gstin else ""
            multi_gst_list = f"""
                        <LEDGSTREGDETAILS.LIST>
                            <APPLICABLEFROM>20200401</APPLICABLEFROM>
                            <GSTREGISTRATIONTYPE>{reg_val_tally}</GSTREGISTRATIONTYPE>{state_tag_tally}{pos_tag_tally}{gstin_tag_tally}
                        </LEDGSTREGDETAILS.LIST>
                        <LEDGERGSTREGISTRATIONDETAILS.LIST>
                            <APPLICABLEFROM>20200401</APPLICABLEFROM>
                            <GSTREGISTRATIONTYPE>{reg_val_tally}</GSTREGISTRATIONTYPE>{pos_tag_tally}{gstin_tag_tally}
                        </LEDGERGSTREGISTRATIONDETAILS.LIST>"""

        gst_tags = f"""{reg_elem}{gstin_elem}{pos_elem}{multi_gst_list}"""

    duty_head = escape_xml(ledger_data.get("duty_head") or ledger_data.get("tax_head") or "")
    tax_tags = ""
    if "duties" in parent.lower() or duty_head:
        head_val = duty_head or ("CGST" if "cgst" in ledger_name.lower() else "SGST" if "sgst" in ledger_name.lower() else "IGST" if "igst" in ledger_name.lower() else "Others")
        tax_tags = f"""
                        <TAXTYPE>GST</TAXTYPE>
                        <GSTDUTYHEAD>{head_val}</GSTDUTYHEAD>"""

    # Bank Details (for Bank Accounts)
    raw_bank_details = ledger_data.get("bankDetails") or ledger_data.get("bank_details") or {}
    if not isinstance(raw_bank_details, dict):
        raw_bank_details = {}

    acc_num = escape_xml(str(raw_bank_details.get("accountNumber") or ledger_data.get("accountNumber") or ledger_data.get("account_number") or "").strip())
    ifsc = escape_xml(str(raw_bank_details.get("ifscCode") or ledger_data.get("ifscCode") or ledger_data.get("ifsc") or "").strip())
    b_name = escape_xml(str(raw_bank_details.get("bankName") or ledger_data.get("bankName") or ledger_data.get("bank_name") or "").strip())
    branch = escape_xml(str(raw_bank_details.get("branchName") or ledger_data.get("branchName") or ledger_data.get("branch") or "").strip())
    holder = escape_xml(str(raw_bank_details.get("accountHolderName") or ledger_data.get("accountHolderName") or ledger_data.get("account_holder_name") or "").strip())

    bank_tags = ""
    if acc_num or ifsc or b_name or branch or holder:
        acc_tag = f"\n                        <BANKACCOUNTNUMBER>{acc_num}</BANKACCOUNTNUMBER>" if acc_num else ""
        ifsc_tag = f"\n                        <IFSCODE>{ifsc}</IFSCODE>" if ifsc else ""
        bname_tag = f"\n                        <BANKNAME>{b_name}</BANKNAME>" if b_name else ""
        branch_tag = f"\n                        <BRANCHNAME>{branch}</BRANCHNAME>" if branch else ""
        holder_tag = f"\n                        <ACCOUNTHOLDERNAME>{holder}</ACCOUNTHOLDERNAME>" if holder else ""
        bank_list_acc = f"\n                            <ACCOUNTNUMBER>{acc_num}</ACCOUNTNUMBER>" if acc_num else ""
        bank_list_ifsc = f"\n                            <IFSCODE>{ifsc}</IFSCODE>" if ifsc else ""
        bank_list_bname = f"\n                            <BANKNAME>{b_name}</BANKNAME>" if b_name else ""
        bank_list_branch = f"\n                            <BRANCHNAME>{branch}</BRANCHNAME>" if branch else ""

        bank_tags = f"""{acc_tag}{ifsc_tag}{bname_tag}{branch_tag}{holder_tag}
                        <BANKDETAILS.LIST>
{bank_list_acc}{bank_list_ifsc}{bank_list_bname}{bank_list_branch}
                        </BANKDETAILS.LIST>"""

    action_attr = escape_xml(action or "Create")

    optional_blocks = [
        mailing_name_tag,
        address_tag,
        country_tag,
        state_tag,
        pincode_tag,
        led_mailing_tag,
        contact_tags,
        gst_tags,
        tax_tags,
        bank_tags,
    ]
    rendered_blocks = "\n".join([b for b in optional_blocks if b])

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
                    <LEDGER ACTION="{action_attr}" NAME="{ledger_name}">
                        <NAME.LIST TYPE="String">
                            <NAME>{ledger_name}</NAME>
                        </NAME.LIST>
                        <PARENT>{parent}</PARENT>
                        <OPENINGBALANCE>{opening_bal:.2f}</OPENINGBALANCE>
                        <ISBILLWISEON>{billwise_val}</ISBILLWISEON>
{rendered_blocks}
                    </LEDGER>
                </TALLYMESSAGE>
            </REQUESTDATA>
        </IMPORTDATA>
    </BODY>
</ENVELOPE>"""
    return xml_envelope

