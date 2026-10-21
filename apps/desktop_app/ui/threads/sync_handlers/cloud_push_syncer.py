import time
import uuid
from typing import List, Dict, Any, Tuple, Optional

from shared.logging_config import get_logger
from shared.auth.cloud_auth_service import cloud_auth_service
from shared.repositories.company_repository import upsert_company_config
from apps.desktop_app.ui.threads.sync_handlers.common import chunk_list

logger = get_logger("app.threads.sync_handlers.cloud_push")

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
    is_incremental: bool = False
):
    if not cloud_auth_service.access_token:
        return

    total_records = len(extracted_ledgers) + len(extracted_stock_items) + len(extracted_vouchers)
    if is_incremental and total_records == 0:
        worker.progress_changed.emit(base_pct + 90, f"[{idx}/{total_companies}] All cloud records up-to-date.")
        return

    sync_type_str = "INCREMENTAL" if is_incremental else "FULL"
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
        }
    )
    if not sync_ok:
        logger.warning(f"Cloud sync session start warning for '{c_name}': {sync_msg}")

    sync_id = (s_data.get("syncJobId") or s_data.get("syncId") or s_data.get("id") or str(uuid.uuid4())) if sync_ok else str(uuid.uuid4())
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
                return
            is_last = (b_idx == total_l and not extracted_stock_items and not extracted_vouchers)
            worker.progress_changed.emit(base_pct + 75, f"Pushing Ledgers Batch #{b_idx}/{total_l} ({len(chunk)} items)...")
            ok_b, msg_b, _ = cloud_auth_service.sync_batch(sync_id, c_name, "LEDGER", chunk, b_idx, is_last)
            if ok_b:
                synced_ledgers += len(chunk)
            else:
                any_batch_failed = True
                failed_batches.append(f"LEDGER #{b_idx}: {msg_b}")
                logger.warning(f"Ledger batch #{b_idx} sync notice for '{c_name}': {msg_b}")
            time.sleep(0.08)

    if extracted_stock_items:
        stock_chunks = list(chunk_list(extracted_stock_items, 100))
        total_s = len(stock_chunks)
        for b_idx, chunk in enumerate(stock_chunks, start=1):
            if worker._is_cancelled:
                return
            is_last = (b_idx == total_s and not extracted_vouchers)
            worker.progress_changed.emit(base_pct + 80, f"Pushing Stock Batch #{b_idx}/{total_s} ({len(chunk)} items)...")
            ok_b, msg_b, _ = cloud_auth_service.sync_batch(sync_id, c_name, "STOCK", chunk, b_idx, is_last)
            if ok_b:
                synced_stock += len(chunk)
            else:
                any_batch_failed = True
                failed_batches.append(f"STOCK #{b_idx}: {msg_b}")
                logger.warning(f"Stock batch #{b_idx} sync notice for '{c_name}': {msg_b}")
            time.sleep(0.08)

    if extracted_vouchers:
        # 25 vouchers per chunk + 250ms backpressure pause to prevent cloud server memory exhaustion
        voucher_chunks = list(chunk_list(extracted_vouchers, 25))
        total_v = len(voucher_chunks)
        for b_idx, chunk in enumerate(voucher_chunks, start=1):
            if worker._is_cancelled:
                return
            is_last = (b_idx == total_v)
            worker.progress_changed.emit(base_pct + 85, f"Pushing Vouchers Batch #{b_idx}/{total_v} ({len(chunk)} items)...")
            ok_b, msg_b, _ = cloud_auth_service.sync_batch(sync_id, c_name, "VOUCHER", chunk, b_idx, is_last)
            if ok_b:
                synced_vouchers += len(chunk)
            else:
                any_batch_failed = True
                failed_batches.append(f"VOUCHER #{b_idx}: {msg_b}")
                logger.warning(f"Voucher batch #{b_idx} sync notice for '{c_name}': {msg_b}")
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

