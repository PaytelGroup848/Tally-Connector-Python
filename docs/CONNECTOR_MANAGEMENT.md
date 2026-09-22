# Module 5 Architecture: Production Connector Management

## Overview
Module 5 introduces the **Connector Management System** for the CtrlBooks application.
A Connector represents a configurable pipeline connection between the application and external data sources (**TALLY** and **BUSY**).

---

## Architecture Highlights

1. **State Model Separation**:
   - `configuration_status`: `DRAFT` | `CONFIGURED` | `INVALID`
   - `connection_status`: `UNKNOWN` | `TESTING` | `CONNECTED` | `FAILED` | `NOT_IMPLEMENTED`
   - `is_active`: `Boolean` (`True` / `False`)

2. **Extensible Adapter Registry**:
   - Abstract `BaseConnectorAdapter` interface contract.
   - Central `ConnectorRegistry` mapping connector types (`TALLY`, `BUSY`) to provider adapter classes.
   - Rejects arbitrary user-supplied Python class names.

3. **Type-Specific Configuration Validation**:
   - `TallyConfigurationSchema`: Validates `host`, `port` (1-65535), `company_name`, `connection_mode` (`HTTP_XML`, `ODBC`, `NATIVE`).
   - `BusyConfigurationSchema`: Validates `company_path`, `application_path`, `connection_mode` (`DIRECT_ACCESS`, `MS_SQL`, `API`), database credentials.
   - Secret Masking: Sensitive keys (password, secret, key, token) are masked as `"****"` in list and details APIs.

4. **State Invalidation & Truthful Connection Testing**:
   - Modifying connection parameters automatically resets `connection_status` back to `UNKNOWN`.
   - Connection test endpoint executes truthful socket/path checks without returning fake connection successes.

5. **PySide6 Desktop GUI Integration**:
   - Live Connectors Overview table with type badge, configuration status, connection status badge, active toggle, and test ping button.
   - Dynamic `AddConnectorDialog` modal showing Tally vs BUSY form fields based on selected connector type.

---

## API Summary

| Method | Endpoint | Required Permission | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/connectors` | `connectors.view` | List connectors with pagination, search, type, and status filtering |
| `GET` | `/api/connectors/{id}` | `connectors.view` | Get connector details (secrets masked) |
| `POST` | `/api/connectors` | `connectors.create` | Create new connector pipeline with validated config |
| `PUT` | `/api/connectors/{id}` | `connectors.update` | Update connector config (resets connection status to UNKNOWN) |
| `POST` | `/api/connectors/{id}/activate` | `connectors.activate` | Activate connector pipeline |
| `POST` | `/api/connectors/{id}/deactivate` | `connectors.deactivate` | Deactivate connector pipeline |
| `POST` | `/api/connectors/{id}/test` | `connectors.test` | Execute truthful connection test via adapter |
| `DELETE` | `/api/connectors/{id}` | `connectors.delete` | Soft delete connector pipeline |

---

## Automated Verification
Run full verification suite:
```bash
python scripts/verify_all.py
```
