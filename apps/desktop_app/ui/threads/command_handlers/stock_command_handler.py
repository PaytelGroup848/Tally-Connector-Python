# pyright: reportArgumentType=false
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, Tuple, Optional
from shared.logging_config import get_logger
from shared.db.mongo_client import get_collection

logger = get_logger("app.threads.command_handlers.stock")


def execute_create_stock_item_command(
    payload: Dict[str, Any],
    cmd: Dict[str, Any],
    comp_id: Optional[str],
    resolved_company: str,
    active_host: str,
    active_port: int,
    importer_service: Any,
) -> Tuple[Dict[str, Any], bool, Dict[str, Any], Optional[str]]:
    """
    Handles CREATE_STOCK_ITEM / CREATE_ITEM remote commands.
    Returns: (norm_payload, success, result_data, error_msg)
    """
    norm_payload = dict(payload)
    norm_payload["target"] = "TALLY"
    norm_payload["host"] = active_host
    norm_payload["port"] = active_port
    norm_payload["tally_host"] = active_host
    norm_payload["tally_port"] = active_port
    norm_payload["companyId"] = comp_id or cmd.get("companyId") or cmd.get("company_id") or payload.get("companyId")
    norm_payload["company_name"] = resolved_company or norm_payload.get("companyName") or norm_payload.get("company_name")
    norm_payload["name"] = norm_payload.get("name") or norm_payload.get("itemName") or norm_payload.get("item_name")
    norm_payload["unit"] = norm_payload.get("unit") or norm_payload.get("units") or "Pcs"
    norm_payload["hsn_code"] = norm_payload.get("hsn_code") or norm_payload.get("hsnCode") or norm_payload.get("hsn", "")
    norm_payload["hsn_description"] = norm_payload.get("hsn_description") or norm_payload.get("hsn_desc") or norm_payload.get("description", "")
    norm_payload["gst_rate"] = (
        norm_payload.get("gst_rate")
        or norm_payload.get("gstRate")
        or norm_payload.get("tax_rate")
        or norm_payload.get("taxRate")
        or norm_payload.get("rate_of_vat")
    )
    norm_payload["quantity"] = (
        norm_payload.get("quantity")
        or norm_payload.get("qty")
        or norm_payload.get("opening_balance")
        or norm_payload.get("openingBalance")
        or 0.0
    )
    norm_payload["rate"] = (
        norm_payload.get("rate")
        or norm_payload.get("opening_rate")
        or norm_payload.get("openingRate")
        or 0.0
    )
    norm_payload["value"] = (
        norm_payload.get("value")
        or norm_payload.get("opening_value")
        or norm_payload.get("openingValue")
        or norm_payload.get("amount")
        or 0.0
    )
    norm_payload["godown"] = (
        norm_payload.get("godown")
        or norm_payload.get("godown_name")
        or norm_payload.get("godownName")
        or norm_payload.get("warehouse")
        or norm_payload.get("location")
        or ""
    )
    norm_payload["batch"] = (
        norm_payload.get("batch")
        or norm_payload.get("batch_name")
        or norm_payload.get("batchName")
        or norm_payload.get("batch_number")
        or norm_payload.get("batchNumber")
        or ""
    )

    success = False
    result_data = {}
    error_msg = None

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        res = loop.run_until_complete(importer_service.create_stock_item(norm_payload))
        if res.get("status") == "SUCCESS":
            success = True
            ext_id = res.get("tallyExternalId") or res.get("guid") or f"TALLY-{norm_payload.get('name')}"
            result_data = {
                "itemName": norm_payload.get("name"),
                "tallyExternalId": ext_id,
                "guid": ext_id,
                "status": "SUCCESS"
            }
            try:
                s_name = norm_payload.get("name")
                for c_name in ["stock_items", "items"]:
                    c_col = get_collection(c_name)
                    q = {"$or": [{"name": s_name}, {"itemName": s_name}]}
                    if comp_id:
                        q["companyId"] = comp_id
                    upd_doc = {
                        "tallyExternalId": ext_id,
                        "itemTallyExternalId": ext_id,
                        "updatedAt": datetime.now(timezone.utc),
                    }
                    if norm_payload.get("quantity"):
                        upd_doc["openingBalance"] = norm_payload.get("quantity")
                        upd_doc["closingBalance"] = norm_payload.get("quantity")
                    if norm_payload.get("rate"):
                        upd_doc["openingRate"] = norm_payload.get("rate")
                        upd_doc["closingRate"] = norm_payload.get("rate")
                    if norm_payload.get("value"):
                        upd_doc["openingValue"] = norm_payload.get("value")
                        upd_doc["closingValue"] = norm_payload.get("value")
                    c_col.update_many(q, {"$set": upd_doc})
            except Exception as m_err:
                logger.debug(f"Direct MongoDB stock item update notice: {m_err}")
        else:
            success = False
            error_msg = res.get("error") or res.get("message") or "Failed to create stock item in Tally."
    finally:
        loop.close()

    return norm_payload, success, result_data, error_msg


def execute_update_stock_item_command(
    payload: Dict[str, Any],
    comp_id: Optional[str],
    resolved_company: str,
    importer_service: Any,
) -> Tuple[Dict[str, Any], bool, Dict[str, Any], Optional[str]]:
    """
    Handles UPDATE_STOCK_ITEM / UPDATE_ITEM / ALTER_STOCK_ITEM remote commands.
    Returns: (norm_payload, success, result_data, error_msg)
    """
    norm_payload = dict(payload)
    norm_payload["target"] = "TALLY"
    norm_payload["companyId"] = comp_id
    norm_payload["company_name"] = resolved_company
    item_name = str(norm_payload.get("itemName") or norm_payload.get("name") or norm_payload.get("item_name") or "")
    norm_payload["name"] = item_name
    unit_val = str(norm_payload.get("unit") or norm_payload.get("units") or norm_payload.get("base_units") or "Pcs")
    norm_payload["unit"] = unit_val
    hsn_val = str(norm_payload.get("hsn_code") or norm_payload.get("hsnCode") or norm_payload.get("hsn") or "")
    norm_payload["hsn_code"] = hsn_val
    norm_payload["hsn_description"] = norm_payload.get("hsn_description") or norm_payload.get("hsn_desc") or norm_payload.get("description", "")
    norm_payload["gst_rate"] = (
        norm_payload.get("gst_rate")
        or norm_payload.get("gstRate")
        or norm_payload.get("tax_rate")
        or norm_payload.get("taxRate")
        or norm_payload.get("rate_of_vat")
    )
    t_ext_id = str(norm_payload.get("tallyExternalId") or norm_payload.get("guid") or norm_payload.get("itemTallyExternalId") or "")
    qty_val = float(norm_payload.get("quantity", 0.0) or norm_payload.get("closingBalance", 0.0) or norm_payload.get("opening_balance", 0.0) or norm_payload.get("openingBalance", 0.0) or 0.0)
    rate_val = float(norm_payload.get("rate", 0.0) or norm_payload.get("closingRate", 0.0) or norm_payload.get("opening_rate", 0.0) or norm_payload.get("openingRate", 0.0) or 0.0)
    value_val = float(norm_payload.get("value", 0.0) or norm_payload.get("closingValue", 0.0) or norm_payload.get("opening_value", 0.0) or norm_payload.get("openingValue", 0.0) or (qty_val * rate_val))
    godown_val = str(norm_payload.get("godown") or norm_payload.get("godown_name") or norm_payload.get("godownName") or norm_payload.get("warehouse") or norm_payload.get("location") or "")
    batch_val = str(norm_payload.get("batch") or norm_payload.get("batch_name") or norm_payload.get("batchName") or norm_payload.get("batch_number") or norm_payload.get("batchNumber") or "")
    norm_payload["quantity"] = qty_val
    norm_payload["rate"] = rate_val
    norm_payload["value"] = value_val
    norm_payload["godown"] = godown_val
    norm_payload["batch"] = batch_val

    success = False
    result_data = {}
    error_msg = None

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        res = loop.run_until_complete(importer_service.update_stock_item(norm_payload))
        if res.get("status") == "SUCCESS":
            success = True
            result_data = {
                "itemName": item_name,
                "tallyExternalId": t_ext_id,
                "status": "SUCCESS",
                "updated": True
            }

            # Overwrite in MongoDB collections without duplicate
            try:
                now_dt = datetime.now(timezone.utc)
                set_doc = {
                    "name": item_name,
                    "itemName": item_name,
                    "tallyExternalId": t_ext_id or item_name,
                    "itemTallyExternalId": t_ext_id or item_name,
                    "closingBalance": qty_val,
                    "quantity": qty_val,
                    "closingRate": rate_val,
                    "rate": rate_val,
                    "closingValue": value_val,
                    "value": value_val,
                    "openingBalance": qty_val,
                    "openingRate": rate_val,
                    "openingValue": value_val,
                    "unit": unit_val,
                    "units": unit_val,
                    "uom": unit_val,
                    "unit_name": unit_val,
                    "baseUnits": unit_val,
                    "base_units": unit_val,
                    "hsnCode": hsn_val,
                    "hsn_code": hsn_val,
                    "hsn": hsn_val,
                    "godown": godown_val,
                    "batch": batch_val,
                    "company_name": resolved_company,
                    "updatedAt": now_dt,
                    "updated_at": now_dt.isoformat()
                }
                if comp_id:
                    set_doc["companyId"] = comp_id
                    set_doc["cloud_company_id"] = str(comp_id)

                for col_name in ["stock_items", "stocks", "items", "stockbalances"]:
                    col = get_collection(col_name)
                    doc = None
                    if t_ext_id:
                        f1 = {"tallyExternalId": t_ext_id}
                        if comp_id:
                            f1["companyId"] = comp_id
                        doc = col.find_one(f1)
                    if not doc and item_name:
                        f2 = {"$or": [{"itemName": item_name}, {"name": item_name}]}
                        if comp_id:
                            f2["companyId"] = comp_id
                        doc = col.find_one(f2)

                    if doc:
                        col.update_one({"_id": doc["_id"]}, {"$set": set_doc})
                    else:
                        upsert_filter = {"tallyExternalId": t_ext_id} if t_ext_id else {"itemName": item_name}
                        if comp_id:
                            upsert_filter["companyId"] = comp_id
                        col.update_one(upsert_filter, {"$set": set_doc}, upsert=True)

                logger.info(f"Overwrote stock item '{item_name}' in MongoDB collections successfully without duplicate.")
            except Exception as m_err:
                logger.warning(f"MongoDB update notice for stock item '{item_name}': {m_err}")
        else:
            success = False
            error_msg = res.get("error") or res.get("message") or "Failed to update stock item in Tally."
    finally:
        loop.close()

    return norm_payload, success, result_data, error_msg

