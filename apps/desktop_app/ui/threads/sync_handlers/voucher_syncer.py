from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime, timezone
from pymongo import UpdateOne, UpdateMany

from shared.logging_config import get_logger
from shared.db.mongo_client import get_collection
from apps.backend.adapters.tally.request_builder import build_collection_xml
from apps.backend.adapters.tally.response_parser import parse_metadata_response
from apps.desktop_app.ui.threads.sync_handlers.common import chunk_list, safe_bulk_write

logger = get_logger("app.threads.sync_handlers.voucher")

def sync_vouchers(worker, c_name: str, port: int, now_iso: str, org_oid, c_oid) -> Tuple[List[Dict[str, Any]], int]:
    extracted_vouchers: List[Dict[str, Any]] = []
    max_voucher_alter = 0
    try:
        v_xml = build_collection_xml(
            "Voucher",
            [
                "DATE", "EFFECTIVEDATE", "VOUCHERTYPENAME", "VOUCHERNUMBER", "REFERENCE", "REFERENCEDATE",
                "PARTYLEDGERNAME", "PARTYNAME", "BASICBUYERNAME", "PLACEOFSUPPLY", "AMOUNT", "NARRATION",
                "GUID", "ALTERID", "ISOPTIONAL", "ISCANCELLED", "ISPOSTDATED",
                "BASICSHIPDOCUMENTNO", "BASICSHIPPEDBY", "BASICFINALDESTINATION", "BASICSHIPDATE", "VEHICLENO",
                "BASICORDERREF", "BASICPURCHASEORDERNO", "BASICORDERDATE", "BASICORDERTERMS.LIST",
                "CONSIGNEEMAILINGNAME", "CONSIGNEEADDRESS.LIST", "CONSIGNEESTATENAME", "CONSIGNEECOUNTRYNAME",
                "CONSIGNEEPINCODE", "CONSIGNEEGSTIN", "PARTYGSTIN", "ADDRESS.LIST", "STATENAME", "PINCODE",
                "ALLLEDGERENTRIES.LIST",
                "ALLLEDGERENTRIES.BILLALLOCATIONS.LIST",
                "ALLLEDGERENTRIES.BILLALLOCATIONS.NAME",
                "ALLLEDGERENTRIES.BILLALLOCATIONS.BILLTYPE",
                "ALLLEDGERENTRIES.BILLALLOCATIONS.AMOUNT",
                "ALLLEDGERENTRIES.BILLALLOCATIONS.BILLCREDITPERIOD",
                "ALLLEDGERENTRIES.BILLALLOCATIONS.DUEDATEOFTOTALAMOUNT",
                "ALLINVENTORYENTRIES.LIST",
                "ALLINVENTORYENTRIES.STOCKITEMNAME",
                "ALLINVENTORYENTRIES.RATE",
                "ALLINVENTORYENTRIES.AMOUNT",
                "ALLINVENTORYENTRIES.ACTUALQTY",
                "ALLINVENTORYENTRIES.BILLEDQTY",
                "ALLINVENTORYENTRIES.GODOWNNAME",
                "ALLINVENTORYENTRIES.BATCHNAME",
                "ALLINVENTORYENTRIES.BATCHALLOCATIONS.LIST",
                "ALLINVENTORYENTRIES.BATCHALLOCATIONS.GODOWNNAME",
                "ALLINVENTORYENTRIES.BATCHALLOCATIONS.BATCHNAME",
                "ALLINVENTORYENTRIES.BATCHALLOCATIONS.BILLEDQTY",
                "ALLINVENTORYENTRIES.BATCHALLOCATIONS.AMOUNT",
                "ALLINVENTORYENTRIES.BATCHALLOCATIONS.BATCHRATE",
                "INVENTORYENTRIES.LIST",
                "INVENTORYENTRIES.STOCKITEMNAME",
                "INVENTORYENTRIES.RATE",
                "INVENTORYENTRIES.AMOUNT",
                "INVENTORYENTRIES.ACTUALQTY",
                "INVENTORYENTRIES.BILLEDQTY",
                "INVENTORYENTRIES.GODOWNNAME",
                "INVENTORYENTRIES.BATCHALLOCATIONS.LIST",
                "LEDGERENTRIES.LIST",
                "LEDGERENTRIES.BILLALLOCATIONS.LIST",
                "LEDGERENTRIES.BILLALLOCATIONS.NAME",
                "LEDGERENTRIES.BILLALLOCATIONS.BILLTYPE",
                "LEDGERENTRIES.BILLALLOCATIONS.AMOUNT",
                "LEDGERENTRIES.BILLALLOCATIONS.BILLCREDITPERIOD",
                "LEDGERENTRIES.BILLALLOCATIONS.DUEDATEOFTOTALAMOUNT"
            ],
            company_name=c_name,
            from_date="20000101",
            to_date="20991231"
        )
        ok_v, code_v, text_v, err_v = worker.tally_client.send_xml_request(worker.tally_host, port, v_xml, timeout=300.0)
        if ok_v and code_v == 200:
            extracted_vouchers = parse_metadata_response(text_v, tag_name="Voucher")
            for v in extracted_vouchers:
                alt = int(v.get("alterid", 0) or 0)
                if alt > max_voucher_alter:
                    max_voucher_alter = alt
        else:
            logger.error(f"Voucher extraction failed for '{c_name}': {err_v or f'HTTP {code_v}'}")

        if not extracted_vouchers:
            logger.info(f"Retrying voucher extraction for '{c_name}' with safe core fields fallback...")
            fallback_fields = [
                "DATE", "EFFECTIVEDATE", "VOUCHERTYPENAME", "VOUCHERNUMBER", "REFERENCE", "REFERENCEDATE",
                "PARTYLEDGERNAME", "PARTYNAME", "BASICBUYERNAME", "PLACEOFSUPPLY", "AMOUNT", "NARRATION",
                "GUID", "ALTERID", "ISOPTIONAL", "ISCANCELLED", "ISPOSTDATED",
                "BASICSHIPDOCUMENTNO", "BASICSHIPPEDBY", "BASICFINALDESTINATION", "BASICSHIPDATE", "VEHICLENO",
                "BASICORDERREF", "BASICPURCHASEORDERNO", "BASICORDERDATE", "BASICORDERTERMS.LIST",
                "CONSIGNEEMAILINGNAME", "CONSIGNEEADDRESS.LIST", "CONSIGNEESTATENAME", "CONSIGNEECOUNTRYNAME",
                "CONSIGNEEPINCODE", "CONSIGNEEGSTIN", "PARTYGSTIN", "ADDRESS.LIST", "STATENAME", "PINCODE",
                "ALLLEDGERENTRIES.LIST", "ALLINVENTORYENTRIES.LIST", "INVENTORYENTRIES.LIST",
                "ALLINVENTORYENTRIES.STOCKITEMNAME", "ALLINVENTORYENTRIES.RATE", "ALLINVENTORYENTRIES.AMOUNT",
                "ALLINVENTORYENTRIES.BILLEDQTY", "ALLINVENTORYENTRIES.GODOWNNAME"
            ]
            v_fb_xml = build_collection_xml("Voucher", fallback_fields, company_name=c_name, from_date="20000101", to_date="20991231")
            ok_fb, code_fb, text_fb, err_fb = worker.tally_client.send_xml_request(worker.tally_host, port, v_fb_xml, timeout=180.0)
            if ok_fb and code_fb == 200:
                extracted_vouchers = parse_metadata_response(text_fb, tag_name="Voucher")
                for v in extracted_vouchers:
                    alt = int(v.get("alterid", 0) or 0)
                    if alt > max_voucher_alter:
                        max_voucher_alter = alt

        if not extracted_vouchers:
            logger.info(f"Retrying voucher extraction for '{c_name}' with minimal raw collection fallback...")
            min_fields = [
                "DATE", "VOUCHERTYPENAME", "VOUCHERNUMBER", "PARTYLEDGERNAME", "PARTYNAME",
                "AMOUNT", "GUID", "ALTERID", "ALLLEDGERENTRIES.LIST"
            ]
            v_min_xml = build_collection_xml("Voucher", min_fields, company_name=c_name, from_date="20000101", to_date="20991231")
            ok_min, code_min, text_min, err_min = worker.tally_client.send_xml_request(worker.tally_host, port, v_min_xml, timeout=120.0)
            if ok_min and code_min == 200:
                extracted_vouchers = parse_metadata_response(text_min, tag_name="Voucher")
                for v in extracted_vouchers:
                    alt = int(v.get("alterid", 0) or 0)
                    if alt > max_voucher_alter:
                        max_voucher_alter = alt
    except Exception as exc:
        logger.warning(f"Voucher extraction error for '{c_name}': {exc}")

    if extracted_vouchers:
        try:
            now_dt = datetime.now(timezone.utc)
            v_col = get_collection("vouchers")
            sales_col = get_collection("sales_invoices")
            purch_col = get_collection("purchase_invoices")
            bank_col = get_collection("bank_transactions")
            bills_col = get_collection("bills_outstanding")

            v_ops, sales_ops, purch_ops, bank_ops, bills_ops = [], [], [], [], []

            for v in extracted_vouchers:
                alt_id = int(v.get("alterid", 0) or 0)
                v_num = str(v.get("voucherNumber") or v.get("voucher_number") or v.get("name") or "")
                v_type = str(v.get("voucherType") or v.get("voucher_type") or v.get("parent") or "")
                v_party = str(v.get("partyLedger") or v.get("party_ledger") or v.get("party") or "")
                raw_amt = v.get("amount") if v.get("amount") is not None else v.get("closing_balance")
                try:
                    amt_val = abs(float(raw_amt)) if raw_amt is not None else 0.0
                except (ValueError, TypeError):
                    amt_val = 0.0
                narr_val = str(v.get("narration") or "")
                guid_val = str(v.get("guid") or "")
                ext_id = str(v.get("tallyExternalId") or guid_val or v_num)
                if not guid_val:
                    guid_val = ext_id
                v_date = str(v.get("date") or v.get("effectiveDate") or "2023-04-01")
                eff_date = str(v.get("effectiveDate") or v_date)
                ref_val = str(v.get("reference") or "")
                ref_date_val = str(v.get("referenceDate") or v_date)
                place_val = str(v.get("placeOfSupply") or "")
                inv_entries = v.get("inventoryEntries") or v.get("items") or []
                led_entries = v.get("ledgerEntries") or v.get("lines") or []
                bill_allocs = v.get("billAllocations") or []
                bank_allocs = v.get("bankAllocations") or []

                adv_settings = v.get("advancedSettings") or {}
                dispatch_doc_no = str(adv_settings.get("dispatchDocNo") or v.get("dispatchDocNo") or "")
                dispatched_through = str(adv_settings.get("dispatchedThrough") or v.get("dispatchedThrough") or "")
                destination = str(adv_settings.get("destination") or v.get("destination") or "")
                vehicle_no = str(adv_settings.get("vehicleNo") or adv_settings.get("carrier") or v.get("vehicleNo") or "")
                order_no = str(adv_settings.get("orderNo") or v.get("orderNo") or "")
                order_date = str(adv_settings.get("orderDate") or v.get("orderDate") or "")
                terms_val = str(adv_settings.get("terms") or v.get("terms") or "")
                consignee_name = str(adv_settings.get("consigneeName") or v.get("consigneeName") or "")
                consignee_address = str(adv_settings.get("consigneeAddress") or v.get("consigneeAddress") or "")
                consignee_gstin = str(adv_settings.get("consigneeGstin") or v.get("consigneeGstin") or "")

                v_doc = {
                    "source": "TALLY",
                    "company_name": c_name,
                    "voucherId": ext_id,
                    "tallyExternalId": ext_id,
                    "voucherNumber": v_num,
                    "voucher_number": v_num,
                    "voucherType": v_type,
                    "voucher_type": v_type,
                    "partyLedger": v_party,
                    "party_ledger": v_party,
                    "partyName": v_party,
                    "customerName": v_party,
                    "customer": v_party,
                    "date": v_date,
                    "effectiveDate": eff_date,
                    "reference": ref_val,
                    "referenceDate": ref_date_val,
                    "placeOfSupply": place_val,
                    "amount": amt_val,
                    "narration": narr_val,
                    "isOptional": bool(v.get("isOptional", False)),
                    "isCancelled": bool(v.get("isCancelled", False)),
                    "isPostDated": bool(v.get("isPostDated", False)),
                    "items": inv_entries,
                    "lines": led_entries,
                    "ledgerEntries": led_entries,
                    "inventoryEntries": inv_entries,
                    "billAllocations": bill_allocs,
                    "bankAllocations": bank_allocs,
                    "advancedSettings": adv_settings,
                    "dispatchDocNo": dispatch_doc_no,
                    "dispatchedThrough": dispatched_through,
                    "destination": destination,
                    "vehicleNo": vehicle_no,
                    "orderNo": order_no,
                    "orderDate": order_date,
                    "terms": terms_val,
                    "consigneeName": consignee_name,
                    "consigneeAddress": consignee_address,
                    "consigneeGstin": consignee_gstin,
                    "guid": guid_val,
                    "alter_id": alt_id,
                    "raw": {
                        "voucherId": ext_id,
                        "tallyExternalId": ext_id,
                        "name": v_num,
                        "voucherNumber": v_num,
                        "parent": v_type,
                        "voucherType": v_type,
                        "party": v_party,
                        "partyLedger": v_party,
                        "customerName": v_party,
                        "date": v_date,
                        "reference": ref_val,
                        "referenceDate": ref_date_val,
                        "placeOfSupply": place_val,
                        "amount": amt_val,
                        "narration": narr_val,
                        "items": inv_entries,
                        "lines": led_entries,
                        "inventoryEntries": inv_entries,
                        "ledgerEntries": led_entries,
                        "billAllocations": bill_allocs,
                        "bankAllocations": bank_allocs,
                        "advancedSettings": adv_settings,
                        "dispatchDetails": {
                            "dispatchDocNo": dispatch_doc_no,
                            "dispatchedThrough": dispatched_through,
                            "destination": destination,
                            "vehicleNo": vehicle_no
                        },
                        "orderDetails": {
                            "orderNo": order_no,
                            "orderDate": order_date,
                            "terms": terms_val
                        },
                        "consigneeDetails": {
                            "consigneeName": consignee_name,
                            "consigneeAddress": consignee_address,
                            "consigneeGstin": consignee_gstin
                        },
                        "alterid": alt_id
                    }
                }
                if org_oid:
                    v_doc["organizationId"] = org_oid
                if c_oid:
                    v_doc["companyId"] = c_oid
                    v_doc["cloud_company_id"] = str(c_oid)
                v_filter: Dict[str, Any] = {"tallyExternalId": ext_id, "company_name": c_name}
                if org_oid:
                    v_filter["organizationId"] = org_oid
                if c_oid:
                    v_filter["companyId"] = c_oid
                v_ops.append(UpdateOne(v_filter, {"$set": v_doc, "$unset": {"updated_at": "", "updatedAt": ""}}, upsert=True))

                lower_type = v_type.lower()
                if any(k in lower_type for k in ["sales", "credit note"]):
                    sales_doc = {
                        "source": "TALLY",
                        "company_name": c_name,
                        "voucherId": ext_id,
                        "tallyExternalId": ext_id,
                        "invoiceNumber": v_num,
                        "voucherNumber": v_num,
                        "invoiceType": v_type,
                        "voucherType": v_type,
                        "invoiceDate": v_date,
                        "date": v_date,
                        "customer": v_party,
                        "customerName": v_party,
                        "partyLedger": v_party,
                        "placeOfSupply": place_val,
                        "reference": ref_val,
                        "referenceDate": ref_date_val,
                        "amount": amt_val,
                        "items": inv_entries,
                        "inventoryEntries": inv_entries,
                        "ledgerEntries": led_entries,
                        "lines": led_entries,
                        "billAllocations": bill_allocs,
                        "advancedSettings": adv_settings,
                        "dispatchDocNo": dispatch_doc_no,
                        "dispatchedThrough": dispatched_through,
                        "destination": destination,
                        "vehicleNo": vehicle_no,
                        "orderNo": order_no,
                        "orderDate": order_date,
                        "terms": terms_val,
                        "consigneeName": consignee_name,
                        "consigneeAddress": consignee_address,
                        "consigneeGstin": consignee_gstin,
                        "narration": narr_val,
                        "guid": guid_val,
                        "updated_at": now_iso
                    }
                    if org_oid:
                        sales_doc["organizationId"] = org_oid
                    if c_oid:
                        sales_doc["companyId"] = c_oid
                    sales_filter: Dict[str, Any] = {"tallyExternalId": ext_id, "company_name": c_name}
                    if org_oid:
                        sales_filter["organizationId"] = org_oid
                    if c_oid:
                        sales_filter["companyId"] = c_oid
                    sales_ops.append(UpdateOne(sales_filter, {"$set": sales_doc}, upsert=True))

                elif any(k in lower_type for k in ["purchase", "debit note"]):
                    purch_doc = {
                        "source": "TALLY",
                        "company_name": c_name,
                        "voucherId": ext_id,
                        "tallyExternalId": ext_id,
                        "invoiceNumber": v_num,
                        "voucherNumber": v_num,
                        "invoiceType": v_type,
                        "voucherType": v_type,
                        "invoiceDate": v_date,
                        "date": v_date,
                        "supplier": v_party,
                        "partyLedger": v_party,
                        "supplierInvoiceNumber": ref_val,
                        "reference": ref_val,
                        "supplierInvoiceDate": ref_date_val,
                        "referenceDate": ref_date_val,
                        "amount": amt_val,
                        "items": inv_entries,
                        "inventoryEntries": inv_entries,
                        "ledgerEntries": led_entries,
                        "lines": led_entries,
                        "billAllocations": bill_allocs,
                        "advancedSettings": adv_settings,
                        "dispatchDocNo": dispatch_doc_no,
                        "dispatchedThrough": dispatched_through,
                        "destination": destination,
                        "vehicleNo": vehicle_no,
                        "orderNo": order_no,
                        "orderDate": order_date,
                        "terms": terms_val,
                        "consigneeName": consignee_name,
                        "consigneeAddress": consignee_address,
                        "consigneeGstin": consignee_gstin,
                        "narration": narr_val,
                        "guid": guid_val,
                        "updated_at": now_iso
                    }
                    if org_oid:
                        purch_doc["organizationId"] = org_oid
                    if c_oid:
                        purch_doc["companyId"] = c_oid
                    purch_filter: Dict[str, Any] = {"tallyExternalId": ext_id, "company_name": c_name}
                    if org_oid:
                        purch_filter["organizationId"] = org_oid
                    if c_oid:
                        purch_filter["companyId"] = c_oid
                    purch_ops.append(UpdateOne(purch_filter, {"$set": purch_doc}, upsert=True))

                elif any(k in lower_type for k in ["receipt", "payment", "contra"]):
                    bank_doc = {
                        "source": "TALLY",
                        "company_name": c_name,
                        "voucherId": ext_id,
                        "tallyExternalId": ext_id,
                        "voucherNumber": v_num,
                        "voucherType": v_type,
                        "date": v_date,
                        "party": v_party,
                        "amount": amt_val,
                        "narration": narr_val,
                        "ledgerEntries": led_entries,
                        "lines": led_entries,
                        "billAllocations": bill_allocs,
                        "bankAllocations": bank_allocs,
                        "guid": guid_val,
                        "updated_at": now_iso
                    }
                    if org_oid:
                        bank_doc["organizationId"] = org_oid
                    if c_oid:
                        bank_doc["companyId"] = c_oid
                    bank_filter: Dict[str, Any] = {"tallyExternalId": ext_id, "company_name": c_name}
                    if org_oid:
                        bank_filter["organizationId"] = org_oid
                    if c_oid:
                        bank_filter["companyId"] = c_oid
                    bank_ops.append(UpdateOne(bank_filter, {"$set": bank_doc}, upsert=True))

                for b in bill_allocs:
                    b_name = str(b.get("billName") or v_num or "").strip()
                    b_party = str(b.get("party") or v_party or "").strip()
                    if not b_name:
                        continue
                    bill_doc = {
                        "source": "TALLY",
                        "company_name": c_name,
                        "voucherId": ext_id,
                        "party": b_party,
                        "billName": b_name,
                        "billType": str(b.get("billType") or "Agst Ref"),
                        "voucherNumber": v_num,
                        "billDate": v_date,
                        "dueDate": str(b.get("dueDate") or ""),
                        "amount": float(b.get("amount", 0.0) or 0.0),
                        "updated_at": now_iso
                    }
                    if org_oid:
                        bill_doc["organizationId"] = org_oid
                    if c_oid:
                        bill_doc["companyId"] = c_oid
                    bills_ops.append(UpdateOne(
                        {"billName": b_name, "party": b_party, "voucherNumber": v_num, "company_name": c_name},
                        {"$set": bill_doc},
                        upsert=True
                    ))

            for ops, col in [(v_ops, v_col), (sales_ops, sales_col), (purch_ops, purch_col), (bank_ops, bank_col), (bills_ops, bills_col)]:
                safe_bulk_write(col, ops, chunk_size=250)

            party_latest_voucher: Dict[str, str] = {}
            for v in extracted_vouchers:
                p = str(v.get("partyLedger") or v.get("party_ledger") or v.get("party") or "").strip()
                g = str(v.get("tallyExternalId") or v.get("guid") or v.get("voucherNumber") or "")
                if p and g:
                    party_latest_voucher[p] = g

            if party_latest_voucher:
                try:
                    cust_col = get_collection("customers")
                    supp_col = get_collection("suppliers")
                    c_updates = []
                    s_updates = []
                    for p_name, v_id in party_latest_voucher.items():
                        party_filter: Dict[str, Any] = {"name": p_name}
                        if c_oid:
                            party_filter["companyId"] = c_oid
                        elif c_name:
                            party_filter["company_name"] = c_name
                        if org_oid:
                            party_filter["organizationId"] = org_oid

                        c_updates.append(UpdateMany(party_filter, {"$set": {"voucherId": v_id, "raw.voucherId": v_id, "updatedAt": now_dt}}))
                        s_updates.append(UpdateMany(party_filter, {"$set": {"voucherId": v_id, "raw.voucherId": v_id, "updatedAt": now_dt}}))
                    if c_updates:
                        for chunk in chunk_list(c_updates, 500):
                            cust_col.bulk_write(chunk, ordered=False)
                    if s_updates:
                        for chunk in chunk_list(s_updates, 500):
                            supp_col.bulk_write(chunk, ordered=False)
                except Exception as c_err:
                    logger.debug(f"Customer/Supplier voucherId update notice: {c_err}")

        except Exception as m_exc:
            logger.warning(f"MongoDB voucher persistence notice: {m_exc}")

    return extracted_vouchers, max_voucher_alter

