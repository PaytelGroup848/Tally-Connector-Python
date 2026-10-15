import asyncio
from typing import Dict, Any, Tuple, Optional
from shared.logging_config import get_logger
from shared.auth.cloud_auth_service import cloud_auth_service

logger = get_logger("app.threads.command_handlers.voucher")


def execute_voucher_command(
    worker: Any,
    payload: Dict[str, Any],
    cmd: Dict[str, Any],
    cmd_id: str,
    cmd_type: str,
    comp_id: Optional[str],
    resolved_company: str,
    active_host: str,
    active_port: int,
    amt: float,
    curr_email: Optional[str],
    curr_org: Optional[str],
) -> Tuple[Dict[str, Any], bool, Dict[str, Any], Optional[str], Dict[str, Any], bool]:
    """
    Handles CREATE_VOUCHER, UPDATE_VOUCHER, CREATE_RECEIPT, CREATE_PAYMENT, CREATE_PURCHASE, etc.
    Returns: (norm_payload, success, result_data, error_msg, error_details, should_continue)
    """
    norm_payload = dict(payload)
    norm_payload["target"] = "TALLY"
    norm_payload["host"] = active_host
    norm_payload["port"] = active_port
    norm_payload["tally_host"] = active_host
    norm_payload["tally_port"] = active_port
    norm_payload["companyId"] = comp_id or cmd.get("companyId") or cmd.get("company_id") or payload.get("companyId")

    if cmd_type in ("CREATE_RECEIPT", "PAYMENT_RECEIVED"):
        default_vtype = "Receipt"
    elif cmd_type in ("CREATE_PAYMENT", "PAYMENT_MADE"):
        default_vtype = "Payment"
    elif cmd_type in ("CREATE_PURCHASE",):
        default_vtype = "Purchase"
    elif cmd_type in ("CREATE_DEBIT_NOTE",):
        default_vtype = "Debit Note"
    elif cmd_type in ("CREATE_CREDIT_NOTE",):
        default_vtype = "Credit Note"
    elif cmd_type in ("CREATE_JOURNAL",):
        default_vtype = "Journal"
    elif cmd_type in ("CREATE_CONTRA",):
        default_vtype = "Contra"
    elif cmd_type in ("CREATE_SALES_ORDER",):
        default_vtype = "Sales Order"
    elif cmd_type in ("CREATE_PURCHASE_ORDER",):
        default_vtype = "Purchase Order"
    elif cmd_type in ("CREATE_STOCK_JOURNAL", "STOCK_JOURNAL"):
        default_vtype = "Stock Journal"
    elif cmd_type in ("CREATE_PHYSICAL_STOCK", "PHYSICAL_STOCK"):
        default_vtype = "Physical Stock"
    else:
        default_vtype = "Sales"

    norm_payload["voucher_type"] = norm_payload.get("voucherType") or norm_payload.get("voucher_type", default_vtype)
    v_type_check = str(norm_payload.get("voucher_type") or "").strip().lower()
    is_pure_inventory = "stock journal" in v_type_check or "physical stock" in v_type_check

    norm_payload["party_ledger"] = (
        "Inventory / Stock" if is_pure_inventory else (
            norm_payload.get("partyLedger")
            or norm_payload.get("party_ledger")
            or norm_payload.get("partyName")
            or norm_payload.get("party_name")
            or norm_payload.get("customerName")
            or norm_payload.get("supplierName")
            or "Cash"
        )
    )
    norm_payload["sales_ledger"] = norm_payload.get("salesLedger") or norm_payload.get("sales_ledger")
    norm_payload["purchase_ledger"] = norm_payload.get("purchaseLedger") or norm_payload.get("purchase_ledger")
    norm_payload["credit_note_ledger"] = (
        norm_payload.get("creditNoteLedger")
        or norm_payload.get("credit_note_ledger")
        or norm_payload.get("salesReturnLedger")
        or norm_payload.get("sales_return_ledger")
    )
    norm_payload["debit_note_ledger"] = (
        norm_payload.get("debitNoteLedger")
        or norm_payload.get("debit_note_ledger")
        or norm_payload.get("purchaseReturnLedger")
        or norm_payload.get("purchase_return_ledger")
    )
    norm_payload["bank_ledger"] = (
        norm_payload.get("bankLedger")
        or norm_payload.get("bank_ledger")
        or norm_payload.get("cash_bank_ledger")
        or norm_payload.get("account")
        or norm_payload.get("bank_account")
    )
    norm_payload["to_account"] = norm_payload.get("toAccount") or norm_payload.get("to_account")
    norm_payload["from_account"] = norm_payload.get("fromAccount") or norm_payload.get("from_account")
    norm_payload["particulars"] = (
        norm_payload.get("particulars")
        or payload.get("particulars")
        or norm_payload.get("ledgerEntries")
        or norm_payload.get("ledger_entries")
    )
    if ("journal" in v_type_check and not is_pure_inventory or "contra" in v_type_check) and not norm_payload["particulars"]:
        c_items = norm_payload.get("items") or payload.get("items")
        if isinstance(c_items, list) and any(
            isinstance(x, dict) and (
                "type" in x
                or "isDebit" in x
                or "is_debit" in x
                or "partyName" in x
                or "ledgerName" in x
            )
            for x in c_items
        ):
            norm_payload["particulars"] = c_items
    norm_payload["ledger_entries"] = norm_payload["particulars"]
    norm_payload["bill_number"] = (
        norm_payload.get("billNumber")
        or norm_payload.get("bill_number")
        or norm_payload.get("billNo")
        or norm_payload.get("bill_no")
        or norm_payload.get("invoiceNumber")
        or norm_payload.get("invoice_number")
    )
    adv_settings_raw = norm_payload.get("advancedSettings") or norm_payload.get("advanced_settings")
    adv_settings: dict = {}
    if isinstance(adv_settings_raw, dict):
        adv_settings = dict(adv_settings_raw)

    norm_payload["order_no"] = (
        norm_payload.get("orderNo")
        or norm_payload.get("order_no")
        or norm_payload.get("orderNumber")
        or norm_payload.get("order_number")
        or adv_settings.get("orderNo")
        or adv_settings.get("order_no")
        or adv_settings.get("orderNumber")
    )
    norm_payload["order_date"] = (
        norm_payload.get("orderDate")
        or norm_payload.get("order_date")
        or adv_settings.get("orderDate")
        or adv_settings.get("order_date")
    )
    norm_payload["terms_of_delivery"] = (
        norm_payload.get("termsOfDelivery")
        or norm_payload.get("terms_of_delivery")
        or adv_settings.get("termsOfDelivery")
        or adv_settings.get("terms_of_delivery")
    )
    norm_payload["dispatch_doc_no"] = (
        norm_payload.get("dispatchDocNo")
        or norm_payload.get("dispatch_doc_no")
        or norm_payload.get("lrNo")
        or norm_payload.get("lrNumber")
        or adv_settings.get("dispatchDocNo")
        or adv_settings.get("dispatch_doc_no")
    )
    norm_payload["dispatch_through"] = (
        norm_payload.get("dispatchThrough")
        or norm_payload.get("dispatch_through")
        or norm_payload.get("transporter")
        or adv_settings.get("dispatchThrough")
        or adv_settings.get("dispatch_through")
    )
    norm_payload["dispatch_destination"] = (
        norm_payload.get("dispatchFrom")
        or norm_payload.get("dispatch_from")
        or norm_payload.get("destination")
        or adv_settings.get("dispatchFrom")
        or adv_settings.get("dispatch_from")
        or adv_settings.get("destination")
    )
    norm_payload["dispatch_date"] = (
        norm_payload.get("dispatchDate")
        or norm_payload.get("dispatch_date")
        or adv_settings.get("dispatchDate")
        or adv_settings.get("dispatch_date")
    )
    norm_payload["vehicle_no"] = (
        norm_payload.get("vehicleNo")
        or norm_payload.get("vehicle_no")
        or norm_payload.get("motorVehicleNo")
        or adv_settings.get("motorVehicleNo")
        or adv_settings.get("vehicleNo")
    )

    norm_payload["consignee_name"] = (
        norm_payload.get("consigneeName")
        or norm_payload.get("consignee_name")
        or adv_settings.get("consigneeName")
        or adv_settings.get("consignee_name")
        or adv_settings.get("shipToName")
    )
    norm_payload["consignee_address"] = (
        norm_payload.get("consigneeAddress")
        or norm_payload.get("consignee_address")
        or adv_settings.get("consigneeAddress")
        or adv_settings.get("consignee_address")
    )
    norm_payload["consignee_state"] = (
        norm_payload.get("consigneeState")
        or norm_payload.get("consignee_state")
        or adv_settings.get("consigneeState")
        or adv_settings.get("consignee_state")
    )
    norm_payload["consignee_country"] = (
        norm_payload.get("consigneeCountry")
        or norm_payload.get("consignee_country")
        or adv_settings.get("consigneeCountry")
        or adv_settings.get("consignee_country")
    )
    norm_payload["consignee_pincode"] = (
        norm_payload.get("consigneePostalCode")
        or norm_payload.get("consignee_postal_code")
        or norm_payload.get("consigneePincode")
        or norm_payload.get("consignee_pincode")
        or adv_settings.get("consigneePostalCode")
        or adv_settings.get("consignee_postal_code")
        or adv_settings.get("consigneePincode")
    )
    norm_payload["consignee_gstin"] = (
        norm_payload.get("consigneeGstinUin")
        or norm_payload.get("consignee_gstin_uin")
        or norm_payload.get("consigneeGstin")
        or norm_payload.get("consignee_gstin")
        or adv_settings.get("consigneeGstinUin")
        or adv_settings.get("consignee_gstin_uin")
        or adv_settings.get("consigneeGstin")
    )

    norm_payload["due_date"] = (
        norm_payload.get("dueDate")
        or norm_payload.get("due_date")
        or norm_payload.get("orderDueDate")
        or norm_payload.get("deliveryDate")
    )
    norm_payload["company_name"] = norm_payload.get("companyName") or norm_payload.get("company_name") or resolved_company
    norm_payload["company_name"] = resolved_company
    norm_payload["date"] = norm_payload.get("date") or norm_payload.get("voucherDate")
    norm_payload["gstin"] = (
        norm_payload.get("gstin")
        or norm_payload.get("gstinUin")
        or norm_payload.get("gstNumber")
        or norm_payload.get("party_gstin")
        or norm_payload.get("partyGstin")
        or norm_payload.get("buyerGstin")
        or adv_settings.get("gstinUin")
        or adv_settings.get("gstin")
        or norm_payload.get("consigneeGstinUin")
    )
    norm_payload["state"] = (
        norm_payload.get("state")
        or norm_payload.get("party_state")
        or norm_payload.get("placeOfSupply")
        or norm_payload.get("place_of_supply")
        or norm_payload.get("supplierState")
        or adv_settings.get("supplierState")
        or adv_settings.get("state")
    )
    norm_payload["address"] = (
        norm_payload.get("address")
        or norm_payload.get("party_address")
        or norm_payload.get("partyAddress")
        or adv_settings.get("address")
        or adv_settings.get("partyAddress")
        or norm_payload.get("consigneeAddress")
    )

    raw_items_val = norm_payload.get("items")
    items_preview = []
    if isinstance(raw_items_val, list):
        items_preview = list(raw_items_val)
    elif isinstance(raw_items_val, dict):
        for sub_k in ("source", "destination", "consumption", "production", "items_out", "items_in", "outward", "inward", "items", "rows"):
            sub_list = raw_items_val.get(sub_k)
            if isinstance(sub_list, list):
                items_preview.extend(sub_list)
    else:
        items_preview = norm_payload.get("inventory_entries") or norm_payload.get("inventoryEntries") or []

    if is_pure_inventory and not items_preview:
        inv_items = []
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
            ex_list = norm_payload.get(extra_key)
            if isinstance(ex_list, list):
                inv_items.extend(ex_list)
        if inv_items:
            items_preview = inv_items

    # Collect all items to enrich units and HSN
    enrich_targets = list(items_preview) if isinstance(items_preview, list) else []
    for extra_key in (
        "source_items", "sourceItems",
        "destination_items", "destinationItems",
        "consumption_items", "consumptionItems",
        "production_items", "productionItems",
        "items_out", "itemsOut",
        "items_in", "itemsIn",
    ):
        ex_list = norm_payload.get(extra_key)
        if isinstance(ex_list, list):
            enrich_targets.extend(ex_list)

    if enrich_targets:
        try:
            from apps.backend.adapters.tally.tally_importer import _lookup_item_master_unit, _lookup_item_master_hsn
            for itm in enrich_targets:
                if isinstance(itm, dict):
                    it_name = str(itm.get("item") or itm.get("itemName") or itm.get("name") or itm.get("stock_item") or "").strip()
                    if it_name:
                        curr_u = str(itm.get("units") or itm.get("unit") or itm.get("uom") or "").strip()
                        if not curr_u or curr_u.lower() == "pcs":
                            mu = _lookup_item_master_unit(resolved_company, it_name)
                            if mu:
                                itm["units"] = mu
                                itm["unit"] = mu
                        curr_h = str(itm.get("hsn_code") or itm.get("hsnCode") or itm.get("hsn") or itm.get("hsnCodeValue") or "").strip()
                        if not curr_h:
                            mh = _lookup_item_master_hsn(resolved_company, it_name)
                            if mh:
                                itm["hsn_code"] = mh
                                itm["hsnCode"] = mh
                                itm["hsn"] = mh
        except Exception as itm_exc:
            logger.debug(f"Voucher item master unit/HSN enrichment notice: {itm_exc}")

    # If amt is 0 or missing, or if it was doubled from deb + cred, calculate from particulars if present
    if norm_payload.get("particulars"):
        parts = norm_payload["particulars"]
        if isinstance(parts, list):
            deb_sum = 0.0
            cred_sum = 0.0
            has_legs = False
            for p in parts:
                if isinstance(p, dict):
                    try:
                        p_val = abs(float(p.get("amount") or p.get("amt") or 0.0))
                        p_typ = str(p.get("type") or p.get("entry_type") or "").strip().lower()
                        if p_typ in ("debit", "dr", "by") or p.get("isDebit") is True or p.get("is_debit") is True:
                            deb_sum += p_val
                            has_legs = True
                        elif p_typ in ("credit", "cr", "to") or p.get("isDebit") is False or p.get("is_debit") is False:
                            cred_sum += p_val
                            has_legs = True
                    except (ValueError, TypeError):
                        pass
            if has_legs:
                if not amt or amt <= 0.0 or (deb_sum > 0 and round(amt, 2) == round(deb_sum + cred_sum, 2)):
                    amt = round(deb_sum if deb_sum > 0 else cred_sum, 2)

    # For Journal or Contra vouchers, if party_ledger defaulted to "Cash", extract real party from particulars
    if (norm_payload.get("party_ledger") in ("", "Cash")) and norm_payload.get("particulars"):
        parts = norm_payload["particulars"]
        if isinstance(parts, list):
            for p in parts:
                if isinstance(p, dict):
                    p_name = str(p.get("partyName") or p.get("party_name") or p.get("ledgerName") or p.get("name") or "").strip()
                    if p_name and p_name.lower() not in ("cash", "bank"):
                        norm_payload["party_ledger"] = p_name
                        break

    if is_pure_inventory and (not amt or amt <= 0.0):
        raw_items_dict: dict = {}
        raw_items_v = norm_payload.get("items")
        if isinstance(raw_items_v, dict):
            raw_items_dict = dict(raw_items_v)
        src_calc = 0.0
        for it_k in ("source_items", "sourceItems", "consumption_items", "consumptionItems", "items_out", "itemsOut", "outward_items", "outwardItems"):
            for it in (norm_payload.get(it_k) or []):
                if isinstance(it, dict):
                    try:
                        q = float(it.get("quantity") if it.get("quantity") is not None else it.get("qty", 0.0))
                        r = float(it.get("rate") if it.get("rate") is not None else it.get("price", 0.0))
                        src_calc += float(it.get("amount") or it.get("taxableValue") or (q * r))
                    except (ValueError, TypeError):
                        pass
        for it in (raw_items_dict.get("source") or raw_items_dict.get("consumption") or raw_items_dict.get("items_out") or []):
            if isinstance(it, dict):
                try:
                    q = float(it.get("quantity") if it.get("quantity") is not None else it.get("qty", 0.0))
                    r = float(it.get("rate") if it.get("rate") is not None else it.get("price", 0.0))
                    src_calc += float(it.get("amount") or it.get("taxableValue") or (q * r))
                except (ValueError, TypeError):
                    pass

        dest_calc = 0.0
        for it_k in ("destination_items", "destinationItems", "production_items", "productionItems", "items_in", "itemsIn", "inward_items", "inwardItems"):
            for it in (norm_payload.get(it_k) or []):
                if isinstance(it, dict):
                    try:
                        q = float(it.get("quantity") if it.get("quantity") is not None else it.get("qty", 0.0))
                        r = float(it.get("rate") if it.get("rate") is not None else it.get("price", 0.0))
                        dest_calc += float(it.get("amount") or it.get("taxableValue") or (q * r))
                    except (ValueError, TypeError):
                        pass
        for it in (raw_items_dict.get("destination") or raw_items_dict.get("production") or raw_items_dict.get("items_in") or []):
            if isinstance(it, dict):
                try:
                    q = float(it.get("quantity") if it.get("quantity") is not None else it.get("qty", 0.0))
                    r = float(it.get("rate") if it.get("rate") is not None else it.get("price", 0.0))
                    dest_calc += float(it.get("amount") or it.get("taxableValue") or (q * r))
                except (ValueError, TypeError):
                    pass

        if src_calc > 0 and dest_calc > 0:
            amt = round(max(src_calc, dest_calc), 2)
        elif src_calc > 0:
            amt = round(src_calc, 2)
        elif dest_calc > 0:
            amt = round(dest_calc, 2)

    if ("journal" in v_type_check and not is_pure_inventory) or "contra" in v_type_check:
        norm_payload["items"] = []
    else:
        norm_payload["items"] = items_preview
    norm_payload["amount"] = amt
    logger.info(
        f"Voucher Payload: Company='{norm_payload.get('company_name')}', Type='{norm_payload.get('voucher_type')}', "
        f"Party='{norm_payload.get('party_ledger')}', GSTIN='{norm_payload.get('gstin')}', "
        f"ItemsCount={len(items_preview) if isinstance(items_preview, list) else 0}, "
        f"Date='{norm_payload.get('date')}', Amount={norm_payload.get('amount')}"
    )

    success = False
    result_data = {}
    error_msg = None
    error_details = {}
    should_continue = False

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        res = loop.run_until_complete(worker.importer_service.import_voucher(norm_payload))
        if res.get("status") == "SUCCESS":
            success = True
            res_amt = res.get("amount")
            if res_amt is not None:
                try:
                    parsed_res_amt = float(res_amt)
                    if parsed_res_amt > 0:
                        norm_payload["amount"] = parsed_res_amt
                except (ValueError, TypeError):
                    pass
            if res.get("company_name"):
                norm_payload["company_name"] = res.get("company_name")
            v_ext = res.get("tallyExternalId") or res.get("guid") or res.get("voucher_number") or "IMPORTED"
            result_data = {
                "tallyVoucherNumber": res.get("voucher_number") or res.get("guid") or "IMPORTED",
                "tallyExternalId": v_ext,
                "guid": v_ext,
                "status": "SUCCESS"
            }
        elif res.get("should_queue"):
            from shared.repositories.voucher_queue_repository import voucher_queue_repo
            q_comp = norm_payload.get("company_name") or resolved_company
            voucher_queue_repo.enqueue_pending_voucher(
                cmd_id=cmd_id,
                cmd_type=cmd_type,
                payload=norm_payload,
                target_company=q_comp,
                user_email=curr_email,
                organization_id=str(curr_org or ""),
                reason=res.get("reason")
            )
            cloud_auth_service.send_command_result(
                command_id=cmd_id,
                status="WAITING_FOR_TALLY",
                result={"status": "QUEUED", "company": q_comp, "message": res.get("message")},
                error_message=res.get("reason")
            )
            v_label = norm_payload.get("voucher_number") or norm_payload.get("voucherNumber") or "Entry"
            worker.command_processed.emit(
                cmd_id,
                cmd_type,
                True,
                f"⏳ Voucher #{v_label} queued for '{q_comp}'. Auto-posts once company opens in Tally.",
                {"should_queue": True, "status": "QUEUED"}
            )
            should_continue = True
        else:
            success = False
            error_msg = res.get("error") or res.get("message") or "Tally rejected voucher creation."
            diag = res.get("diagnostic") or {}
            raw_err_amt = norm_payload.get("amount")
            err_amt = amt
            if raw_err_amt is not None:
                try:
                    err_amt = float(raw_err_amt)
                except (ValueError, TypeError):
                    err_amt = amt
            error_details = {
                "voucher_type": norm_payload.get("voucher_type", "Sales"),
                "voucher_number": norm_payload.get("voucher_number") or norm_payload.get("voucherNumber") or "N/A",
                "company": norm_payload.get("company_name") or resolved_company,
                "party": norm_payload.get("party_ledger") or "Cash",
                "amount": err_amt,
                "date": norm_payload.get("date") or "N/A",
                "reason": res.get("reason") or diag.get("reason") or error_msg,
                "action": res.get("action") or diag.get("action") or "Please verify the voucher details in your web app.",
                "technical_error": error_msg,
                "cmd_id": cmd_id,
                "cmd_type": cmd_type
            }
            logger.error(f"Command #{cmd_id} failed in Tally: {error_msg}")
    finally:
        loop.close()

    return norm_payload, success, result_data, error_msg, error_details, should_continue

