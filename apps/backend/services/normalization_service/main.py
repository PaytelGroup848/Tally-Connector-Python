

from fastapi import FastAPI
from shared.config import get_settings
from shared.logging_config import setup_logging, get_logger
from shared.exceptions import register_exception_handlers
from shared.middleware import add_request_id_middleware
from shared.models import SourceRecord, NormalizedRecord, RecordType, SourceType
from shared.fingerprint import fingerprint

setup_logging("normalization_service")
logger = get_logger("app.normalization_service")
settings = get_settings()

app = FastAPI(
    title="CtrlBooks Normalization Service",
    description="Transforms raw accounting data from Tally & BUSY into unified canonical schemas"
)

add_request_id_middleware(app)
register_exception_handlers(app)

def normalize_company(record: SourceRecord) -> dict:
    d = record.data
    return {
        "company_name": d.get("name") or d.get("company_name"),
        "financial_year_start": d.get("financial_year_start") or d.get("financial_year"),
        "source": record.source.value
    }

def normalize_ledger(record: SourceRecord) -> dict:
    d = record.data
    from shared.auth.cloud_auth_service import classify_ledger_type
    if record.source == SourceType.TALLY:
        parent_val = d.get("parent") or "Primary"
        c_bal = d.get("closingBalance") if d.get("closingBalance") is not None else d.get("closing_balance", 0.0)
        op_bal = d.get("openingBalance") if d.get("openingBalance") is not None else d.get("opening_balance", 0.0)
        l_type = d.get("ledgerType") or d.get("ledger_type") or classify_ledger_type(parent_val)
        return {
            "tallyExternalId": d.get("tallyExternalId") or d.get("guid") or d.get("name"),
            "name": d.get("name"),
            "parent": parent_val,
            "group": d.get("group") or parent_val,
            "ledgerType": l_type,
            "openingBalance": float(op_bal or 0.0),
            "closingBalance": float(c_bal or 0.0),
            "closing_balance": float(c_bal or 0.0),
            "gstin": d.get("gstin") or d.get("partygstin"),
            "currency": d.get("currency", "INR"),
            "source_software": "tally"
        }
    else:
        parent_val = d.get("group_name") or d.get("group", "Primary")
        c_bal = d.get("closingBalance") if d.get("closingBalance") is not None else d.get("balance", d.get("closing_balance", 0.0))
        op_bal = d.get("openingBalance") if d.get("openingBalance") is not None else d.get("opening_balance", 0.0)
        l_type = d.get("ledgerType") or d.get("ledger_type") or classify_ledger_type(parent_val)
        return {
            "tallyExternalId": d.get("tallyExternalId") or d.get("guid") or d.get("name"),
            "name": d.get("account_name") or d.get("name"),
            "parent": parent_val,
            "group": parent_val,
            "ledgerType": l_type,
            "openingBalance": float(op_bal or 0.0),
            "closingBalance": float(c_bal or 0.0),
            "closing_balance": float(c_bal or 0.0),
            "gstin": d.get("gstin"),
            "currency": d.get("currency", "INR"),
            "source_software": "busy"
        }

def normalize_voucher(record: SourceRecord) -> dict:
    d = record.data
    if record.source == SourceType.TALLY:
        return {
            "voucher_number": d.get("voucher_number"),
            "voucher_type": d.get("voucher_type"),
            "date": d.get("date"),
            "party_name": d.get("party_name"),
            "amount": float(d.get("amount", 0.0)),
            "narration": d.get("narration", ""),
            "source_software": "tally"
        }
    else:
        return {
            "voucher_number": d.get("voucher_no") or d.get("voucher_number"),
            "voucher_type": d.get("voucher_type"),
            "date": d.get("date"),
            "party_name": d.get("account_name") or d.get("party_name"),
            "amount": float(d.get("total_amount", d.get("amount", 0.0))),
            "narration": d.get("remarks", d.get("narration", "")),
            "source_software": "busy"
        }

def normalize_stock_item(record: SourceRecord) -> dict:
    d = record.data
    if record.source == SourceType.TALLY:
        return {
            "item_name": d.get("item_name"),
            "category": d.get("category", "General"),
            "quantity": float(d.get("closing_qty", d.get("opening_qty", 0))),
            "unit": d.get("unit", "Pcs"),
            "rate": float(d.get("rate", 0.0)),
            "source_software": "tally"
        }
    else:
        return {
            "item_name": d.get("item_name"),
            "category": d.get("group_name", "General"),
            "quantity": float(d.get("stock_qty", 0)),
            "unit": d.get("unit", "Pcs"),
            "rate": float(d.get("sale_price", 0.0)),
            "source_software": "busy"
        }

@app.get("/health")
async def health():
    return {"service": "normalization_service", "status": "ok"}

@app.post("/normalize")
async def normalize(record: SourceRecord):
    """Normalizes any incoming raw record (Tally or BUSY) to canonical LR schema."""
    if record.record_type == RecordType.COMPANY:
        canonical = normalize_company(record)
    elif record.record_type == RecordType.LEDGER:
        canonical = normalize_ledger(record)
    elif record.record_type == RecordType.VOUCHER:
        canonical = normalize_voucher(record)
    elif record.record_type == RecordType.STOCK_ITEM:
        canonical = normalize_stock_item(record)
    else:
        canonical = record.data

    fp = fingerprint(canonical)

    normalized_obj = NormalizedRecord(
        source=record.source,
        record_type=record.record_type,
        external_id=record.external_id,
        company_name=record.company_name,
        canonical=canonical,
        fingerprint=fp
    )
    return normalized_obj.model_dump(mode="json")
