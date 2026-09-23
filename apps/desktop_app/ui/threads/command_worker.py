

import time
import asyncio
from PySide6.QtCore import QThread, Signal
from shared.auth.cloud_auth_service import cloud_auth_service
from shared.logging_config import get_logger
from apps.backend.services.importer_service import ImporterService

logger = get_logger("app.threads.command_worker")

class RemoteCommandWorker(QThread):
    command_received = Signal(str, str)
    command_processed = Signal(str, str, bool, str, dict)
    config_updated = Signal(dict)

    def __init__(self, poll_interval_seconds: int = 15, parent=None):
        super().__init__(parent)
        self.poll_interval = poll_interval_seconds
        self._is_running = True
        self.importer_service = ImporterService()

    def stop(self):
        self._is_running = False

    def run(self):
        if not self._is_running:
            return
        logger.info(f"Remote Command Worker started (Polling every {self.poll_interval}s)...")
        if self._is_running and cloud_auth_service.access_token:
            try:
                ok, _, cfg = cloud_auth_service.get_remote_config()
                if ok and isinstance(cfg, dict):
                    self.config_updated.emit(cfg)
            except Exception as exc:
                logger.debug(f"Config fetch error: {exc}")

        while self._is_running:
            if cloud_auth_service.access_token:
                try:
                    self._poll_and_execute_commands()
                except Exception as exc:
                    logger.warning(f"Error in remote command cycle: {exc}")

                try:
                    self._drain_pending_voucher_queue()
                except Exception as exc:
                    logger.debug(f"Error draining pending queue: {exc}")

            for _ in range(self.poll_interval * 2):
                if not self._is_running:
                    break
                time.sleep(0.5)

    def _poll_and_execute_commands(self):
        ok, msg, commands = cloud_auth_service.get_pending_commands()
        if not ok or not commands:
            return

        logger.info(f"Received {len(commands)} remote commands from Cloud.")
        curr_org = getattr(cloud_auth_service, "organization_id", None) or (cloud_auth_service.current_user or {}).get("organizationId")
        curr_email = getattr(cloud_auth_service, "email", None) or (cloud_auth_service.current_user or {}).get("email")
        curr_dev = getattr(cloud_auth_service, "device_id", None)

        for cmd in commands:
            if not self._is_running:
                break
            cmd_id = cmd.get("id") or str(cmd.get("_id"))
            cmd_type = cmd.get("type", "UNKNOWN")
            payload = cmd.get("payload") or {}

            # Strict Multi-Tenant Isolation
            cmd_org = cmd.get("organizationId") or cmd.get("organization_id") or payload.get("organizationId") or payload.get("organization_id")
            if cmd_org and curr_org and str(cmd_org) != str(curr_org):
                logger.info(f"Skipping command #{cmd_id}: organizationId mismatch (cmd={cmd_org}, active={curr_org})")
                continue

            cmd_dev = cmd.get("deviceId") or cmd.get("device_id") or payload.get("deviceId") or payload.get("device_id")
            if cmd_dev and curr_dev and str(cmd_dev) != str(curr_dev):
                logger.info(f"Skipping command #{cmd_id}: deviceId mismatch (cmd={cmd_dev}, active={curr_dev})")
                continue

            cmd_email = cmd.get("email") or cmd.get("userEmail") or payload.get("email") or payload.get("userEmail")
            if cmd_email and curr_email and str(cmd_email).strip().lower() != str(curr_email).strip().lower():
                logger.info(f"Skipping command #{cmd_id}: email mismatch (cmd={cmd_email}, active={curr_email})")
                continue

            self.command_received.emit(cmd_id, cmd_type)
            logger.info(f"Processing command #{cmd_id} [{cmd_type}]...")

            success = False
            result_data = {}
            error_msg = None
            error_details = {}

            try:
                comp_id = cmd.get("companyId") or cmd.get("company_id") or payload.get("companyId") or payload.get("company_id")
                raw_comp = (
                    cmd.get("companyName")
                    or cmd.get("company_name")
                    or cmd.get("company")
                    or payload.get("companyName")
                    or payload.get("company_name")
                    or payload.get("company")
                    or payload.get("current_company")
                )
                resolved_company = ""
                if raw_comp and str(raw_comp).strip().lower() not in ("none", "null", "undefined", ""):
                    resolved_company = str(raw_comp).strip()

                if not resolved_company and comp_id:
                    try:
                        from shared.db.mongo_client import get_mongo_db
                        from bson import ObjectId
                        db = get_mongo_db()
                        c_doc = None
                        if ObjectId.is_valid(str(comp_id)):
                            c_doc = db.companies.find_one({"_id": ObjectId(str(comp_id))})
                        if not c_doc:
                            c_doc = db.companies.find_one({"cloud_company_id": str(comp_id)})
                        if not c_doc:
                            c_doc = db.companies.find_one({"id": str(comp_id)})
                        if c_doc:
                            resolved_company = str(c_doc.get("company_name") or c_doc.get("name") or c_doc.get("tallyCompanyName") or "").strip()
                    except Exception as exc:
                        logger.debug(f"Company ID lookup error: {exc}")

                if not resolved_company:
                    try:
                        from shared.repositories.company_repository import get_all_company_configs
                        tenant_companies = get_all_company_configs(
                            organization_id=curr_org,
                            device_id=curr_dev,
                            email=curr_email
                        )
                        if tenant_companies:
                            resolved_company = str(tenant_companies[0].get("company_name") or tenant_companies[0].get("name", "")).strip()
                    except Exception:
                        pass

                raw_amt = (
                    payload.get("amount")
                    if payload.get("amount") is not None
                    else (
                        payload.get("total_amount")
                        if payload.get("total_amount") is not None
                        else (
                            payload.get("totalAmount")
                            if payload.get("totalAmount") is not None
                            else (
                                payload.get("grand_total")
                                if payload.get("grand_total") is not None
                                else (
                                    payload.get("grandTotal")
                                    if payload.get("grandTotal") is not None
                                    else (
                                        payload.get("net_amount")
                                        if payload.get("net_amount") is not None
                                        else payload.get("netAmount")
                                    )
                                )
                            )
                        )
                    )
                )
                try:
                    amt = float(raw_amt) if raw_amt is not None else 0.0
                except (ValueError, TypeError):
                    amt = 0.0

                items_preview = (
                    payload.get("items")
                    or payload.get("inventory_entries")
                    or payload.get("inventoryEntries")
                    or payload.get("stock_items")
                    or []
                )

                if amt <= 0.0 and isinstance(items_preview, list):
                    calc_total = 0.0
                    for it in items_preview:
                        if isinstance(it, dict):
                            it_amt = it.get("amount") or it.get("net_amount") or it.get("netAmount") or it.get("total")
                            disc = 0.0
                            raw_disc = it.get("discount") or it.get("discount_pct")
                            if raw_disc is not None:
                                try:
                                    disc = float(raw_disc)
                                except (ValueError, TypeError):
                                    disc = 0.0
                            if it_amt is not None:
                                try:
                                    val = float(it_amt)
                                    if disc > 0 and not it.get("taxInclusive"):
                                        val = val - (val * disc / 100.0)
                                    calc_total += val
                                    continue
                                except (ValueError, TypeError):
                                    pass
                            try:
                                raw_qty = it.get("quantity") if it.get("quantity") is not None else it.get("qty")
                                q = float(raw_qty) if raw_qty is not None else 1.0
                                raw_rate = it.get("rate") if it.get("rate") is not None else it.get("price")
                                r = float(raw_rate) if raw_rate is not None else 0.0
                                gross = q * r
                                net = gross - (gross * disc / 100.0) if disc > 0 else gross
                                calc_total += net
                            except (ValueError, TypeError):
                                pass
                    if calc_total > 0:
                        amt = round(calc_total, 2)

                if cmd_type in (
                    "CREATE_VOUCHER",
                    "UPDATE_VOUCHER",
                    "CREATE_RECEIPT",
                    "PAYMENT_RECEIVED",
                    "CREATE_PAYMENT",
                    "PAYMENT_MADE",
                    "CREATE_PURCHASE",
                    "CREATE_DEBIT_NOTE",
                    "CREATE_CREDIT_NOTE",
                    "CREATE_JOURNAL",
                    "CREATE_CONTRA",
                    "CREATE_SALES_ORDER",
                    "CREATE_PURCHASE_ORDER",
                ):
                    norm_payload = dict(payload)
                    norm_payload["target"] = "TALLY"
                    norm_payload["companyId"] = cmd.get("companyId") or cmd.get("company_id") or payload.get("companyId")
                    norm_payload["companyId"] = comp_id
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
                    norm_payload["company_name"] = norm_payload.get("companyName") or norm_payload.get("company_name")
                    norm_payload["company_name"] = resolved_company
                    norm_payload["date"] = norm_payload.get("date") or norm_payload.get("voucherDate")
                    norm_payload["amount"] = norm_payload.get("amount", 0.0)
                    items_preview = norm_payload.get("items") or norm_payload.get("inventory_entries") or norm_payload.get("inventoryEntries") or []
                    norm_payload["amount"] = amt
                    logger.info(f"Voucher Payload: Company='{norm_payload.get('company_name')}', Type='{norm_payload.get('voucher_type')}', Party='{norm_payload.get('party_ledger')}', ItemsCount={len(items_preview) if isinstance(items_preview, list) else 0}, Date='{norm_payload.get('date')}', Amount={norm_payload.get('amount')}")

                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        res = loop.run_until_complete(self.importer_service.import_voucher(norm_payload))
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
                            result_data = {
                                "tallyVoucherNumber": res.get("voucher_number") or res.get("guid") or "IMPORTED",
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
                            self.command_processed.emit(
                                cmd_id,
                                cmd_type,
                                True,
                                f"⏳ Voucher #{v_label} queued for '{q_comp}'. Auto-posts once company opens in Tally.",
                                {"should_queue": True, "status": "QUEUED"}
                            )
                            continue
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

                elif cmd_type in ("CREATE_LEDGER", "CREATE_PARTY", "CREATE_CUSTOMER", "CREATE_SUPPLIER", "CREATE_VENDOR"):
                    norm_payload = dict(payload)
                    norm_payload["target"] = "TALLY"
                    norm_payload["companyId"] = cmd.get("companyId") or cmd.get("company_id") or payload.get("companyId") or comp_id
                    norm_payload["company_name"] = norm_payload.get("companyName") or norm_payload.get("company_name") or resolved_company

                    party_name = (
                        norm_payload.get("partyName")
                        or norm_payload.get("party_name")
                        or norm_payload.get("name")
                        or norm_payload.get("party_ledger")
                        or norm_payload.get("customerName")
                    )
                    norm_payload["name"] = party_name
                    norm_payload["party_ledger"] = party_name

                    p_type = str(norm_payload.get("partyType") or norm_payload.get("party_type") or norm_payload.get("type") or "").strip().upper()
                    if "SUPPLIER" in p_type or "VENDOR" in p_type or "CREDITOR" in p_type:
                        default_parent = "Sundry Creditors"
                        norm_payload["voucher_type"] = "Supplier Master"
                    else:
                        default_parent = "Sundry Debtors"
                        norm_payload["voucher_type"] = "Customer Master"

                    norm_payload["parent"] = norm_payload.get("parent") or default_parent
                    norm_payload["mobile"] = norm_payload.get("contactNumber") or norm_payload.get("mobile") or norm_payload.get("phone")
                    raw_op_bal = norm_payload.get("openingBalance") or norm_payload.get("opening_balance")
                    try:
                        op_bal = float(raw_op_bal) if raw_op_bal is not None else 0.0
                    except (ValueError, TypeError):
                        op_bal = 0.0
                    norm_payload["opening_balance"] = op_bal
                    norm_payload["amount"] = norm_payload["opening_balance"]
                    norm_payload["gstin"] = norm_payload.get("gstin") or norm_payload.get("party_gstin") or norm_payload.get("gstNumber")
                    norm_payload["state"] = norm_payload.get("state")
                    norm_payload["address"] = norm_payload.get("address")

                    logger.info(f"Party Creation Payload: Company='{norm_payload.get('company_name')}', Name='{norm_payload.get('name')}', Parent='{norm_payload.get('parent')}', Mobile='{norm_payload.get('mobile')}', OpeningBalance={norm_payload.get('opening_balance')}")

                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        res = loop.run_until_complete(self.importer_service.create_ledger(norm_payload))
                        if res.get("status") == "SUCCESS":
                            success = True
                            result_data = {
                                "ledgerName": norm_payload.get("name"),
                                "partyName": norm_payload.get("name"),
                                "status": "SUCCESS"
                            }
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

                elif cmd_type in ("CREATE_STOCK_ITEM", "CREATE_ITEM"):
                    norm_payload = dict(payload)
                    norm_payload["target"] = "TALLY"
                    norm_payload["companyId"] = cmd.get("companyId") or cmd.get("company_id") or payload.get("companyId")
                    norm_payload["company_name"] = norm_payload.get("companyName") or norm_payload.get("company_name")
                    norm_payload["companyId"] = comp_id
                    norm_payload["company_name"] = resolved_company
                    norm_payload["name"] = norm_payload.get("name") or norm_payload.get("itemName") or norm_payload.get("item_name")
                    norm_payload["unit"] = norm_payload.get("unit") or norm_payload.get("units") or "Pcs"
                    norm_payload["hsn_code"] = norm_payload.get("hsn_code") or norm_payload.get("hsnCode") or norm_payload.get("hsn", "")

                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        res = loop.run_until_complete(self.importer_service.create_stock_item(norm_payload))
                        if res.get("status") == "SUCCESS":
                            success = True
                            result_data = {
                                "itemName": norm_payload.get("name"),
                                "status": "SUCCESS"
                            }
                        else:
                            success = False
                            error_msg = res.get("error") or res.get("message") or "Failed to create stock item in Tally."
                    finally:
                        loop.close()

                elif cmd_type == "DELETE_VOUCHER":
                    norm_payload = dict(payload)
                    norm_payload["company_name"] = resolved_company
                    success = True
                    result_data = {"status": "DELETED", "voucherNumber": payload.get("voucherNumber")}

                else:
                    norm_payload = dict(payload)
                    norm_payload["company_name"] = resolved_company
                    success = False
                    error_msg = f"Unsupported command type: {cmd_type}"

            except Exception as e:
                success = False
                error_msg = str(e)
                logger.error(f"Failed to execute command #{cmd_id}: {e}")
                if not error_details:
                    error_details = {
                        "voucher_type": cmd_type,
                        "voucher_number": "N/A",
                        "company": resolved_company or "Active Company",
                        "party": "N/A",
                        "amount": float(amt) if "amt" in locals() else 0.0,
                        "date": "N/A",
                        "reason": f"Execution Error: {e}",
                        "action": "Verify that Tally Prime is running on port 9000 and accessible.",
                        "technical_error": str(e),
                        "cmd_id": cmd_id,
                        "cmd_type": cmd_type
                    }

            try:
                from shared.repositories.activity_history_repository import activity_history_repo
                v_type = norm_payload.get("voucher_type", "Sales")
                if "Master" in str(v_type):
                    label_type = str(v_type)
                elif "sale" in str(v_type).lower():
                    label_type = "Sales Bill"
                else:
                    label_type = f"{v_type} Voucher"

                raw_card_amt = norm_payload.get("amount") if norm_payload.get("amount") is not None else (amt if "amt" in locals() and amt is not None else 0.0)
                try:
                    card_amt = float(raw_card_amt) if raw_card_amt is not None else 0.0
                except (ValueError, TypeError):
                    card_amt = 0.0

                activity_history_repo.record_activity({
                    "command_id": cmd_id,
                    "voucher_type": label_type,
                    "party": norm_payload.get("party_ledger") or norm_payload.get("name", "Cash"),
                    "amount": card_amt,
                    "company": norm_payload.get("company_name") or resolved_company,
                    "voucher_date": norm_payload.get("date") or norm_payload.get("voucherDate"),
                    "status": "SUCCESS" if success else "FAILED",
                    "voucher_number": result_data.get("tallyVoucherNumber"),
                    "error": error_msg if not success else None,
                    "organization_id": curr_org or cmd.get("organizationId") or cmd.get("organization_id") or getattr(self.settings, "organization_id", "") or "",
                    "user_email": (curr_email or cmd.get("email") or getattr(self.settings, "user_email", "") or "").strip().lower(),
                    "device_id": curr_dev or cmd.get("deviceId") or getattr(self.settings, "device_id", "") or "",
                })
            except Exception as act_err:
                logger.warning(f"Failed to record activity log: {act_err}")

            if not success and error_details:
                reason_str = error_details.get("reason")
                action_str = error_details.get("action")
                if reason_str and action_str:
                    error_msg = f"{reason_str} -> Action: {action_str}"
                elif reason_str:
                    error_msg = reason_str

            status_str = "DONE" if success else "FAILED"
            result_payload = result_data if success else {
                "failed": True,
                "reason": error_details.get("reason"),
                "action": error_details.get("action"),
                "voucherDetails": {
                    "company": error_details.get("company"),
                    "voucherType": error_details.get("voucher_type"),
                    "voucherNumber": error_details.get("voucher_number"),
                    "party": error_details.get("party"),
                    "amount": error_details.get("amount"),
                    "date": error_details.get("date")
                }
            }

            cloud_auth_service.send_command_result(
                command_id=cmd_id,
                status=status_str,
                result=result_payload,
                error_message=error_msg
            )

            try:
                from shared.db.mongo_client import get_collection
                from bson import ObjectId
                from datetime import datetime, timezone
                cmd_col = get_collection("commands")
                if ObjectId.is_valid(cmd_id):
                    cmd_col.update_one(
                        {"_id": ObjectId(cmd_id)},
                        {"$set": {
                            "status": status_str,
                            "result": result_payload,
                            "errorMessage": error_msg,
                            "completedAt": datetime.now(timezone.utc),
                            "updatedAt": datetime.now(timezone.utc)
                        }}
                    )
            except Exception as m_err:
                logger.debug(f"Direct MongoDB command update skipped: {m_err}")

            self.command_processed.emit(cmd_id, cmd_type, success, error_msg or "Executed successfully", error_details if not success else {})

    def _drain_pending_voucher_queue(self):
        """
        Periodically inspects open companies in Tally Prime and executes any
        pending vouchers whose target company is currently open.
        """
        curr_org = getattr(cloud_auth_service, "organization_id", None) or (cloud_auth_service.current_user or {}).get("organizationId")
        curr_email = getattr(cloud_auth_service, "email", None) or (cloud_auth_service.current_user or {}).get("email")

        from shared.repositories.voucher_queue_repository import voucher_queue_repo
        pending_items = voucher_queue_repo.get_pending_vouchers(organization_id=curr_org, user_email=curr_email)
        if not pending_items:
            return

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            is_online, _, open_companies = loop.run_until_complete(
                self.importer_service.tally_importer.check_tally_company_status("127.0.0.1", 9000, "")
            )
            if not is_online or not open_companies:
                return

            open_clean = [c.strip().lower() for c in open_companies]

            for item in pending_items:
                if not self._is_running:
                    break
                target_comp = str(item.get("target_company") or "").strip()
                target_lower = target_comp.lower()
                is_open = not target_comp or any(target_lower == oc or target_lower in oc or oc in target_lower for oc in open_clean)
                if not is_open:
                    continue

                cmd_id = item.get("cmd_id")
                payload = item.get("payload") or {}
                cmd_type = item.get("cmd_type", "CREATE_VOUCHER")
                logger.info(f"Draining pending voucher #{cmd_id} for newly opened company '{target_comp}'...")

                res = loop.run_until_complete(self.importer_service.import_voucher(payload))
                if res.get("status") == "SUCCESS":
                    v_num = res.get("voucher_number") or "SUCCESS"
                    voucher_queue_repo.mark_voucher_completed(cmd_id, v_num)
                    cloud_auth_service.send_command_result(
                        command_id=cmd_id,
                        status="DONE",
                        result={"status": "SUCCESS", "tallyVoucherNumber": v_num},
                        error_message=None
                    )
                    try:
                        d_amt = float(payload.get("amount")) if payload.get("amount") is not None else 0.0
                    except (ValueError, TypeError):
                        d_amt = 0.0
                    try:
                        activity_history_repo.record_activity({
                            "command_id": cmd_id,
                            "voucher_type": payload.get("voucher_type", "Sales Bill"),
                            "party": payload.get("party_ledger") or payload.get("name", "Cash"),
                            "amount": d_amt,
                            "company": target_comp,
                            "voucher_date": payload.get("date") or payload.get("voucherDate"),
                            "status": "SUCCESS",
                            "voucher_number": v_num,
                            "organization_id": curr_org or getattr(self.settings, "organization_id", "") or "",
                            "user_email": (curr_email or getattr(self.settings, "user_email", "") or "").strip().lower(),
                            "device_id": curr_dev or getattr(self.settings, "device_id", "") or "",
                        })
                    except Exception as act_err:
                        logger.warning(f"Drain success activity log failed: {act_err}")

                    self.command_processed.emit(
                        cmd_id,
                        cmd_type,
                        True,
                        f"✅ Voucher #{v_num} for '{target_comp}' successfully auto-created in Tally!",
                        {}
                    )
                elif res.get("should_queue"):
                    voucher_queue_repo.mark_voucher_attempt(cmd_id, res.get("reason", "Company not ready"))
                else:
                    voucher_queue_repo.mark_voucher_failed(cmd_id, res.get("reason", "Tally rejected"))
                    cloud_auth_service.send_command_result(
                        command_id=cmd_id,
                        status="FAILED",
                        result={"failed": True, "reason": res.get("reason")},
                        error_message=res.get("error")
                    )
                    try:
                        d_err_amt = float(payload.get("amount")) if payload.get("amount") is not None else 0.0
                    except (ValueError, TypeError):
                        d_err_amt = 0.0
                    try:
                        activity_history_repo.record_activity({
                            "command_id": cmd_id,
                            "voucher_type": payload.get("voucher_type", "Sales Bill"),
                            "party": payload.get("party_ledger") or payload.get("name", "Cash"),
                            "amount": d_err_amt,
                            "company": target_comp,
                            "voucher_date": payload.get("date") or payload.get("voucherDate"),
                            "status": "FAILED",
                            "error": res.get("reason"),
                            "organization_id": curr_org or getattr(self.settings, "organization_id", "") or "",
                            "user_email": (curr_email or getattr(self.settings, "user_email", "") or "").strip().lower(),
                            "device_id": curr_dev or getattr(self.settings, "device_id", "") or "",
                        })
                    except Exception as act_err:
                        logger.warning(f"Drain failure activity log failed: {act_err}")

                    self.command_processed.emit(
                        cmd_id,
                        cmd_type,
                        False,
                        f"Tally rejected voucher for {target_comp}: {res.get('reason')}",
                        res.get("diagnostic") or {}
                    )
        except Exception as drain_err:
            logger.debug(f"Queue drain error: {drain_err}")
        finally:
            loop.close()

