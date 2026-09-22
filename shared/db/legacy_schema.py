"""
CtrlBooks - Legacy SQLite DDL Schema Initialization
----------------------------------------------------------------
Provides legacy SQLite table creation scripts for backward compatibility.
Must strictly stay under 150 lines of code.
"""

LEGACY_SQLITE_DDL = """
CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    name TEXT NOT NULL,
    data_path TEXT,
    host TEXT,
    port INTEGER,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS normalized_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    record_type TEXT NOT NULL,
    external_id TEXT NOT NULL,
    company_name TEXT NOT NULL,
    canonical_json TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    normalized_at TEXT NOT NULL,
    UNIQUE(source, record_type, external_id, company_name)
);

CREATE TABLE IF NOT EXISTS change_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    source TEXT NOT NULL,
    record_type TEXT NOT NULL,
    external_id TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    previous_fingerprint TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    level TEXT NOT NULL,
    service TEXT NOT NULL,
    action TEXT NOT NULL,
    message TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sync_jobs (
    job_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    company_name TEXT NOT NULL,
    state TEXT NOT NULL,
    progress INTEGER NOT NULL,
    message TEXT NOT NULL,
    stats_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS event_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL
);
"""

def apply_auto_migrations(conn):
    """Executes safe ALTER TABLE migrations for SQLite columns."""
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(users);")
    u_cols = [row["name"] for row in cursor.fetchall()]
    if u_cols and "username" not in u_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN username VARCHAR(100);")
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_username ON users (username);")

    cursor.execute("PRAGMA table_info(connectors);")
    c_cols = [row["name"] for row in cursor.fetchall()]
    if c_cols:
        for col, col_def in [
            ("description", "VARCHAR(255)"),
            ("configuration_json", "TEXT"),
            ("configuration_status", "VARCHAR(50) DEFAULT 'DRAFT'"),
            ("connection_status", "VARCHAR(50) DEFAULT 'UNKNOWN'"),
            ("last_tested_at", "DATETIME"),
            ("last_connected_at", "DATETIME"),
            ("last_error_message", "TEXT"),
            ("updated_by", "VARCHAR(36)")
        ]:
            if col not in c_cols:
                cursor.execute(f"ALTER TABLE connectors ADD COLUMN {col} {col_def};")
    conn.commit()
