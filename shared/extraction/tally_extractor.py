"""
CtrlBooks - Tally Data Extractor & Record Normalizer
----------------------------------------------------------------
Executes truthful XML queries against Tally Prime HTTP server (Port 9000),
normalizes raw XML responses into CanonicalDataRecord objects, enforces read-only safety,
checks multi-company sync enablement toggles, and implements ALTERID incremental delta sync.
"""

import uuid
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from shared.extraction.base import BaseDataExtractor, BaseRecordNormalizer, CanonicalDataRecord
from apps.backend.adapters.tally.tally_client import TallyClient
from apps.backend.adapters.tally.request_builder import build_collection_xml
from apps.backend.adapters.tally.response_parser import parse_tally_xml_response
from shared.extraction.filter_registry import extraction_filter_registry
from shared.repositories.company_repository import (
    is_company_sync_enabled,
    update_company_last_alter_id,
    get_all_company_configs,
)
from shared.exceptions import ValidationError
from shared.logging_config import get_logger

logger = get_logger("app.extraction.tally")

TALLY_ENTITY_MAP = {
    "LEDGER": (
        "Ledger",
        ["NAME", "PARENT", "CLOSINGBALANCE", "OPENINGBALANCE", "ADDRESS", "PHONE", "EMAIL", "PARTYGSTIN", "GUID", "ALTERID"],
    ),
    "STOCK_ITEM": (
        "StockItem",
        ["NAME", "PARENT", "CATEGORY", "BASEUNITS", "ADDITIONALUNITS", "GSTREPUOM", "CLOSINGBALANCE", "OPENINGBALANCE", "CLOSINGRATE", "CLOSINGVALUE", "OPENINGRATE", "OPENINGVALUE", "GSTAPPLICABLE", "HSNCODE", "HSNDETAILS.LIST", "GSTDETAILS.LIST", "BATCHNAME", "BATCHALLOCATIONS.LIST", "GODOWNALLOCATIONS.LIST", "GUID", "ALTERID"],
    ),
    "VOUCHER": ("Voucher", ["DATE", "EFFECTIVEDATE", "VOUCHERTYPENAME", "VOUCHERNUMBER", "PARTYLEDGERNAME", "PARTYNAME", "BASICBUYERNAME", "AMOUNT", "NARRATION", "GUID", "ALTERID", "ALLLEDGERENTRIES.LIST"]),
    "ACCOUNT_GROUP": ("Group", ["NAME", "PARENT", "GUID", "ALTERID"]),
    "VOUCHER_TYPE": ("VoucherType", ["NAME", "PARENT", "NUMBERINGMETHOD", "GUID", "ALTERID"]),
    "UNIT": ("Unit", ["NAME", "SYMBOL", "DECIMALPLACES", "GUID", "ALTERID"]),
    "GODOWN": ("Godown", ["NAME", "PARENT", "ADDRESS", "GUID", "ALTERID"]),
    "COST_CENTRE": ("CostCentre", ["NAME", "CATEGORY", "GUID", "ALTERID"]),
}

class TallyRecordNormalizer(BaseRecordNormalizer):
    def normalize(
        self,
        raw_record: Dict[str, Any],
        connector_id: str,
        company_identifier: str,
        canonical_entity_type: str,
    ) -> CanonicalDataRecord:
        c_entity = canonical_entity_type.strip().upper()
        s_id = str(
            raw_record.get("name")
            or raw_record.get("guid")
            or raw_record.get("voucher_number")
            or uuid.uuid4().hex[:8]
        )

        data: Dict[str, Any] = {}

        if c_entity == "LEDGER":
            data = {
                "name": raw_record.get("name"),
                "code": raw_record.get("code") or raw_record.get("guid"),
                "parent": raw_record.get("parent"),
                "opening_balance": raw_record.get("opening_balance"),
                "closing_balance": raw_record.get("closing_balance"),
                "address": raw_record.get("address"),
                "phone": raw_record.get("phone"),
                "email": raw_record.get("email"),
                "tax_identifier": raw_record.get("tax_identifier") or raw_record.get("gstin"),
                "alter_id": raw_record.get("alter_id"),
                "is_active": True,
            }
        elif c_entity == "STOCK_ITEM":
            data = {
                "name": raw_record.get("name"),
                "code": raw_record.get("code") or raw_record.get("guid"),
                "group": raw_record.get("group") or raw_record.get("parent"),
                "godown": raw_record.get("godown") or "Main Location",
                "batch": raw_record.get("batch") or "Primary Batch",
                "unit": raw_record.get("unit") or raw_record.get("base_units"),
                "opening_quantity": raw_record.get("opening_quantity") or raw_record.get("opening_balance"),
                "opening_rate": raw_record.get("opening_rate"),
                "opening_value": raw_record.get("opening_value"),
                "tax_rate": raw_record.get("tax_rate"),
                "hsn_sac_code": raw_record.get("hsn_sac_code") or raw_record.get("hsn_code"),
                "alter_id": raw_record.get("alter_id"),
            }
        elif c_entity == "VOUCHER":
            data = {
                "voucher_number": raw_record.get("voucher_number"),
                "voucher_type": raw_record.get("voucher_type"),
                "date": raw_record.get("date"),
                "party_name": raw_record.get("party_name"),
                "amount": raw_record.get("amount"),
                "narration": raw_record.get("narration"),
                "alter_id": raw_record.get("alter_id"),
            }
        elif c_entity == "ACCOUNT_GROUP":
            data = {
                "name": raw_record.get("name"),
                "code": raw_record.get("code") or raw_record.get("guid"),
                "parent": raw_record.get("parent"),
                "alter_id": raw_record.get("alter_id"),
            }
        elif c_entity == "VOUCHER_TYPE":
            data = {
                "name": raw_record.get("name"),
                "parent": raw_record.get("parent"),
                "numbering_method": raw_record.get("numbering_method"),
                "alter_id": raw_record.get("alter_id"),
            }
        elif c_entity == "UNIT":
            data = {
                "name": raw_record.get("name"),
                "symbol": raw_record.get("symbol") or raw_record.get("name"),
                "decimal_places": raw_record.get("decimal_places", 0),
                "alter_id": raw_record.get("alter_id"),
            }
        elif c_entity == "GODOWN":
            data = {
                "name": raw_record.get("name"),
                "parent": raw_record.get("parent"),
                "address": raw_record.get("address"),
                "alter_id": raw_record.get("alter_id"),
            }
        elif c_entity == "COST_CENTRE":
            data = {
                "name": raw_record.get("name"),
                "category": raw_record.get("category"),
                "alter_id": raw_record.get("alter_id"),
            }
        else:
            data = dict(raw_record)

        return CanonicalDataRecord(
            record_id=f"rec-{uuid.uuid4().hex[:12]}",
            connector_id=connector_id,
            company_identifier=company_identifier,
            source_type="TALLY",
            source_entity_type=raw_record.get("_raw_tag", c_entity),
            canonical_entity_type=c_entity,
            source_identifier=s_id,
            data=data,
            source_metadata=raw_record.get("_source_metadata", {"guid": raw_record.get("guid")}),
            extracted_at=datetime.now(timezone.utc),
        )

class TallyDataExtractor(BaseDataExtractor):
    def __init__(self):
        self.client = TallyClient()
        self.normalizer = TallyRecordNormalizer()

    @property
    def provider_type(self) -> str:
        return "TALLY"

    def validate_request(
        self,
        connector_config: Dict[str, Any],
        company_identifier: str,
        canonical_entity_type: str,
        filters: Optional[Dict[str, Any]] = None,
    ) -> None:
        c_entity = (canonical_entity_type or "").strip().upper()
        if c_entity not in TALLY_ENTITY_MAP:
            raise ValidationError(
                f"Tally does not support canonical entity type '{canonical_entity_type}'. Allowed types: {', '.join(TALLY_ENTITY_MAP.keys())}"
            )

        host = connector_config.get("host", "127.0.0.1")
        port = connector_config.get("port", 9000)
        self.client.validate_host_and_port(host, port)
        extraction_filter_registry.validate_filters(c_entity, filters)

    def extract(
        self,
        connector_config: Dict[str, Any],
        company_identifier: str,
        canonical_entity_type: str,
        filters: Optional[Dict[str, Any]] = None,
        cursor: Optional[str] = None,
        page_size: int = 100,
    ) -> Dict[str, Any]:
        if not is_company_sync_enabled("TALLY", company_identifier):
            logger.info(f"Sync is disabled for company '{company_identifier}'. Skipping extraction.")
            return {
                "records": [],
                "returned": 0,
                "next_cursor": None,
                "status": "DISABLED",
                "error": f"Sync is disabled for company '{company_identifier}'",
            }

        self.validate_request(connector_config, company_identifier, canonical_entity_type, filters)
        c_entity = canonical_entity_type.strip().upper()
        clean_filters = extraction_filter_registry.validate_filters(c_entity, filters)

        host = connector_config.get("host", "127.0.0.1")
        port = int(connector_config.get("port", 9000))
        tally_tag, fetch_fields = TALLY_ENTITY_MAP[c_entity]

        from_alter_id = None
        if clean_filters and "from_alter_id" in clean_filters:
            from_alter_id = int(clean_filters["from_alter_id"])
        else:
            try:
                configs = get_all_company_configs()
                for cfg in configs:
                    if cfg.get("company_name") == company_identifier and cfg.get("source_type") == "TALLY":
                        from_alter_id = cfg.get("last_alter_id", 0)
                        break
            except Exception:
                from_alter_id = None

        xml_payload = build_collection_xml(
            collection_type=tally_tag,
            fetch_fields=fetch_fields,
            company_name=company_identifier,
            from_alter_id=from_alter_id if (from_alter_id and from_alter_id > 0) else None,
        )

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                success, status_code, response_xml, err_msg = pool.submit(
                    lambda: asyncio.run(self.client.send_xml_request_async(host, port, xml_payload, timeout=10.0))
                ).result()
        else:
            success, status_code, response_xml, err_msg = asyncio.run(
                self.client.send_xml_request_async(host, port, xml_payload, timeout=10.0)
            )

        if not success or status_code != 200:
            logger.error(f"Tally XML extraction failed for {c_entity}: {err_msg}")
            return {
                "records": [],
                "returned": 0,
                "next_cursor": None,
                "status": "SOURCE_UNAVAILABLE",
                "error": err_msg or f"HTTP {status_code}",
            }

        raw_items = self._parse_tally_response_items(response_xml, tally_tag)

        max_alter_id = 0
        for item in raw_items:
            alt = item.get("alter_id")
            if alt and isinstance(alt, int) and alt > max_alter_id:
                max_alter_id = alt

        if max_alter_id > 0:
            try:
                update_company_last_alter_id("TALLY", company_identifier, max_alter_id)
                logger.info(f"Updated Tally ALTERID checkpoint for '{company_identifier}' -> {max_alter_id}")
            except Exception as exc:
                logger.warning(f"Unable to update ALTERID checkpoint: {exc}")

        filtered_raw = self._apply_in_memory_filters(raw_items, clean_filters)

        offset = 0
        if cursor and cursor.startswith("offset_"):
            try:
                offset = int(cursor.split("_")[1])
            except ValueError:
                offset = 0

        sliced_items = filtered_raw[offset : offset + page_size]
        next_offset = offset + len(sliced_items)
        next_cursor = f"offset_{next_offset}" if next_offset < len(filtered_raw) else None

        connector_id = connector_config.get("connector_id", "tally-conn")
        canonical_records = [
            self.normalizer.normalize(item, connector_id, company_identifier, c_entity)
            for item in sliced_items
        ]

        status_code_str = "SUCCESS" if canonical_records else "EMPTY"
        return {
            "records": canonical_records,
            "returned": len(canonical_records),
            "next_cursor": next_cursor,
            "status": status_code_str,
            "error": None,
        }

    def extract_single(
        self,
        connector_config: Dict[str, Any],
        company_identifier: str,
        canonical_entity_type: str,
        source_identifier: str,
    ) -> Optional[CanonicalDataRecord]:
        res = self.extract(
            connector_config=connector_config,
            company_identifier=company_identifier,
            canonical_entity_type=canonical_entity_type,
            filters={"identifier": source_identifier, "name": source_identifier},
            page_size=50,
        )
        records = res.get("records", [])
        for r in records:
            if str(r.source_identifier).strip().lower() == str(source_identifier).strip().lower():
                return r
            if str(r.data.get("name", "")).strip().lower() == str(source_identifier).strip().lower():
                return r
        return records[0] if records else None

    def extract_preview(
        self,
        connector_config: Dict[str, Any],
        company_identifier: str,
        canonical_entity_type: str,
        limit: int = 10,
    ) -> List[CanonicalDataRecord]:
        bounded_limit = min(limit, 50)
        res = self.extract(
            connector_config=connector_config,
            company_identifier=company_identifier,
            canonical_entity_type=canonical_entity_type,
            page_size=bounded_limit,
        )
        return res.get("records", [])

    def _parse_tally_response_items(self, xml_text: str, tag_name: str) -> List[Dict[str, Any]]:
        is_ok, root, err = parse_tally_xml_response(xml_text)
        if not is_ok or root is None:
            return []

        items = []
        xml_tag = tag_name.upper()
        for elem in root.findall(f".//{xml_tag}"):
            item_name = elem.get("NAME")
            if not item_name:
                name_elem = elem.find("NAME")
                if name_elem is None:
                    name_elem = elem.find(f"{xml_tag}.LIST/NAME")
                if name_elem is not None and name_elem.text:
                    item_name = name_elem.text.strip()

            parent_elem = elem.find("PARENT")
            guid_elem = elem.find("GUID")
            bal_elem = elem.find("CLOSINGBALANCE")
            op_bal_elem = elem.find("OPENINGBALANCE")
            addr_elem = elem.find("ADDRESS")
            phone_elem = elem.find("PHONE")
            email_elem = elem.find("EMAIL")
            gst_elem = elem.find("PARTYGSTIN")
            v_num_elem = elem.find("VOUCHERNUMBER")
            v_type_elem = elem.find("VOUCHERTYPENAME")
            v_date_elem = elem.find("DATE")
            alter_elem = elem.find("ALTERID")

            alter_id_val = None
            if alter_elem is not None and alter_elem.text and alter_elem.text.strip().isdigit():
                alter_id_val = int(alter_elem.text.strip())

            item_dict: Dict[str, Any] = {
                "name": item_name.strip() if item_name else None,
                "parent": parent_elem.text.strip() if parent_elem is not None and parent_elem.text else None,
                "guid": guid_elem.text.strip() if guid_elem is not None and guid_elem.text else None,
                "closing_balance": float(bal_elem.text.strip()) if bal_elem is not None and bal_elem.text else None,
                "opening_balance": float(op_bal_elem.text.strip()) if op_bal_elem is not None and op_bal_elem.text else None,
                "address": addr_elem.text.strip() if addr_elem is not None and addr_elem.text else None,
                "phone": phone_elem.text.strip() if phone_elem is not None and phone_elem.text else None,
                "email": email_elem.text.strip() if email_elem is not None and email_elem.text else None,
                "gstin": gst_elem.text.strip() if gst_elem is not None and gst_elem.text else None,
                "voucher_number": v_num_elem.text.strip() if v_num_elem is not None and v_num_elem.text else None,
                "voucher_type": v_type_elem.text.strip() if v_type_elem is not None and v_type_elem.text else None,
                "date": v_date_elem.text.strip() if v_date_elem is not None and v_date_elem.text else None,
                "alter_id": alter_id_val,
                "_raw_tag": xml_tag,
            }
            if item_dict["name"] or item_dict["voucher_number"] or item_dict["guid"]:
                items.append(item_dict)

        return items

    def _apply_in_memory_filters(
        self, raw_items: List[Dict[str, Any]], filters: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        if not filters:
            return raw_items

        filtered = []
        name_query = (filters.get("name") or filters.get("identifier") or "").strip().lower()
        v_type_filter = (filters.get("voucher_type") or "").strip().lower()

        for item in raw_items:
            i_name = str(item.get("name") or "").lower()
            i_vnum = str(item.get("voucher_number") or "").lower()
            i_guid = str(item.get("guid") or "").lower()

            if name_query and (name_query not in i_name and name_query not in i_vnum and name_query not in i_guid):
                continue

            if v_type_filter and v_type_filter not in str(item.get("voucher_type") or "").lower():
                continue

            filtered.append(item)

        return filtered

tally_data_extractor = TallyDataExtractor()
