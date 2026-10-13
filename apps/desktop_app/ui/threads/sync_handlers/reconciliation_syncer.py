from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime, timezone
from pymongo import UpdateOne
from shared.logging_config import get_logger
from shared.db.mongo_client import get_collection
from shared.auth.cloud_auth_service import cloud_auth_service


logger = get_logger("app.threads.sync_handlers.reconciliation")

def reconcile_pending_commands(
    worker,
    c_name: str,
    org_oid,
    c_oid,
    extracted_ledgers: list,
    extracted_stock_items: list,
    extracted_vouchers: list
):
    """
    Auto-reconciles pending/sent 2-way sync commands against extracted Tally data.
    If a Party, Stock Item, or Voucher that was in 'SENT' or 'PENDING' status is
    already confirmed present in Tally Prime, automatically marks it 'DONE' in MongoDB
    and notifies the Cloud Server so the web portal status changes from SENT to DONE.
    """
    try:
        cmd_col = get_collection("commands")
        or_comps: List[Dict[str, Any]] = [
            {"company_name": c_name},
            {"payload.company_name": c_name},
            {"payload.companyName": c_name},
            {"companyName": c_name}
        ]
        if c_oid:
            or_comps.append({"companyId": c_oid})
            or_comps.append({"payload.companyId": c_oid})
            or_comps.append({"payload.companyId": str(c_oid)})
            or_comps.append({"companyId": str(c_oid)})

        q_filter: Dict[str, Any] = {
            "status": {"$in": ["SENT", "PENDING", "WAITING_FOR_TALLY", "QUEUED"]},
            "$or": or_comps
        }
        if org_oid:
            q_filter["organizationId"] = org_oid

        pending_cmds = list(cmd_col.find(q_filter))
        if not pending_cmds:
            return

        logger.info(f"Auto-Reconciling {len(pending_cmds)} pending command(s) for company '{c_name}'...")

        ledger_names = {str(l.get("name") or "").strip().lower() for l in extracted_ledgers if l.get("name")}
        stock_names = {str(s.get("name") or s.get("itemName") or "").strip().lower() for s in extracted_stock_items if s.get("name") or s.get("itemName")}
        voucher_nums = {str(v.get("voucher_number") or v.get("voucherNumber") or "").strip().lower() for v in extracted_vouchers if v.get("voucher_number") or v.get("voucherNumber")}

        now_utc = datetime.now(timezone.utc)
        reconciled_count = 0

        for cmd in pending_cmds:
            cmd_id = str(cmd.get("_id") or cmd.get("id"))
            cmd_type = str(cmd.get("type") or "").upper()
            payload = cmd.get("payload") or {}
            matched = False
            res_payload = {}

            if cmd_type in ("CREATE_PARTY", "CREATE_LEDGER"):
                p_name = str(payload.get("name") or payload.get("partyName") or payload.get("party_name") or payload.get("party_ledger") or "").strip()
                if p_name and p_name.lower() in ledger_names:
                    matched = True
                    res_payload = {
                        "ledgerName": p_name,
                        "partyName": p_name,
                        "status": "SUCCESS",
                        "reconciled": True
                    }

            elif cmd_type in ("CREATE_STOCK_ITEM", "CREATE_ITEM", "UPDATE_STOCK_ITEM", "UPDATE_ITEM", "ALTER_STOCK_ITEM"):
                s_name = str(payload.get("itemName") or payload.get("name") or payload.get("item_name") or "").strip()
                if s_name and s_name.lower() in stock_names:
                    matched = True
                    res_payload = {
                        "itemName": s_name,
                        "status": "SUCCESS",
                        "reconciled": True
                    }

            elif cmd_type in ("CREATE_VOUCHER", "CREATE_RECEIPT", "CREATE_PAYMENT", "CREATE_PURCHASE", "CREATE_SALES_ORDER", "CREATE_PURCHASE_ORDER"):
                v_num = str(payload.get("voucher_number") or payload.get("voucherNumber") or payload.get("invoiceNumber") or "").strip()
                if v_num and v_num.lower() in voucher_nums:
                    matched = True
                    res_payload = {
                        "tallyVoucherNumber": v_num,
                        "status": "SUCCESS",
                        "reconciled": True
                    }

            if matched:
                reconciled_count += 1
                cmd_col.update_one(
                    {"_id": cmd["_id"]},
                    {"$set": {
                        "status": "DONE",
                        "result": res_payload,
                        "errorMessage": None,
                        "completedAt": now_utc,
                        "updatedAt": now_utc
                    }}
                )
                try:
                    cloud_auth_service.send_command_result(
                        command_id=cmd_id,
                        status="DONE",
                        result=res_payload,
                        error_message=None
                    )
                except Exception as c_err:
                    logger.debug(f"Cloud command result notification notice: {c_err}")

                logger.info(f"✅ Reconciled command #{cmd_id} [{cmd_type}] -> DONE (confirmed in Tally)")

        if reconciled_count > 0:
            logger.info(f"Reconciliation complete: {reconciled_count} command(s) updated to DONE for '{c_name}'.")
    except Exception as r_err:
        logger.debug(f"Command reconciliation notice: {r_err}")

