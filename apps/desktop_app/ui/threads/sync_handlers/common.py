"""
Common helper utilities for background sync handlers.
"""
from shared.logging_config import get_logger

logger = get_logger("app.threads.sync_handlers.common")


def chunk_list(lst: list, chunk_size: int = 101):
    for i in range(0, len(lst), chunk_size):
        yield lst[i:i + chunk_size]


def safe_bulk_write(col, ops: list, chunk_size: int = 250):
    if not ops:
        return
    for chunk in chunk_list(ops, chunk_size):
        try:
            col.bulk_write(chunk, ordered=False)
        except Exception as exc:
            logger.debug(f"MongoDB write batch note for {getattr(col, 'name', 'col')}: {exc}")

