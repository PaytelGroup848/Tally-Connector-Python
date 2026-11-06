import time
import uuid
from typing import List, Dict, Any, Tuple, Optional

from shared.logging_config import get_logger
from shared.auth.cloud_auth_service import cloud_auth_service
from shared.repositories.company_repository import upsert_company_config
from apps.desktop_app.ui.threads.sync_handlers.common import chunk_list

logger = get_logger("app.threads.sync_handlers.cloud_push")

def validate_batch_response(
    ok_b: bool,
    msg_b: str,
    b_data: Any,
    expected_count: int = 0
) -> Tuple[bool, int, str]:
    """
    Validates Cloud API /sync/batch response payload.

    Rules:
    1. If HTTP / transport failed (ok_b is False), return failure.
    2. Response data must be a JSON object (dict).
    3. Explicit 'success: false' is treated as failure.
    4. Required fields 'upserted' (or 'synced') and 'failed' (or 'failedCount') must exist.
       Missing fields are NOT automatically assumed to be zero.
    5. Counts must be non-negative integers.
    6. If 'failed > 0', return failure (partial batch failure).
    7. If expected_count > 0 and upserted == 0 and failed == 0, return failure (contradictory).
    8. Otherwise, return success with validated upserted count.

    Returns:
        Tuple[bool, int, str]: (is_success, upserted_count, error_description)
    """
    if not ok_b:
        return False, 0, msg_b or "Batch HTTP request failed"

    if not isinstance(b_data, dict):
        return False, 0, f"Invalid batch response format: expected dict, got {type(b_data).__name__}"

    # Unwrap nested data if backend sends {"success": true, "data": {...}}
    inner = b_data.get("data")
    payload: Dict[str, Any] = inner if isinstance(inner, dict) else b_data

    # Check explicit success flag if present
    if b_data.get("success") is False or payload.get("success") is False:
        err = b_data.get("message") or payload.get("message") or b_data.get("error") or "Cloud API returned success=False"
        return False, 0, str(err)

    # Extract raw counts - safely check upserted / synced
    raw_upserted = payload.get("upserted")
    if raw_upserted is None:
        raw_upserted = payload.get("synced")

    raw_failed = payload.get("failed")
    if raw_failed is None:
        raw_failed = payload.get("failedCount")

    # Safe validation: Do NOT automatically assume missing counts are 0
    if raw_upserted is None or raw_failed is None:
        missing = []
        if raw_upserted is None:
            missing.append("upserted")
        if raw_failed is None:
            missing.append("failed")
        return False, 0, f"Batch response missing required count field(s): {', '.join(missing)}"

    try:
        upserted_count = int(raw_upserted)
        failed_count = int(raw_failed)
        if upserted_count < 0 or failed_count < 0:
            return False, 0, f"Invalid negative count: upserted={upserted_count}, failed={failed_count}"
    except (ValueError, TypeError):
        return False, 0, f"Invalid count types: upserted={raw_upserted!r}, failed={raw_failed!r}"

    # If all expected records in this batch were successfully upserted, treat as successful!
    if expected_count > 0 and upserted_count >= expected_count:
        if failed_count > 0:
            logger.info(f"Batch completed: {upserted_count} records upserted (server also noted {failed_count} unmapped/failed records).")
        return True, upserted_count, msg_b or f"Batch synced ({upserted_count} upserted)"

    # Check partial batch failure
    if failed_count > 0:
        err_msg = f"Batch reported {failed_count} failed record(s) (upserted={upserted_count})"
        errors_list = payload.get("errors") or b_data.get("errors")
        if isinstance(errors_list, list) and errors_list:
            first_err = str(errors_list[0])
            err_msg += f": {first_err}"
        return False, upserted_count, err_msg

    # Contradictory check: items sent but 0 upserted and 0 failed
    if expected_count > 0 and upserted_count == 0 and failed_count == 0:
        return False, 0, f"Contradictory batch response: {expected_count} records sent but 0 upserted and 0 failed"

    return True, upserted_count, msg_b or f"Batch synced ({upserted_count} upserted)"

def push_cloud_sync(
    worker,
    c_name: str,
    c_guid: str,
    extracted_ledgers: list,
    extracted_stock_items: list,
    extracted_vouchers: list,
    last_alter_id: int,
    base_pct: int,
    idx: int,
    total_companies: int,
    is_incremental: bool = False,
    company_id: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    is_full_replace: Optional[bool] = None,
    extracted_pl_accounts: Optional[list] = None
) -> Tuple[bool, str]:
    if not cloud_auth_service.access_token:
        return True, "No cloud token (offline mode)"

    total_records = len(extracted_ledgers) + len(extracted_stock_items) + len(extracted_vouchers)
    if is_incremental and total_records == 0:
        worker.progress_changed.emit(base_pct + 90, f"[{idx}/{total_companies}] All cloud records up-to-date.")
        return True, "All cloud records up-to-date."

    if is_full_replace is None:
        is_full_replace = not is_incremental
    sync_type_str = "INITIAL" if is_full_replace else "INCREMENTAL"
    worker.progress_changed.emit(base_pct + 70, f"[{idx}/{total_companies}] Initiating Cloud Sync ({sync_type_str})...")
    sync_ok, sync_msg, s_data = cloud_auth_service.sync_start(
        company_name=c_name,
        company_guid=c_guid,
        sync_type=sync_type_str,
        total_records=total_records,
        metadata={
            "totalLedgers": len(extracted_ledgers),
            "totalStockItems": len(extracted_stock_items),
            "totalVouchers": len(extracted_vouchers),
            "lastAlterId": last_alter_id
        },
        company_id=company_id
    )
    if not sync_ok:
        logger.error(f"Cloud sync session start error for '{c_name}': {sync_msg}")
        msg_str = str(sync_msg or "")
        if "no subscription" in msg_str.lower() or "different email" in msg_str.lower() or "already registered" in msg_str.lower():
            return False, "This company is already registered with a different email address."
        return False, f"Cloud Sync rejected: {sync_msg}"

    sync_id = s_data.get("syncJobId") or s_data.get("syncId") or s_data.get("id") or str(uuid.uuid4())
    any_batch_failed = False
    failed_batches: List[str] = []
    synced_ledgers = 0
    synced_stock = 0
    synced_vouchers = 0

    if extracted_ledgers:
        ledger_chunks = list(chunk_list(extracted_ledgers, 100))
        total_l = len(ledger_chunks)
        for b_idx, chunk in enumerate(ledger_chunks, start=1):
            if worker._is_cancelled:
                return False, "Sync cancelled by user"
            is_last = (b_idx == total_l and not extracted_stock_items and not extracted_vouchers)
            worker.progress_changed.emit(base_pct + 75, f"Pushing Ledgers Batch #{b_idx}/{total_l} ({len(chunk)} items)...")
            ok_b, msg_b, b_data = cloud_auth_service.sync_batch(
                sync_id, c_name, "LEDGER", chunk, b_idx, is_last,
                company_id=company_id,
                sync_type=sync_type_str,
                is_full_replace=is_full_replace,
                start_date=start_date,
                end_date=end_date
            )
            is_valid, count_upserted, err_desc = validate_batch_response(ok_b, msg_b, b_data, expected_count=len(chunk))
            if is_valid:
                synced_ledgers += count_upserted
            else:
                any_batch_failed = True
                failed_batches.append(f"LEDGER #{b_idx}: {err_desc}")
                logger.warning(f"Ledger batch #{b_idx} sync notice for '{c_name}': {err_desc}")
            time.sleep(0.08)

    if extracted_stock_items:
        stock_chunks = list(chunk_list(extracted_stock_items, 100))
        total_s = len(stock_chunks)
        for b_idx, chunk in enumerate(stock_chunks, start=1):
            if worker._is_cancelled:
                return False, "Sync cancelled by user"
            is_last = (b_idx == total_s and not extracted_vouchers)
            worker.progress_changed.emit(base_pct + 80, f"Pushing Stock Batch #{b_idx}/{total_s} ({len(chunk)} items)...")
            ok_b, msg_b, b_data = cloud_auth_service.sync_batch(
                sync_id, c_name, "STOCK", chunk, b_idx, is_last,
                company_id=company_id,
                sync_type=sync_type_str,
                is_full_replace=is_full_replace,
                start_date=start_date,
                end_date=end_date
            )
            is_valid, count_upserted, err_desc = validate_batch_response(ok_b, msg_b, b_data, expected_count=len(chunk))
            if is_valid:
                synced_stock += count_upserted
            else:
                any_batch_failed = True
                failed_batches.append(f"STOCK #{b_idx}: {err_desc}")
                logger.warning(f"Stock batch #{b_idx} sync notice for '{c_name}': {err_desc}")
            time.sleep(0.08)

    if extracted_vouchers:
        # Prepare PL data structure if present to attach directly to vouchers
        pl_data = None
        if extracted_pl_accounts:
            purchase_acc = next((item for item in extracted_pl_accounts if item.get("category") == "PURCHASE_ACCOUNTS"), {})
            sales_acc = next((item for item in extracted_pl_accounts if item.get("category") == "SALES_ACCOUNTS"), {})
            direct_exp = next((item for item in extracted_pl_accounts if item.get("category") == "DIRECT_EXPENSES"), {})
            indirect_exp = next((item for item in extracted_pl_accounts if item.get("category") == "INDIRECT_EXPENSES"), {})
            direct_inc = next((item for item in extracted_pl_accounts if item.get("category") == "DIRECT_INCOMES"), {})
            indirect_inc = next((item for item in extracted_pl_accounts if item.get("category") == "INDIRECT_INCOMES"), {})
            summary_acc = next((item for item in extracted_pl_accounts if item.get("category") == "PL_SUMMARY"), {})
            pl_data = {
                "purchaseAccounts": purchase_acc,
                "salesAccounts": sales_acc,
                "directExpenses": direct_exp,
                "indirectExpenses": indirect_exp,
                "directIncomes": direct_inc,
                "indirectIncomes": indirect_inc,
                "plSummary": summary_acc,
                "plAccounts": extracted_pl_accounts
            }

        # Build comprehensive P&L ledger map from extracted PL accounts & ledgers
        from shared.cloud.voucher_group_resolver import build_pl_ledger_group_map, resolve_voucher_group

        pl_ledger_map = build_pl_ledger_group_map(
            extracted_pl_accounts=extracted_pl_accounts,
            extracted_ledgers=extracted_ledgers,
            pl_data=pl_data
        )

        # Pre-assign exact voucherGroup to every voucher based on its ledger lines
        for v in extracted_vouchers:
            if isinstance(v, dict):
                v_grp = resolve_voucher_group(v, pl_ledger_map=pl_ledger_map)
                v["voucherGroup"] = v_grp
                if "raw" in v and isinstance(v["raw"], dict):
                    v["raw"]["voucherGroup"] = v_grp

        # 25 vouchers per chunk + 250ms backpressure pause to prevent cloud server memory exhaustion
        voucher_chunks = list(chunk_list(extracted_vouchers, 25))
        total_v = len(voucher_chunks)
        for b_idx, chunk in enumerate(voucher_chunks, start=1):
            if worker._is_cancelled:
                return False, "Sync cancelled by user"
            is_last = (b_idx == total_v)
            worker.progress_changed.emit(base_pct + 85, f"Pushing Vouchers Batch #{b_idx}/{total_v} ({len(chunk)} items)...")
            ok_b, msg_b, b_data = cloud_auth_service.sync_batch(
                sync_id, c_name, "VOUCHER", chunk, b_idx, is_last,
                company_id=company_id,
                sync_type=sync_type_str,
                is_full_replace=is_full_replace,
                start_date=start_date,
                end_date=end_date,
                pl_data=pl_data
            )
            is_valid, count_upserted, err_desc = validate_batch_response(ok_b, msg_b, b_data, expected_count=len(chunk))
            if is_valid:
                synced_vouchers += count_upserted
            else:
                any_batch_failed = True
                failed_batches.append(f"VOUCHER #{b_idx}: {err_desc}")
                logger.warning(f"Voucher batch #{b_idx} sync notice for '{c_name}': {err_desc}")
            time.sleep(0.25)

    total_synced = synced_ledgers + synced_stock + synced_vouchers
    final_status = "COMPLETED" if not any_batch_failed else "FAILED"
    if any_batch_failed:
        logger.error(f"Cloud sync completed with failures for '{c_name}': {len(failed_batches)} batches failed: {failed_batches[:3]}")
    else:
        logger.info(f"Cloud sync completed successfully for '{c_name}': {total_synced}/{total_records} records pushed.")

    cloud_auth_service.sync_complete(
        sync_id=sync_id,
        company_name=c_name,
        status=final_status,
        total_synced=total_synced,
        last_alter_id=last_alter_id,
        summary={
            "ledgersSynced": synced_ledgers,
            "stockItemsSynced": synced_stock,
            "vouchersSynced": synced_vouchers,
            "totalRecords": total_records,
            "errors": failed_batches[:10] if failed_batches else []
        }
    )

    if any_batch_failed:
        err_summary = "; ".join(failed_batches[:2])
        return False, f"Cloud sync incomplete: {len(failed_batches)} batch(es) failed ({err_summary})"

    return True, f"Successfully pushed {total_synced} records to Cloud."

