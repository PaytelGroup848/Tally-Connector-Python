from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime, timezone
from pymongo import UpdateOne

from shared.logging_config import get_logger
from shared.db.mongo_client import get_collection
from apps.backend.adapters.tally.request_builder import build_collection_xml
from apps.backend.adapters.tally.response_parser import parse_metadata_response
from apps.desktop_app.ui.threads.sync_handlers.common import chunk_list, safe_bulk_write

logger = get_logger("app.threads.sync_handlers.stock")

def sync_stock_items(worker, c_name: str, port: int, now_iso: str, org_oid, c_oid) -> Tuple[List[Dict[str, Any]], int]:
    extracted_stock_items: List[Dict[str, Any]] = []
    max_stock_alter = 0
    try:
        s_xml = build_collection_xml(
            "StockItem",
            ["NAME", "PARENT", "CATEGORY", "BASEUNITS", "ADDITIONALUNITS", "GSTREPUOM", "CLOSINGBALANCE", "OPENINGBALANCE", "STARTINGFROM", "ACTIVEFROM", "APPLICABLEFROM", "CLOSINGRATE", "CLOSINGVALUE", "OPENINGRATE", "OPENINGVALUE", "HSNCODE", "GSTAPPLICABLE", "HSNDETAILS.LIST", "GSTDETAILS.LIST", "TARIFFLIST.LIST", "TARIFFCODE", "GSTCLASSIFICATION", "GSTHSNNAME", "HSNNAME", "BATCHNAME", "BATCHALLOCATIONS.LIST", "GODOWNALLOCATIONS.LIST", "GUID", "ALTERID", "REORDERLEVEL"],
            company_name=c_name
        )
        ok_s, code_s, text_s, err_s = worker.tally_client.send_xml_request(worker.tally_host, port, s_xml, timeout=60.0)
        if ok_s and code_s == 200:
            extracted_stock_items = parse_metadata_response(text_s, tag_name="StockItem")
            for s in extracted_stock_items:
                alt = int(s.get("alterid", 0) or 0)
                if alt > max_stock_alter:
                    max_stock_alter = alt
        else:
            logger.error(f"Stock items extraction failed for '{c_name}': {err_s or f'HTTP {code_s}'}")
    except Exception as exc:
        logger.warning(f"Stock items extraction error for '{c_name}': {exc}")

    from shared.config import get_settings
    if extracted_stock_items and get_settings().direct_mongo_sync_enabled:
        try:
            s_col = get_collection("stock_items")
            stocks_col = get_collection("stocks")
            stockbal_col = get_collection("stockbalances")
            items_col = get_collection("items")
            units_col = get_collection("units")

            # Build units lookup
            units_lookup: Dict[str, Dict[str, Any]] = {}
            try:
                for u_doc in units_col.find({"company_name": c_name}):
                    u_name = str(u_doc.get("name") or "").strip()
                    u_sym = str(u_doc.get("symbol") or "").strip()
                    raw_u = u_doc.get("raw") or {}
                    u_info = {
                        "name": u_name or u_sym,
                        "symbol": u_sym or u_name,
                        "guid": str(u_doc.get("guid") or raw_u.get("guid") or ""),
                        "alterid": int(u_doc.get("alter_id") or raw_u.get("alterid") or 0)
                    }
                    if u_name:
                        units_lookup[u_name.lower()] = u_info
                    if u_sym:
                        units_lookup[u_sym.lower()] = u_info
            except Exception as u_exc:
                logger.debug(f"Units lookup notice: {u_exc}")

            # Build stock groups lookup for HSN and GST inheritance
            stock_groups_lookup: Dict[str, str] = {}
            stock_groups_gst_lookup: Dict[str, float] = {}
            group_parent_map: Dict[str, str] = {}
            try:
                sg_col = get_collection("stock_groups")
                sg_query: Dict[str, Any] = {"$or": [{"company_name": c_name}]}
                if c_oid:
                    sg_query["$or"].append({"companyId": c_oid})
                for sg_doc in sg_col.find(sg_query):
                    sgn = str(sg_doc.get("name") or "").strip().lower()
                    sgh = str(sg_doc.get("hsnCode") or sg_doc.get("hsn_code") or sg_doc.get("hsn") or "").strip()
                    sgp = str(sg_doc.get("parent") or "").strip().lower()
                    try:
                        sg_gst = float(sg_doc.get("gstRate") or sg_doc.get("gst_rate") or sg_doc.get("taxRate") or sg_doc.get("tax_rate") or 0.0)
                    except (ValueError, TypeError):
                        sg_gst = 0.0
                    if sgn:
                        group_parent_map[sgn] = sgp
                        if sgh:
                            stock_groups_lookup[sgn] = sgh
                        if sg_gst > 0.0:
                            stock_groups_gst_lookup[sgn] = sg_gst
            except Exception as sg_exc:
                logger.debug(f"Stock groups lookup notice: {sg_exc}")

            def resolve_group_hsn(grp_name: str) -> str:
                curr = (grp_name or "").strip().lower()
                visited = set()
                while curr and curr not in visited:
                    visited.add(curr)
                    if curr in stock_groups_lookup and stock_groups_lookup[curr]:
                        return stock_groups_lookup[curr]
                    curr = group_parent_map.get(curr, "")
                return ""

            def resolve_group_gst_rate(grp_name: str) -> float:
                curr = (grp_name or "").strip().lower()
                visited = set()
                while curr and curr not in visited:
                    visited.add(curr)
                    if curr in stock_groups_gst_lookup and stock_groups_gst_lookup[curr]:
                        return stock_groups_gst_lookup[curr]
                    curr = group_parent_map.get(curr, "")
                return 0.0

            now_utc = datetime.now(timezone.utc)
            s_ops = []
            items_ops = []
            stocks_ops = []
            stockbal_ops = []

            for s_idx, s in enumerate(extracted_stock_items, start=1):
                alt_id = int(s.get("alterid", 0) or 0)
                ext_id = str(s.get("tallyExternalId") or s.get("guid") or s.get("name") or f"STOCK-{s_idx:03d}")
                item_name = str(s.get("name") or s.get("itemName") or "")
                item_ext_id = str(s.get("guid") or s.get("itemTallyExternalId") or ext_id)
                godown_name = str(s.get("godown") or "Main Location")
                batch_val = str(s.get("batch") or s.get("batchName") or s.get("batch_name") or "Primary Batch").strip()
                unit_val = str(s.get("unit") or s.get("units") or s.get("baseUnits") or s.get("base_units") or s.get("uom") or "").strip()
                hsn_val = str(s.get("hsnCode") or s.get("hsn_code") or s.get("hsn") or "").strip()

                # Fallback HSN and GST inheritance from parent Stock Group
                parent_grp = str(s.get("parent") or s.get("group") or "").strip()
                if not hsn_val and parent_grp:
                    hsn_val = resolve_group_hsn(parent_grp)

                try:
                    gst_rate_val = float(s.get("gstRate") or s.get("gst_rate") or s.get("taxRate") or s.get("tax_rate") or 0.0)
                except (ValueError, TypeError):
                    gst_rate_val = 0.0
                if gst_rate_val <= 0.0 and parent_grp:
                    gst_rate_val = resolve_group_gst_rate(parent_grp)

                taxability_val = str(s.get("taxability") or ("Taxable" if gst_rate_val > 0 else "Exempt"))

                unit_obj = units_lookup.get(unit_val.lower())
                if not unit_obj and unit_val:
                    unit_obj = {
                        "name": unit_val,
                        "symbol": unit_val,
                        "guid": "",
                        "alterid": 0
                    }

                if not unit_val:
                    unit_val = "Pcs"

                # Populate extracted_stock_items in-place for cloud sync
                s["unit"] = unit_val
                s["units"] = unit_val
                s["uom"] = unit_val
                s["unit_name"] = unit_val
                s["baseUnits"] = unit_val
                s["base_units"] = unit_val
                s["hsnCode"] = hsn_val
                s["hsn_code"] = hsn_val
                s["hsn"] = hsn_val
                s["gstRate"] = gst_rate_val
                s["gst_rate"] = gst_rate_val
                s["taxRate"] = gst_rate_val
                s["tax_rate"] = gst_rate_val
                s["taxability"] = taxability_val
                s["parent"] = parent_grp
                s["group"] = parent_grp

                try:
                    qty = float(s.get("quantity", 0.0) or s.get("closingBalance", 0.0) or 0.0)
                except (ValueError, TypeError):
                    qty = 0.0
                try:
                    rate = float(s.get("rate", 0.0) or s.get("closingRate", 0.0) or 0.0)
                except (ValueError, TypeError):
                    rate = 0.0
                try:
                    val = float(s.get("value", 0.0) or s.get("closingValue", 0.0) or 0.0)
                except (ValueError, TypeError):
                    val = 0.0
                if val == 0.0 and qty != 0.0 and rate != 0.0:
                    val = round(qty * rate, 2)

                s_doc = {
                    "source": "TALLY",
                    "company_name": c_name,
                    "tallyExternalId": ext_id,
                    "name": item_name,
                    "itemName": item_name,
                    "itemTallyExternalId": item_ext_id,
                    "godown": godown_name,
                    "batch": batch_val,
                    "quantity": qty,
                    "rate": rate,
                    "value": val,
                    "parent": s.get("parent"),
                    "group": s.get("group") or s.get("parent"),
                    "category": s.get("category", ""),
                    "unit": unit_val,
                    "units": unit_val,
                    "uom": unit_val,
                    "unit_name": unit_val,
                    "baseUnits": unit_val,
                    "base_units": unit_val,
                    "unit_details": unit_obj,
                    "alternateUnit": s.get("alternateUnit", ""),
                    "hsnCode": hsn_val,
                    "hsn_code": hsn_val,
                    "hsn": hsn_val,
                    "gstRate": gst_rate_val,
                    "gst_rate": gst_rate_val,
                    "taxRate": gst_rate_val,
                    "tax_rate": gst_rate_val,
                    "taxability": taxability_val,
                    "gstApplicable": s.get("gstApplicable", "Applicable"),
                    "reorderLevel": s.get("reorderLevel", "0"),
                    "date": str(s.get("date") or "2022-04-01"),
                    "openingBalance": s.get("openingBalance", 0.0),
                    "openingRate": s.get("openingRate", 0.0),
                    "openingValue": s.get("openingValue", 0.0),
                    "closingBalance": qty,
                    "closingRate": rate,
                    "closingValue": val,
                    "guid": s.get("guid"),
                    "alter_id": alt_id,
                    "raw": s.get("raw") or s,
                    "updated_at": now_iso
                }
                if org_oid:
                    s_doc["organizationId"] = org_oid
                if c_oid:
                    s_doc["companyId"] = c_oid
                    s_doc["cloud_company_id"] = str(c_oid)
                item_filter: Dict[str, Any] = {"tallyExternalId": ext_id, "company_name": c_name}
                if org_oid:
                    item_filter["organizationId"] = org_oid
                if c_oid:
                    item_filter["companyId"] = c_oid
                s_ops.append(UpdateOne(item_filter, {"$set": s_doc}, upsert=True))
                items_ops.append(UpdateOne(item_filter, {"$set": s_doc}, upsert=True))

                stock_record_doc = {
                    "tallyExternalId": ext_id,
                    "itemName": item_name,
                    "name": item_name,
                    "itemTallyExternalId": item_ext_id,
                    "parent": parent_grp,
                    "group": parent_grp,
                    "category": s.get("category", ""),
                    "unit": unit_val,
                    "units": unit_val,
                    "uom": unit_val,
                    "unit_name": unit_val,
                    "baseUnits": unit_val,
                    "base_units": unit_val,
                    "unit_details": unit_obj,
                    "hsnCode": hsn_val,
                    "hsn_code": hsn_val,
                    "hsn": hsn_val,
                    "gstRate": gst_rate_val,
                    "gst_rate": gst_rate_val,
                    "taxRate": gst_rate_val,
                    "tax_rate": gst_rate_val,
                    "taxability": taxability_val,
                    "godown": godown_name,
                    "batch": batch_val,
                    "quantity": qty,
                    "rate": rate,
                    "value": val,
                    "company_name": c_name,
                    "source": "TALLY",
                    "updated_at": now_iso
                }
                if org_oid:
                    stock_record_doc["organizationId"] = org_oid
                if c_oid:
                    stock_record_doc["companyId"] = c_oid
                    stock_record_doc["cloud_company_id"] = str(c_oid)
                stocks_filter: Dict[str, Any] = {"tallyExternalId": ext_id, "company_name": c_name}
                if org_oid:
                    stocks_filter["organizationId"] = org_oid
                if c_oid:
                    stocks_filter["companyId"] = c_oid
                stocks_ops.append(UpdateOne(
                    stocks_filter,
                    {"$set": stock_record_doc},
                    upsert=True
                ))

                stockbal_doc = {
                    "tallyExternalId": ext_id,
                    "itemName": item_name,
                    "name": item_name,
                    "itemTallyExternalId": item_ext_id,
                    "parent": parent_grp,
                    "group": parent_grp,
                    "category": s.get("category", ""),
                    "unit": unit_val,
                    "units": unit_val,
                    "uom": unit_val,
                    "unit_name": unit_val,
                    "baseUnits": unit_val,
                    "base_units": unit_val,
                    "hsnCode": hsn_val,
                    "hsn_code": hsn_val,
                    "hsn": hsn_val,
                    "gstRate": gst_rate_val,
                    "gst_rate": gst_rate_val,
                    "taxRate": gst_rate_val,
                    "tax_rate": gst_rate_val,
                    "taxability": taxability_val,
                    "godown": godown_name,
                    "batch": batch_val,
                    "quantity": qty,
                    "rate": rate,
                    "value": val,
                    "company_name": c_name,
                    "source": "TALLY",
                    "raw": {
                        "tallyExternalId": ext_id,
                        "itemName": item_name,
                        "itemTallyExternalId": item_ext_id,
                        "unit": unit_obj if unit_obj else unit_val,
                        "units": unit_val,
                        "uom": unit_val,
                        "unit_name": unit_val,
                        "hsnCode": hsn_val,
                        "hsn_code": hsn_val,
                        "hsn": hsn_val,
                        "godown": godown_name,
                        "batch": batch_val,
                        "quantity": qty,
                        "rate": rate,
                        "value": val,
                        "voucherId": s.get("voucherId"),
                    },
                    "updatedAt": now_utc
                }
                stockbal_filter = {"tallyExternalId": ext_id, "company_name": c_name}
                if org_oid:
                    stockbal_filter["organizationId"] = org_oid
                    stockbal_doc["organizationId"] = org_oid
                if c_oid:
                    stockbal_filter["companyId"] = c_oid
                    stockbal_doc["companyId"] = c_oid
                    stockbal_doc["cloud_company_id"] = str(c_oid)

                stockbal_ops.append(UpdateOne(
                    stockbal_filter,
                    {"$set": stockbal_doc, "$setOnInsert": {"createdAt": now_utc, "__v": 0}},
                    upsert=True
                ))

            for ops, col in [(s_ops, s_col), (items_ops, items_col), (stocks_ops, stocks_col), (stockbal_ops, stockbal_col)]:
                safe_bulk_write(col, ops, chunk_size=250)
        except Exception as m_exc:
            logger.warning(f"MongoDB stock item persistence notice: {m_exc}")

    return extracted_stock_items, max_stock_alter

