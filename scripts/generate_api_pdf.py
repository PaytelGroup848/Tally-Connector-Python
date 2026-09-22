"""
CtrlBooks - API Documentation PDF Generator
Generates a comprehensive, professional PDF documenting all APIs across the system.
Optimized for Qt QTextDocument PDF rendering.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtGui import QGuiApplication, QTextDocument, QPdfWriter, QPageSize, QPageLayout
from PySide6.QtCore import QMarginsF

def build_api_html():
    html = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
    body {
        font-family: 'Segoe UI', Arial, sans-serif;
        color: #1E293B;
        margin: 10px 20px;
        line-height: 1.4;
        font-size: 10pt;
    }
    .header {
        border-bottom: 2.5px solid #10B981;
        padding-bottom: 8px;
        margin-bottom: 16px;
    }
    .brand-title {
        font-size: 22pt;
        font-weight: 800;
        color: #0F172A;
        margin: 0;
    }
    .brand-subtitle {
        font-size: 11pt;
        font-weight: 600;
        color: #059669;
        margin: 2px 0 0 0;
    }
    .doc-meta {
        font-size: 8.5pt;
        color: #64748B;
        margin-top: 4px;
    }
    h1 {
        font-size: 14pt;
        font-weight: 700;
        color: #0F172A;
        border-bottom: 1.5px solid #CBD5E1;
        padding-bottom: 4px;
        margin-top: 18px;
        margin-bottom: 8px;
    }
    h2 {
        font-size: 11.5pt;
        font-weight: 700;
        color: #0369A1;
        margin-top: 14px;
        margin-bottom: 6px;
    }
    p {
        margin: 4px 0;
    }
    .badge-get {
        background-color: #E0F2FE;
        color: #0369A1;
        font-weight: 800;
        font-size: 8.5pt;
        padding: 2px 6px;
    }
    .badge-post {
        background-color: #DCFCE7;
        color: #15803D;
        font-weight: 800;
        font-size: 8.5pt;
        padding: 2px 6px;
    }
    table.data-table {
        width: 100%;
        border-collapse: collapse;
        margin: 8px 0 14px 0;
        font-size: 9pt;
    }
    table.data-table th {
        background-color: #F1F5F9;
        color: #0F172A;
        text-align: left;
        padding: 6px 8px;
        border: 1px solid #CBD5E1;
        font-weight: 700;
    }
    table.data-table td {
        padding: 5px 8px;
        border: 1px solid #E2E8F0;
        vertical-align: top;
    }
    table.code-table {
        width: 100%;
        border-collapse: collapse;
        margin: 6px 0 12px 0;
        background-color: #F8FAFC;
        border: 1px solid #CBD5E1;
    }
    table.code-table td {
        padding: 8px 10px;
        font-family: 'Consolas', 'Courier New', monospace;
        font-size: 8.5pt;
        color: #0F172A;
        white-space: pre;
    }
    .info-box {
        background-color: #ECFDF5;
        border: 1px solid #A7F3D0;
        padding: 8px 12px;
        margin: 10px 0;
        font-size: 9pt;
        color: #065F46;
    }
    .tip-box {
        background-color: #F0F9FF;
        border: 1px solid #BAE6FD;
        padding: 8px 12px;
        margin: 8px 0;
        font-size: 9pt;
        color: #0369A1;
    }
</style>
</head>
<body>

<div class="header">
    <div class="brand-title">CtrlBooks API Reference Manual</div>
    <div class="brand-subtitle">Complete Accounting Synchronization, Data Extraction & AI Execution API</div>
    <div class="doc-meta">
        <b>Version:</b> 1.0.1 &nbsp;|&nbsp; 
        <b>Target Engine:</b> Tally Prime (HTTP XML Port 9000) &nbsp;|&nbsp; 
        <b>API Gateway:</b> Port 8000 &nbsp;|&nbsp; 
        <b>Date:</b> September 2026
    </div>
</div>

<div class="info-box">
    <b>Document Purpose:</b> This official technical manual provides complete API specifications for Backend Developers and AI Engineers integrating web applications, autonomous AI agents, voice assistants, and enterprise platforms with <b>CtrlBooks</b> and local <b>Tally Prime</b> instances.
</div>

<h1>1. Architectural Overview & AI Integration Patterns</h1>
<p>Because Tally Prime operates on client desktop machines (behind local network NAT and firewalls on port 9000), external Web applications and Cloud AI assistants cannot establish direct inbound HTTP connections. CtrlBooks resolves this through two production-proven integration patterns:</p>

<div class="tip-box">
    <b>Pattern A: Cloud 2-Way Command Queue (Recommended for Web AI & Chatbots)</b><br>
    &bull; The Web AI receives natural language (e.g. <i>"Create sales invoice for Acme Traders for 10 bags Cement"</i>).<br>
    &bull; AI converts intent into a standardized JSON command and queues it in the Cloud database.<br>
    &bull; The desktop background agent (<code>RemoteCommandWorker</code>) polls for commands every 15 seconds.<br>
    &bull; The built-in <code>ImporterService</code> posts the XML directly into Tally Prime.<br>
    &bull; Execution status, voucher number, and confirmation are returned to the Cloud automatically.
</div>

<div class="tip-box">
    <b>Pattern B: Local REST API Gateway (Port 8000)</b><br>
    For local microservices, desktop agents, or connections tunneled through localhost/VPN, the local API Gateway serves high-performance REST endpoints on <code>http://localhost:8000</code>.
</div>

<h1>2. System Health & Tally Connectivity APIs</h1>

<table class="data-table">
    <tr>
        <th width="15%">Method</th>
        <th width="35%">Endpoint</th>
        <th width="50%">Description</th>
    </tr>
    <tr>
        <td><span class="badge-get">GET</span></td>
        <td><code>/api/system/check</code></td>
        <td>Performs real-time diagnostics: OS compatibility, RAM capacity, Python version, and live connectivity to Tally Prime on port 9000.</td>
    </tr>
    <tr>
        <td><span class="badge-get">GET</span></td>
        <td><code>/api/system/settings/connection</code></td>
        <td>Returns configured Tally host (default: <code>127.0.0.1</code>), port (default: <code>9000</code>), and auto-sync intervals.</td>
    </tr>
    <tr>
        <td><span class="badge-post">POST</span></td>
        <td><code>/api/system/settings/connection</code></td>
        <td>Updates connection parameters (host IP, port, auto-connect toggle).</td>
    </tr>
    <tr>
        <td><span class="badge-get">GET</span></td>
        <td><code>/health</code></td>
        <td>Lightweight Gateway health check with sub-millisecond response latency.</td>
    </tr>
</table>

<p><b>Sample Response:</b> <code>GET /api/system/check</code></p>
<table class="code-table"><tr><td>{
  "status": "GOOD",
  "checks": {
    "os_compatible": true,
    "os_name": "win32",
    "ram_total_gb": 16.0,
    "ram_compatible": true,
    "tally_connected": true
  },
  "version": "1.0.1"
}</td></tr></table>

<h1>3. Data Extraction & Query APIs (Read Tally Data)</h1>
<p>These endpoints allow AI agents to look up existing company data, customer balances, product stock quantities, and past vouchers before executing transactions.</p>

<table class="data-table">
    <tr>
        <th width="15%">Method</th>
        <th width="35%">Endpoint</th>
        <th width="50%">Description</th>
    </tr>
    <tr>
        <td><span class="badge-get">GET</span></td>
        <td><code>/api/v1/website/companies</code></td>
        <td>Lists all synced companies with record count summaries (total ledgers, total vouchers, total stock items).</td>
    </tr>
    <tr>
        <td><span class="badge-get">GET</span></td>
        <td><code>/api/v1/website/dashboard/summary</code></td>
        <td>Aggregated metrics across all companies for dashboard widgets and high-level KPIs.</td>
    </tr>
    <tr>
        <td><span class="badge-get">GET</span></td>
        <td><code>/api/v1/website/entities/LEDGER</code></td>
        <td>Queries party and account ledgers (Customers, Vendors, Bank accounts). Supports <code>company_name</code> and <code>search</code> query parameters.</td>
    </tr>
    <tr>
        <td><span class="badge-get">GET</span></td>
        <td><code>/api/v1/website/entities/STOCK_ITEM</code></td>
        <td>Queries inventory products (Item Name, Closing Stock, Unit, Standard Rate, HSN Code).</td>
    </tr>
    <tr>
        <td><span class="badge-get">GET</span></td>
        <td><code>/api/v1/website/entities/VOUCHER</code></td>
        <td>Retrieves paginated past transactions (Sales, Purchase, Receipts, Payments) with date and party filters.</td>
    </tr>
    <tr>
        <td><span class="badge-get">GET</span></td>
        <td><code>/api/v1/website/records/{record_id}</code></td>
        <td>Fetches single raw JSON record details by extracted unique record ID.</td>
    </tr>
    <tr>
        <td><span class="badge-post">POST</span></td>
        <td><code>/api/v1/website/sync-and-store</code></td>
        <td>Triggers on-demand live extraction from Tally and persists records to the database.</td>
    </tr>
</table>

<p><b>Sample Query:</b> <code>GET /api/v1/website/entities/LEDGER?company_name=Tarun+Enterprise+(25-26)&search=Acme</code></p>
<table class="code-table"><tr><td>{
  "success": true,
  "data": {
    "total": 1,
    "page": 1,
    "page_size": 50,
    "items": [
      {
        "id": "rec_67890",
        "entity_type": "LEDGER",
        "name": "Acme Traders",
        "parent": "Sundry Debtors",
        "closing_balance": 24500.0,
        "gstin": "27AAPFU0939F1ZV",
        "mobile": "9876543210",
        "state": "Maharashtra"
      }
    ]
  }
}</td></tr></table>

<h1>4. AI Transaction Execution Payloads (Write to Tally)</h1>
<p>When an AI agent or user requests an action, the AI formats the extracted intention into standard JSON commands. The CtrlBooks engine converts them to Tally XML and executes them truthfully.</p>

<h2>A. Sales Invoice (Tax Invoice with Inventory & GST)</h2>
<p><b>Command Type:</b> <code>CREATE_VOUCHER</code> (or <code>Sales</code>)</p>
<table class="code-table"><tr><td>{
  "type": "CREATE_VOUCHER",
  "companyName": "Tarun Enterprise (25-26)",
  "payload": {
    "voucher_type": "Sales",
    "party_ledger": "Acme Traders",
    "date": "2026-09-22",
    "narration": "AI Generated Tax Invoice via Voice / Prompt",
    "amount": 11800.0,
    "items": [
      {
        "name": "Cement 50kg",
        "quantity": 10.0,
        "rate": 1000.0,
        "unit": "Bags",
        "amount": 10000.0
      }
    ],
    "ledger_entries": [
      {
        "ledger": "CGST @ 9%",
        "amount": 900.0
      },
      {
        "ledger": "SGST @ 9%",
        "amount": 900.0
      }
    ]
  }
}</td></tr></table>

<h2>B. Payment Receipt (Money Received from Customer)</h2>
<p><b>Command Type:</b> <code>CREATE_RECEIPT</code> (or <code>Receipt</code>)</p>
<table class="code-table"><tr><td>{
  "type": "CREATE_RECEIPT",
  "companyName": "Tarun Enterprise (25-26)",
  "payload": {
    "voucher_type": "Receipt",
    "party_ledger": "Acme Traders",
    "date": "2026-09-22",
    "amount": 5000.0,
    "narration": "Payment received via Bank Transfer (Ref #NEFT9823)",
    "ledger_entries": [
      {
        "ledger": "HDFC Bank",
        "amount": 5000.0
      }
    ]
  }
}</td></tr></table>

<h2>C. Vendor Payment (Money Paid to Supplier)</h2>
<p><b>Command Type:</b> <code>CREATE_PAYMENT</code> (or <code>Payment</code>)</p>
<table class="code-table"><tr><td>{
  "type": "CREATE_PAYMENT",
  "companyName": "Tarun Enterprise (25-26)",
  "payload": {
    "voucher_type": "Payment",
    "party_ledger": "Tata Steel Ltd",
    "date": "2026-09-22",
    "amount": 25000.0,
    "narration": "Vendor payment against invoice #TS-401",
    "ledger_entries": [
      {
        "ledger": "State Bank of India",
        "amount": 25000.0
      }
    ]
  }
}</td></tr></table>

<h2>D. Create New Party Master (Customer / Supplier)</h2>
<p><b>Command Type:</b> <code>CREATE_LEDGER</code></p>
<table class="code-table"><tr><td>{
  "type": "CREATE_LEDGER",
  "companyName": "Tarun Enterprise (25-26)",
  "payload": {
    "name": "Global Infotech Solutions",
    "parent": "Sundry Debtors",
    "state": "Karnataka",
    "gstin": "29AABCU9603R1ZM",
    "mobile": "9988776655",
    "email": "accounts@globalinfotech.com",
    "address": "100 Feet Ring Road, Bangalore",
    "opening_balance": 0.0
  }
}</td></tr></table>

<h2>E. Create New Stock Item (Product Master)</h2>
<p><b>Command Type:</b> <code>CREATE_STOCK_ITEM</code></p>
<table class="code-table"><tr><td>{
  "type": "CREATE_STOCK_ITEM",
  "companyName": "Tarun Enterprise (25-26)",
  "payload": {
    "name": "Steel Reinforcement Rod 12mm",
    "unit": "Kgs",
    "hsn_code": "72142090",
    "company_name": "Tarun Enterprise (25-26)"
  }
}</td></tr></table>

<h1>5. Supported Transaction Voucher Types Matrix</h1>

<table class="data-table">
    <tr>
        <th width="20%">Voucher Type</th>
        <th width="35%">Command Type Keyword</th>
        <th width="45%">Accounting Function</th>
    </tr>
    <tr>
        <td><b>Sales</b></td>
        <td><code>CREATE_VOUCHER</code> / <code>Sales</code></td>
        <td>Customer invoicing with stock allocation & GST tax ledgers.</td>
    </tr>
    <tr>
        <td><b>Purchase</b></td>
        <td><code>CREATE_PURCHASE</code> / <code>Purchase</code></td>
        <td>Supplier bill entry with inventory addition & input credit.</td>
    </tr>
    <tr>
        <td><b>Receipt</b></td>
        <td><code>CREATE_RECEIPT</code> / <code>PAYMENT_RECEIVED</code></td>
        <td>Incoming cash, UPI, cheque, or bank receipts.</td>
    </tr>
    <tr>
        <td><b>Payment</b></td>
        <td><code>CREATE_PAYMENT</code> / <code>PAYMENT_MADE</code></td>
        <td>Outgoing supplier, expense, or payroll payments.</td>
    </tr>
    <tr>
        <td><b>Journal</b></td>
        <td><code>CREATE_JOURNAL</code> / <code>Journal</code></td>
        <td>General adjustments, depreciation, and year-end entries.</td>
    </tr>
    <tr>
        <td><b>Contra</b></td>
        <td><code>CREATE_CONTRA</code> / <code>Contra</code></td>
        <td>Cash to bank deposits, cash withdrawals, or inter-bank transfers.</td>
    </tr>
    <tr>
        <td><b>Credit Note</b></td>
        <td><code>CREATE_CREDIT_NOTE</code></td>
        <td>Sales returns or rate difference allowances to customers.</td>
    </tr>
    <tr>
        <td><b>Debit Note</b></td>
        <td><code>CREATE_DEBIT_NOTE</code></td>
        <td>Purchase returns or discounts received from vendors.</td>
    </tr>
    <tr>
        <td><b>Sales Order</b></td>
        <td><code>CREATE_SALES_ORDER</code></td>
        <td>Pending customer purchase orders prior to invoice generation.</td>
    </tr>
    <tr>
        <td><b>Purchase Order</b></td>
        <td><code>CREATE_PURCHASE_ORDER</code></td>
        <td>Outbound procurement orders sent to vendors.</td>
    </tr>
</table>

<h1>6. Enterprise Safety & Reliability Safeguards</h1>
<p>When developing an AI automation platform, safety and transactional integrity are paramount. CtrlBooks includes the following safeguards out of the box:</p>

<table class="data-table">
    <tr>
        <th width="25%">Protection Mechanism</th>
        <th width="75%">How It Protects The Accounting Ledger</th>
    </tr>
    <tr>
        <td><b>Idempotency Guard</b></td>
        <td>Each entry is tracked by a composite hash (<code>company:voucher_type:voucher_number</code>). If a network timeout, web retry, or double prompt occurs, the engine returns the existing voucher confirmation without creating a duplicate in Tally.</td>
    </tr>
    <tr>
        <td><b>Auto-Creation of Masters</b></td>
        <td>If an AI entry references a new customer that does not yet exist in Tally, <code>ImporterService</code> automatically provisions the party ledger under <i>Sundry Debtors</i> with GSTIN details before executing the voucher. The voucher never fails due to missing party errors.</td>
    </tr>
    <tr>
        <td><b>Offline Resilient Queue</b></td>
        <td>If the client turns off their computer or closes Tally Prime, vouchers are safely persisted to the local <code>sync_queue</code> table. When Tally is reopened, the background agent automatically drains and posts all pending entries.</td>
    </tr>
    <tr>
        <td><b>Penny Balancing</b></td>
        <td>Automatically compensates for floating-point rounding discrepancies between item tax subtotals and invoice totals to ensure zero ledger rejections.</td>
    </tr>
</table>

<hr style="border: none; border-top: 1px solid #CBD5E1; margin: 24px 0 10px 0;">
<div style="font-size: 8.5pt; color: #64748B; text-align: center;">
    CtrlBooks™ &copy; 2026. Confidential & Proprietary. Created for internal AI Integration and Technical Development.
</div>

</body>
</html>
"""
    return html

def main():
    print("=========================================================")
    print(" Generating Official API Documentation PDF: CtrlBooks")
    print("=========================================================")

    app = QGuiApplication.instance()
    if not app:
        app = QGuiApplication(sys.argv)

    html_content = build_api_html()

    doc = QTextDocument()
    doc.setHtml(html_content)

    out_pdf = ROOT / "CtrlBooks_API_Documentation.pdf"
    writer = QPdfWriter(str(out_pdf))
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setResolution(300)

    layout = QPageLayout()
    layout.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    layout.setMargins(QMarginsF(14, 16, 14, 16))
    writer.setPageLayout(layout)

    doc.print_(writer)

    if out_pdf.exists():
        size_kb = out_pdf.stat().st_size / 1024
        print(f"\n[OK] PDF Generated successfully!")
        print(f"File Path: {out_pdf}")
        print(f"File Size: {size_kb:.1f} KB")
    else:
        print("[!] Error generating PDF.")
        sys.exit(1)

if __name__ == "__main__":
    main()

