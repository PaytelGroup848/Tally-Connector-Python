# CtrlBooks — Database Foundation & Persistence Layer (Module 2)

This document details the production-ready database architecture, ORM schema models, repository access pattern, and Alembic migration system established in **Module 2**.

---

## 1. Database Strategy & Environment Architecture

- **Development Engine**: SQLite (`sqlite:///data/ctrlbooks.db`) with Write-Ahead Logging (`PRAGMA journal_mode=WAL;`) and foreign key enforcement on connection.
- **Production Engine**: PostgreSQL (or MySQL / SQL Server) configured via `DATABASE_URL`.
- **Connection Management**:
  - `QueuePool` for production database servers with configurable `DATABASE_POOL_SIZE` (default 5), `DATABASE_MAX_OVERFLOW` (10), and `DATABASE_POOL_TIMEOUT` (30s).
  - Thread-safe session context manager `get_db_session()` and FastAPI dependency `get_db()` with automatic commit, rollback safety, and session cleanup.

---

## 2. Core Schema Entities (14 Tables)

All tables use UTC timezone-aware timestamps (`created_at`, `updated_at`), indexed foreign keys, constraints, and string UUID primary keys (`id`).

| Entity Table | Primary Key | Description & Key Columns |
|---|---|---|
| **`users`** | UUID | User identity foundation (`full_name`, `email`, `mobile`, `password_hash`, `status`, `last_login_at`). |
| **`roles`** | UUID | System roles (`name`, `description`). |
| **`user_roles`** | UUID | User role assignment junction (`user_id`, `role_id`). |
| **`connectors`** | UUID | Connector metadata (`name`, `connector_type`, `status`, `is_active`, `source_id`, `destination_id`, `last_sync_at`, `deleted_at`). Supports soft delete. |
| **`data_sources`** | UUID | Source configurations (`name`, `source_type`, `status`, `configuration_json`, `deleted_at`). Supports soft delete and secret masking. |
| **`destinations`** | UUID | Target sync destinations (`name`, `destination_type`, `status`, `configuration_json`, `deleted_at`). Supports soft delete and secret masking. |
| **`field_mappings`** | UUID | Source to target field mappings (`connector_id`, `source_field`, `destination_field`, `transform_rule`, `is_required`). |
| **`sync_jobs_v2`** | UUID | Sync execution tracking (`connector_id`, `status`, `started_at`, `completed_at`, `records_read`, `records_processed`, `records_success`, `records_failed`, `error_message`). |
| **`sync_errors`** | UUID | Record-level sync failure logs (`job_id`, `record_reference`, `error_code`, `error_message`, `retry_count`). |
| **`activity_logs`** | UUID | User and connector audit history (`user_id`, `connector_id`, `event_type`, `status`, `message`, `request_id`). |
| **`notifications`** | UUID | Application notifications (`user_id`, `severity`, `title`, `message`, `is_read`, `read_at`). |
| **`application_settings`** | UUID | Application settings (`scope`, `key`, `value_json`, `updated_by`). Unique per `(scope, key)`. |
| **`health_history`** | UUID | Monitoring history (`component`, `status`, `latency_ms`, `details_json`, `checked_at`). |
| **`sync_checkpoints`** | UUID | Incremental sync state (`connector_id`, `entity_name`, `checkpoint_value`, `last_processed_at`). |

---

## 3. Data Access & Repository Pattern

All models are accessed through type-safe repository classes extending `BaseRepository[T]`:

```python
from shared.db.session import get_db_session
from shared.repositories import UserRepository, ConnectorRepository

with get_db_session() as db:
    user_repo = UserRepository()
    user = user_repo.get_by_email(db, "admin@example.com")
```

### Key Repository Features:
1. **Soft Delete Filtering**: Queries on soft-deletable entities (`connectors`, `data_sources`, `destinations`) exclude soft-deleted items by default.
2. **Transaction Rollback Safety**: Any database integrity violation or exception automatically triggers a rollback and raises a clean domain exception (`ConflictException`, `ValidationError`, `AppException`).
3. **Secret Protection**: Data source and destination configurations provide `get_configuration(mask_secrets=True)` sanitizing passwords and API keys.

---

## 4. Alembic Migrations

Alembic configuration is initialized in `alembic.ini` and `shared/db/migrations/`:

### Create a Naming Migration
```powershell
alembic revision -m "add_new_feature_table"
```

### Apply Migrations
```powershell
alembic upgrade head
```

### Startup Automatic Initialization
Application startup automatically invokes `shared.database.initialize_database()`, executing ORM table initialization and safe forward schema creation without dropping existing tables.

---

## 5. Environment Variables for Database

Add database settings to `.env`:

```ini
# PostgreSQL (Production) or SQLite (Development)
DATABASE_URL=sqlite:///data/ctrlbooks.db

DATABASE_POOL_SIZE=5
DATABASE_MAX_OVERFLOW=10
DATABASE_POOL_TIMEOUT=30
```
