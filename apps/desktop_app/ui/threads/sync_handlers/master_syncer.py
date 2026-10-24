from typing import List, Dict, Any, Tuple, Optional
from pymongo import UpdateOne
from shared.logging_config import get_logger
from shared.db.mongo_client import get_collection
from apps.backend.adapters.tally.request_builder import build_collection_xml
from apps.backend.adapters.tally.response_parser import parse_metadata_response
from apps.desktop_app.ui.threads.sync_handlers.common import chunk_list

logger = get_logger("app.threads.sync_handlers.master")

def sync_groups(worker, c_name: str, port: int, now_iso: str, org_oid, c_oid):
    from shared.config import get_settings
    if not get_settings().direct_mongo_sync_enabled:
        return
    try:
        grp_xml = build_collection_xml("Group", ["NAME", "PARENT", "GUID", "ALTERID", "ISADDABLE", "ISSUBLEDGER", "NATUREOFGROUP"], company_name=c_name)
        ok_g, code_g, text_g, err_g = worker.tally_client.send_xml_request(worker.tally_host, port, grp_xml, timeout=30.0)
        if ok_g and code_g == 200:
            grp_items = parse_metadata_response(text_g, tag_name="Group")
            grp_col = get_collection("groups")
            grp_ops = []
            for g in grp_items:
                g_doc = {
                    "source": "TALLY",
                    "company_name": c_name,
                    "tallyExternalId": g.get("tallyExternalId") or g.get("name"),
                    "name": g.get("name"),
                    "parent": g.get("parent"),
                    "isPrimary": g.get("isPrimary", False),
                    "isAddable": g.get("isAddable", True),
                    "isSubLedger": g.get("isSubLedger", False),
                    "natureOfGroup": g.get("natureOfGroup", ""),
                    "guid": g.get("guid"),
                    "alter_id": int(g.get("alterid", 0) or 0),
                    "raw": g.get("raw") or g,
                    "updated_at": now_iso
                }
                if org_oid:
                    g_doc["organizationId"] = org_oid
                if c_oid:
                    g_doc["companyId"] = c_oid
                grp_ops.append(UpdateOne({"name": g.get("name"), "company_name": c_name}, {"$set": g_doc}, upsert=True))
            if grp_ops:
                for chunk in chunk_list(grp_ops, 500):
                    grp_col.bulk_write(chunk, ordered=False)
        else:
            logger.warning(f"Groups extraction failed for '{c_name}': {err_g or f'HTTP {code_g}'}")
    except Exception as exc:
        logger.warning(f"Groups extraction error for '{c_name}': {exc}")

def sync_godowns(worker, c_name: str, port: int, now_iso: str, org_oid, c_oid):
    from shared.config import get_settings
    if not get_settings().direct_mongo_sync_enabled:
        return
    try:
        gd_xml = build_collection_xml("Godown", ["NAME", "PARENT", "GUID", "ALTERID", "ADDRESS.LIST"], company_name=c_name)
        ok_gd, code_gd, text_gd, err_gd = worker.tally_client.send_xml_request(worker.tally_host, port, gd_xml, timeout=30.0)
        if ok_gd and code_gd == 200:
            gd_items = parse_metadata_response(text_gd, tag_name="Godown")
            gd_col = get_collection("godowns")
            gd_ops = []
            for gd in gd_items:
                gd_doc = {
                    "source": "TALLY",
                    "company_name": c_name,
                    "tallyExternalId": gd.get("tallyExternalId") or gd.get("name"),
                    "name": gd.get("name"),
                    "parent": gd.get("parent"),
                    "address": gd.get("address", ""),
                    "guid": gd.get("guid"),
                    "alter_id": int(gd.get("alterid", 0) or 0),
                    "raw": gd.get("raw") or gd,
                    "updated_at": now_iso
                }
                if org_oid:
                    gd_doc["organizationId"] = org_oid
                if c_oid:
                    gd_doc["companyId"] = c_oid
                gd_ops.append(UpdateOne({"name": gd.get("name"), "company_name": c_name}, {"$set": gd_doc}, upsert=True))
            if gd_ops:
                for chunk in chunk_list(gd_ops, 500):
                    gd_col.bulk_write(chunk, ordered=False)
        else:
            logger.warning(f"Godowns extraction failed for '{c_name}': {err_gd or f'HTTP {code_gd}'}")
    except Exception as exc:
        logger.warning(f"Godowns extraction error for '{c_name}': {exc}")

def sync_units(worker, c_name: str, port: int, now_iso: str, org_oid, c_oid):
    from shared.config import get_settings
    if not get_settings().direct_mongo_sync_enabled:
        return
    try:
        u_xml = build_collection_xml("Unit", ["NAME", "SYMBOL", "ORIGINALNAME", "DECIMALPLACES", "GUID", "ALTERID"], company_name=c_name)
        ok_u, code_u, text_u, err_u = worker.tally_client.send_xml_request(worker.tally_host, port, u_xml, timeout=30.0)
        if ok_u and code_u == 200:
            u_items = parse_metadata_response(text_u, tag_name="Unit")
            u_col = get_collection("units")
            u_ops = []
            for u in u_items:
                u_doc = {
                    "source": "TALLY",
                    "company_name": c_name,
                    "tallyExternalId": u.get("tallyExternalId") or u.get("name"),
                    "name": u.get("name"),
                    "symbol": u.get("symbol"),
                    "originalName": u.get("originalName"),
                    "decimalPlaces": u.get("decimalPlaces", 0),
                    "guid": u.get("guid"),
                    "alter_id": int(u.get("alterid", 0) or 0),
                    "raw": u.get("raw") or u,
                    "updated_at": now_iso
                }
                if org_oid:
                    u_doc["organizationId"] = org_oid
                if c_oid:
                    u_doc["companyId"] = c_oid
                u_ops.append(UpdateOne({"name": u.get("name"), "company_name": c_name}, {"$set": u_doc}, upsert=True))
            if u_ops:
                for chunk in chunk_list(u_ops, 500):
                    u_col.bulk_write(chunk, ordered=False)
        else:
            logger.warning(f"Units extraction failed for '{c_name}': {err_u or f'HTTP {code_u}'}")
    except Exception as exc:
        logger.warning(f"Units extraction error for '{c_name}': {exc}")

def sync_stock_groups(worker, c_name: str, port: int, now_iso: str, org_oid, c_oid):
    from shared.config import get_settings
    if not get_settings().direct_mongo_sync_enabled:
        return
    try:
        sg_xml = build_collection_xml("StockGroup", ["NAME", "PARENT", "GUID", "ALTERID", "HSNCODE", "HSNDETAILS.LIST", "TARIFFLIST.LIST", "GSTDETAILS.LIST"], company_name=c_name)
        ok_sg, code_sg, text_sg, err_sg = worker.tally_client.send_xml_request(worker.tally_host, port, sg_xml, timeout=30.0)
        if ok_sg and code_sg == 200:
            sg_items = parse_metadata_response(text_sg, tag_name="StockGroup")
            sg_col = get_collection("stock_groups")
            sg_ops = []
            for sg in sg_items:
                sg_hsn = str(sg.get("hsnCode") or sg.get("hsn_code") or sg.get("hsn") or "").strip()
                sg_doc = {
                    "source": "TALLY",
                    "company_name": c_name,
                    "tallyExternalId": sg.get("tallyExternalId") or sg.get("name"),
                    "name": sg.get("name"),
                    "parent": sg.get("parent"),
                    "guid": sg.get("guid"),
                    "hsnCode": sg_hsn,
                    "hsn_code": sg_hsn,
                    "hsn": sg_hsn,
                    "alter_id": int(sg.get("alterid", 0) or 0),
                    "raw": sg.get("raw") or sg,
                    "updated_at": now_iso
                }
                if org_oid:
                    sg_doc["organizationId"] = org_oid
                if c_oid:
                    sg_doc["companyId"] = c_oid
                    sg_doc["cloud_company_id"] = str(c_oid)
                sg_filter = {"name": sg.get("name"), "company_name": c_name}
                if c_oid:
                    sg_filter["companyId"] = c_oid
                sg_ops.append(UpdateOne(sg_filter, {"$set": sg_doc}, upsert=True))
            if sg_ops:
                for chunk in chunk_list(sg_ops, 500):
                    sg_col.bulk_write(chunk, ordered=False)
        else:
            logger.warning(f"Stock groups extraction failed for '{c_name}': {err_sg or f'HTTP {code_sg}'}")
    except Exception as exc:
        logger.warning(f"Stock groups extraction notice: {exc}")

def sync_voucher_types(worker, c_name: str, port: int, now_iso: str, org_oid, c_oid):
    from shared.config import get_settings
    if not get_settings().direct_mongo_sync_enabled:
        return
    try:
        vt_xml = build_collection_xml(
            "VoucherType",
            ["NAME", "PARENT", "NUMBERINGMETHOD", "ISDEEMEDPOSITIVE", "AFFECTSSTOCK", "ISACTIVE", "GUID", "ALTERID"],
            company_name=c_name
        )
        ok_vt, code_vt, text_vt, err_vt = worker.tally_client.send_xml_request(worker.tally_host, port, vt_xml, timeout=30.0)
        if ok_vt and code_vt == 200:
            vt_items = parse_metadata_response(text_vt, tag_name="VoucherType")
            vt_col = get_collection("voucher_types")
            vt_ops = []
            for vt in vt_items:
                vt_doc = {
                    "source": "TALLY",
                    "company_name": c_name,
                    "tallyExternalId": vt.get("tallyExternalId") or vt.get("name"),
                    "name": vt.get("name"),
                    "parent": vt.get("parent"),
                    "guid": vt.get("guid"),
                    "alter_id": int(vt.get("alterid", 0) or 0),
                    "raw": vt.get("raw") or vt,
                    "updated_at": now_iso
                }
                if org_oid:
                    vt_doc["organizationId"] = org_oid
                if c_oid:
                    vt_doc["companyId"] = c_oid
                vt_ops.append(UpdateOne({"name": vt.get("name"), "company_name": c_name}, {"$set": vt_doc}, upsert=True))
            if vt_ops:
                for chunk in chunk_list(vt_ops, 500):
                    vt_col.bulk_write(chunk, ordered=False)
        else:
            logger.warning(f"Voucher types extraction failed for '{c_name}': {err_vt or f'HTTP {code_vt}'}")
    except Exception as exc:
        logger.warning(f"Voucher types extraction error for '{c_name}': {exc}")

