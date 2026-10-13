

# pyright: reportGeneralTypeIssues=false
import time
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from bson import ObjectId
from PySide6.QtCore import QThread, Signal
from shared.auth.cloud_auth_service import cloud_auth_service
from shared.logging_config import get_logger
from shared.db.mongo_client import get_collection
from shared.repositories.activity_history_repository import activity_history_repo
from shared.repositories.voucher_queue_repository import voucher_queue_repo
from apps.backend.services.importer_service import ImporterService
from apps.desktop_app.ui.threads.command_handlers import (
    execute_voucher_command,
    execute_party_command,
    execute_create_stock_item_command,
    execute_update_stock_item_command,
)

logger = get_logger("app.threads.command_worker")

class RemoteCommandWorker(QThread):
    command_received = Signal(str, str)
    command_processed = Signal(str, str, bool, str, dict)
    config_updated = Signal(dict)

    def __init__(self, poll_interval_seconds: int = 15, parent=None):
        super().__init__(parent)
        from shared.config import get_settings
        self.settings = get_settings()
        self.poll_interval = poll_interval_seconds
        self._is_running = True
        self.importer_service = ImporterService()
        self.last_heartbeat_time: float = 0.0
        self.heartbeat_interval_seconds: float = 30.0

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
                # 1. Periodic presence heartbeat to Cloud Server (keeps web status ONLINE)
                now = time.time()
                if now - self.last_heartbeat_time >= self.heartbeat_interval_seconds:
                    self.last_heartbeat_time = now
                    try:
                        ok, hb_msg, hb_data = cloud_auth_service.send_heartbeat()
                        if ok:
                            logger.debug(f"Heartbeat sent to cloud: {hb_msg} (Tally: {hb_data.get('tallyConnected')})")
                    except Exception as exc:
                        logger.debug(f"Heartbeat cycle notice: {exc}")

                # 2. Remote command polling
                try:
                    self._poll_and_execute_commands()
                except Exception as exc:
                    logger.warning(f"Error in remote command cycle: {exc}")

                # 3. Drain pending voucher queue
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
                # Don't drop commands created from web browser or without hardware binding
                if str(cmd_dev).strip().lower() not in ("web", "browser", "portal", "cloud", "all", "none", "", "null", "undefined"):
                    logger.info(f"Skipping command #{cmd_id}: deviceId mismatch (cmd={cmd_dev}, active={curr_dev})")
                    continue

            cmd_email = cmd.get("email") or cmd.get("userEmail") or payload.get("email") or payload.get("userEmail")
            if cmd_email and curr_email and str(cmd_email).strip().lower() != str(curr_email).strip().lower():
                # Allow teammates in the same organization
                if not (cmd_org and curr_org and str(cmd_org) == str(curr_org)):
                    logger.info(f"Skipping command #{cmd_id}: email mismatch (cmd={cmd_email}, active={curr_email})")
                    continue

            self.command_received.emit(cmd_id, cmd_type)
            logger.info(f"Processing command #{cmd_id} [{cmd_type}]...")

            success = False
            result_data = {}
            error_msg = None
            error_details = {}
            resolved_company: str = ""
            active_host: str = str(getattr(self.settings, "tally_host", "localhost") or "localhost")
            active_port: int = int(getattr(self.settings, "tally_port", 9000) or 9000)
            amt: float = 0.0
            norm_payload: Dict[str, Any] = dict(payload)

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
                if raw_comp and str(raw_comp).strip().lower() not in ("none", "null", "undefined", ""):
                    resolved_company = str(raw_comp).strip()

                if not resolved_company and comp_id:
                    try:
                        from shared.db.mongo_client import get_mongo_db
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

                from shared.connection_config import resolve_active_tally_port
                cmd_host = payload.get("host") or payload.get("tally_host") or cmd.get("host") or cmd.get("tally_host")
                cmd_port = payload.get("port") or payload.get("tally_port") or cmd.get("port") or cmd.get("tally_port")
                active_host, active_port = resolve_active_tally_port(preferred_port=cmd_port, preferred_host=cmd_host)

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
                    norm_payload, success, result_data, error_msg, error_details, should_continue = execute_voucher_command(
                        worker=self,
                        payload=payload,
                        cmd=cmd,
                        cmd_id=cmd_id,
                        cmd_type=cmd_type,
                        comp_id=comp_id,
                        resolved_company=resolved_company,
                        active_host=active_host,
                        active_port=active_port,
                        amt=amt,
                        curr_email=curr_email,
                        curr_org=curr_org,
                    )
                    if should_continue:
                        continue

                elif cmd_type in ("CREATE_LEDGER", "CREATE_PARTY", "CREATE_CUSTOMER", "CREATE_SUPPLIER", "CREATE_VENDOR"):
                    norm_payload, success, result_data, error_msg, error_details = execute_party_command(
                        payload=payload,
                        cmd=cmd,
                        cmd_id=cmd_id,
                        cmd_type=cmd_type,
                        comp_id=comp_id,
                        resolved_company=resolved_company,
                        active_host=active_host,
                        active_port=active_port,
                        importer_service=self.importer_service,
                    )

                elif cmd_type in ("CREATE_STOCK_ITEM", "CREATE_ITEM"):
                    norm_payload, success, result_data, error_msg = execute_create_stock_item_command(
                        payload=payload,
                        cmd=cmd,
                        comp_id=comp_id,
                        resolved_company=resolved_company,
                        active_host=active_host,
                        active_port=active_port,
                        importer_service=self.importer_service,
                    )

                elif cmd_type in ("UPDATE_STOCK_ITEM", "UPDATE_ITEM", "ALTER_STOCK_ITEM"):
                    norm_payload, success, result_data, error_msg = execute_update_stock_item_command(
                        payload=payload,
                        comp_id=comp_id,
                        resolved_company=resolved_company,
                        importer_service=self.importer_service,
                    )

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
                    err_card_amt: float = 0.0
                    try:
                        if "amt" in locals() and amt is not None:
                            err_card_amt = float(amt)
                    except (ValueError, TypeError):
                        err_card_amt = 0.0

                    error_details = {
                        "voucher_type": cmd_type,
                        "voucher_number": "N/A",
                        "company": resolved_company or "Active Company",
                        "party": "N/A",
                        "amount": err_card_amt,
                        "date": "N/A",
                        "reason": f"Execution Error: {e}",
                        "action": f"Verify that Tally Prime is running on port {active_port if 'active_port' in locals() else 'configured port'} and accessible.",
                        "technical_error": str(e),
                        "cmd_id": cmd_id,
                        "cmd_type": cmd_type
                    }

            try:
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
                    "organization_id": curr_org or cmd.get("organizationId") or cmd.get("organization_id") or getattr(self.settings, "organization_id", "") or cloud_auth_service.organization_id or "",
                    "user_email": (curr_email or cmd.get("email") or getattr(self.settings, "user_email", "") or cloud_auth_service.email or "").strip().lower(),
                    "device_id": curr_dev or cmd.get("deviceId") or getattr(self.settings, "device_id", "") or cloud_auth_service.device_id or "",
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
                cmd_col = get_collection("commands")
                if ObjectId.is_valid(cmd_id):
                    cmd_col.update_one(
                        {"_id": ObjectId(cmd_id)},
                        {"$set": {
                            "status": status_str,
                            "result": result_payload,
                            "resultPayload": result_payload,
                            "tallyExternalId": result_payload.get("tallyExternalId") if isinstance(result_payload, dict) else None,
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
        curr_dev = getattr(cloud_auth_service, "device_id", None) or getattr(self.settings, "device_id", "")

        pending_items = voucher_queue_repo.get_pending_vouchers(organization_id=curr_org, user_email=curr_email)
        if not pending_items:
            return

        from shared.connection_config import resolve_active_tally_port
        drain_host, drain_port = resolve_active_tally_port()

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            is_online, _, open_companies = loop.run_until_complete(
                self.importer_service.tally_importer.check_tally_company_status(drain_host, drain_port, "")
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

                cmd_id = str(item.get("cmd_id") or "")
                if not cmd_id:
                    continue
                payload: dict = item.get("payload") or {}
                payload["host"] = drain_host
                payload["port"] = drain_port
                payload["tally_host"] = drain_host
                payload["tally_port"] = drain_port
                cmd_type = str(item.get("cmd_type", "CREATE_VOUCHER"))
                logger.info(f"Draining pending voucher #{cmd_id} for newly opened company '{target_comp}' on {drain_host}:{drain_port}...")

                res = loop.run_until_complete(self.importer_service.import_voucher(payload))
                if res.get("status") == "SUCCESS":
                    v_num = str(res.get("voucher_number") or "SUCCESS")
                    v_ext = res.get("tallyExternalId") or res.get("guid") or v_num
                    voucher_queue_repo.mark_voucher_completed(cmd_id, v_num)
                    cloud_auth_service.send_command_result(
                        command_id=cmd_id,
                        status="DONE",
                        result={"status": "SUCCESS", "tallyVoucherNumber": v_num, "tallyExternalId": v_ext, "guid": v_ext},
                        error_message=None
                    )
                    d_amt: float = 0.0
                    try:
                        raw_d_amt = payload.get("amount")
                        if raw_d_amt is not None:
                            d_amt = float(raw_d_amt)
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
                            "organization_id": curr_org or getattr(self.settings, "organization_id", "") or cloud_auth_service.organization_id or "",
                            "user_email": (curr_email or getattr(self.settings, "user_email", "") or cloud_auth_service.email or "").strip().lower(),
                            "device_id": curr_dev or getattr(self.settings, "device_id", "") or cloud_auth_service.device_id or "",
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
                    voucher_queue_repo.mark_voucher_attempt(cmd_id, str(res.get("reason", "Company not ready")))
                else:
                    voucher_queue_repo.mark_voucher_failed(cmd_id, str(res.get("reason", "Tally rejected")))
                    cloud_auth_service.send_command_result(
                        command_id=cmd_id,
                        status="FAILED",
                        result={"failed": True, "reason": res.get("reason")},
                        error_message=res.get("error")
                    )
                    d_err_amt: float = 0.0
                    try:
                        raw_err_amt = payload.get("amount")
                        if raw_err_amt is not None:
                            d_err_amt = float(raw_err_amt)
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
                            "organization_id": curr_org or getattr(self.settings, "organization_id", "") or cloud_auth_service.organization_id or "",
                            "user_email": (curr_email or getattr(self.settings, "user_email", "") or cloud_auth_service.email or "").strip().lower(),
                            "device_id": curr_dev or getattr(self.settings, "device_id", "") or cloud_auth_service.device_id or "",
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

