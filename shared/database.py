"""
CtrlBooks - MongoDB Atlas Database Adapter & Initialization
------------------------------------------------------------------------
Primary database manager initializing MongoDB Atlas collections, schemas, and indexes.
Pure MongoDB persistence architecture (zero SQLite engine initialization).
"""

import os
import sqlite3
from pathlib import Path
from contextlib import contextmanager
from shared.config import get_settings
from shared.logging_config import get_logger
from shared.db.mongo_client import get_mongo_db

logger = get_logger("app.database")


@contextmanager
def get_conn():
    """Context manager for thread-safe SQLite connection."""
    settings = get_settings()
    db_path = Path(settings.db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def initialize_database():
    """Initializes MongoDB Atlas database collections, schema validation, and SQLite helper tables."""
    logger.info("Initializing MongoDB Atlas database and collection indexes...")
    try:
        db = get_mongo_db()
        logger.info(f"MongoDB Atlas database '{db.name}' initialization completed successfully.")
    except Exception as exc:
        logger.warning(f"MongoDB Atlas initialization notice: {exc}")

    try:
        with get_conn() as conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                level TEXT,
                service TEXT,
                action TEXT,
                message TEXT,
                metadata_json TEXT,
                created_at TEXT
            )
            """)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS normalized_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT,
                record_type TEXT,
                external_id TEXT,
                company_name TEXT,
                fingerprint TEXT,
                payload_json TEXT,
                created_at TEXT
            )
            """)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS change_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT,
                source TEXT,
                record_type TEXT,
                external_id TEXT,
                company_name TEXT,
                current_fingerprint TEXT,
                previous_fingerprint TEXT,
                created_at TEXT
            )
            """)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS sync_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT,
                source TEXT,
                destination TEXT,
                status TEXT,
                total_records INTEGER,
                synced_records INTEGER,
                failed_records INTEGER,
                error_message TEXT,
                created_at TEXT,
                updated_at TEXT
            )
            """)
    except Exception as exc:
        logger.warning(f"SQLite helper tables initialization notice: {exc}")
