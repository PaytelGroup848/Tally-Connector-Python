# Module 8 Architecture: Data Discovery & Unified Source Metadata System

## Overview
Module 8 implements the **Data Discovery & Unified Source Metadata System**. It introduces a canonical metadata model unifying Tally Prime and BUSY Accounting source structures without faking discovery records or connection success.

---

## Architecture Flow

```
TALLY / BUSY Source Adapter
       ↓
Company Context (Validated Company Name/Path)
       ↓
Source-Specific Normalizer (TallyMetadataNormalizer / BusyMetadataNormalizer)
       ↓
Unified Canonical Metadata (UnifiedSourceMetadata)
       ↓
Metadata Repository (Batched Upsert & Stale Reconciliation)
       ↓
API Gateway / PySide6 Desktop Metadata Browser
```

---

## Canonical Entity Categories

- `COMPANY`
- `ACCOUNT_GROUP`
- `LEDGER`
- `VOUCHER_TYPE`
- `STOCK_GROUP`
- `STOCK_CATEGORY`
- `STOCK_ITEM`
- `UNIT`
- `GODOWN`
- `COST_CENTRE`

---

## Core Database Models

1. **`UnifiedSourceMetadata`**:
   - `id`: UUID primary key
   - `connector_id`: FK to `connectors.id`
   - `company_identifier`: Active target company name/code
   - `source_type`: `TALLY` or `BUSY`
   - `source_entity_type`: Raw source entity name (`Ledger`, `Account`, `STOCKITEM`, `Item`)
   - `canonical_entity_type`: Canonical category (`LEDGER`, `STOCK_ITEM`, `VOUCHER_TYPE`, etc.)
   - `source_identifier`: Source GUID / ID
   - `source_name`, `display_name`
   - `parent_source_identifier`, `parent_display_name`
   - `status`: `ACTIVE` or `STALE`
   - `source_metadata_json`: Text (JSON string containing extra attributes)

2. **`MetadataDiscoveryRun`**:
   - Tracks discovery run execution history, requested entity types, and record counters (`records_discovered`, `records_created`, `records_updated`, `records_marked_stale`, `records_failed`).

---

## API Summary

| Method | Endpoint | Required Permission | Description |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/connectors/{id}/metadata/discover` | `metadata.discover` | Batched real source data discovery |
| `POST` | `/api/connectors/{id}/metadata/refresh` | `metadata.refresh` | Refresh & reconcile canonical metadata |
| `GET` | `/api/connectors/{id}/metadata` | `metadata.view` | Paginated connector metadata listing |
| `GET` | `/api/connectors/{id}/metadata/{metadata_id}` | `metadata.view` | Single metadata record detail |
| `GET` | `/api/metadata/search?query=...` | `metadata.search` | Global unified metadata search |

---

## Verification
Run unit, integration, and master verification pipeline:
```bash
python -m unittest discover -s tests/unit
python -m unittest discover -s tests/integration
python scripts/verify_all.py
```
