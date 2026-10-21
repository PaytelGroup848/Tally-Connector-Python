import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, Tuple, Optional
from shared.logging_config import get_logger
from shared.db.mongo_client import get_collection

logger = get_logger("app.threads.command_handlers.party")


def execute_party_command(
    payload: Dict[str, Any],
    cmd: Dict[str, Any],
    cmd_id: str,
    cmd_type: str,
    comp_id: Optional[str],
    resolved_company: str,
    active_host: str,
    active_port: int,
    importer_service: Any,
) -> Tuple[Dict[str, Any], bool, Dict[str, Any], Optional[str], Dict[str, Any]]:
    """
    Normalizes party payload and invokes importer_service.create_ledger.
    Handles Sundry Debtors / Sundry Creditors, multi-key address, pincode, state, mobile,
    GSTIN, and updates local MongoDB collections.
    Returns: (norm_payload, success, result_data, error_msg, error_details)
    """
    norm_payload = dict(payload)
    norm_payload["target"] = "TALLY"
    norm_payload["host"] = active_host
    norm_payload["port"] = active_port
    norm_payload["tally_host"] = active_host
    norm_payload["tally_port"] = active_port
    norm_payload["companyId"] = cmd.get("companyId") or cmd.get("company_id") or payload.get("companyId") or comp_id
    norm_payload["company_name"] = norm_payload.get("companyName") or norm_payload.get("company_name") or resolved_company

    party_name = (
        norm_payload.get("partyName")
        or norm_payload.get("party_name")
        or norm_payload.get("name")
        or norm_payload.get("ledgerName")
        or norm_payload.get("ledger_name")
        or norm_payload.get("party_ledger")
        or norm_payload.get("customerName")
    )
    norm_payload["name"] = party_name
    norm_payload["party_ledger"] = party_name

    p_type = str(norm_payload.get("partyType") or norm_payload.get("party_type") or norm_payload.get("ledgerType") or norm_payload.get("ledger_type") or norm_payload.get("type") or "").strip().upper()
    if "SUPPLIER" in p_type or "VENDOR" in p_type or "CREDITOR" in p_type:
        default_parent = "Sundry Creditors"
        norm_payload["voucher_type"] = "Supplier Master"
    elif "BANK" in p_type:
        default_parent = "Bank Accounts"
        norm_payload["voucher_type"] = "Bank Master"
    else:
        default_parent = "Sundry Debtors"
        norm_payload["voucher_type"] = "Customer Master"

    norm_payload["parent"] = norm_payload.get("parent") or default_parent
    norm_payload["bankDetails"] = norm_payload.get("bankDetails") or norm_payload.get("bank_details")
    norm_payload["mobile"] = (
        norm_payload.get("contactNumber")
        or norm_payload.get("mobile")
        or norm_payload.get("phone")
        or norm_payload.get("mobile_number")
        or norm_payload.get("mobileNumber")
    )
    norm_payload["email"] = (
        norm_payload.get("email")
        or norm_payload.get("email_id")
        or norm_payload.get("party_email")
    )
    raw_op_bal = norm_payload.get("openingBalance") or norm_payload.get("opening_balance")
    try:
        op_bal = float(raw_op_bal) if raw_op_bal is not None else 0.0
    except (ValueError, TypeError):
        op_bal = 0.0
    norm_payload["opening_balance"] = op_bal
    norm_payload["amount"] = norm_payload["opening_balance"]
    norm_payload["gstin"] = (
        norm_payload.get("gstin")
        or norm_payload.get("party_gstin")
        or norm_payload.get("gstNumber")
        or norm_payload.get("gst_number")
        or norm_payload.get("gst")
        or norm_payload.get("taxNumber")
    )
    norm_payload["state"] = (
        norm_payload.get("state")
        or norm_payload.get("state_name")
        or norm_payload.get("stateName")
        or norm_payload.get("placeOfSupply")
        or norm_payload.get("place_of_supply")
    )
    norm_payload["country"] = norm_payload.get("country") or norm_payload.get("country_name") or norm_payload.get("countryName") or "India"
    norm_payload["pincode"] = (
        norm_payload.get("pincode")
        or norm_payload.get("pin")
        or norm_payload.get("pinCode")
        or norm_payload.get("postalCode")
        or norm_payload.get("postal_code")
        or norm_payload.get("zip")
        or norm_payload.get("zipCode")
        or norm_payload.get("zip_code")
        or norm_payload.get("pin_code")
    )
    norm_payload["address"] = (
        norm_payload.get("address")
        or norm_payload.get("postalAddress")
        or norm_payload.get("postal_address")
        or norm_payload.get("billingAddress")
        or norm_payload.get("billing_address")
        or norm_payload.get("party_address")
        or norm_payload.get("street")
        or norm_payload.get("addressLine1")
        or norm_payload.get("address_line1")
        or norm_payload.get("full_address")
        or norm_payload.get("fullAddress")
    )
    norm_payload["registration_type"] = (
        norm_payload.get("registration_type")
        or norm_payload.get("registrationType")
        or norm_payload.get("gst_registration_type")
        or norm_payload.get("gstRegistrationType")
        or norm_payload.get("gst_type")
    )

    logger.info(
        f"Party Creation Payload: Company='{norm_payload.get('company_name')}', "
        f"Name='{norm_payload.get('name')}', Parent='{norm_payload.get('parent')}', "
        f"Mobile='{norm_payload.get('mobile')}', GSTIN='{norm_payload.get('gstin')}', "
        f"State='{norm_payload.get('state')}', Pincode='{norm_payload.get('pincode')}', "
        f"Address='{norm_payload.get('address')}', "
        f"OpeningBalance={norm_payload.get('opening_balance')}"
    )

    success = False
    result_data = {}
    error_msg = None
    error_details = {}

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        res = loop.run_until_complete(importer_service.create_ledger(norm_payload))
        if res.get("status") == "SUCCESS" or res.get("already_exists") or (res.get("error") and "already exists" in str(res.get("error")).lower()):
            success = True
            ext_id = res.get("tallyExternalId") or res.get("guid") or f"TALLY-{norm_payload.get('name')}"
            result_data = {
                "ledgerName": norm_payload.get("name"),
                "partyName": norm_payload.get("name"),
                "tallyExternalId": ext_id,
                "guid": ext_id,
                "status": "SUCCESS",
                "already_exists": bool(res.get("already_exists"))
            }
            try:
                p_name = norm_payload.get("name")
                is_supp = "SUPPLIER" in p_type or "VENDOR" in p_type or "CREDITOR" in p_type
                col_names = ["suppliers", "ledgers"] if is_supp else ["customers", "ledgers"]
                for c_name in col_names:
                    c_col = get_collection(c_name)
                    q = {"name": p_name}
                    if comp_id:
                        q["companyId"] = comp_id
                    c_col.update_many(q, {"$set": {"tallyExternalId": ext_id, "updatedAt": datetime.now(timezone.utc)}})
            except Exception as m_err:
                logger.debug(f"Direct MongoDB party update notice: {m_err}")
        else:
            success = False
            error_msg = res.get("error") or res.get("message") or "Failed to create party/ledger in Tally."
            error_details = {
                "voucher_type": norm_payload["voucher_type"],
                "voucher_number": "N/A",
                "company": norm_payload.get("company_name") or resolved_company,
                "party": norm_payload.get("name") or "N/A",
                "amount": norm_payload["opening_balance"],
                "date": "N/A",
                "reason": error_msg,
                "action": "Check if party name already exists or if Tally Prime is accessible.",
                "technical_error": error_msg,
                "cmd_id": cmd_id,
                "cmd_type": cmd_type
            }
    finally:
        loop.close()

    return norm_payload, success, result_data, error_msg, error_details

