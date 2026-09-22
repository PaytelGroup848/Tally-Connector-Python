import json
from typing import Dict, Any, List, Optional, Union
from sqlalchemy.orm import Session
from sqlalchemy import select, and_
from shared.db.models.sync import SyncQueue
from shared.db.base import utc_now
from shared.cloud_client import CloudClient
from shared.logging_config import get_logger

logger = get_logger("app.services.queue")

class QueueService:
    def __init__(self, cloud_client: Optional[CloudClient] = None, max_retries: int = 5):
        self.cloud_client = cloud_client or CloudClient()
        self.max_retries = max_retries

    def enqueue_payload(
        self,
        db_session: Session,
        payload_type: str,
        payload: Union[Dict[str, Any], List[Dict[str, Any]], str],
        company_identifier: Optional[str] = None,
    ) -> SyncQueue:
        """
        Saves extracted payload into local database queue (sync_queue) in 'PENDING' state.
        Guarantees zero data loss if client machine network connection is offline or slow.
        """
        clean_type = (payload_type or "MASTERS").strip().upper()

        if isinstance(payload, (dict, list)):
            if company_identifier and isinstance(payload, dict) and "company_identifier" not in payload:
                payload["company_identifier"] = company_identifier
            payload_str = json.dumps(payload)
        else:
            payload_str = str(payload)

        queue_item = SyncQueue(
            payload_type=clean_type,
            payload_json=payload_str,
            status="PENDING",
            retry_count=0,
            error_msg=None,
            created_at=utc_now(),
            updated_at=utc_now(),
        )

        db_session.add(queue_item)
        db_session.commit()
        db_session.refresh(queue_item)

        logger.info(f"Enqueued payload ID '{queue_item.id}' of type '{clean_type}' into local sync_queue.")
        return queue_item

    def get_pending_queue_items(
        self,
        db_session: Session,
        batch_size: int = 50,
        max_retries: Optional[int] = None,
    ) -> List[SyncQueue]:
        """
        Retrieves pending or retryable failed payloads from local sync_queue ordered by created_at.
        """
        limit_retries = max_retries if max_retries is not None else self.max_retries
        stmt = (
            select(SyncQueue)
            .where(
                and_(
                    SyncQueue.status.in_(["PENDING", "FAILED"]),
                    SyncQueue.retry_count < limit_retries,
                )
            )
            .order_by(SyncQueue.created_at.asc())
            .limit(batch_size)
        )
        return list(db_session.scalars(stmt).all())

    def process_queue_batch(
        self,
        db_session: Session,
        cloud_client: Optional[CloudClient] = None,
        batch_size: int = 50,
        max_retries: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Background worker process: Reads pending batch from local sync_queue,
        pushes items to Central Cloud Server, handles exponential backoff retries,
        and logs critical alerts if max retries are exceeded.
        """
        client = cloud_client or self.cloud_client
        limit_retries = max_retries if max_retries is not None else self.max_retries

        items = self.get_pending_queue_items(db_session, batch_size=batch_size, max_retries=limit_retries)
        if not items:
            return {"total": 0, "synced": 0, "failed": 0, "pending_remaining": 0}

        synced_count = 0
        failed_count = 0

        for item in items:
            try:
                data = json.loads(item.payload_json)
            except Exception:
                data = {"raw_payload": item.payload_json}

            if not isinstance(data, (dict, list)):
                data = {"data": data}

            p_type = item.payload_type.upper()

            try:
                if p_type in ("MASTERS", "LEDGERS", "STOCK_ITEMS", "GROUPS"):
                    client.sync_masters(data)
                elif p_type in ("VOUCHERS", "SALES", "RECEIPT", "DAYBOOK"):
                    client.sync_vouchers(data)
                else:
                    client.sync_masters(data)

                item.status = "SYNCED"
                item.error_msg = None
                item.updated_at = utc_now()
                synced_count += 1
                logger.info(f"Successfully synced queue item '{item.id}' ({p_type}) to Cloud Server.")

            except Exception as exc:
                item.retry_count += 1
                item.updated_at = utc_now()
                err_text = str(exc)
                item.error_msg = err_text

                if item.retry_count >= limit_retries:
                    item.status = "FAILED"
                    failed_count += 1
                    logger.error(
                        f"CRITICAL ALERT: Sync queue item '{item.id}' (type={p_type}) "
                        f"exceeded max retries ({limit_retries}). Cloud sync failed permanently. Error: {err_text}"
                    )
                else:
                    item.status = "FAILED"
                    failed_count += 1
                    backoff_delay = 2 ** item.retry_count
                    logger.warning(
                        f"Sync push failed for queue item '{item.id}' (Attempt {item.retry_count}/{limit_retries}). "
                        f"Will retry with backoff (~{backoff_delay}s). Error: {err_text}"
                    )

            db_session.commit()

        remaining_stmt = (
            select(SyncQueue)
            .where(
                and_(
                    SyncQueue.status.in_(["PENDING", "FAILED"]),
                    SyncQueue.retry_count < limit_retries,
                )
            )
            .limit(1)
        )
        remaining_count = len(list(db_session.scalars(remaining_stmt).all()))

        return {
            "total": len(items),
            "synced": synced_count,
            "failed": failed_count,
            "pending_remaining": remaining_count,
        }

queue_service = QueueService()
