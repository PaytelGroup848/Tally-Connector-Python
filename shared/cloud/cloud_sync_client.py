import httpx
from typing import Dict, Any, Optional, Tuple, List
from shared.logging_config import get_logger
from shared.cloud.helpers import (
    _safe_get_collection,
    format_tally_date,
    classify_ledger_type,
)

logger = get_logger("app.cloud.sync_client")


class CloudSyncClient:
    """Handles cloud batch sync streaming operations (sync/start, sync/batch, sync/complete)."""

    def __init__(self, auth_service):
        self.auth = auth_service

    @property
    def base_url(self) -> str:
        return self.auth.base_url

    @property
    def access_token(self) -> Optional[str]:
        return self.auth.access_token

    @property
    def refresh_token_val(self) -> Optional[str]:
        return self.auth.refresh_token_val

    @property
    def _device_id(self) -> str:
        return self.auth._device_id

    def _get_client(self, timeout: float = 30.0) -> httpx.Client:
        return self.auth._get_client(timeout)

    def refresh_token(self):
        return self.auth.refresh_token()

    def get_cloud_companies(self):
        return self.auth.get_cloud_companies()

    def link_company(self, company_name: str, company_guid: str = ""):
        return self.auth.link_company(company_name, company_guid)

    def _extract_error_message(self, res: httpx.Response, data: Dict[str, Any], default_msg: str) -> str:
        return self.auth._extract_error_message(res, data, default_msg)

    def sync_start(
        self,
        company_name: str,
        company_guid: str = "",
        sync_type: str = "INCREMENTAL",
        total_records: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
        company_id: Optional[str] = None
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """Calls Cloud Sync Start endpoint (/sync/start)."""
        if not self.access_token:
            return False, "Not authenticated. Please login first.", {}

        target_cid = company_id
        if not target_cid or len(str(target_cid)) < 12:
            ok_c, c_list = self.get_cloud_companies()
            if ok_c and c_list:
                for c in c_list:
                    c_n = c.get("tallyCompanyName") or c.get("companyName") or c.get("name") or ""
                    if c_n.strip().lower() == company_name.strip().lower():
                        target_cid = c.get("id") or c.get("_id")
                        break

        if not target_cid or len(str(target_cid)) < 12:
            link_ok, _, link_data = self.link_company(company_name, company_guid)
            if link_ok and link_data:
                target_cid = link_data.get("id") or link_data.get("_id")

        if not target_cid:
            target_cid = company_guid or company_name

        if target_cid and len(str(target_cid)) >= 8:
            try:
                col = _safe_get_collection("companies")
                if col is not None:
                    col.update_one(
                        {"$or": [{"company_name": company_name}, {"name": company_name}, {"tallyCompanyName": company_name}]},
                        {"$set": {"cloud_company_id": str(target_cid)}},
                        upsert=True
                    )
            except Exception:
                pass

        s_type = "INITIAL" if sync_type.upper() in ("INITIAL", "FULL") else "INCREMENTAL"

        url = f"{self.base_url}/sync/start"
        headers = {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}
        payload = {
            "companyId": str(target_cid),
            "type": s_type
        }
        logger.info(f"Calling Cloud Sync Start for '{company_name}' ({s_type}, companyId: {target_cid})")

        try:
            client = self._get_client(15.0)
            res = client.post(url, json=payload, headers=headers)
            data = res.json() if res.text else {}

            if res.status_code == 401 and self.refresh_token_val:
                refreshed, _ = self.refresh_token()
                if refreshed and self.access_token:
                    headers["Authorization"] = f"Bearer {self.access_token}"
                    res = client.post(url, json=payload, headers=headers)
                    data = res.json() if res.text else {}

            if res.status_code == 200 or data.get("success") is True:
                resp_data = data.get("data") or data
                msg = data.get("message", "Cloud sync session started successfully.")
                return True, msg, resp_data
            else:
                err_msg = self._extract_error_message(res, data, "Failed to start sync session")
                logger.warning(f"Cloud sync/start HTTP {res.status_code}: {err_msg}")
                return False, err_msg, {}
        except Exception as exc:
            logger.error(f"Error calling sync/start: {exc}")
            return False, f"Connection error starting sync session: {exc}", {}

    def sync_batch(
        self,
        sync_id: str,
        company_name: str,
        entity_type: str,
        items: list[Dict[str, Any]],
        batch_number: int = 1,
        is_last_batch: bool = False
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """Calls Cloud Sync Batch endpoint (/sync/batch)."""
        if not self.access_token:
            return False, "Not authenticated. Please login first.", {}

        url = f"{self.base_url}/sync/batch"
        headers = {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}
        
        u_type = str(entity_type).upper()
        if "LEDGER" in u_type:
            norm_entity = "LEDGER"
        elif "STOCK" in u_type:
            norm_entity = "STOCK"
        elif "SUPPLIER" in u_type or "VENDOR" in u_type:
            norm_entity = "SUPPLIER"
        elif "CUSTOMER" in u_type:
            norm_entity = "CUSTOMER"
        else:
            norm_entity = "VOUCHER"

        records_to_send = []
        if norm_entity == "STOCK":
            for r in items:
                if not isinstance(r, dict):
                    continue
                t_ext_id = r.get("tallyExternalId") or r.get("guid") or r.get("name") or ""
                item_name = r.get("itemName") or r.get("name") or ""
                item_ext_id = r.get("itemTallyExternalId") or r.get("guid") or t_ext_id
                godown_val = r.get("godown") or "Main Location"
                parent_val = str(r.get("parent") or r.get("group") or "")
                group_val = str(r.get("group") or r.get("parent") or parent_val)
                cat_val = str(r.get("category") or "")

                try:
                    qty = float(r.get("quantity", 0.0) or r.get("closingBalance", 0.0) or 0.0)
                except (ValueError, TypeError):
                    qty = 0.0
                try:
                    rate = float(r.get("rate", 0.0) or r.get("closingRate", 0.0) or 0.0)
                except (ValueError, TypeError):
                    rate = 0.0
                try:
                    val = float(r.get("value", 0.0) or r.get("closingValue", 0.0) or 0.0)
                except (ValueError, TypeError):
                    val = 0.0
                if val == 0.0 and qty != 0.0 and rate != 0.0:
                    val = round(qty * rate, 2)

                try:
                    op_qty = float(r.get("openingBalance", 0.0) or 0.0)
                except (ValueError, TypeError):
                    op_qty = 0.0
                try:
                    op_rate = float(r.get("openingRate", 0.0) or 0.0)
                except (ValueError, TypeError):
                    op_rate = 0.0
                try:
                    op_val = float(r.get("openingValue", 0.0) or 0.0)
                except (ValueError, TypeError):
                    op_val = 0.0

                try:
                    gst_rate_val = float(r.get("gstRate") or r.get("gst_rate") or r.get("taxRate") or r.get("tax_rate") or 0.0)
                except (ValueError, TypeError):
                    gst_rate_val = 0.0

                taxability_val = str(r.get("taxability") or ("Taxable" if gst_rate_val > 0 else "Exempt"))
                unit_val = str(r.get("unit") or r.get("uom") or r.get("units") or r.get("unit_name") or r.get("baseUnits") or r.get("base_units") or "").strip()
                if not unit_val:
                    unit_val = "Pcs"
                hsn_val = str(r.get("hsnCode") or r.get("hsn_code") or r.get("hsn") or "").strip()
                batch_val = str(r.get("batch") or r.get("batchName") or r.get("batch_name") or "Primary Batch").strip()

                records_to_send.append({
                    "tallyExternalId": str(t_ext_id),
                    "itemName": str(item_name),
                    "name": str(item_name),
                    "itemTallyExternalId": str(item_ext_id),
                    "parent": parent_val,
                    "group": group_val,
                    "category": cat_val,
                    "godown": str(godown_val),
                    "batch": str(batch_val),
                    "quantity": qty,
                    "rate": rate,
                    "value": val,
                    "openingBalance": op_qty,
                    "openingRate": op_rate,
                    "openingValue": op_val,
                    "closingBalance": qty,
                    "closingRate": rate,
                    "closingValue": val,
                    "unit": unit_val,
                    "units": unit_val,
                    "uom": unit_val,
                    "unit_name": unit_val,
                    "baseUnits": unit_val,
                    "base_units": unit_val,
                    "unit_details": r.get("unit_details") or {},
                    "hsnCode": hsn_val,
                    "hsn_code": hsn_val,
                    "hsn": hsn_val,
                    "gstRate": gst_rate_val,
                    "gst_rate": gst_rate_val,
                    "taxRate": gst_rate_val,
                    "tax_rate": gst_rate_val,
                    "taxability": taxability_val,
                    "gstApplicable": str(r.get("gstApplicable") or "Applicable"),
                    "reorderLevel": str(r.get("reorderLevel") or "0"),
                    "alternateUnit": str(r.get("alternateUnit") or ""),
                })
        elif norm_entity == "CUSTOMER":
            for r in items:
                if not isinstance(r, dict):
                    continue
                raw_val = r.get("raw")
                raw_dict: Dict[str, Any] = dict(raw_val) if isinstance(raw_val, dict) else {}
                t_ext_id = r.get("tallyExternalId") or r.get("guid") or r.get("name") or raw_dict.get("guid") or ""
                name_val = r.get("name") or raw_dict.get("name") or ""
                parent_val = r.get("parent") or raw_dict.get("parent") or "Sundry Debtors"
                group_val = r.get("group") or raw_dict.get("group") or parent_val
                gstin_val = r.get("gstin") or raw_dict.get("gstin") or raw_dict.get("partygstin") or ""
                email_val = r.get("email") or raw_dict.get("email") or ""
                phone_val = r.get("phone") or raw_dict.get("phone") or raw_dict.get("mobile") or ""
                address_val = r.get("address") or raw_dict.get("address") or ""
                state_val = r.get("state") or raw_dict.get("state") or ""
                country_val = r.get("country") or raw_dict.get("country") or "India"
                pincode_val = r.get("pincode") or raw_dict.get("pincode") or ""
                reg_type_val = r.get("registration_type") or raw_dict.get("registration_type") or ""
                pan_val = r.get("pan") or raw_dict.get("pan") or raw_dict.get("incometaxnumber") or ""
                credit_limit_val = float(r.get("creditLimit", 0.0) or raw_dict.get("creditLimit", 0.0) or 0.0)
                credit_days_val = int(r.get("creditDays", 0) or raw_dict.get("creditDays", 0) or 0)
                credit_period_val = str(r.get("creditPeriod") or raw_dict.get("creditPeriod") or raw_dict.get("billCreditPeriod") or "")
                alt_id = int(r.get("alter_id", 0) or r.get("alterId", 0) or raw_dict.get("alterid", 0) or 0)
                try:
                    op_bal = float(r.get("openingBalance", 0.0) or raw_dict.get("openingbalance", 0.0) or 0.0)
                except (ValueError, TypeError):
                    op_bal = 0.0
                try:
                    c_bal = float(r.get("closingBalance", 0.0) or raw_dict.get("closingbalance", 0.0) or 0.0)
                except (ValueError, TypeError):
                    c_bal = 0.0

                records_to_send.append({
                    "tallyExternalId": str(t_ext_id),
                    "name": str(name_val),
                    "parent": str(parent_val),
                    "group": str(group_val),
                    "ledgerType": "CUSTOMER",
                    "gstin": str(gstin_val) if gstin_val else None,
                    "pan": str(pan_val),
                    "email": str(email_val),
                    "phone": str(phone_val),
                    "address": str(address_val),
                    "state": str(state_val),
                    "country": str(country_val),
                    "pincode": str(pincode_val),
                    "registration_type": str(reg_type_val),
                    "creditLimit": credit_limit_val,
                    "creditDays": credit_days_val,
                    "creditPeriod": credit_period_val,
                    "billCreditPeriod": credit_period_val,
                    "openingBalance": op_bal,
                    "closingBalance": c_bal,
                    "alterId": alt_id
                })
        elif norm_entity == "SUPPLIER":
            for r in items:
                if not isinstance(r, dict):
                    continue
                raw_val = r.get("raw")
                raw_dict: Dict[str, Any] = dict(raw_val) if isinstance(raw_val, dict) else {}
                t_ext_id = r.get("tallyExternalId") or r.get("guid") or r.get("name") or raw_dict.get("guid") or ""
                name_val = r.get("name") or raw_dict.get("name") or ""
                parent_val = r.get("parent") or raw_dict.get("parent") or "Sundry Creditors"
                group_val = r.get("group") or raw_dict.get("group") or parent_val
                gstin_val = r.get("gstin") or raw_dict.get("gstin") or raw_dict.get("partygstin") or ""
                email_val = r.get("email") or raw_dict.get("email") or ""
                phone_val = r.get("phone") or raw_dict.get("phone") or raw_dict.get("mobile") or ""
                address_val = r.get("address") or raw_dict.get("address") or ""
                state_val = r.get("state") or raw_dict.get("state") or ""
                country_val = r.get("country") or raw_dict.get("country") or "India"
                pincode_val = r.get("pincode") or raw_dict.get("pincode") or ""
                reg_type_val = r.get("registration_type") or raw_dict.get("registration_type") or ""
                pan_val = r.get("pan") or raw_dict.get("pan") or raw_dict.get("incometaxnumber") or ""
                credit_limit_val = float(r.get("creditLimit", 0.0) or raw_dict.get("creditLimit", 0.0) or 0.0)
                credit_days_val = int(r.get("creditDays", 0) or raw_dict.get("creditDays", 0) or 0)
                credit_period_val = str(r.get("creditPeriod") or raw_dict.get("creditPeriod") or raw_dict.get("billCreditPeriod") or "")
                alt_id = int(r.get("alter_id", 0) or r.get("alterId", 0) or raw_dict.get("alterid", 0) or 0)
                try:
                    op_bal = float(r.get("openingBalance", 0.0) or raw_dict.get("openingbalance", 0.0) or 0.0)
                except (ValueError, TypeError):
                    op_bal = 0.0
                try:
                    c_bal = float(r.get("closingBalance", 0.0) or raw_dict.get("closingbalance", 0.0) or 0.0)
                except (ValueError, TypeError):
                    c_bal = 0.0

                records_to_send.append({
                    "tallyExternalId": str(t_ext_id),
                    "name": str(name_val),
                    "parent": str(parent_val),
                    "group": str(group_val),
                    "ledgerType": "LIABILITY",
                    "gstin": str(gstin_val) if gstin_val else None,
                    "pan": str(pan_val),
                    "email": str(email_val),
                    "phone": str(phone_val),
                    "address": str(address_val),
                    "state": str(state_val),
                    "country": str(country_val),
                    "pincode": str(pincode_val),
                    "registration_type": str(reg_type_val),
                    "creditLimit": credit_limit_val,
                    "creditDays": credit_days_val,
                    "creditPeriod": credit_period_val,
                    "billCreditPeriod": credit_period_val,
                    "openingBalance": op_bal,
                    "closingBalance": c_bal,
                    "alterId": alt_id
                })
        elif norm_entity == "LEDGER":
            for r in items:
                if not isinstance(r, dict):
                    continue
                raw_val = r.get("raw")
                raw_dict: Dict[str, Any] = dict(raw_val) if isinstance(raw_val, dict) else {}
                
                c_bal = r.get("closingBalance")
                if c_bal is None:
                    c_bal = r.get("closing_balance")
                if c_bal is None:
                    c_bal = raw_dict.get("closing_balance", raw_dict.get("closingbalance"))
                if c_bal is None:
                    c_bal = 0.0

                op_bal = r.get("openingBalance")
                if op_bal is None:
                    op_bal = r.get("opening_balance")
                if op_bal is None:
                    op_bal = raw_dict.get("opening_balance", raw_dict.get("openingbalance", 0.0))
                if op_bal is None:
                    op_bal = 0.0

                parent_val = r.get("parent") or raw_dict.get("parent") or ""
                group_val = r.get("group") or parent_val
                raw_ltype = r.get("ledgerType") or r.get("ledger_type") or raw_dict.get("ledger_type") or raw_dict.get("ledgerclassification")
                comp_ltype = classify_ledger_type(parent_val, raw_ltype)

                gstin_val = r.get("gstin") or raw_dict.get("gstin") or raw_dict.get("partygstin")
                t_ext_id = r.get("tallyExternalId") or r.get("guid") or raw_dict.get("guid") or r.get("name") or raw_dict.get("name") or ""
                name_val = r.get("name") or raw_dict.get("name") or ""

                email_val = r.get("email") or raw_dict.get("email") or ""
                phone_val = r.get("phone") or raw_dict.get("phone") or raw_dict.get("mobile") or ""
                address_val = r.get("address") or raw_dict.get("address") or ""
                state_val = r.get("state") or raw_dict.get("state") or ""
                country_val = r.get("country") or raw_dict.get("country") or "India"
                pincode_val = r.get("pincode") or raw_dict.get("pincode") or ""
                reg_type_val = r.get("registration_type") or raw_dict.get("registration_type") or ""
                pan_val = r.get("pan") or raw_dict.get("pan") or raw_dict.get("incometaxnumber") or ""
                credit_limit_val = float(r.get("creditLimit", 0.0) or raw_dict.get("creditLimit", 0.0) or 0.0)
                credit_days_val = int(r.get("creditDays", 0) or raw_dict.get("creditDays", 0) or 0)
                credit_period_val = str(r.get("creditPeriod") or raw_dict.get("creditPeriod") or raw_dict.get("billCreditPeriod") or "")
                alt_id = int(r.get("alter_id", 0) or r.get("alterId", 0) or raw_dict.get("alterid", 0) or 0)

                records_to_send.append({
                    "tallyExternalId": str(t_ext_id),
                    "name": str(name_val),
                    "parent": str(parent_val),
                    "group": str(group_val),
                    "ledgerType": comp_ltype,
                    "openingBalance": float(op_bal),
                    "closingBalance": float(c_bal),
                    "gstin": str(gstin_val) if gstin_val else None,
                    "pan": str(pan_val),
                    "email": str(email_val),
                    "phone": str(phone_val),
                    "address": str(address_val),
                    "state": str(state_val),
                    "country": str(country_val),
                    "pincode": str(pincode_val),
                    "registration_type": str(reg_type_val),
                    "creditLimit": credit_limit_val,
                    "creditDays": credit_days_val,
                    "creditPeriod": credit_period_val,
                    "billCreditPeriod": credit_period_val,
                    "alterId": alt_id
                })
        elif norm_entity == "VOUCHER":
            for r in items:
                if not isinstance(r, dict):
                    continue
                raw_val = r.get("raw")
                raw_dict: Dict[str, Any] = dict(raw_val) if isinstance(raw_val, dict) else {}
                
                v_num = str(r.get("voucherNumber") or r.get("voucher_number") or raw_dict.get("name") or raw_dict.get("vouchernumber") or "")
                v_type = str(r.get("voucherType") or r.get("voucher_type") or raw_dict.get("parent") or raw_dict.get("vouchertypename") or "Sales")
                v_party = str(r.get("partyLedger") or r.get("party_ledger") or raw_dict.get("party") or raw_dict.get("partyledgername") or "Cash")
                
                raw_amt = r.get("amount")
                if raw_amt is None:
                    raw_amt = raw_dict.get("amount", raw_dict.get("closing_balance", raw_dict.get("closingbalance", 0.0)))
                try:
                    amt_val = abs(float(raw_amt)) if raw_amt is not None else 0.0
                except (ValueError, TypeError):
                    amt_val = 0.0

                d_val = r.get("date") or raw_dict.get("date") or r.get("effectiveDate")
                formatted_date = format_tally_date(d_val) or "2023-04-01"
                v_narr = str(r.get("narration") or raw_dict.get("narration") or "")
                t_ext_id = str(r.get("voucherId") or r.get("tallyExternalId") or r.get("guid") or raw_dict.get("guid") or v_num)

                adv_settings = r.get("advancedSettings") or raw_dict.get("advancedSettings") or {}
                ref_num = str(r.get("reference") or raw_dict.get("reference") or "")
                ref_date = str(r.get("referenceDate") or raw_dict.get("referenceDate") or formatted_date)
                pos_val = str(r.get("placeOfSupply") or raw_dict.get("placeOfSupply") or "")
                cust_name = str(r.get("customerName") or r.get("customer") or v_party)
                inv_items = r.get("items") or r.get("inventoryEntries") or []
                ledger_lines = r.get("lines") or r.get("ledgerEntries") or []
                bills = r.get("billAllocations") or []
                banks = r.get("bankAllocations") or []

                dispatch_doc_no = str(adv_settings.get("dispatchDocNo") or r.get("dispatchDocNo") or raw_dict.get("dispatchDocNo") or "")
                dispatched_through = str(adv_settings.get("dispatchedThrough") or r.get("dispatchedThrough") or raw_dict.get("dispatchedThrough") or "")
                destination = str(adv_settings.get("destination") or r.get("destination") or raw_dict.get("destination") or "")
                vehicle_no = str(adv_settings.get("vehicleNo") or adv_settings.get("carrier") or r.get("vehicleNo") or raw_dict.get("vehicleNo") or "")
                order_no = str(adv_settings.get("orderNo") or r.get("orderNo") or raw_dict.get("orderNo") or "")
                order_date = str(adv_settings.get("orderDate") or r.get("orderDate") or raw_dict.get("orderDate") or "")
                terms_val = str(adv_settings.get("terms") or r.get("terms") or raw_dict.get("terms") or "")
                consignee_name = str(adv_settings.get("consigneeName") or r.get("consigneeName") or raw_dict.get("consigneeName") or "")
                consignee_address = str(adv_settings.get("consigneeAddress") or r.get("consigneeAddress") or raw_dict.get("consigneeAddress") or "")
                consignee_state = str(adv_settings.get("consigneeState") or r.get("consigneeState") or raw_dict.get("consigneeState") or "")
                consignee_country = str(adv_settings.get("consigneeCountry") or r.get("consigneeCountry") or raw_dict.get("consigneeCountry") or "")
                consignee_pincode = str(adv_settings.get("consigneePincode") or r.get("consigneePincode") or raw_dict.get("consigneePincode") or "")
                consignee_gstin = str(adv_settings.get("consigneeGstin") or r.get("consigneeGstin") or raw_dict.get("consigneeGstin") or "")

                clean_adv_settings = {
                    "dispatchDocNo": dispatch_doc_no,
                    "dispatchedThrough": dispatched_through,
                    "destination": destination,
                    "carrier": vehicle_no,
                    "vehicleNo": vehicle_no,
                    "orderNo": order_no,
                    "orderDate": order_date,
                    "terms": terms_val,
                    "consigneeName": consignee_name,
                    "consigneeAddress": consignee_address,
                    "consigneeState": consignee_state,
                    "consigneeCountry": consignee_country,
                    "consigneePincode": consignee_pincode,
                    "consigneeGstin": consignee_gstin,
                }

                raw_obj = {
                    "voucherId": str(t_ext_id),
                    "tallyExternalId": str(t_ext_id),
                    "name": str(raw_dict.get("name") or v_num),
                    "voucherNumber": str(v_num),
                    "parent": str(raw_dict.get("parent") or v_type),
                    "voucherType": str(v_type),
                    "party": str(raw_dict.get("party") or v_party),
                    "partyLedger": str(v_party),
                    "customerName": str(cust_name),
                    "customer": str(cust_name),
                    "date": str(formatted_date),
                    "reference": str(ref_num),
                    "referenceDate": str(ref_date),
                    "placeOfSupply": str(pos_val),
                    "amount": float(amt_val),
                    "narration": str(v_narr),
                    "items": inv_items,
                    "lines": ledger_lines,
                    "inventoryEntries": inv_items,
                    "ledgerEntries": ledger_lines,
                    "billAllocations": bills,
                    "bankAllocations": banks,
                    "advancedSettings": clean_adv_settings,
                    "dispatchDetails": {
                        "dispatchDocNo": dispatch_doc_no,
                        "dispatchedThrough": dispatched_through,
                        "destination": destination,
                        "vehicleNo": vehicle_no,
                    },
                    "orderDetails": {
                        "orderNo": order_no,
                        "orderDate": order_date,
                        "terms": terms_val,
                    },
                    "consigneeDetails": {
                        "consigneeName": consignee_name,
                        "consigneeAddress": consignee_address,
                        "consigneeState": consignee_state,
                        "consigneeGstin": consignee_gstin,
                    },
                    "alterid": int(raw_dict.get("alterid") or r.get("alter_id") or r.get("alterId") or 0)
                }

                records_to_send.append({
                    "voucherId": str(t_ext_id),
                    "tallyExternalId": str(t_ext_id),
                    "voucherNumber": str(v_num),
                    "voucherType": str(v_type),
                    "date": str(formatted_date),
                    "amount": float(amt_val),
                    "partyLedger": str(v_party),
                    "customerName": str(cust_name),
                    "customer": str(cust_name),
                    "partyName": str(v_party),
                    "reference": str(ref_num),
                    "referenceDate": str(ref_date),
                    "placeOfSupply": str(pos_val),
                    "narration": str(v_narr),
                    "lines": ledger_lines,
                    "items": inv_items,
                    "inventoryEntries": inv_items,
                    "ledgerEntries": ledger_lines,
                    "billAllocations": bills,
                    "bankAllocations": banks,
                    "advancedSettings": clean_adv_settings,
                    "dispatchDocNo": dispatch_doc_no,
                    "dispatchedThrough": dispatched_through,
                    "destination": destination,
                    "carrier": vehicle_no,
                    "vehicleNo": vehicle_no,
                    "orderNo": order_no,
                    "orderDate": order_date,
                    "terms": terms_val,
                    "consigneeName": consignee_name,
                    "consigneeAddress": consignee_address,
                    "consigneeState": consignee_state,
                    "consigneeGstin": consignee_gstin,
                    "raw": raw_obj
                })
        else:
            records_to_send = items

        payload = {
            "syncJobId": sync_id,
            "batchNumber": batch_number,
            "entityType": norm_entity,
            "records": records_to_send,
            "isLastBatch": is_last_batch
        }
        logger.info(f"Calling Cloud Sync Batch #{batch_number} for '{company_name}' ({norm_entity}: {len(records_to_send)} items)")

        try:
            client = self._get_client(30.0)
            res = client.post(url, json=payload, headers=headers)
            data = res.json() if res.text else {}

            if res.status_code == 401 and self.refresh_token_val:
                refreshed, _ = self.refresh_token()
                if refreshed and self.access_token:
                    headers["Authorization"] = f"Bearer {self.access_token}"
                    res = client.post(url, json=payload, headers=headers)
                    data = res.json() if res.text else {}

            if res.status_code == 200 or data.get("success") is True:
                resp_data = data.get("data") or data
                msg = data.get("message", f"Batch #{batch_number} synced successfully.")
                return True, msg, resp_data
            else:
                err_msg = self._extract_error_message(res, data, f"Failed to sync batch #{batch_number}")
                logger.warning(f"Cloud sync/batch HTTP {res.status_code}: {err_msg}")
                return False, err_msg, {}
        except Exception as exc:
            return False, f"Connection error sending sync batch: {exc}", {}


    def sync_complete(
        self,
        sync_id: str,
        company_name: str = "",
        status: str = "COMPLETED",
        total_synced: int = 0,
        last_alter_id: int = 0,
        summary: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """Calls Cloud Sync Complete endpoint (/sync/complete)."""
        if not self.access_token:
            return False, "Not authenticated. Please login first.", {}

        url = f"{self.base_url}/sync/complete"
        headers = {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}
        payload = {
            "syncJobId": sync_id,
            "status": status.upper()
        }
        logger.info(f"Calling Cloud Sync Complete for '{company_name}' (Status: {status})")

        try:
            client = self._get_client(15.0)
            res = client.post(url, json=payload, headers=headers)
            data = res.json() if res.text else {}

            if res.status_code == 401 and self.refresh_token_val:
                refreshed, _ = self.refresh_token()
                if refreshed and self.access_token:
                    headers["Authorization"] = f"Bearer {self.access_token}"
                    res = client.post(url, json=payload, headers=headers)
                    data = res.json() if res.text else {}

            if res.status_code == 200 or data.get("success") is True:
                resp_data = data.get("data") or data
                msg = data.get("message", "Cloud sync session completed successfully.")
                return True, msg, resp_data
            else:
                err_msg = self._extract_error_message(res, data, "Failed to complete sync session")
                logger.warning(f"Cloud sync/complete HTTP {res.status_code}: {err_msg}")
                return False, err_msg, {}
        except Exception as exc:
            logger.error(f"Error calling sync/complete: {exc}")
            return False, f"Connection error completing sync session: {exc}", {}


