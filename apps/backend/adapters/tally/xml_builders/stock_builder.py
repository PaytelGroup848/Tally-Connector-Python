from typing import Dict, Any, Optional
from apps.backend.adapters.tally.xml_builders.common import escape_xml, _clean_str



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


def _build_stock_item_gst_xml(item_data: Dict[str, Any]) -> str:
    """
    Constructs dual-compatible GST statutory tags for Stock Items in Tally.
    Works seamlessly across Tally ERP 9, TallyPrime 1.x/2.x, and TallyPrime 3.0+/4.0+/5.0+.
    Populates 'Specify Details Here' for HSN/SAC and GST Rate details with CGST/SGST/IGST breakdown.
    """
    hsn_code = escape_xml(_clean_str(item_data.get("hsn_code") or item_data.get("hsnCode") or item_data.get("hsn") or ""))
    hsn_desc = escape_xml(_clean_str(item_data.get("hsn_description") or item_data.get("hsn_desc") or item_data.get("description") or ""))

    raw_gst_rate = item_data.get("gst_rate")
    if raw_gst_rate is None:
        raw_gst_rate = item_data.get("tax_rate")
    if raw_gst_rate is None:
        raw_gst_rate = item_data.get("gstRate")
    if raw_gst_rate is None:
        raw_gst_rate = item_data.get("taxRate")
    if raw_gst_rate is None:
        raw_gst_rate = item_data.get("rate_of_vat")

    gst_rate: Optional[float] = None
    if raw_gst_rate is not None and str(raw_gst_rate).strip():
        try:
            gst_rate = float(str(raw_gst_rate).replace("%", "").strip())
        except (ValueError, TypeError):
            gst_rate = None

    applicable_from = str(item_data.get("applicable_from") or "20240401").replace("-", "").strip()
    if len(applicable_from) != 8:
        applicable_from = "20240401"

    gst_blocks = [
        "<GSTAPPLICABLE>&#4; Applicable</GSTAPPLICABLE>",
        "<GSTTYPEOFSUPPLY>Goods</GSTTYPEOFSUPPLY>",
    ]

    if hsn_code:
        gst_blocks.append(f"<HSNCODE>{hsn_code}</HSNCODE>")
        desc_elem = f"\n <HSNDESCRIPTION>{hsn_desc}</HSNDESCRIPTION>" if hsn_desc else ""
        gst_blocks.append(f"""<HSNDETAILS.LIST>
                            <APPLICABLEFROM>{applicable_from}</APPLICABLEFROM>
                            <HSNCODE>{hsn_code}</HSNCODE>
                            <HSN>{hsn_code}</HSN>{desc_elem}
                            <SRCOFHSNDETAILS>Specify Details Here</SRCOFHSNDETAILS>
                        </HSNDETAILS.LIST>""")

    if gst_rate is not None and gst_rate >= 0:
        taxability = "Taxable" if gst_rate > 0 else "Exempt"
        half_rate = round(gst_rate / 2.0, 2)
        rate_int_or_float = f"{gst_rate:g}"
        half_int_or_float = f"{half_rate:g}"
        gst_blocks.append(f"""<GSTDETAILS.LIST>
                            <APPLICABLEFROM>{applicable_from}</APPLICABLEFROM>
                            <TAXABILITY>{taxability}</TAXABILITY>
                            <SRCOFGSTDETAILS>Specify Details Here</SRCOFGSTDETAILS>
                            <STATEWISEDETAILS.LIST>
                                <STATENAME>&#4; Any</STATENAME>
                                <RATEDETAILS.LIST>
                                    <GSTRATEDUTYHEAD>CGST</GSTRATEDUTYHEAD>
                                    <GSTRATEVALUATIONTYPE>Based on Value</GSTRATEVALUATIONTYPE>
                                    <GSTRATE>{half_int_or_float}</GSTRATE>
                                </RATEDETAILS.LIST>
                                <RATEDETAILS.LIST>
                                    <GSTRATEDUTYHEAD>SGST/UTGST</GSTRATEDUTYHEAD>
                                    <GSTRATEVALUATIONTYPE>Based on Value</GSTRATEVALUATIONTYPE>
                                    <GSTRATE>{half_int_or_float}</GSTRATE>
                                </RATEDETAILS.LIST>
                                <RATEDETAILS.LIST>
                                    <GSTRATEDUTYHEAD>IGST</GSTRATEDUTYHEAD>
                                    <GSTRATEVALUATIONTYPE>Based on Value</GSTRATEVALUATIONTYPE>
                                    <GSTRATE>{rate_int_or_float}</GSTRATE>
                                </RATEDETAILS.LIST>
                            </STATEWISEDETAILS.LIST>
                        </GSTDETAILS.LIST>""")

    return "\n" + "\n".join(gst_blocks)


def build_godown_import_xml(godown_name: str, company_name: str = "") -> str:
    """Constructs a Tally XML Master Import envelope with ACTION='Create' to ensure Godown exists."""
    clean_gname = escape_xml(_clean_str(godown_name or "Main Location"))
    c_tag = f"<SVCURRENTCOMPANY>{escape_xml(company_name)}</SVCURRENTCOMPANY>" if company_name else ""
    return f"""<ENVELOPE>
    <HEADER><TALLYREQUEST>Import Data</TALLYREQUEST></HEADER>
    <BODY>
        <IMPORTDATA>
            <REQUESTDESC>
                <REPORTNAME>All Masters</REPORTNAME>
                <STATICVARIABLES>
                    {c_tag}
                </STATICVARIABLES>
            </REQUESTDESC>
            <REQUESTDATA>
                <TALLYMESSAGE xmlns:UDF="TallyUDF">
                    <GODOWN ACTION="Create" NAME="{clean_gname}">
                        <NAME>{clean_gname}</NAME>
                    </GODOWN>
                </TALLYMESSAGE>
            </REQUESTDATA>
        </IMPORTDATA>
    </BODY>
</ENVELOPE>"""


def build_stock_item_import_xml(item_data: Dict[str, Any]) -> str:
    """
    Constructs a valid Tally XML Master Import envelope with ACTION="Create" to insert a STOCK ITEM
    (with Base Unit, HSN Code, GST Details, Opening Balance, Rate, Value, Godown, and Batch) into Tally Prime.
    """
    company_name = escape_xml(item_data.get("company_name", ""))
    company_tag = f"<SVCURRENTCOMPANY>{company_name}</SVCURRENTCOMPANY>" if company_name else ""
    item_name = escape_xml(_clean_str(item_data.get("name") or item_data.get("itemName") or ""))
    base_unit = escape_xml(_clean_str(item_data.get("unit") or item_data.get("units") or item_data.get("base_units") or "Pcs"))
    gst_xml = _build_stock_item_gst_xml(item_data)

    try:
        qty = float(item_data.get("quantity", 0.0) or item_data.get("opening_balance", 0.0) or item_data.get("openingBalance", 0.0) or item_data.get("closingBalance", 0.0) or 0.0)
    except (ValueError, TypeError):
        qty = 0.0

    try:
        rate = float(item_data.get("rate", 0.0) or item_data.get("price", 0.0) or item_data.get("opening_rate", 0.0) or item_data.get("openingRate", 0.0) or item_data.get("closingRate", 0.0) or 0.0)
    except (ValueError, TypeError):
        rate = 0.0

    try:
        val = float(item_data.get("value", 0.0) or item_data.get("amount", 0.0) or item_data.get("opening_value", 0.0) or item_data.get("openingValue", 0.0) or item_data.get("closingValue", 0.0) or (qty * rate))
    except (ValueError, TypeError):
        val = qty * rate

    godown = escape_xml(_clean_str(item_data.get("godown") or item_data.get("godown_name") or item_data.get("godownName") or ""))
    batch = escape_xml(_clean_str(item_data.get("batch") or item_data.get("batch_name") or item_data.get("batchName") or ""))

    if qty != 0:
        balance_tags = f"""
                        <OPENINGBALANCE>{qty} {base_unit}</OPENINGBALANCE>
                        <OPENINGRATE>{rate}/{base_unit}</OPENINGRATE>
                        <OPENINGVALUE>-{abs(val):.2f}</OPENINGVALUE>"""
    else:
        balance_tags = """
                        <OPENINGBALANCE>0</OPENINGBALANCE>"""

    batch_alloc = ""
    if qty != 0 and (godown or batch):
        g_name = godown or "Main Location"
        b_name = batch or "Primary Batch"
        batch_alloc = f"""
                        <BATCHALLOCATIONS.LIST>
                            <GODOWNNAME>{g_name}</GODOWNNAME>
                            <BATCHNAME>{b_name}</BATCHNAME>
                            <OPENINGBALANCE>{qty} {base_unit}</OPENINGBALANCE>
                            <OPENINGRATE>{rate}/{base_unit}</OPENINGRATE>
                            <OPENINGVALUE>-{abs(val):.2f}</OPENINGVALUE>
                        </BATCHALLOCATIONS.LIST>"""

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
                        <BASEUNITS>{base_unit}</BASEUNITS>{balance_tags}{gst_xml}{batch_alloc}
                    </STOCKITEM>
                </TALLYMESSAGE>
            </REQUESTDATA>
        </IMPORTDATA>
    </BODY>
</ENVELOPE>"""
    return xml_envelope


def build_stock_item_alter_xml(item_data: Dict[str, Any]) -> str:
    """
    Constructs a valid Tally XML Master Import envelope with ACTION="Alter" to update an existing STOCK ITEM
    (quantity, rate, value, HSN, GST, batch, godown) in Tally Prime.
    """
    company_name = escape_xml(item_data.get("company_name", ""))
    company_tag = f"<SVCURRENTCOMPANY>{company_name}</SVCURRENTCOMPANY>" if company_name else ""
    item_name = escape_xml(_clean_str(item_data.get("name") or item_data.get("itemName") or ""))
    base_unit = escape_xml(_clean_str(item_data.get("unit") or item_data.get("units") or item_data.get("base_units") or "Pcs"))
    gst_xml = _build_stock_item_gst_xml(item_data)

    qty = float(item_data.get("quantity", 0.0) or item_data.get("closingBalance", 0.0) or 0.0)
    rate = float(item_data.get("rate", 0.0) or item_data.get("closingRate", 0.0) or 0.0)
    val = float(item_data.get("value", 0.0) or item_data.get("closingValue", 0.0) or (qty * rate))
    godown = escape_xml(_clean_str(item_data.get("godown") or ""))
    batch = escape_xml(_clean_str(item_data.get("batch") or item_data.get("batchName") or ""))

    if qty != 0:
        balance_tags = f"""<OPENINGBALANCE>{qty} {base_unit}</OPENINGBALANCE>
                        <OPENINGRATE>{rate}/{base_unit}</OPENINGRATE>
                        <OPENINGVALUE>-{abs(val):.2f}</OPENINGVALUE>"""
    else:
        balance_tags = f"""<OPENINGBALANCE>0</OPENINGBALANCE>
                        <OPENINGVALUE>0</OPENINGVALUE>"""

    batch_alloc = ""
    if qty != 0 and (godown or batch):
        g_name = godown or "Main Location"
        b_name = batch or "Primary Batch"
        batch_alloc = f"""
                        <BATCHALLOCATIONS.LIST>
                            <GODOWNNAME>{g_name}</GODOWNNAME>
                            <BATCHNAME>{b_name}</BATCHNAME>
                            <OPENINGBALANCE>{qty} {base_unit}</OPENINGBALANCE>
                            <OPENINGRATE>{rate}/{base_unit}</OPENINGRATE>
                            <OPENINGVALUE>-{abs(val):.2f}</OPENINGVALUE>
                        </BATCHALLOCATIONS.LIST>"""

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
                    <STOCKITEM ACTION="Alter" NAME="{item_name}">
                        <NAME.LIST>
                            <NAME>{item_name}</NAME>
                        </NAME.LIST>
                        <BASEUNITS>{base_unit}</BASEUNITS>
                        {balance_tags}{gst_xml}{batch_alloc}
                    </STOCKITEM>
                </TALLYMESSAGE>
            </REQUESTDATA>
        </IMPORTDATA>
    </BODY>
</ENVELOPE>"""
    return xml_envelope

