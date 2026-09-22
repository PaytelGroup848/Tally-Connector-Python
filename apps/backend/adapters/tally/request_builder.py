

from typing import List, Optional

METADATA_TYPE_MAP = {
    "companies": ("Company", ["NAME", "GUID", "BOOKSFROM", "STARTINGFROM", "ADDRESS.LIST", "STATENAME", "COUNTRYNAME", "PINCODE", "PHONENUMBER", "EMAIL", "GSTREGISTRATIONNUMBER", "INCOMETAXNUMBER", "CIN", "BASECURRENCYNAME"]),
    "groups": ("Group", ["NAME", "PARENT", "GUID", "ALTERID", "ISADDABLE", "ISSUBLEDGER", "NATUREOFGROUP"]),
    "ledgers": ("Ledger", ["NAME", "PARENT", "CLOSINGBALANCE", "OPENINGBALANCE", "STARTINGFROM", "ACTIVEFROM", "APPLICABLEFROM", "OPENINGBALANCEDATE", "PARTYGSTIN", "GSTIN", "LEDGERCLASSIFICATION", "GUID", "ALTERID", "EMAIL", "LEDGERPHONE", "LEDGERMOBILE", "ADDRESS.LIST", "INCOMETAXNUMBER", "BILLCREDITPERIOD", "CREDITLIMIT", "ISBILLWISEON", "LEDGERGSTREGISTRATIONDETAILS.LIST"]),
    "voucher_types": ("VoucherType", ["NAME", "PARENT", "GUID", "ALTERID"]),
    "cost_centres": ("CostCentre", ["NAME", "CATEGORY", "GUID", "ALTERID"]),
    "godowns": ("Godown", ["NAME", "PARENT", "GUID", "ALTERID", "ADDRESS.LIST"]),
    "stock_groups": ("StockGroup", ["NAME", "PARENT", "GUID", "ALTERID"]),
    "stock_categories": ("StockCategory", ["NAME", "PARENT", "GUID", "ALTERID"]),
    "stock_items": ("StockItem", ["NAME", "PARENT", "CATEGORY", "BASEUNITS", "ADDITIONALUNITS", "GSTREPUOM", "CLOSINGBALANCE", "OPENINGBALANCE", "STARTINGFROM", "ACTIVEFROM", "APPLICABLEFROM", "CLOSINGRATE", "CLOSINGVALUE", "OPENINGRATE", "OPENINGVALUE", "HSNCODE", "HSN", "GSTAPPLICABLE", "HSNDETAILS.*", "GSTDETAILS.*", "TARIFFLIST.*", "BATCHNAME", "BATCHALLOCATIONS.LIST", "GODOWNALLOCATIONS.LIST", "GUID", "ALTERID", "REORDERLEVEL"]),
    "units": ("Unit", ["NAME", "SYMBOL", "ORIGINALNAME", "DECIMALPLACES", "GUID", "ALTERID"]),
    "vouchers": ("Voucher", ["DATE", "EFFECTIVEDATE", "VOUCHERTYPENAME", "VOUCHERNUMBER", "REFERENCE", "REFERENCEDATE", "PARTYLEDGERNAME", "PARTYNAME", "BASICBUYERNAME", "PLACEOFSUPPLY", "AMOUNT", "NARRATION", "GUID", "ALTERID", "ISOPTIONAL", "ISCANCELLED", "ISPOSTDATED", "ALLLEDGERENTRIES.LIST", "ALLINVENTORYENTRIES.LIST", "LEDGERENTRIES.LIST"]),
}

ALLOWED_METADATA_TYPES = list(METADATA_TYPE_MAP.keys())

def build_company_list_xml() -> str:
    """Builds a lightweight XML query to fetch list of open companies from Tally."""
    return build_collection_xml(collection_type="Company", fetch_fields=["NAME", "GUID", "BOOKSFROM"])

def build_collection_xml(
    collection_type: str,
    fetch_fields: List[str],
    company_name: Optional[str] = None,
    from_alter_id: Optional[int] = None
) -> str:
    """
    Constructs a valid TDL Envelope for Tally Export request.
    Supports ALTERID incremental delta filtering ($ALTERID > from_alter_id) for vouchers & masters.
    """
    fetch_tags = "".join([f"<FETCH>{field}</FETCH>" for field in fetch_fields])

    company_var = ""
    if company_name and company_name.strip():
        clean_company = company_name.strip().replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        company_var = f"<SVCURRENTCOMPANY>{clean_company}</SVCURRENTCOMPANY>"

    filter_tag = ""
    system_tag = ""
    if from_alter_id is not None and from_alter_id > 0:
        filter_tag = "<FILTER>AlterIdFilter</FILTER>"
        system_tag = f"<SYSTEM NAME=\"AlterIdFilter\">$ALTERID &gt; {from_alter_id}</SYSTEM>"

    return f"""<ENVELOPE>
    <HEADER>
        <VERSION>1</VERSION>
        <TALLYREQUEST>EXPORT</TALLYREQUEST>
        <TYPE>COLLECTION</TYPE>
        <ID>CustomCollection</ID>
    </HEADER>
    <BODY>
        <DESC>
            <STATICVARIABLES>
                <SVEXPORTFORMAT>$$SYSNAME:XML</SVEXPORTFORMAT>
                {company_var}
            </STATICVARIABLES>
            <TDL>
                <TDLMESSAGE>
                    <COLLECTION NAME="CustomCollection" ISINITIALISE="Yes">
                        <TYPE>{collection_type}</TYPE>
                        {fetch_tags}
                        {filter_tag}
                    </COLLECTION>
                    {system_tag}
                </TDLMESSAGE>
            </TDL>
        </DESC>
    </BODY>
</ENVELOPE>"""
