"""
CtrlBooks - Profit and Loss (Purchase & Sales Accounts) Syncer
-------------------------------------------------------------
Extracts period-specific Profit & Loss accounts (Purchase Accounts, Sales Accounts,
and high-level P&L metrics) from Tally scoped strictly to the active sync date range
(from_date -> to_date).
"""

from typing import List, Dict, Any, Optional
from shared.logging_config import get_logger
from apps.backend.adapters.tally.response_parser import parse_metadata_response
from shared.cloud.helpers import format_tally_date

logger = get_logger("app.threads.sync_handlers.pl")

def sync_pl_accounts(
    tally_client,
    host: str,
    port: int,
    company_name: str,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Extracts Purchase Accounts, Sales Accounts, and Profit & Loss summary from Tally
    strictly scoped to the provided date range (from_date to to_date).
    """
    try:
        # Format dates for Tally XML: YYYYMMDD
        clean_company = (company_name or "").strip().replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        
        f_date_str = str(from_date).strip() if from_date else "2020-04-01"
        t_date_str = str(to_date).strip() if to_date else "2099-03-31"

        f_d_tally = f_date_str.replace("-", "").strip()
        t_d_tally = t_date_str.replace("-", "").strip()

        fmt_from = format_tally_date(from_date) if from_date else None
        fmt_to = format_tally_date(to_date) if to_date else None

        # 1. Query Tally Collection for Ledgers under the active company & date range
        xml = f"""<ENVELOPE>
    <HEADER>
        <VERSION>1</VERSION>
        <TALLYREQUEST>EXPORT</TALLYREQUEST>
        <TYPE>COLLECTION</TYPE>
        <ID>PLCollection</ID>
    </HEADER>
    <BODY>
        <DESC>
            <STATICVARIABLES>
                <SVEXPORTFORMAT>$$SYSNAME:XML</SVEXPORTFORMAT>
                <SVCURRENTCOMPANY>{clean_company}</SVCURRENTCOMPANY>
                <SVFROMDATE TYPE="Date">{f_d_tally}</SVFROMDATE>
                <SVTODATE TYPE="Date">{t_d_tally}</SVTODATE>
            </STATICVARIABLES>
            <TDL>
                <TDLMESSAGE>
                    <COLLECTION NAME="PLCollection" ISINITIALISE="Yes">
                        <TYPE>Ledger</TYPE>
                        <FETCH>NAME,PARENT,CLOSINGBALANCE,OPENINGBALANCE,CLOSINGBALANCEDATE</FETCH>
                    </COLLECTION>
                </TDLMESSAGE>
            </TDL>
        </DESC>
    </BODY>
</ENVELOPE>"""

        ok, code, txt, err = tally_client.send_xml_request(host, port, xml, timeout=30.0)
        if not ok or code != 200:
            logger.warning(f"PL extraction collection request failed for '{company_name}': {err or f'HTTP {code}'}")
            return []

        ledgers = parse_metadata_response(txt, "Ledger")

        # 2. Categorize ledgers across all P&L groups
        purchase_ledgers = []
        purchase_total = 0.0

        sales_ledgers = []
        sales_total = 0.0

        direct_exp_ledgers = []
        direct_exp_total = 0.0

        indirect_exp_ledgers = []
        indirect_exp_total = 0.0

        direct_inc_ledgers = []
        direct_inc_total = 0.0

        indirect_inc_ledgers = []
        indirect_inc_total = 0.0

        for l in ledgers:
            parent = str(l.get("parent") or "").strip().lower()
            raw_bal = float(l.get("closingBalance") or 0.0)
            if abs(raw_bal) <= 0.0001:
                continue
            l_name = str(l.get("name") or "").strip()

            if parent == "purchase accounts" or "purchase account" in parent:
                # In Tally XML, Debit purchase is negative in CLOSINGBALANCE, Credit is positive
                display_amt = -raw_bal
                purchase_total += display_amt
                purchase_ledgers.append({
                    "ledgerName": l_name,
                    "amount": round(display_amt, 2),
                    "rawAmount": raw_bal,
                    "drCr": "Dr" if raw_bal < 0 else "Cr"
                })
            elif parent == "sales accounts" or "sales account" in parent:
                # In Tally XML, Credit sales is positive in CLOSINGBALANCE
                display_amt = raw_bal
                sales_total += display_amt
                sales_ledgers.append({
                    "ledgerName": l_name,
                    "amount": round(display_amt, 2),
                    "rawAmount": raw_bal,
                    "drCr": "Cr" if raw_bal > 0 else "Dr"
                })
            elif "indirect exp" in parent:
                # Indirect expenses (Debit side): Dr is negative in XML CLOSINGBALANCE
                display_amt = -raw_bal
                indirect_exp_total += display_amt
                indirect_exp_ledgers.append({
                    "ledgerName": l_name,
                    "amount": round(display_amt, 2),
                    "rawAmount": raw_bal,
                    "drCr": "Dr" if raw_bal < 0 else "Cr"
                })
            elif "direct exp" in parent:
                # Direct expenses (Debit side): Dr is negative in XML CLOSINGBALANCE
                display_amt = -raw_bal
                direct_exp_total += display_amt
                direct_exp_ledgers.append({
                    "ledgerName": l_name,
                    "amount": round(display_amt, 2),
                    "rawAmount": raw_bal,
                    "drCr": "Dr" if raw_bal < 0 else "Cr"
                })
            elif "indirect inc" in parent:
                # Indirect incomes (Credit side): Cr is positive in XML CLOSINGBALANCE
                display_amt = raw_bal
                indirect_inc_total += display_amt
                indirect_inc_ledgers.append({
                    "ledgerName": l_name,
                    "amount": round(display_amt, 2),
                    "rawAmount": raw_bal,
                    "drCr": "Cr" if raw_bal > 0 else "Dr"
                })
            elif "direct inc" in parent:
                # Direct incomes (Credit side): Cr is positive in XML CLOSINGBALANCE
                display_amt = raw_bal
                direct_inc_total += display_amt
                direct_inc_ledgers.append({
                    "ledgerName": l_name,
                    "amount": round(display_amt, 2),
                    "rawAmount": raw_bal,
                    "drCr": "Cr" if raw_bal > 0 else "Dr"
                })

        purchase_ledgers.sort(key=lambda x: abs(x["amount"]), reverse=True)
        sales_ledgers.sort(key=lambda x: abs(x["amount"]), reverse=True)
        direct_exp_ledgers.sort(key=lambda x: abs(x["amount"]), reverse=True)
        indirect_exp_ledgers.sort(key=lambda x: abs(x["amount"]), reverse=True)
        direct_inc_ledgers.sort(key=lambda x: abs(x["amount"]), reverse=True)
        indirect_inc_ledgers.sort(key=lambda x: abs(x["amount"]), reverse=True)

        # 3. Extract Opening/Closing Stock and Gross Profit from P&L report
        pl_summary = {
            "openingStock": 0.0,
            "closingStock": 0.0,
            "grossProfit": 0.0,
            "nettProfit": 0.0,
            "directExpenses": 0.0,
            "indirectExpenses": 0.0,
            "indirectIncomes": 0.0,
            "directIncomes": 0.0,
            "purchaseAccounts": 0.0,
            "salesAccounts": 0.0
        }

        report_xml = f"""<ENVELOPE>
  <HEADER>
    <TALLYREQUEST>Export Data</TALLYREQUEST>
  </HEADER>
  <BODY>
    <EXPORTDATA>
      <REQUESTDESC>
        <REPORTNAME>Profit and Loss</REPORTNAME>
        <STATICVARIABLES>
          <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
          <SVCURRENTCOMPANY>{clean_company}</SVCURRENTCOMPANY>
          <SVFROMDATE TYPE="Date">{f_d_tally}</SVFROMDATE>
          <SVTODATE TYPE="Date">{t_d_tally}</SVTODATE>
        </STATICVARIABLES>
      </REQUESTDESC>
    </EXPORTDATA>
  </BODY>
</ENVELOPE>"""

        ok_r, code_r, txt_r, _ = tally_client.send_xml_request(host, port, report_xml, timeout=30.0)
        if ok_r and code_r == 200:
            import xml.etree.ElementTree as ET
            try:
                root = ET.fromstring(txt_r)
                current_name = ""
                for elem in root:
                    if elem.tag == "DSPACCNAME":
                        disp = elem.find("DSPDISPNAME")
                        if disp is not None and disp.text:
                            current_name = disp.text.strip().lower()
                    elif elem.tag == "PLAMT":
                        sub = elem.find("PLSUBAMT")
                        main = elem.find("BSMAINAMT")
                        val_str = ""
                        if sub is not None and sub.text and sub.text.strip():
                            val_str = sub.text.strip()
                        elif main is not None and main.text and main.text.strip():
                            val_str = main.text.strip()
                        if val_str:
                            try:
                                v = abs(float(val_str.replace(",", "")))
                                if "opening stock" in current_name:
                                    pl_summary["openingStock"] = v
                                elif "closing stock" in current_name:
                                    pl_summary["closingStock"] = v
                                elif "indirect expenses" in current_name or "indirect expense" in current_name:
                                    pl_summary["indirectExpenses"] = v
                                elif "direct expenses" in current_name or "direct expense" in current_name:
                                    pl_summary["directExpenses"] = v
                                elif "indirect incomes" in current_name or "indirect income" in current_name:
                                    pl_summary["indirectIncomes"] = v
                                elif "direct incomes" in current_name or "direct income" in current_name:
                                    pl_summary["directIncomes"] = v
                                elif "gross profit" in current_name:
                                    pl_summary["grossProfit"] = v
                                elif "nett profit" in current_name or "net profit" in current_name:
                                    pl_summary["nettProfit"] = v
                                elif "purchase accounts" in current_name:
                                    pl_summary["purchaseAccounts"] = v
                                elif "sales accounts" in current_name:
                                    pl_summary["salesAccounts"] = v
                            except Exception:
                                pass
            except Exception:
                pass

        # Reconcile summary totals with ledger sums if report was empty or missing sub-totals
        eff_direct_exp = pl_summary["directExpenses"] if pl_summary.get("directExpenses", 0.0) > 0 else round(direct_exp_total, 2)
        eff_indirect_exp = pl_summary["indirectExpenses"] if pl_summary.get("indirectExpenses", 0.0) > 0 else round(indirect_exp_total, 2)
        eff_direct_inc = pl_summary.get("directIncomes", 0.0) if pl_summary.get("directIncomes", 0.0) > 0 else round(direct_inc_total, 2)
        eff_indirect_inc = pl_summary["indirectIncomes"] if pl_summary.get("indirectIncomes", 0.0) > 0 else round(indirect_inc_total, 2)

        if purchase_total == 0.0 and pl_summary.get("purchaseAccounts", 0.0) > 0.0:
            purchase_total = pl_summary["purchaseAccounts"]
        if sales_total == 0.0 and pl_summary.get("salesAccounts", 0.0) > 0.0:
            sales_total = pl_summary["salesAccounts"]

        # Calculate Gross Profit and Nett Profit matching Tally P&L report
        if pl_summary["grossProfit"] == 0.0 and (sales_total > 0 or purchase_total > 0):
            calc_gp = (sales_total + eff_direct_inc + pl_summary["closingStock"]) - (pl_summary["openingStock"] + purchase_total + eff_direct_exp)
            pl_summary["grossProfit"] = round(calc_gp, 2)

        if pl_summary["nettProfit"] == 0.0 and pl_summary["grossProfit"] != 0.0:
            calc_np = pl_summary["grossProfit"] + eff_indirect_inc - eff_indirect_exp
            pl_summary["nettProfit"] = round(calc_np, 2)

        # Build records to push
        records: List[Dict[str, Any]] = [
            {
                "category": "PURCHASE_ACCOUNTS",
                "side": "DEBIT",
                "groupName": "Purchase Accounts",
                "totalAmount": round(purchase_total, 2),
                "startDate": fmt_from,
                "endDate": fmt_to,
                "ledgers": purchase_ledgers
            },
            {
                "category": "SALES_ACCOUNTS",
                "side": "CREDIT",
                "groupName": "Sales Accounts",
                "totalAmount": round(sales_total, 2),
                "startDate": fmt_from,
                "endDate": fmt_to,
                "ledgers": sales_ledgers
            },
            {
                "category": "DIRECT_EXPENSES",
                "side": "DEBIT",
                "groupName": "Direct Expenses",
                "totalAmount": round(eff_direct_exp, 2),
                "startDate": fmt_from,
                "endDate": fmt_to,
                "ledgers": direct_exp_ledgers
            },
            {
                "category": "INDIRECT_EXPENSES",
                "side": "DEBIT",
                "groupName": "Indirect Expenses",
                "totalAmount": round(eff_indirect_exp, 2),
                "startDate": fmt_from,
                "endDate": fmt_to,
                "ledgers": indirect_exp_ledgers
            },
            {
                "category": "DIRECT_INCOMES",
                "side": "CREDIT",
                "groupName": "Direct Incomes",
                "totalAmount": round(eff_direct_inc, 2),
                "startDate": fmt_from,
                "endDate": fmt_to,
                "ledgers": direct_inc_ledgers
            },
            {
                "category": "INDIRECT_INCOMES",
                "side": "CREDIT",
                "groupName": "Indirect Incomes",
                "totalAmount": round(eff_indirect_inc, 2),
                "startDate": fmt_from,
                "endDate": fmt_to,
                "ledgers": indirect_inc_ledgers
            },
            {
                "category": "PL_SUMMARY",
                "groupName": "Profit & Loss Summary",
                "startDate": fmt_from,
                "endDate": fmt_to,
                "openingStock": round(pl_summary.get("openingStock", 0.0), 2),
                "closingStock": round(pl_summary.get("closingStock", 0.0), 2),
                "grossProfit": round(pl_summary.get("grossProfit", 0.0), 2),
                "nettProfit": round(pl_summary.get("nettProfit", 0.0), 2),
                "purchaseAccountsTotal": round(purchase_total, 2),
                "salesAccountsTotal": round(sales_total, 2),
                "purchaseAccounts": round(purchase_total, 2),
                "salesAccounts": round(sales_total, 2),
                "directExpenses": round(eff_direct_exp, 2),
                "indirectExpenses": round(eff_indirect_exp, 2),
                "directIncomes": round(eff_direct_inc, 2),
                "indirectIncomes": round(eff_indirect_inc, 2)
            }
        ]

        logger.info(
            f"Extracted PL accounts for '{company_name}' [{fmt_from} -> {fmt_to}]: "
            f"Purchase={round(purchase_total, 2)} ({len(purchase_ledgers)}), "
            f"Sales={round(sales_total, 2)} ({len(sales_ledgers)}), "
            f"DirectExp={round(eff_direct_exp, 2)} ({len(direct_exp_ledgers)}), "
            f"IndirectExp={round(eff_indirect_exp, 2)} ({len(indirect_exp_ledgers)}), "
            f"DirectInc={round(eff_direct_inc, 2)} ({len(direct_inc_ledgers)}), "
            f"IndirectInc={round(eff_indirect_inc, 2)} ({len(indirect_inc_ledgers)})"
        )
        return records

    except Exception as exc:
        logger.warning(f"Error extracting PL accounts for '{company_name}': {exc}")
        return []

