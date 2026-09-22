# Module 6 Architecture: Production TallyPrime Connector Integration

## Overview
Module 6 implements the **TallyPrime Connector Integration** layer. It enables real HTTP/XML communication with local or remote TallyPrime / Tally ERP 9 environments without fake connection successes, fake companies, or hardcoded mock accounting data.

---

## Layered Architecture

```
API Layer (/api/connectors/{id}/tally/*)
   ↓
Tally Service (tally_service.py)
   ↓
Tally Adapter (TallyConnectorAdapter)
   ↓
Tally Client (tally_client.py)
   ↓
Request Builder (request_builder.py) & Response Parser (response_parser.py)
   ↓
TallyPrime HTTP Endpoint (http://host:port/)
```

---

## Core Components

1. **Request Builder (`request_builder.py`)**:
   - Centralized TDL Envelope generator.
   - Maps metadata allow-list (`companies`, `groups`, `ledgers`, `voucher_types`, `cost_centres`, `godowns`, `stock_groups`, `stock_categories`, `units`).
   - Supports active company scope (`<STATICVARIABLES><SVCURRENTCOMPANY>Company Name</SVCURRENTCOMPANY></STATICVARIABLES>`).

2. **Response Parser (`response_parser.py`)**:
   - Safe XML parsing avoiding XXE vulnerabilities.
   - Detects malformed XML, `<LINEERROR>`, and status error codes.
   - Normalizes company and metadata objects into Python dictionaries.

3. **HTTP Client (`tally_client.py`)**:
   - `httpx.AsyncClient` with connect timeout (5s), read timeout (10s), and bounded retries (max 1 retry).
   - SSRF safety guards: Host IP/domain validation (rejecting protocol schemes or path traversal).

4. **Company Discovery & Selection (`tally_service.py`)**:
   - `get_tally_companies()`: Queries running Tally instance and returns open company list.
   - `select_tally_company()`: Re-validates company against real Tally list before saving into connector config JSON, invalidating dependent metadata, and recording audit event `TALLY_COMPANY_SELECTED`.

5. **Metadata Discovery**:
   - `get_tally_metadata()`: Validates allow-list parameter, queries real Tally instance via adapter, and returns normalized metadata.

---

## API Summary

| Method | Endpoint | Required Permission | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/connectors/{id}/test` | `connectors.test` | Real Tally XML connection test ping |
| `GET` | `/api/connectors/{id}/health` | `connectors.view` | Real lightweight health check |
| `GET` | `/api/connectors/{id}/tally/companies` | `tally.view_companies` | Discover open companies in Tally |
| `POST` | `/api/connectors/{id}/tally/company` | `tally.select_company` | Re-validate and select target Tally company |
| `GET` | `/api/connectors/{id}/tally/metadata?type=ledgers` | `tally.view_metadata` | Discover metadata from Tally for allow-listed types |

---

## Verification
Run unit, integration, and full pipeline verification:
```bash
python -m unittest discover -s tests/unit
python -m unittest discover -s tests/integration
python scripts/verify_all.py
```
