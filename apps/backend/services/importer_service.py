

from collections import OrderedDict
from typing import Any

from apps.backend.adapters.tally.tally_importer import TallyImporter
from shared.connection_config import resolve_active_tally_port
from shared.exceptions import ValidationError
from shared.logging_config import get_logger

logger = get_logger("app.services.importer")


def _safe_float(val: Any, default: float = 0.0) -> float:
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


class ImporterService:
    def __init__(
        self,
        tally_importer: TallyImporter | None = None,
    ):
        self.tally_importer: TallyImporter = tally_importer if tally_importer is not None else TallyImporter()
        self._idempotency_cache: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._max_cache_size: int = 1000

    def _resolve_connection_endpoint(self, payload: dict[str, Any]) -> tuple[str, int]:
        """Resolves target Tally host and port dynamically without hardcoded fallback."""
        raw_port = payload.get("port") or payload.get("tally_port")
        raw_host = payload.get("host") or payload.get("tally_host")
        return resolve_active_tally_port(preferred_port=raw_port, preferred_host=raw_host)

    def validate_import_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Validates the structure and required fields of incoming voucher payload.
        Returns normalized payload dict or raises ValidationError.
        """
        if not payload or not isinstance(payload, dict):
            raise ValidationError("Payload must be a non-empty JSON dictionary.")

        target = (payload.get("target") or payload.get("software") or "").strip().upper()
        if not target:
            raise ValidationError("Missing required field 'target'.")
        if target != "TALLY":
            raise ValidationError(f"Invalid target '{target}'. Target must be 'TALLY'.")

        voucher_type = str(
            payload.get("voucher_type")
            or payload.get("voucherType")
            or payload.get("vtype")
            or payload.get("type")
            or "Sales"
        ).strip()
        if not voucher_type:
            voucher_type = "Sales"

        party_raw = (
            payload.get("party_ledger")
            or payload.get("partyLedger")
            or payload.get("party_name")
            or payload.get("partyName")
            or payload.get("party")
            or payload.get("customer")
            or payload.get("customer_name")
            or payload.get("customerName")
            or payload.get("supplier")
            or payload.get("supplier_name")
            or payload.get("supplierName")
            or payload.get("vendor")
            or payload.get("vendor_name")
            or payload.get("vendorName")
            or payload.get("received_from")
            or payload.get("receivedFrom")
            or payload.get("paid_to")
            or payload.get("paidTo")
            or payload.get("ledger_name")
            or payload.get("ledgerName")
        )
        if isinstance(party_raw, dict):
            party_raw = party_raw.get("name") or party_raw.get("ledgerName") or party_raw.get("customerName") or party_raw.get("partyName")
        if not party_raw:
            if voucher_type.lower() in ("stock journal", "physical stock"):
                party = "Inventory / Stock"
            elif voucher_type.lower() in ("journal", "contra", "receipt", "payment"):
                party = None
                for p_key in ("particulars", "ledger_entries", "ledgerEntries", "debit_particulars", "credit_particulars", "items"):
                    p_list = payload.get(p_key)
                    if isinstance(p_list, list) and len(p_list) > 0:
                        for p_first in p_list:
                            if isinstance(p_first, dict):
                                candidate = (
                                    p_first.get("partyName") or p_first.get("party_name")
                                    or p_first.get("ledgerName") or p_first.get("ledger_name")
                                    or p_first.get("name") or p_first.get("ledger")
                                    or p_first.get("party") or p_first.get("customer")
                                    or p_first.get("supplier") or p_first.get("vendor")
                                )
                                if candidate and str(candidate).strip().lower() not in ("cash", "bank"):
                                    party = str(candidate).strip()
                                    break
                                elif candidate and not party:
                                    party = str(candidate).strip()
                        if party:
                            break
                if not party:
                    if voucher_type.lower() in ("receipt", "payment"):
                        party = "Cash"
                    elif "contra" in voucher_type.lower():
                        party = "Contra Account"
                    else:
                        party = "Journal Account"
            else:
                raise ValidationError("Missing required party ledger/name in payload.")
        else:
            party = str(party_raw).strip()
            if not party or party.lower() in ("none", "null", "undefined"):
                if voucher_type.lower() in ("stock journal", "physical stock"):
                    party = "Inventory / Stock"
                elif voucher_type.lower() in ("journal", "contra"):
                    party = "Contra Account" if "contra" in voucher_type.lower() else "Journal Account"
                else:
                    party = "Cash"

        try:
            raw_amt = payload.get("amount")
            if raw_amt is None:
                raw_amt = payload.get("total_amount", 0.0)
            amt = float(raw_amt or 0.0)
            if amt < 0:
                raise ValidationError("Voucher amount cannot be negative.")
        except (ValueError, TypeError):
            amt = 0.0

        if amt <= 0.0 and voucher_type.lower() in ("contra", "journal"):
            for p_key in ("particulars", "ledger_entries", "ledgerEntries", "debit_particulars", "items"):
                p_list = payload.get(p_key)
                if isinstance(p_list, list) and len(p_list) > 0:
                    d_sum = 0.0
                    c_sum = 0.0
                    has_l = False
                    for p in p_list:
                        if isinstance(p, dict):
                            pv = float(p.get("amount") or p.get("amt") or 0.0)
                            pt = str(p.get("type") or p.get("entry_type") or "").strip().lower()
                            if pt in ("debit", "dr", "by") or p.get("isDebit") is True or p.get("is_debit") is True:
                                d_sum += pv
                                has_l = True
                            elif pt in ("credit", "cr", "to") or p.get("isDebit") is False or p.get("is_debit") is False:
                                c_sum += pv
                                has_l = True
                    if has_l:
                        amt = round(d_sum if d_sum > 0 else c_sum, 2)
                        break

        if amt <= 0.0 and voucher_type.lower() in ("stock journal", "physical stock"):
            raw_items_val = payload.get("items")
            raw_items_dict: dict[str, Any] = dict(raw_items_val) if isinstance(raw_items_val, dict) else {}
            src_calc = 0.0
            for it_k in ("source_items", "sourceItems", "consumption_items", "consumptionItems", "items_out", "itemsOut", "outward_items", "outwardItems"):
                items_list = payload.get(it_k)
                if isinstance(items_list, list):
                    for it in items_list:
                        if isinstance(it, dict):
                            it_amt = _safe_float(it.get("amount") or it.get("taxableValue"))
                            if it_amt <= 0.0:
                                q_val = it.get("quantity") if it.get("quantity") is not None else it.get("qty")
                                r_val = it.get("rate") if it.get("rate") is not None else it.get("price")
                                it_amt = _safe_float(q_val) * _safe_float(r_val)
                            src_calc += it_amt
            source_list = raw_items_dict.get("source") or raw_items_dict.get("consumption") or raw_items_dict.get("items_out")
            if isinstance(source_list, list):
                for it in source_list:
                    if isinstance(it, dict):
                        it_amt = _safe_float(it.get("amount") or it.get("taxableValue"))
                        if it_amt <= 0.0:
                            q_val = it.get("quantity") if it.get("quantity") is not None else it.get("qty")
                            r_val = it.get("rate") if it.get("rate") is not None else it.get("price")
                            it_amt = _safe_float(q_val) * _safe_float(r_val)
                        src_calc += it_amt

            dest_calc = 0.0
            for it_k in ("destination_items", "destinationItems", "production_items", "productionItems", "items_in", "itemsIn", "inward_items", "inwardItems"):
                items_list = payload.get(it_k)
                if isinstance(items_list, list):
                    for it in items_list:
                        if isinstance(it, dict):
                            it_amt = _safe_float(it.get("amount") or it.get("taxableValue"))
                            if it_amt <= 0.0:
                                q_val = it.get("quantity") if it.get("quantity") is not None else it.get("qty")
                                r_val = it.get("rate") if it.get("rate") is not None else it.get("price")
                                it_amt = _safe_float(q_val) * _safe_float(r_val)
                            dest_calc += it_amt
            dest_list = raw_items_dict.get("destination") or raw_items_dict.get("production") or raw_items_dict.get("items_in")
            if isinstance(dest_list, list):
                for it in dest_list:
                    if isinstance(it, dict):
                        it_amt = _safe_float(it.get("amount") or it.get("taxableValue"))
                        if it_amt <= 0.0:
                            q_val = it.get("quantity") if it.get("quantity") is not None else it.get("qty")
                            r_val = it.get("rate") if it.get("rate") is not None else it.get("price")
                            it_amt = _safe_float(q_val) * _safe_float(r_val)
                        dest_calc += it_amt

            if src_calc > 0 and dest_calc > 0:
                amt = round(max(src_calc, dest_calc), 2)
            elif src_calc > 0:
                amt = round(src_calc, 2)
            elif dest_calc > 0:
                amt = round(dest_calc, 2)

        clean_payload = dict(payload)
        clean_payload["target"] = target
        clean_payload["voucher_type"] = voucher_type
        clean_payload["party_ledger"] = party
        clean_payload["amount"] = amt
        return clean_payload

    async def import_voucher(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Main entrypoint for importing pending sales invoices and receipts into accounting software.
        Routes to Tally Prime HTTP interface (port 9000).
        Automatically creates missing party ledgers beforehand.
        """
        logger.info(f"Receiving 2-Way Sync import request for target '{payload.get('target')}'")
        validated_payload = self.validate_import_payload(payload)
        target = validated_payload["target"]

        # Idempotency check: prevent duplicate voucher posting on web retries
        v_num_raw = (
            validated_payload.get("voucher_number")
            or validated_payload.get("voucherNumber")
            or validated_payload.get("invoice_number")
            or validated_payload.get("reference")
        )
        comp_name_raw = str(validated_payload.get("company_name") or validated_payload.get("company") or "").strip()
        v_type_raw = str(validated_payload.get("voucher_type") or "Sales").strip()

        cmd_id = (
            validated_payload.get("command_id")
            or validated_payload.get("cmd_id")
            or validated_payload.get("commandId")
            or validated_payload.get("id")
        )
        party_str = str(validated_payload.get("party_ledger") or validated_payload.get("party") or "").strip().lower()
        amt_val = round(float(validated_payload.get("amount") or 0.0), 2)
        v_num_str = str(v_num_raw or "").strip().lower()

        idemp_key = None
        if cmd_id:
            idemp_key = f"cmd:{cmd_id}"
        elif v_num_str and not v_num_str.startswith("web-"):
            is_generic_num = v_type_raw.lower() in ("receipt", "payment") and v_num_str.isdigit()
            if is_generic_num:
                idemp_key = f"{comp_name_raw.lower()}:{v_type_raw.lower()}:{v_num_str}:{party_str}:{amt_val}"
            else:
                idemp_key = f"{comp_name_raw.lower()}:{v_type_raw.lower()}:{v_num_str}"

        if idemp_key and idemp_key in self._idempotency_cache:
            logger.info(f"Idempotent hit for key '{idemp_key}'. Returning cached confirmation.")
            self._idempotency_cache.move_to_end(idemp_key)
            return self._idempotency_cache[idemp_key]

        host, port = self._resolve_connection_endpoint(payload)

        result = await self.tally_importer.import_voucher(
            host=host, port=port, voucher_data=validated_payload
        )

        should_queue = bool(result.get("should_queue", False))
        if result.get("success"):
            calc_status = "SUCCESS"
        elif should_queue:
            calc_status = "QUEUED"
        else:
            calc_status = "FAILED"

        response = {
            "status": calc_status,
            "should_queue": should_queue,
            "target": target,
            "voucher_type": validated_payload["voucher_type"],
            "voucher_number": result.get("voucher_number"),
            "tallyExternalId": result.get("tallyExternalId") or result.get("voucher_number"),
            "guid": result.get("guid") or result.get("voucher_number"),
            "amount": float(result.get("amount", validated_payload.get("amount", 0.0))),
            "company_name": result.get("company_name") or validated_payload.get("company_name", ""),
            "message": result.get("message"),
            "error": result.get("error"),
            "reason": result.get("reason"),
            "action": result.get("action"),
            "diagnostic": result.get("diagnostic"),
        }

        if result.get("success"):
            logger.info(f"Voucher successfully imported into {target}: Voucher #{result.get('voucher_number')}")
            if idemp_key:
                if idemp_key in self._idempotency_cache:
                    self._idempotency_cache.move_to_end(idemp_key)
                self._idempotency_cache[idemp_key] = response
                if len(self._idempotency_cache) > self._max_cache_size:
                    self._idempotency_cache.popitem(last=False)
                try:
                    from datetime import datetime, timezone

                    from shared.db.mongo_client import get_collection
                    col = get_collection("imported_vouchers_idempotency")
                    col.update_one(
                        {"idempotency_key": idemp_key},
                        {"$set": {
                            "idempotency_key": idemp_key,
                            "company_name": comp_name_raw,
                            "voucher_type": v_type_raw,
                            "voucher_number": result.get("voucher_number"),
                            "amount": response["amount"],
                            "response": response,
                            "created_at": datetime.now(timezone.utc)
                        }},
                        upsert=True
                    )
                except Exception as ex:  # noqa: BLE001
                    logger.debug(f"Idempotency persistence notice: {ex}")
        else:
            logger.error(f"Voucher import failed for {target}: {result.get('error')}")

        return response

    async def create_ledger(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Creates a new customer/debtor ledger explicitly in Tally Prime."""
        clean_payload = dict(payload)
        clean_payload["target"] = "TALLY"
        host, port = self._resolve_connection_endpoint(clean_payload)

        ledger_name = (
            clean_payload.get("name")
            or clean_payload.get("ledgerName")
            or clean_payload.get("ledger_name")
            or clean_payload.get("partyName")
            or clean_payload.get("party_name")
            or clean_payload.get("party_ledger")
            or clean_payload.get("customerName")
        )
        clean_payload["name"] = ledger_name

        result = await self.tally_importer.import_ledger(
            host=host, port=port, ledger_data=clean_payload
        )

        ext_id = result.get("tallyExternalId") or result.get("guid") or f"TALLY-{ledger_name}"
        return {
            "status": "SUCCESS" if result.get("success") else "FAILED",
            "target": "TALLY",
            "name": ledger_name,
            "tallyExternalId": ext_id,
            "guid": ext_id,
            "already_exists": result.get("already_exists", False),
            "message": result.get("message"),
            "error": result.get("error")
        }

    async def create_stock_item(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Creates a new stock item explicitly in Tally Prime with base unit."""
        clean_payload = dict(payload)
        host, port = self._resolve_connection_endpoint(clean_payload)
        company = str(clean_payload.get("company_name") or clean_payload.get("company") or "")
        item_name = str(clean_payload.get("name") or clean_payload.get("itemName") or clean_payload.get("item_name") or "")
        unit_name = str(clean_payload.get("unit") or clean_payload.get("units") or clean_payload.get("base_units") or "Pcs")
        hsn_code = str(clean_payload.get("hsn_code") or clean_payload.get("hsnCode") or clean_payload.get("hsn") or "")
        hsn_desc = str(clean_payload.get("hsn_description") or clean_payload.get("hsn_desc") or clean_payload.get("description") or "")
        gst_rate = clean_payload.get("gst_rate") or clean_payload.get("gstRate") or clean_payload.get("tax_rate") or clean_payload.get("taxRate")
        quantity = clean_payload.get("quantity") or clean_payload.get("qty") or clean_payload.get("opening_balance") or clean_payload.get("openingBalance") or 0.0
        rate = clean_payload.get("rate") or clean_payload.get("opening_rate") or clean_payload.get("openingRate") or 0.0
        value = clean_payload.get("value") or clean_payload.get("opening_value") or clean_payload.get("openingValue") or clean_payload.get("amount") or 0.0
        godown = str(clean_payload.get("godown") or clean_payload.get("godown_name") or clean_payload.get("godownName") or clean_payload.get("warehouse") or clean_payload.get("location") or "")
        batch = str(clean_payload.get("batch") or clean_payload.get("batch_name") or clean_payload.get("batchName") or clean_payload.get("batch_number") or clean_payload.get("batchNumber") or "")

        ok = await self.tally_importer.ensure_stock_item(
            host=host,
            port=port,
            company_name=company,
            item_name=item_name,
            unit_name=unit_name,
            hsn_code=hsn_code,
            hsn_desc=hsn_desc,
            gst_rate=gst_rate,
            quantity=quantity,
            rate=rate,
            value=value,
            godown=godown,
            batch=batch,
        )

        ext_id = None
        if ok:
            ext_id = await self.tally_importer.fetch_stock_item_guid(host, port, company, item_name)
        if not ext_id:
            ext_id = f"TALLY-{item_name}"

        return {
            "status": "SUCCESS" if ok else "FAILED",
            "target": "TALLY",
            "name": item_name,
            "itemName": item_name,
            "tallyExternalId": ext_id,
            "guid": ext_id,
            "message": f"Stock item '{item_name}' created in Tally" if ok else f"Failed to create stock item '{item_name}'",
            "error": None if ok else f"Failed to ensure stock item '{item_name}'"
        }

    async def update_stock_item(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Updates/alters an existing stock item explicitly in Tally Prime."""
        clean_payload = dict(payload)
        host, port = self._resolve_connection_endpoint(clean_payload)
        company = str(clean_payload.get("company_name") or clean_payload.get("company") or "")
        item_name = str(clean_payload.get("name") or clean_payload.get("itemName") or clean_payload.get("item_name") or "")

        ok, err = await self.tally_importer.alter_stock_item(
            host=host,
            port=port,
            company_name=company,
            item_data=clean_payload,
        )

        return {
            "status": "SUCCESS" if ok else "FAILED",
            "target": "TALLY",
            "name": item_name,
            "message": f"Stock item '{item_name}' updated in Tally" if ok else f"Failed to update stock item '{item_name}'",
            "error": err if not ok else None
        }

    async def create_unit(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Creates a new unit of measurement explicitly in Tally Prime."""
        clean_payload = dict(payload)
        host, port = self._resolve_connection_endpoint(clean_payload)
        company = str(clean_payload.get("company_name") or clean_payload.get("company") or "")
        unit_name = str(clean_payload.get("name") or clean_payload.get("symbol") or clean_payload.get("unit_name") or "Pcs")
        decimal_places = int(clean_payload.get("decimal_places") or clean_payload.get("decimalPlaces") or 0)

        ok = await self.tally_importer.ensure_unit(
            host=host,
            port=port,
            company_name=company,
            unit_name=unit_name,
            decimal_places=decimal_places,
        )

        return {
            "status": "SUCCESS" if ok else "FAILED",
            "target": "TALLY",
            "name": unit_name,
            "message": f"Unit '{unit_name}' created in Tally" if ok else f"Failed to create unit '{unit_name}'",
            "error": None if ok else f"Failed to ensure unit '{unit_name}'"
        }

importer_service = ImporterService()
