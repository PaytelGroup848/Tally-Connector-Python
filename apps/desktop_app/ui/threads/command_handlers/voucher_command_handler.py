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
    else:
        default_vtype = "Sales"

    norm_payload["voucher_type"] = norm_payload.get("voucherType") or norm_payload.get("voucher_type", default_vtype)
    norm_payload["party_ledger"] = (
        norm_payload.get("partyLedger")
        or norm_payload.get("party_ledger")
        or norm_payload.get("partyName")
        or norm_payload.get("party_name")
        or norm_payload.get("customerName")
        or norm_payload.get("supplierName")
        or "Cash"
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
    norm_payload["ledger_entries"] = norm_payload.get("ledgerEntries") or norm_payload.get("ledger_entries")
    norm_payload["bill_number"] = (
        norm_payload.get("billNumber")
        or norm_payload.get("bill_number")
        or norm_payload.get("billNo")
        or norm_payload.get("bill_no")
        or norm_payload.get("invoiceNumber")
        or norm_payload.get("invoice_number")
    )
    norm_payload["order_no"] = (
        norm_payload.get("orderNo")
        or norm_payload.get("order_no")
        or norm_payload.get("orderNumber")
        or norm_payload.get("order_number")
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
        or norm_payload.get("consigneeGstinUin")
        or norm_payload.get("buyerGstin")
    )
    norm_payload["state"] = (
        norm_payload.get("state")
        or norm_payload.get("party_state")
        or norm_payload.get("placeOfSupply")
        or norm_payload.get("place_of_supply")
        or norm_payload.get("supplierState")
    )
    norm_payload["address"] = (
        norm_payload.get("address")
        or norm_payload.get("party_address")
        or norm_payload.get("partyAddress")
        or norm_payload.get("consigneeAddress")
    )

    items_preview = norm_payload.get("items") or norm_payload.get("inventory_entries") or norm_payload.get("inventoryEntries") or []
    if isinstance(items_preview, list):
        try:
            from apps.backend.adapters.tally.tally_importer import _lookup_item_master_unit, _lookup_item_master_hsn
            for itm in items_preview:
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

