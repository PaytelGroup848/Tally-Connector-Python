

import re
import xml.etree.ElementTree as ET
from typing import Any

from apps.backend.adapters.tally.tally_client import TallyClient
from shared.logging_config import get_logger

logger = get_logger("app.adapters.tally.importer")


__all__ = [
    "_ITEM_MASTER_HSN_CACHE",
    "_ITEM_MASTER_UNIT_CACHE",
    "_PARTY_MASTER_GSTIN_CACHE",
    "TallyImporter",
    "_balance_double_entry_accounting",
    "_clean_str",
    "_lookup_item_master_hsn",
    "_lookup_item_master_unit",
    "_lookup_party_master_gstin",
    "build_ledger_import_xml",
    "build_stock_item_alter_xml",
    "build_stock_item_import_xml",
    "build_unit_import_xml",
    "build_voucher_import_xml",
    "build_voucher_type_import_xml",
    "determine_voucher_type_parent",
    "diagnose_voucher_rejection",
    "escape_xml",
    "format_tally_date",
    "parse_tally_import_response",
]

from apps.backend.adapters.tally.xml_builders import (
    _ITEM_MASTER_HSN_CACHE,
    _ITEM_MASTER_UNIT_CACHE,
    _PARTY_MASTER_GSTIN_CACHE,
    _balance_double_entry_accounting,
    _clean_str,
    _lookup_item_master_hsn,
    _lookup_item_master_unit,
    _lookup_party_master_gstin,
    build_ledger_import_xml,
    build_stock_item_alter_xml,
    build_stock_item_import_xml,
    build_unit_import_xml,
    build_voucher_import_xml,
    build_voucher_type_import_xml,
    determine_voucher_type_parent,
    escape_xml,
    format_tally_date,
)
from apps.backend.adapters.tally.xml_builders.voucher_builder import (
    _extract_item_name,
    _extract_items_list,
)


def parse_tally_import_response(xml_text: str, default_voucher_number: str | None = None) -> tuple[bool, str | None, str | None]:
  
    if not xml_text or not xml_text.strip():
        return False, None, "Empty response received from Tally Prime server."

    lower_raw = xml_text.strip().lower()
    if "<!doctype html" in lower_raw or "<html" in lower_raw or "license server is running" in lower_raw or "gateway release" in lower_raw:
        return False, None, "Connected to Tally License Server or Web server instead of Tally Prime. Ensure Tally Prime is running and ODBC/XML port is correct."

    clean_xml = re.sub(r'&#(0?[0-8]|1[124-9]|2[0-9]|3[01]);', '', xml_text)
    clean_xml = re.sub(r'&#\d+;', '', clean_xml)
    clean_xml = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F]', '', clean_xml)
    clean_xml = re.sub(r'<(/?[a-zA-Z0-9_\.]+):([a-zA-Z0-9_\.]+)((?:\s+[^>]*)?)>', r'<\1_\2\3>', clean_xml)

    try:
        root = ET.fromstring(clean_xml)
    except ET.ParseError as pe:
        return False, None, f"Malformed XML response from Tally Prime: {pe}"

    # Check for direct rejection or error text in root element (e.g. <RESPONSE>Unknown Request, cannot be processed</RESPONSE>)
    root_text = (root.text or "").strip()
    if root_text and any(k in root_text.lower() for k in ("unknown request", "cannot be processed", "error", "fail", "invalid", "rejected", "not found", "does not exist", "unable to")):
        return False, None, f"Tally rejected request: {root_text}"

    line_errors = []
    for line_err in root.findall(".//LINEERROR"):
        if line_err.text and line_err.text.strip():
            line_errors.append(line_err.text.strip())

    if line_errors:
        clean_error = "; ".join(line_errors)
        logger.warning(f"Tally Import LINEERROR: {clean_error}")
        return False, None, f"Tally XML Line Error: {clean_error}"

    errors_elem = root.find(".//ERRORS")
    if errors_elem is not None and errors_elem.text:
        try:
            err_count = int(errors_elem.text.strip())
            if err_count > 0 and not line_errors:
                return False, None, f"Tally reported {err_count} import error(s)."
        except ValueError:
            pass

    exceptions_elem = root.find(".//EXCEPTIONS")
    if exceptions_elem is not None and exceptions_elem.text:
        try:
            exc_count = int(exceptions_elem.text.strip())
            if exc_count > 0 and not line_errors:
                return False, None, f"Tally reported {exc_count} exception(s) during voucher creation."
        except ValueError:
            pass

    voucher_num = default_voucher_number
    vnum_elem = root.find(".//VOUCHERNUMBER")
    if vnum_elem is not None and vnum_elem.text and vnum_elem.text.strip():
        voucher_num = vnum_elem.text.strip()
    else:
        last_id_elem = root.find(".//LASTVOUCHERID")
        if last_id_elem is None:
            last_id_elem = root.find(".//LASTVCHID")
        if last_id_elem is not None and last_id_elem.text and last_id_elem.text.strip():
            v_text = last_id_elem.text.strip()
            if v_text not in ("0", ""):
                voucher_num = voucher_num or f"VCH-{v_text}"

    altered_elem = root.find(".//ALTERED")
    alt_count = 0
    if altered_elem is not None and altered_elem.text:
        try:
            alt_count = int(altered_elem.text.strip())
        except ValueError:
            pass

    created_elem = root.find(".//CREATED")
    if created_elem is not None and created_elem.text:
        try:
            c_count = int(created_elem.text.strip())
            if c_count > 0:
                return True, voucher_num or "CREATED", None
            elif alt_count > 0:
                return True, voucher_num or "ALTERED", None
            else:
                return False, None, "Tally rejected creation (CREATED: 0, ALTERED: 0)."
        except ValueError:
            pass
    elif alt_count > 0:
        return True, voucher_num or "ALTERED", None
    elif len(root) == 0:
        msg = root_text or "Tally returned an empty or invalid response envelope."
        return False, None, f"Tally rejected creation: {msg}"

    return True, voucher_num or "SUCCESS", None

def diagnose_voucher_rejection(
    voucher_data: dict[str, Any],
    tally_response_text: str = "",
    parse_error: str | None = ""
) -> dict[str, Any]:
    """
    Intelligently diagnoses why Tally Prime rejected a voucher import request
    and provides human-readable English explanations (Root Cause) and Actionable Steps.
    """
    company_name = str(voucher_data.get("company_name") or voucher_data.get("companyName") or voucher_data.get("company") or "")
    v_date = str(voucher_data.get("date") or voucher_data.get("voucherDate") or "")
    v_type = str(voucher_data.get("voucher_type") or voucher_data.get("voucherType") or "Sales")
    v_type_lower = v_type.lower()
    is_pure_inventory = "stock journal" in v_type_lower or "physical stock" in v_type_lower
    raw_amt = voucher_data.get("amount")
    raw_items_val = voucher_data.get("items")
    items = []
    if isinstance(raw_items_val, list):
        items = list(raw_items_val)
    elif isinstance(raw_items_val, dict):
        for sub_k in ("source", "destination", "consumption", "production", "items_out", "items_in", "outward", "inward", "items", "rows"):
            sub_list = raw_items_val.get(sub_k)
            if isinstance(sub_list, list):
                items.extend(sub_list)
    else:
        items = voucher_data.get("inventory_entries") or []

    if is_pure_inventory and not items:
        inv_items = []
        for extra_key in (
            "source_items", "sourceItems",
            "destination_items", "destinationItems",
            "consumption_items", "consumptionItems",
            "production_items", "productionItems",
            "items_out", "itemsOut",
            "items_in", "itemsIn"
        ):
            ex_list = voucher_data.get(extra_key)
            if isinstance(ex_list, list):
                inv_items.extend(ex_list)
        if inv_items:
            items = inv_items

    reasons = []
    actions = []

    if tally_response_text and "<LINEERROR>" in tally_response_text:
        line_errs = re.findall(r"<LINEERROR>(.*?)</LINEERROR>", tally_response_text, re.IGNORECASE)
        for le in line_errs:
            clean_le = le.replace("&apos;", "'").replace("&quot;", '"').replace("&amp;", "&").strip()
            if clean_le:
                reasons.append(f"Tally Master Error: {clean_le}")
                if "svcurrentcompany" in clean_le.lower() or "currentcompany" in clean_le.lower():
                    actions.append(
                        f"Company '{company_name}' is not open in Tally Prime. Please open '{company_name}' inside Tally Prime (Gateway of Tally) and retry the entry from the web app."
                    )
                elif "ledger" in clean_le.lower():
                    actions.append("Ensure the required ledger accounts exist and are active in Tally.")
                elif "item" in clean_le.lower() or "unit" in clean_le.lower():
                    actions.append("Ensure the stock item and its unit of measure are created in Tally.")

    v_year = None
    if v_date:
        parsed_tally_date = format_tally_date(v_date)
        if len(parsed_tally_date) == 8 and parsed_tally_date.isdigit():
            v_year = int(parsed_tally_date[:4])

    fy_match = re.search(r"(20\d\d)\s*-\s*(20\d\d)", company_name)
    if fy_match and v_year:
        start_y = int(fy_match.group(1))
        end_y = int(fy_match.group(2))
        if v_year < start_y or v_year > end_y:
            reasons.append(
                f"Financial Year Mismatch: Voucher date '{v_date}' (Year {v_year}) is outside company '{company_name}' financial year ({start_y}-{end_y}). Tally rejects vouchers posted into a closed or future financial period."
            )
            actions.append(
                f"Select the active company for the current financial year on the Web App (e.g. 'Tarun Enterprise (25-26)'), or change the voucher date to be within {start_y}-{end_y}."
            )
    else:
        fy2_match = re.search(r"\(?(\d{2})\s*-\s*(\d{2})\)?", company_name)
        if fy2_match and v_year:
            start_y = 2000 + int(fy2_match.group(1))
            end_y = 2000 + int(fy2_match.group(2))
            if v_year < start_y or v_year > end_y:
                reasons.append(
                    f"Financial Year Mismatch: Voucher date '{v_date}' is outside company '{company_name}' financial year ({start_y}-{end_y})."
                )
                actions.append(
                    f"Ensure the voucher date matches the active company's financial year ({start_y}-{end_y})."
                )

    try:
        amt_val = float(raw_amt or 0.0)
    except (ValueError, TypeError):
        amt_val = 0.0

    all_items_zero = False
    if isinstance(items, list) and len(items) > 0:
        total_item_amt = 0.0
        for it in items:
            try:
                q = float(it.get("quantity") if it.get("quantity") is not None else it.get("qty", 0.0))
                r = float(it.get("rate") if it.get("rate") is not None else it.get("price", 0.0))
                total_item_amt += (q * r)
            except (ValueError, TypeError):
                pass
        if total_item_amt <= 0.0:
            all_items_zero = True

    has_particulars = bool(
        voucher_data.get("particulars")
        or voucher_data.get("ledger_entries")
        or voucher_data.get("ledgerEntries")
        or voucher_data.get("debit_particulars")
    )
    if has_particulars and amt_val <= 0.0:
        for p in (voucher_data.get("particulars") or voucher_data.get("ledger_entries") or []):
            if isinstance(p, dict):
                p_amt = float(p.get("amount") or p.get("amt") or 0.0)
                if p_amt > 0:
                    amt_val = p_amt
                    break

    party_input = voucher_data.get("partyLedger") or voucher_data.get("party_ledger") or voucher_data.get("party") or ""
    if is_pure_inventory and not party_input:
        party_input = "Inventory / Stock"

    if not is_pure_inventory:
        if amt_val <= 0.0 and (all_items_zero or len(items) == 0) and not has_particulars:
            reasons.append(
                "Zero-Value Invoice: Total voucher amount is Rs. 0.00 (item quantity or rate is 0). Tally Prime standard settings do not allow zero-value invoices without explicit configuration."
            )
            actions.append(
                "Enter a valid positive Quantity, Rate, and Amount for your items on the Web App before creating the invoice."
            )

        if not party_input and has_particulars:
            for p in (voucher_data.get("particulars") or voucher_data.get("ledger_entries") or []):
                if isinstance(p, dict):
                    p_n = p.get("partyName") or p.get("party_name") or p.get("ledgerName") or p.get("name")
                    if p_n:
                        party_input = str(p_n).strip()
                        break

        if not party_input or str(party_input).strip() == "":
            reasons.append(
                "Missing Customer / Party Ledger: No customer or debtor was selected in the web request (defaulted to Cash)."
            )
            actions.append(
                "Select a valid Customer / Debtor ledger from the customer dropdown on the Web App."
            )
    else:
        if len(items) == 0:
            reasons.append(
                "Empty Stock Journal: No source or destination items provided in the request."
            )
            actions.append(
                "Add at least one Source (Consumption) or Destination (Production) item with valid Quantity and Rate on the Web App."
            )
        elif all_items_zero:
            reasons.append(
                "Zero-Value Stock Journal: Item quantity or rate is 0.00."
            )
            actions.append(
                "Enter a valid positive Quantity and Rate for your Stock Journal items on the Web App."
            )

    if not reasons:
        reasons.append(
            f"Tally rejected voucher creation ({parse_error or 'Validation exception'})."
        )
        actions.append(
            "Check that Tally Prime is running, the company is open, and all ledger accounts (Sales, Party, Tax) exist in Tally."
        )

    combined_reason = " | ".join(reasons)
    combined_action = " ".join(actions)

    return {
        "reason": combined_reason,
        "action": combined_action,
        "reasons": reasons,
        "actions": actions,
        "technical_error": parse_error or "Tally reported an exception during voucher creation.",
        "voucher_type": v_type,
        "voucher_number": str(voucher_data.get("voucher_number") or voucher_data.get("voucherNumber") or "N/A"),
        "company_name": company_name or "N/A",
        "party": str(party_input or voucher_data.get("party_ledger") or "Cash"),
        "amount": amt_val,
        "date": v_date or "N/A"
    }

class TallyImporter:
    def __init__(self, client: TallyClient | None = None):
        self.client = client or TallyClient()
        self._voucher_types_cache: dict[str, dict[str, str]] = {}
        self._known_ledgers: dict[str, set] = {}
        self._known_units: dict[str, set] = {}
        self._known_stock_items: dict[str, set] = {}
        self._company_states: dict[str, str] = {}
        self._company_gstins: dict[str, str] = {}

    async def check_tally_company_status(
        self, host: str, port: int, company_name: str
    ) -> tuple[bool, bool, list[str]]:
        """
        Checks if Tally Prime is running and if company_name is currently opened in Tally.
        Returns (is_tally_online: bool, is_company_loaded: bool, open_companies: List[str]).
        """
        try:
            from apps.backend.adapters.tally.request_builder import (
                build_company_list_xml,
            )
            from apps.backend.adapters.tally.response_parser import parse_company_list
            xml_req = build_company_list_xml()
            ok, status, resp_txt, err = await self.client.send_xml_request_async(
                host=host, port=port, xml_content=xml_req, timeout=4.0
            )
            if not ok or status != 200 or not resp_txt:
                return False, False, []

            resp_lower = resp_txt.strip().lower()
            if "<!doctype html" in resp_lower or "<html" in resp_lower or "license server is running" in resp_lower:
                return False, False, []

            companies = parse_company_list(resp_txt)
            for c in companies:
                c_n = str(c.get("name") or c.get("company_name", "")).strip().lower()
                if c_n:
                    if c.get("state"):
                        self._company_states[c_n] = str(c["state"]).strip()
                    if c.get("gstin"):
                        self._company_gstins[c_n] = str(c["gstin"]).strip()

            open_names = [str(c.get("name") or c.get("company_name", "")).strip() for c in companies if c.get("name") or c.get("company_name")]
            if not company_name or not company_name.strip():
                return True, len(open_names) > 0, open_names

            target = company_name.strip().lower()
            loaded = any(target == name.lower() or target in name.lower() or name.lower() in target for name in open_names)
            return True, loaded, open_names
        except Exception as exc:
            logger.debug(f"Error checking Tally company status: {exc}")
            return False, False, []

    async def ensure_ledger(
        self,
        host: str,
        port: int,
        company_name: str,
        ledger_name: str,
        parent: str = "Sundry Debtors",
        extra_info: dict[str, Any] | None = None
    ) -> bool:
        """
        Auto-Creates the ledger in Tally if it does not already exist.
        Runs safely on-the-fly before voucher posting.
        """
        if not ledger_name or not ledger_name.strip():
            return False

        clean_name = ledger_name.strip()
        if clean_name.lower() in ("cash", "profit & loss a/c", "profit &amp; loss a/c"):
            return True

        comp_key = (company_name or "").strip().lower()
        if comp_key not in self._known_ledgers:
            self._known_ledgers[comp_key] = set()
        if clean_name.lower() in self._known_ledgers[comp_key]:
            return True

        ledger_payload = {
            "company_name": company_name,
            "name": clean_name,
            "parent": parent,
            **(extra_info or {})
        }
        xml_envelope = build_ledger_import_xml(ledger_payload)

        try:
            ok, status, res_text, _ = await self.client.send_xml_request_async(
                host=host, port=port, xml_content=xml_envelope, serialize_company=company_name
            )
            if ok and status == 200:
                self._known_ledgers[comp_key].add(clean_name.lower())
                logger.info(f"Auto-Ensured Ledger '{clean_name}' under '{parent}' in Tally (Company: '{company_name}')")
                return True
        except Exception as exc:
            logger.warning(f"Auto-ensure ledger '{clean_name}' encountered error: {exc}")

        return False

    async def ensure_unit(
        self, host: str, port: int, company_name: str, unit_name: str, decimal_places: int = 0
    ) -> bool:
        """
        Auto-Creates the Unit of Measure in Tally if it does not already exist.
        """
        if not unit_name or not unit_name.strip():
            return False
        clean_name = unit_name.strip()
        comp_key = (company_name or "").strip().lower()
        if comp_key not in self._known_units:
            self._known_units[comp_key] = set()
        if clean_name.lower() in self._known_units[comp_key]:
            return True

        xml = build_unit_import_xml({
            "company_name": company_name,
            "name": clean_name,
            "decimal_places": decimal_places,
        })
        try:
            ok, status, res_text, _ = await self.client.send_xml_request_async(
                host=host, port=port, xml_content=xml, serialize_company=company_name
            )
            if ok and status == 200:
                self._known_units[comp_key].add(clean_name.lower())
                logger.info(f"Auto-Ensured Unit '{clean_name}' in Tally (Company: '{company_name}')")
                return True
        except Exception as exc:
            logger.debug(f"Auto-ensure unit '{clean_name}' error: {exc}")
        return False

    async def ensure_godown(
        self, host: str, port: int, company_name: str, godown_name: str
    ) -> bool:
        """Auto-creates Godown in Tally if it does not already exist."""
        clean_gname = godown_name.strip() if godown_name else ""
        if not clean_gname or clean_gname.lower() in ("main location", "primary", "default", "none"):
            return True
        from apps.backend.adapters.tally.xml_builders.stock_builder import (
            build_godown_import_xml,
        )
        g_xml = build_godown_import_xml(clean_gname, company_name)
        try:
            ok, status, _, _ = await self.client.send_xml_request_async(
                host=host, port=port, xml_content=g_xml, serialize_company=company_name
            )
            return ok and status == 200
        except Exception as exc:
            logger.debug(f"Auto-ensure godown '{clean_gname}' notice: {exc}")
            return False

    async def ensure_stock_item(
        self,
        host: str,
        port: int,
        company_name: str,
        item_name: str,
        unit_name: str = "Pcs",
        hsn_code: str = "",
        hsn_desc: str = "",
        gst_rate: Any | None = None,
        quantity: Any | None = None,
        rate: Any | None = None,
        value: Any | None = None,
        godown: str | None = None,
        batch: str | None = None,
    ) -> bool:
        """
        Auto-Creates the Stock Item in Tally if it does not already exist with opening stock & GST details.
        Ensures the Unit and Godown exist in Tally first, then inserts the Stock Item.
        """
        if not item_name or not item_name.strip():
            return False
        clean_name = item_name.strip()
        comp_key = (company_name or "").strip().lower()
        if comp_key not in self._known_stock_items:
            self._known_stock_items[comp_key] = set()

        has_opening = False
        if quantity is not None:
            try:
                has_opening = float(quantity or 0.0) != 0.0
            except (ValueError, TypeError):
                has_opening = False

        if clean_name.lower() in self._known_stock_items[comp_key] and not has_opening:
            return True

        clean_unit = unit_name.strip() if unit_name else ""
        if not clean_unit or clean_unit.lower() == "pcs":
            lookup_u = _lookup_item_master_unit(company_name, clean_name)
            if lookup_u:
                clean_unit = lookup_u
        if not clean_unit:
            clean_unit = "Pcs"

        clean_hsn = hsn_code.strip() if hsn_code else ""
        if not clean_hsn:
            lookup_h = _lookup_item_master_hsn(company_name, clean_name)
            if lookup_h:
                clean_hsn = lookup_h

        await self.ensure_unit(host=host, port=port, company_name=company_name, unit_name=clean_unit)
        if godown:
            await self.ensure_godown(host=host, port=port, company_name=company_name, godown_name=godown)

        # If item already exists but has opening balance to apply, use alter_stock_item
        if clean_name.lower() in self._known_stock_items[comp_key] and has_opening:
            alt_ok, _ = await self.alter_stock_item(
                host=host,
                port=port,
                company_name=company_name,
                item_data={
                    "name": clean_name,
                    "unit": clean_unit,
                    "hsn_code": clean_hsn,
                    "hsn_description": hsn_desc,
                    "gst_rate": gst_rate,
                    "quantity": quantity,
                    "rate": rate,
                    "value": value,
                    "godown": godown,
                    "batch": batch,
                }
            )
            return alt_ok

        item_xml = build_stock_item_import_xml({
            "company_name": company_name,
            "name": clean_name,
            "unit": clean_unit,
            "hsn_code": clean_hsn,
            "hsn_description": hsn_desc,
            "gst_rate": gst_rate,
            "quantity": quantity,
            "rate": rate,
            "value": value,
            "godown": godown,
            "batch": batch,
        })
        try:
            ok, status, res_text, _ = await self.client.send_xml_request_async(
                host=host, port=port, xml_content=item_xml, serialize_company=company_name
            )
            if ok and status == 200:
                parsed_ok, _, err = parse_tally_import_response(res_text or "")
                if parsed_ok:
                    self._known_stock_items[comp_key].add(clean_name.lower())
                    logger.info(f"Auto-Ensured Stock Item '{clean_name}' with Unit '{clean_unit}' in Tally (Company: '{company_name}')")
                    return True
                elif err and any(k in err.lower() for k in ("already exists", "duplicate")):
                    self._known_stock_items[comp_key].add(clean_name.lower())
                    if has_opening:
                        alt_ok, _ = await self.alter_stock_item(
                            host=host,
                            port=port,
                            company_name=company_name,
                            item_data={
                                "name": clean_name,
                                "unit": clean_unit,
                                "hsn_code": clean_hsn,
                                "hsn_description": hsn_desc,
                                "gst_rate": gst_rate,
                                "quantity": quantity,
                                "rate": rate,
                                "value": value,
                                "godown": godown,
                                "batch": batch,
                            }
                        )
                        return alt_ok
                    return True
        except Exception as exc:
            logger.warning(f"Auto-ensure stock item '{clean_name}' error: {exc}")
        return False

    async def alter_stock_item(
        self, host: str, port: int, company_name: str, item_data: dict[str, Any]
    ) -> tuple[bool, str | None]:
        """Alters/updates an existing Stock Item in Tally Prime."""
        clean_name = str(item_data.get("name") or item_data.get("itemName") or "").strip()
        if not clean_name:
            return False, "Item name is required"

        clean_unit = str(item_data.get("unit") or item_data.get("units") or item_data.get("base_units") or "Pcs").strip()
        await self.ensure_unit(host=host, port=port, company_name=company_name, unit_name=clean_unit)

        item_xml = build_stock_item_alter_xml({
            **item_data,
            "company_name": company_name,
            "name": clean_name
        })
        try:
            ok, status, res_text, _ = await self.client.send_xml_request_async(
                host=host, port=port, xml_content=item_xml, serialize_company=company_name
            )
            if ok and status == 200:
                parsed_ok, _, err = parse_tally_import_response(res_text or "")
                if parsed_ok:
                    comp_key = (company_name or "").strip().lower()
                    if comp_key in self._known_stock_items:
                        self._known_stock_items[comp_key].add(clean_name.lower())
                    logger.info(f"Altered Stock Item '{clean_name}' in Tally (Company: '{company_name}')")
                    return True, None

                # Fallback 1: If rejected due to Godown/Batch allocations, retry without allocations
                if err and any(k in err.lower() for k in ("batch", "godown", "allocation")):
                    logger.info(f"Retrying Alter Stock Item '{clean_name}' without batch allocations: {err}")
                    fallback_data = dict(item_data)
                    fallback_data["godown"] = ""
                    fallback_data["batch"] = ""
                    fallback_xml = build_stock_item_alter_xml({
                        **fallback_data,
                        "company_name": company_name,
                        "name": clean_name
                    })
                    ok2, status2, res_text2, _ = await self.client.send_xml_request_async(
                        host=host, port=port, xml_content=fallback_xml, serialize_company=company_name
                    )
                    if ok2 and status2 == 200:
                        p_ok2, _, _ = parse_tally_import_response(res_text2 or "")
                        if p_ok2:
                            logger.info(f"Altered Stock Item '{clean_name}' without batch allocations in Tally")
                            return True, None

                # Fallback 2: If item does not exist in Tally yet, create it and then alter
                if err and any(k in err.lower() for k in ("not found", "cannot find", "can't find", "does not exist", "created: 0, altered: 0")):
                    logger.info(f"Item '{clean_name}' not found for alter, creating new stock item first...")
                    create_ok = await self.ensure_stock_item(
                        host=host, port=port, company_name=company_name,
                        item_name=clean_name, unit_name=clean_unit,
                        hsn_code=str(item_data.get("hsn_code") or item_data.get("hsnCode") or "")
                    )
                    if create_ok:
                        ok3, _, res_text3, _ = await self.client.send_xml_request_async(
                            host=host, port=port, xml_content=item_xml, serialize_company=company_name
                        )
                        p_ok3, _, _ = parse_tally_import_response(res_text3 or "")
                        if p_ok3:
                            return True, None

                return False, err or "Tally rejected alter request"
            return False, f"HTTP status {status} from Tally"
        except Exception as exc:
            logger.warning(f"Alter stock item '{clean_name}' error: {exc}")
            return False, str(exc)

    async def ensure_voucher_type(
        self, host: str, port: int, company_name: str, voucher_type_name: str, parent: str | None = None
    ) -> tuple[bool, str]:
        """
        Auto-Checks if the Voucher Type exists in Tally Prime.
        If it does not exist, searches for smart aliases (e.g. 'Quotation' -> 'Quotation Voucher' / 'Sales Quotation')
        or automatically creates the custom Voucher Type in Tally with Active=Yes.
        Returns (success: bool, resolved_voucher_type_name: str).
        """
        if not voucher_type_name or not voucher_type_name.strip():
            return True, "Sales"

        comp_key = (company_name or "").strip()
        v_clean = voucher_type_name.strip()
        v_lower = v_clean.lower()

        if comp_key not in self._voucher_types_cache:
            self._voucher_types_cache[comp_key] = {}

        cached = self._voucher_types_cache[comp_key]
        if v_lower in cached:
            return True, cached[v_lower]

        # Query existing voucher types from Tally
        try:
            from apps.backend.adapters.tally.request_builder import build_collection_xml
            xml_q = build_collection_xml(
                collection_type="VoucherType",
                fetch_fields=["NAME", "PARENT", "ISACTIVE"],
                company_name=comp_key if comp_key else None
            )
            ok, status, txt, _ = await self.client.send_xml_request_async(host=host, port=port, xml_content=xml_q)
            if ok and status == 200 and txt:
                clean_txt = re.sub(r"&#\d+;", "", txt)
                try:
                    root = ET.fromstring(clean_txt)
                    for vt in root.findall(".//VOUCHERTYPE"):
                        t_name = vt.get("NAME") or ""
                        name_elem = vt.find("NAME")
                        if not t_name and name_elem is not None and name_elem.text:
                            t_name = name_elem.text or ""
                        t_name = t_name.strip()
                        if t_name:
                            cached[t_name.lower()] = t_name
                except Exception:
                    matches = re.findall(r'<VOUCHERTYPE [^>]*NAME="([^"]+)"', clean_txt)
                    for m in matches:
                        m_str = m.strip()
                        if m_str:
                            cached[m_str.lower()] = m_str
        except Exception as exc:
            logger.warning(f"Failed to query VoucherType collection from Tally: {exc}")

        # Check in refreshed cache
        if v_lower in cached:
            return True, cached[v_lower]

        # Smart alias check for Quotation
        if v_lower in ("quotation", "quote", "estimates", "estimate"):
            for alias in ("quotation voucher", "sales quotation", "quote", "estimate", "proforma invoice"):
                if alias in cached:
                    resolved = cached[alias]
                    cached[v_lower] = resolved
                    logger.info(f"Smart-mapped voucher type '{voucher_type_name}' to existing '{resolved}' in Tally")
                    return True, resolved

        # Try to auto-create custom voucher type in Tally
        resolved_parent = parent or determine_voucher_type_parent(v_clean)
        candidates = ["Quotation Voucher", "Sales Quotation"] if v_lower == "quotation" else [v_clean]

        for cand in candidates:
            cand_lower = cand.lower()
            if cand_lower in cached:
                cached[v_lower] = cached[cand_lower]
                return True, cached[cand_lower]

            vt_xml = build_voucher_type_import_xml({
                "company_name": comp_key,
                "name": cand,
                "parent": resolved_parent,
            })
            try:
                ok, status, res_txt, _ = await self.client.send_xml_request_async(
                    host=host, port=port, xml_content=vt_xml
                )
                if ok and status == 200 and ("<CREATED>1</CREATED>" in res_txt or "<ALTERED>1</ALTERED>" in res_txt):
                    if "<EXCEPTIONS>0</EXCEPTIONS>" in res_txt and "<ERRORS>0</ERRORS>" in res_txt:
                        logger.info(f"Auto-Created Voucher Type '{cand}' under '{resolved_parent}' in Tally (Company: '{comp_key}')")
                        cached[cand_lower] = cand
                        cached[v_lower] = cand
                        return True, cand
            except Exception as e:
                logger.warning(f"Failed to auto-create voucher type '{cand}': {e}")

        logger.warning(f"Voucher type '{voucher_type_name}' not found and could not be created; falling back to '{resolved_parent}'")
        cached[v_lower] = resolved_parent
        return True, resolved_parent

    async def fetch_ledger_guid(self, host: str, port: int, company_name: str, ledger_name: str) -> str | None:
        """Queries Tally Prime HTTP interface for a Ledger's GUID / Master ID."""
        if not ledger_name or not str(ledger_name).strip():
            return None
        clean_party = escape_xml(str(ledger_name).strip())
        clean_comp = escape_xml(str(company_name).strip()) if company_name else ""
        company_tag = f"<SVCURRENTCOMPANY>{clean_comp}</SVCURRENTCOMPANY>" if clean_comp else ""
        xml_req = f"""<ENVELOPE>
  <HEADER>
    <VERSION>1</VERSION>
    <TALLYREQUEST>EXPORT</TALLYREQUEST>
    <TYPE>OBJECT</TYPE>
    <SUBTYPE>Ledger</SUBTYPE>
    <ID TYPE="Name">{clean_party}</ID>
  </HEADER>
  <BODY>
    <DESC>
      <STATICVARIABLES>
        <SVEXPORTFORMAT>$$SYSNAME:XML</SVEXPORTFORMAT>
        {company_tag}
      </STATICVARIABLES>
      <FETCHLIST>
        <FETCH>NAME</FETCH>
        <FETCH>GUID</FETCH>
        <FETCH>ALTERID</FETCH>
        <FETCH>MASTERID</FETCH>
      </FETCHLIST>
    </DESC>
  </BODY>
</ENVELOPE>"""
        try:
            ok, code, text, _ = await self.client.send_xml_request_async(host, port, xml_req, timeout=5.0)
            if ok and code == 200 and text:
                import xml.etree.ElementTree as ET
                root = ET.fromstring(text)
                led = root.find(".//LEDGER")
                if led is not None:
                    guid_val = led.findtext("GUID")
                    if guid_val and guid_val.strip():
                        return guid_val.strip()
                    master_id = led.findtext("MASTERID") or led.attrib.get("ID")
                    if master_id and master_id.strip():
                        return master_id.strip()
                    alt_id = led.findtext("ALTERID")
                    if alt_id and alt_id.strip():
                        return alt_id.strip()
        except Exception as exc:
            logger.debug(f"fetch_ledger_guid notice: {exc}")
        return None

    async def fetch_stock_item_guid(self, host: str, port: int, company_name: str, item_name: str) -> str | None:
        """Queries Tally Prime HTTP interface for a Stock Item's GUID / Master ID."""
        if not item_name or not str(item_name).strip():
            return None
        clean_item = escape_xml(str(item_name).strip())
        clean_comp = escape_xml(str(company_name).strip()) if company_name else ""
        company_tag = f"<SVCURRENTCOMPANY>{clean_comp}</SVCURRENTCOMPANY>" if clean_comp else ""
        xml_req = f"""<ENVELOPE>
  <HEADER>
    <VERSION>1</VERSION>
    <TALLYREQUEST>EXPORT</TALLYREQUEST>
    <TYPE>OBJECT</TYPE>
    <SUBTYPE>StockItem</SUBTYPE>
    <ID TYPE="Name">{clean_item}</ID>
  </HEADER>
  <BODY>
    <DESC>
      <STATICVARIABLES>
        <SVEXPORTFORMAT>$$SYSNAME:XML</SVEXPORTFORMAT>
        {company_tag}
      </STATICVARIABLES>
      <FETCHLIST>
        <FETCH>NAME</FETCH>
        <FETCH>GUID</FETCH>
        <FETCH>ALTERID</FETCH>
        <FETCH>MASTERID</FETCH>
      </FETCHLIST>
    </DESC>
  </BODY>
</ENVELOPE>"""
        try:
            ok, code, text, _ = await self.client.send_xml_request_async(host, port, xml_req, timeout=5.0)
            if ok and code == 200 and text:
                import xml.etree.ElementTree as ET
                root = ET.fromstring(text)
                it = root.find(".//STOCKITEM")
                if it is not None:
                    guid_val = it.findtext("GUID")
                    if guid_val and guid_val.strip():
                        return guid_val.strip()
                    master_id = it.findtext("MASTERID") or it.attrib.get("ID")
                    if master_id and master_id.strip():
                        return master_id.strip()
                    alt_id = it.findtext("ALTERID")
                    if alt_id and alt_id.strip():
                        return alt_id.strip()
        except Exception as exc:
            logger.debug(f"fetch_stock_item_guid notice: {exc}")
        return None

    async def fetch_voucher_guid(
        self, host: str, port: int, company_name: str, voucher_number: str, voucher_date: str | None = None
    ) -> str | None:
        """Queries Tally Prime HTTP interface for a Voucher's GUID / Master ID by voucher number."""
        if not voucher_number or not str(voucher_number).strip():
            return None
        clean_vnum = str(voucher_number).strip()
        clean_comp = escape_xml(str(company_name).strip()) if company_name else ""
        company_tag = f"<SVCURRENTCOMPANY>{clean_comp}</SVCURRENTCOMPANY>" if clean_comp else ""

        date_tags = ""
        if voucher_date:
            clean_d = str(voucher_date).replace("-", "").replace("/", "").strip()
            if len(clean_d) == 8 and clean_d.isdigit():
                date_tags = f"""<SVFROMDATE TYPE="Date">{clean_d}</SVFROMDATE>
        <SVTODATE TYPE="Date">{clean_d}</SVTODATE>"""

        xml_req = f"""<ENVELOPE>
  <HEADER>
    <VERSION>1</VERSION>
    <TALLYREQUEST>EXPORT</TALLYREQUEST>
    <TYPE>COLLECTION</TYPE>
    <ID>VchByDateCol</ID>
  </HEADER>
  <BODY>
    <DESC>
      <STATICVARIABLES>
        <SVEXPORTFORMAT>$$SYSNAME:XML</SVEXPORTFORMAT>
        {date_tags}
        {company_tag}
      </STATICVARIABLES>
      <TDL>
        <TDLMESSAGE>
          <COLLECTION NAME="VchByDateCol" ISINITIALISE="Yes">
            <TYPE>Voucher</TYPE>
            <FETCH>VOUCHERNUMBER,GUID,ALTERID,MASTERID</FETCH>
          </COLLECTION>
        </TDLMESSAGE>
      </TDL>
    </DESC>
  </BODY>
</ENVELOPE>"""
        try:
            ok, code, text, _ = await self.client.send_xml_request_async(host, port, xml_req, timeout=5.0)
            if ok and code == 200 and text:
                import xml.etree.ElementTree as ET
                clean_text = re.sub(r'&#(0?[0-8]|1[124-9]|2[0-9]|3[01]);', '', text)
                clean_text = re.sub(r'&#\d+;', '', clean_text)
                root = ET.fromstring(clean_text)
                for v in root.findall(".//VOUCHER"):
                    vn = v.findtext("VOUCHERNUMBER")
                    if vn and vn.strip() == clean_vnum:
                        guid_val = v.findtext("GUID")
                        if guid_val and guid_val.strip():
                            return guid_val.strip()
                        master_id = v.findtext("MASTERID") or v.attrib.get("ID")
                        if master_id and master_id.strip():
                            return master_id.strip()
                        alt_id = v.findtext("ALTERID")
                        if alt_id and alt_id.strip():
                            return alt_id.strip()
        except Exception as exc:
            logger.debug(f"fetch_voucher_guid notice: {exc}")
        return None

    async def import_ledger(self, host: str, port: int, ledger_data: dict[str, Any]) -> dict[str, Any]:
        """Explicitly creates a Ledger in Tally Prime and retrieves its tallyExternalId immediately."""
        ledger_name = str(ledger_data.get("name") or ledger_data.get("party_ledger") or ledger_data.get("partyName") or ledger_data.get("party_name") or "").strip()
        comp_name = str(ledger_data.get("company_name") or "")

        # Guard: Check Tally connectivity & verify if target company is open in Tally Prime
        is_online, is_loaded, open_comps = await self.check_tally_company_status(host, port, comp_name)
        if not is_online:
            return {
                "success": False,
                "message": f"Tally Prime is offline at {host}:{port}.",
                "error": f"Tally Prime is not running or HTTP port {port} is closed.",
            }
        if comp_name and not is_loaded:
            return {
                "success": False,
                "message": f"Company '{comp_name}' is not currently open in Tally.",
                "error": f"Company '{comp_name}' is not open in Tally Prime (Active: {', '.join(open_comps) or 'None'}).",
            }

        xml_payload = build_ledger_import_xml(ledger_data, action="Create")
        ok, status_code, res_text, err_msg = await self.client.send_xml_request_async(
            host=host, port=port, xml_content=xml_payload, serialize_company=comp_name
        )

        if not ok or status_code != 200:
            return {
                "success": False,
                "message": "Failed to post ledger XML to Tally Prime HTTP interface.",
                "error": err_msg or f"HTTP status code {status_code}",
            }

        success, _, parse_err = parse_tally_import_response(res_text, default_voucher_number="LEDGER_CREATED")
        if not success:
            if parse_err and any(k in parse_err.lower() for k in ("already exists", "duplicate", "already present")):
                logger.info(f"Ledger '{ledger_name}' already exists in Tally Prime. Attempting ACTION='Alter' to sync full details (Address, Mobile, GSTIN, State, Pincode)...")
                alter_payload = build_ledger_import_xml(ledger_data, action="Alter")
                alt_ok, alt_status, alt_res, _ = await self.client.send_xml_request_async(
                    host=host, port=port, xml_content=alter_payload, serialize_company=comp_name
                )
                if alt_ok and alt_status == 200:
                    alt_success, _, _ = parse_tally_import_response(alt_res, default_voucher_number="LEDGER_ALTERED")
                    if alt_success:
                        logger.info(f"Ledger '{ledger_name}' successfully updated in Tally Prime via ACTION='Alter'.")
                tally_guid = await self.fetch_ledger_guid(host, port, comp_name, ledger_name)
                return {
                    "success": True,
                    "already_exists": True,
                    "message": f"Ledger '{ledger_name}' updated in Tally Prime with full details.",
                    "error": None,
                    "tallyExternalId": tally_guid or f"TALLY-{ledger_name}",
                    "guid": tally_guid or f"TALLY-{ledger_name}",
                }
            return {
                "success": False,
                "message": "Tally Prime rejected the ledger creation.",
                "error": parse_err,
            }

        tally_guid = await self.fetch_ledger_guid(host, port, comp_name, ledger_name)
        return {
            "success": True,
            "message": f"Ledger '{ledger_name}' successfully created in Tally Prime.",
            "error": None,
            "tallyExternalId": tally_guid or f"TALLY-{ledger_name}",
            "guid": tally_guid or f"TALLY-{ledger_name}",
        }

    async def import_voucher(self, host: str, port: int, voucher_data: dict[str, Any]) -> dict[str, Any]:
        company_name = voucher_data.get("company_name", "")

        # Guard: Check Tally connectivity & verify if target company is open in Tally Prime
        is_online, is_loaded, open_comps = await self.check_tally_company_status(host, port, company_name)
        if not is_online:
            logger.info(f"Tally Prime is offline at {host}:{port}. Queueing voucher.")
            return {
                "success": False,
                "should_queue": True,
                "status": "TALLY_OFFLINE",
                "voucher_number": None,
                "company_name": company_name,
                "message": f"Tally Prime is offline at {host}:{port}.",
                "reason": f"Tally Prime is not running or HTTP port {port} is closed.",
                "action": f"Ensure Tally Prime is running on port {port}. Voucher will auto-post once connected.",
            }
        if company_name and not is_loaded:
            logger.info(f"Target company '{company_name}' is not open in Tally. Queueing voucher.")
            return {
                "success": False,
                "should_queue": True,
                "status": "COMPANY_NOT_LOADED",
                "voucher_number": None,
                "company_name": company_name,
                "message": f"Company '{company_name}' is not currently open in Tally.",
                "reason": f"Company '{company_name}' is not open in Tally Prime (Active: {', '.join(open_comps) or 'None'}).",
                "action": f"Open '{company_name}' inside Tally Prime (Gateway of Tally). Voucher will auto-post.",
            }

        comp_key = (company_name or "").strip().lower()
        if not voucher_data.get("company_state") and comp_key in self._company_states:
            voucher_data["company_state"] = self._company_states[comp_key]
        if not voucher_data.get("company_gstin") and comp_key in self._company_gstins:
            voucher_data["company_gstin"] = self._company_gstins[comp_key]

        raw_vtype = _clean_str(
            voucher_data.get("voucher_type")
            or voucher_data.get("voucherType")
            or voucher_data.get("vtype")
            or voucher_data.get("type")
            or "Sales"
        )
        ok_vt, resolved_vtype = await self.ensure_voucher_type(
            host=host, port=port, company_name=company_name, voucher_type_name=raw_vtype
        )
        if resolved_vtype:
            voucher_data["voucher_type"] = resolved_vtype
            voucher_data["voucherType"] = resolved_vtype
            v_type = resolved_vtype.lower()
        else:
            v_type = (voucher_data.get("voucher_type") or "Sales").lower()

        party_ledger = (
            voucher_data.get("party_ledger")
            or voucher_data.get("party_name")
            or voucher_data.get("partyLedger")
            or voucher_data.get("ledger")
            or ""
        )
        explicit_parent = (
            voucher_data.get("party_parent")
            or voucher_data.get("partyParent")
            or voucher_data.get("parent")
            or voucher_data.get("group")
        )
        if explicit_parent:
            party_parent = explicit_parent
        else:
            party_type_hint = str(voucher_data.get("partyType") or voucher_data.get("party_type") or "").strip().upper()
            if "DEBTOR" in party_type_hint or "CUSTOMER" in party_type_hint or "CLIENT" in party_type_hint:
                party_parent = "Sundry Debtors"
            elif "CREDITOR" in party_type_hint or "SUPPLIER" in party_type_hint or "VENDOR" in party_type_hint:
                party_parent = "Sundry Creditors"
            elif any(k in v_type for k in ("sales", "receipt", "quotation", "quote", "estimate", "proforma", "credit note", "credit_note", "sales return")):
                party_parent = "Sundry Debtors"
            else:
                party_parent = "Sundry Creditors"

        v_type_lower = v_type.lower()
        is_stock_journal = "stock journal" in v_type_lower
        is_physical_stock = "physical stock" in v_type_lower
        is_pure_inventory = is_stock_journal or is_physical_stock

        if not is_pure_inventory and party_ledger and party_ledger.lower() not in ("cash", "bank"):
            await self.ensure_ledger(
                host=host,
                port=port,
                company_name=company_name,
                ledger_name=party_ledger,
                parent=party_parent,
                extra_info={
                    "state": voucher_data.get("state"),
                    "gstin": voucher_data.get("gstin") or voucher_data.get("party_gstin"),
                    "mobile": voucher_data.get("mobile") or voucher_data.get("phone"),
                    "address": voucher_data.get("address"),
                }
            )

        raw_txn_type = _clean_str(voucher_data.get("transactionType") or voucher_data.get("transaction_type"))
        bank_ledger_to_ensure = _clean_str(
            voucher_data.get("bank_ledger")
            or voucher_data.get("bankLedger")
            or voucher_data.get("cash_bank_ledger")
            or voucher_data.get("cashBankLedger")
            or voucher_data.get("account")
            or voucher_data.get("accountName")
            or voucher_data.get("account_name")
            or voucher_data.get("bank_account")
            or voucher_data.get("bankAccount")
            or (
                "Cash"
                if raw_txn_type and raw_txn_type.upper() in ("CASH", "CASH_IN_HAND", "CASH-IN-HAND")
                else raw_txn_type
            )
            or ""
        )
        if bank_ledger_to_ensure and bank_ledger_to_ensure.lower() not in ("cash", "cash in hand", "cash-in-hand"):
            await self.ensure_ledger(
                host=host,
                port=port,
                company_name=company_name,
                ledger_name=bank_ledger_to_ensure,
                parent="Bank Accounts"
            )

        # For Journal, Contra, Receipt, and Payment vouchers, ensure all non-cash/bank ledgers in particulars exist in Tally
        if ("journal" in v_type and not is_pure_inventory) or "contra" in v_type or "receipt" in v_type or "payment" in v_type:
            raw_j_entries = (
                voucher_data.get("particulars")
                or voucher_data.get("ledger_entries")
                or voucher_data.get("ledgerEntries")
                or voucher_data.get("items")
                or []
            )
            if isinstance(raw_j_entries, list):
                for j_ent in raw_j_entries:
                    if isinstance(j_ent, dict):
                        j_name = str(
                            j_ent.get("partyName")
                            or j_ent.get("party_name")
                            or j_ent.get("ledgerName")
                            or j_ent.get("ledger_name")
                            or j_ent.get("name")
                            or j_ent.get("ledger")
                            or j_ent.get("party")
                            or j_ent.get("customer")
                            or j_ent.get("supplier")
                            or ""
                        ).strip()
                        if j_name and j_name.lower() not in ("cash", "cash in hand", "cash-in-hand"):
                            j_type = str(j_ent.get("type") or j_ent.get("entry_type") or "Debit").strip().lower()
                            if "contra" in v_type:
                                j_parent = "Bank Accounts"
                            elif "receipt" in v_type:
                                j_parent = "Sundry Debtors"
                            elif "payment" in v_type:
                                j_parent = "Sundry Creditors"
                            else:
                                j_parent = "Sundry Debtors" if j_type in ("debit", "dr", "by") else "Sundry Creditors"
                            await self.ensure_ledger(
                                host=host,
                                port=port,
                                company_name=company_name,
                                ledger_name=j_name,
                                parent=j_parent,
                            )

        items = list(_extract_items_list(voucher_data) or [])
        if ("journal" in v_type and not is_pure_inventory) or "contra" in v_type or "receipt" in v_type or "payment" in v_type:
            items = []
        if is_pure_inventory:
            raw_items_d: dict[str, Any] = {}
            raw_items_val_imp = voucher_data.get("items")
            if isinstance(raw_items_val_imp, dict):
                raw_items_d = dict(raw_items_val_imp)
            if raw_items_d:
                for sub_k in ("source", "destination", "consumption", "production", "items_out", "items_in", "outward", "inward"):
                    sub_list = raw_items_d.get(sub_k)
                    if isinstance(sub_list, list):
                        items.extend(sub_list)

            for extra_key in (
                "source_items", "sourceItems",
                "destination_items", "destinationItems",
                "consumption_items", "consumptionItems",
                "production_items", "productionItems",
                "items_out", "itemsOut",
                "items_in", "itemsIn",
                "outward_items", "outwardItems",
                "inward_items", "inwardItems",
            ):
                extra_list = voucher_data.get(extra_key)
                if extra_list and isinstance(extra_list, list):
                    items.extend(extra_list)

        if items and isinstance(items, list):
            for it in items:
                i_name = _extract_item_name(it)
                if i_name:
                    i_unit = _clean_str(it.get("units") or it.get("unit") or it.get("uom") or it.get("baseUnits") or it.get("base_units"))
                    if not i_unit or i_unit.lower() == "pcs":
                        mu = _lookup_item_master_unit(company_name, i_name)
                        if mu:
                            i_unit = mu
                    if not i_unit:
                        i_unit = "Pcs"

                    i_hsn = _clean_str(it.get("hsn_code") or it.get("hsnCode") or it.get("hsn"))
                    if not i_hsn:
                        mh = _lookup_item_master_hsn(company_name, i_name)
                        if mh:
                            i_hsn = mh

                    i_godown = _clean_str(
                        it.get("godown")
                        or it.get("godownName")
                        or it.get("godown_name")
                        or it.get("sourceGodown")
                        or it.get("destinationGodown")
                        or it.get("fromGodown")
                        or it.get("toGodown")
                    )

                    await self.ensure_stock_item(
                        host=host, port=port, company_name=company_name, item_name=i_name, unit_name=i_unit, hsn_code=i_hsn, godown=i_godown
                    )

        if not is_pure_inventory:
            if "credit note" in v_type or "sales return" in v_type:
                cn_ledger = _clean_str(
                    voucher_data.get("credit_note_ledger")
                    or voucher_data.get("sales_return_ledger")
                    or voucher_data.get("creditNoteLedger")
                    or voucher_data.get("salesReturnLedger")
                    or "Sales Return"
                )
                await self.ensure_ledger(
                    host=host,
                    port=port,
                    company_name=company_name,
                    ledger_name=cn_ledger,
                    parent="Sales Accounts"
                )
                for itm in voucher_data.get("items") or []:
                    if isinstance(itm, dict):
                        i_cn = _clean_str(
                            itm.get("credit_note_ledger")
                            or itm.get("sales_return_ledger")
                            or itm.get("creditNoteLedger")
                            or itm.get("salesReturnLedger")
                        )
                        if i_cn:
                            await self.ensure_ledger(
                                host=host,
                                port=port,
                                company_name=company_name,
                                ledger_name=i_cn,
                                parent="Sales Accounts"
                            )
            elif "debit note" in v_type or "purchase return" in v_type:
                dn_ledger = _clean_str(
                    voucher_data.get("debit_note_ledger")
                    or voucher_data.get("purchase_return_ledger")
                    or voucher_data.get("debitNoteLedger")
                    or voucher_data.get("purchaseReturnLedger")
                    or "Purchase Return"
                )
                await self.ensure_ledger(
                    host=host,
                    port=port,
                    company_name=company_name,
                    ledger_name=dn_ledger,
                    parent="Purchase Accounts"
                )
                for itm in voucher_data.get("items") or []:
                    if isinstance(itm, dict):
                        i_dn = _clean_str(
                            itm.get("debit_note_ledger")
                            or itm.get("purchase_return_ledger")
                            or itm.get("debitNoteLedger")
                            or itm.get("purchaseReturnLedger")
                        )
                        if i_dn:
                            await self.ensure_ledger(
                                host=host,
                                port=port,
                                company_name=company_name,
                                ledger_name=i_dn,
                                parent="Purchase Accounts"
                            )
            elif "sales" in v_type or "quotation" in v_type or "quote" in v_type:
                sales_ledger = _clean_str(voucher_data.get("sales_ledger") or voucher_data.get("salesLedger") or "Sales")
                await self.ensure_ledger(
                    host=host,
                    port=port,
                    company_name=company_name,
                    ledger_name=sales_ledger,
                    parent="Sales Accounts"
                )
            elif "purchase" in v_type:
                purchase_ledger = _clean_str(voucher_data.get("purchase_ledger") or voucher_data.get("purchaseLedger") or "Purchase")
                await self.ensure_ledger(
                    host=host,
                    port=port,
                    company_name=company_name,
                    ledger_name=purchase_ledger,
                    parent="Purchase Accounts"
                )
            elif "receipt" in v_type or "payment" in v_type:
                bank_ledger = _clean_str(
                    voucher_data.get("bank_ledger")
                    or voucher_data.get("bankLedger")
                    or voucher_data.get("cash_bank_ledger")
                    or voucher_data.get("account")
                    or voucher_data.get("bank_account")
                    or "Cash"
                )
                if bank_ledger.lower() not in ("cash",):
                    bank_parent = voucher_data.get("bank_parent") or voucher_data.get("bankParent") or "Bank Accounts"
                    await self.ensure_ledger(
                        host=host,
                        port=port,
                        company_name=company_name,
                        ledger_name=bank_ledger,
                        parent=bank_parent
                    )

        xml_payload = build_voucher_import_xml(voucher_data)

        if not is_pure_inventory:
            for tax in voucher_data.get("_calculated_tax_entries", []):
                tax_name = tax.get("name")
                if tax_name:
                    await self.ensure_ledger(
                        host=host,
                        port=port,
                        company_name=company_name,
                        ledger_name=tax_name,
                        parent="Duties & Taxes"
                    )

            if voucher_data.get("_has_round_off"):
                await self.ensure_ledger(
                    host=host,
                    port=port,
                    company_name=company_name,
                    ledger_name="Round Off",
                    parent="Indirect Expenses"
                )

        ok, status_code, res_text, err_msg = await self.client.send_xml_request_async(
            host=host, port=port, xml_content=xml_payload, serialize_company=company_name
        )
        

        if not ok or status_code != 200:
            return {
                "success": False,
                "voucher_number": None,
                "message": "Failed to post voucher XML to Tally Prime HTTP interface.",
                "error": err_msg or f"HTTP status code {status_code}",
            }

        success, v_num, parse_err = parse_tally_import_response(
            res_text, default_voucher_number=voucher_data.get("voucher_number") or voucher_data.get("_generated_voucher_number")
        )

        if not success:
            logger.warning(f"Tally Import Failed. Error: {parse_err}. Response:\n{res_text}\nPayload Sent:\n{xml_payload}")
            diagnostic = diagnose_voucher_rejection(voucher_data, res_text, parse_err or "")
            is_company_err = "svcurrentcompany" in str(parse_err or "").lower() or "svcurrentcompany" in str(res_text or "").lower()
            return {
                "success": False,
                "should_queue": is_company_err,
                "status": "COMPANY_NOT_LOADED" if is_company_err else "FAILED",
                "voucher_number": None,
                "message": "Tally Prime rejected the voucher import.",
                "error": parse_err,
                "reason": diagnostic.get("reason"),
                "action": diagnostic.get("action"),
                "diagnostic": diagnostic,
            }

        v_date = voucher_data.get("date") or voucher_data.get("voucher_date") or ""
        v_guid = await self.fetch_voucher_guid(host, port, company_name, str(v_num), voucher_date=str(v_date)) if v_num else None
        return {
            "success": True,
            "voucher_number": v_num,
            "amount": float(voucher_data.get("amount", 0.0)),
            "company_name": company_name or voucher_data.get("company_name", ""),
            "message": f"Voucher '{v_num}' successfully created in Tally Prime.",
            "error": None,
            "tallyExternalId": v_guid or v_num,
            "guid": v_guid or v_num,
        }
