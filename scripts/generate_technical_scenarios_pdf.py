"""
CtrlBooks - Technical Deep-Dive Scenarios PDF Generator
Generates an in-depth engineering specification PDF covering concurrency, double-entry math, pre-flight auto-healing, idempotency, and DPAPI security.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESKTOP = Path("C:/Users/Sales/Desktop")
sys.path.insert(0, str(ROOT))

from PySide6.QtGui import QGuiApplication, QTextDocument, QPdfWriter, QPageSize, QPageLayout
from PySide6.QtCore import QMarginsF

def build_technical_html():
    return """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>CtrlBooks - Deep Technical Architecture & Scenarios</title>
<style>
    body {
        font-family: 'Segoe UI', Arial, Helvetica, sans-serif;
        color: #1E293B;
        margin: 15px 25px;
        line-height: 1.5;
        font-size: 9pt;
    }
    .header {
        border-bottom: 3px solid #10B981;
        padding-bottom: 12px;
        margin-bottom: 18px;
    }
    .main-title {
        font-size: 21pt;
        font-weight: 800;
        color: #0F172A;
        margin: 0;
    }
    .sub-title {
        font-size: 11pt;
        font-weight: 700;
        color: #059669;
        margin: 4px 0 6px 0;
    }
    .badge-pill {
        display: inline-block;
        padding: 3px 9px;
        background-color: #ECFDF5;
        color: #065F46;
        border: 1px solid #A7F3D0;
        border-radius: 12px;
        font-weight: 700;
        font-size: 8pt;
    }
    h2 {
        font-size: 12.5pt;
        font-weight: 800;
        color: #0F172A;
        border-bottom: 1.5px solid #E2E8F0;
        padding-bottom: 5px;
        margin-top: 20px;
        margin-bottom: 10px;
    }
    h3 {
        font-size: 10pt;
        font-weight: 700;
        color: #1E293B;
        margin-top: 12px;
        margin-bottom: 5px;
    }
    p {
        margin: 5px 0;
        color: #334155;
    }
    .code-box {
        background-color: #F8FAFC;
        border: 1px solid #CBD5E1;
        border-radius: 6px;
        padding: 8px 12px;
        font-family: 'Consolas', 'Courier New', monospace;
        font-size: 8pt;
        color: #0F172A;
        line-height: 1.35;
        margin: 8px 0;
    }
    .card-scenario {
        background-color: #FFFFFF;
        border: 1.5px solid #E2E8F0;
        border-radius: 8px;
        padding: 10px 14px;
        margin: 10px 0;
    }
    .callout-green {
        background-color: #F0FDF4;
        border-left: 4px solid #10B981;
        padding: 8px 12px;
        margin: 8px 0;
        border-radius: 0 6px 6px 0;
    }
    .callout-blue {
        background-color: #F0F9FF;
        border-left: 4px solid #0284C7;
        padding: 8px 12px;
        margin: 8px 0;
        border-radius: 0 6px 6px 0;
    }
    .callout-amber {
        background-color: #FFFBEB;
        border-left: 4px solid #F59E0B;
        padding: 8px 12px;
        margin: 8px 0;
        border-radius: 0 6px 6px 0;
    }
    table {
        width: 100%;
        border-collapse: collapse;
        margin: 8px 0 14px 0;
        font-size: 8.5pt;
    }
    th {
        background-color: #0F172A;
        color: #FFFFFF;
        text-align: left;
        padding: 7px 9px;
        font-weight: 700;
        border: 1px solid #0F172A;
    }
    td {
        padding: 6px 9px;
        border: 1px solid #E2E8F0;
        color: #334155;
        vertical-align: top;
    }
    tr:nth-child(even) td {
        background-color: #F8FAFC;
    }
    .footer {
        margin-top: 30px;
        border-top: 1px solid #E2E8F0;
        padding-top: 10px;
        font-size: 8pt;
        color: #94A3B8;
        text-align: center;
    }
</style>
</head>
<body>

<div class="header">
    <div class="main-title">CtrlBooks - Technical Deep-Dive & Engineering Scenarios</div>
    <div class="sub-title">In-Depth Analysis of Concurrency, Double-Entry Math, Auto-Healing, and Security Protocols</div>
    <div class="meta-bar">
        <span><b>Architecture Build:</b> v1.0.19</span> &nbsp;|&nbsp;
        <span><b>Security Level:</b> Enterprise DPAPI Bound</span> &nbsp;|&nbsp;
        <span class="badge-pill">Production Engineering Whitepaper</span>
    </div>
</div>

<h2>1. Technical Scenario 1: Multi-Threading & Asyncio Concurrency Model</h2>
<p>
    A critical engineering challenge in desktop ERP connectors is ensuring that heavy I/O operations (fetching 20,000 vouchers, parsing complex XML, polling cloud endpoints) 
    <b>never freeze the Qt GUI event loop</b>.
</p>

<div class="card-scenario">
    <b>Thread Hierarchy & Event Isolation:</b>
    <ul>
        <li><b>Main Thread (QApplication GUI Loop):</b> Strictly dedicated to 60fps rendering, animations, user input, and system tray interactions. No network calls or file I/O ever run on this thread.</li>
        <li><b>SyncWorker (Dedicated QThread):</b> Runs long-running Tally extraction loops using raw sockets. Chunks payloads into batches of 50 and streams them to the cloud.</li>
        <li><b>CommandWorker (Dedicated QThread with Isolated Asyncio Loop):</b> Runs a cooperative background daemon polling for cloud actions. It isolates asynchronous Python tasks using:</li>
    </ul>
    <div class="code-box">
loop = asyncio.new_event_loop()<br>
asyncio.set_event_loop(loop)<br>
try:<br>
&nbsp;&nbsp;&nbsp;&nbsp;res = loop.run_until_complete(worker.importer_service.import_voucher(norm_payload))<br>
finally:<br>
&nbsp;&nbsp;&nbsp;&nbsp;loop.close()
    </div>
    <p>
        <b>Thread-Safe Communication:</b> Inter-thread communication is strictly implemented via <b>Qt Signals &amp; Slots</b> (<code>emit()</code>), 
        eliminating race conditions and Python GIL contention.
    </p>
</div>

<h2>2. Technical Scenario 2: Tally Double-Entry XML Math & Balance Enforcement</h2>
<p>
    Tally Prime enforces strict double-entry mathematical balance. The algebraic sum of debits and credits in an XML envelope must equal exactly zero:
</p>
<div class="callout-green">
    <b>Fundamental Accounting Invariant:</b> &nbsp;&nbsp; <b>&Sigma; Debit (+) + &Sigma; Credit (&minus;) = 0.00</b><br>
    If this condition fails by even 0.01 paise, Tally Prime aborts the entire transaction with <code>&lt;LINEERROR&gt;Totals do not match&lt;/LINEERROR&gt;</code>.
</div>

<p>CtrlBooks enforces this through automated double-entry normalization inside <code>voucher_builder.py</code>:</p>
<table>
    <tr>
        <th style="width: 25%;">Entry Type</th>
        <th style="width: 30%;">XML Representation</th>
        <th style="width: 45%;">Mathematical Sign & Allocation Logic</th>
    </tr>
    <tr>
        <td><b>Debtor / Party (Debit)</b></td>
        <td><code>&lt;ISDEEMEDPOSITIVE&gt;Yes&lt;/ISDEEMEDPOSITIVE&gt;<br>&lt;AMOUNT&gt;-59000.00&lt;/AMOUNT&gt;</code></td>
        <td>In Tally XML, deemed positive entries carry a negative numerical sign to indicate debit asset increase.</td>
    </tr>
    <tr>
        <td><b>Sales Account (Credit)</b></td>
        <td><code>&lt;ISDEEMEDPOSITIVE&gt;No&lt;/ISDEEMEDPOSITIVE&gt;<br>&lt;AMOUNT&gt;50000.00&lt;/AMOUNT&gt;</code></td>
        <td>Deemed negative entry with positive numerical value representing revenue recognition.</td>
    </tr>
    <tr>
        <td><b>Tax Ledgers (CGST / SGST)</b></td>
        <td><code>&lt;ISDEEMEDPOSITIVE&gt;No&lt;/ISDEEMEDPOSITIVE&gt;<br>&lt;AMOUNT&gt;4500.00&lt;/AMOUNT&gt;</code></td>
        <td>Calculated from item HSN and GST rate percentages; allocated to statutory tax sub-ledgers.</td>
    </tr>
    <tr>
        <td><b>Fractional Round-Off</b></td>
        <td><code>&lt;LEDGERNAME&gt;Round Off&lt;/LEDGERNAME&gt;</code></td>
        <td>Auto-injected if mathematical calculation results in fractional paise (e.g., ₹0.02 adjustment).</td>
    </tr>
</table>

<h2>3. Technical Scenario 3: Pre-Flight Master Inspection &amp; Auto-Healing Engine</h2>
<p>
    When invoices are created on <b>ctrlbooks.com</b>, they frequently reference new parties, stock items, or units of measurement that do not yet exist in Tally. 
    Ordinary connectors crash with <i>"Ledger Does Not Exist"</i>. CtrlBooks executes a <b>Pre-Flight Auto-Healing Engine</b> (<code>tally_importer.py</code>):
</p>

<div class="callout-blue">
    <b>The Auto-Healing Sequence:</b><br>
    1. <b>TDL Query Check:</b> Sends a lightweight collection filter to Tally: <code>SELECT $Name FROM Ledger WHERE $Name = 'PartyName'</code>.<br>
    2. <b>Missing Master Detection:</b> If response is empty, the pre-flight engine halts the voucher insertion.<br>
    3. <b>Parent Classification:</b> Customer ➔ <code>Sundry Debtors</code>, Supplier ➔ <code>Sundry Creditors</code>, Bank ➔ <code>Bank Accounts</code>.<br>
    4. <b>XML Master Construction:</b> Dispatches <code>&lt;LEDGER ACTION="Create"&gt;</code> containing GSTIN, State Name, Pincode, Address, and Country.<br>
    5. <b>Transactional Insertion:</b> Once Tally confirms <code>&lt;CREATED&gt;1&lt;/CREATED&gt;</code>, the voucher XML is dispatched. <b>Result: Zero failure rate on new customer invoices.</b>
</div>

<h2>4. Technical Scenario 4: Idempotency &amp; Duplicate Prevention (State Machine)</h2>
<p>
    In real-world networks, HTTP requests can timeout after Tally has already written the transaction. 
    If the client naively retries, Tally would record duplicate invoices. CtrlBooks enforces <b>strict idempotency</b>:
</p>
<div class="card-scenario">
    <ul>
        <li><b>Unique Command ID Binding:</b> Every web invoice carries an immutable MongoDB ObjectId (e.g., <code>cmd_6a990531...</code>).</li>
        <li><b>Reference Tag Locking:</b> The command ID is permanently injected into Tally's <code>&lt;BASICORDERREF&gt;</code> and <code>&lt;REFERENCE&gt;</code> tags.</li>
        <li><b>Pre-Execution Audit:</b> Before executing any creation XML, the engine queries Tally for an existing voucher with that Reference ID.</li>
        <li><b>Recovery Handoff:</b> If an existing record is discovered, the engine retrieves Tally's permanent internal <code>GUID</code>, skips duplicate creation, and returns <code>status: DONE</code>.</li>
    </ul>
</div>

<h2>5. Technical Scenario 5: Offline Resilience &amp; The SQLite Queue State Machine</h2>
<p>
    If an accountant shuts down Tally Prime or closes the target company while a web transaction is initiated:
</p>
<div class="callout-amber">
    <b>Local Persistence Queue (voucher_queue_repository.py):</b><br>
    1. <b>Socket Failure Detection:</b> Connection probe detects port 9000 is closed or company name is unmounted.<br>
    2. <b>Disk-Persisted SQLite Storage:</b> The command payload is encrypted and written to <code>sync_queue</code> in <code>data/ctrlbooks.db</code>.<br>
    3. <b>Cloud Notification:</b> The cloud gateway is notified with <code>status: WAITING_FOR_TALLY</code>.<br>
    4. <b>Heartbeat Daemon:</b> The background probe pings Tally every 2000ms.<br>
    5. <b>FIFO Auto-Drain:</b> The instant Tally and the target company open, queued transactions are processed sequentially (First-In, First-Out), ensuring proper voucher serial numbers.
</div>

<h2>6. Technical Scenario 6: Cryptographic Credential Vault (Windows DPAPI)</h2>
<table>
    <tr>
        <th style="width: 25%;">Security Layer</th>
        <th style="width: 75%;">Technical Implementation (win_credential_store.py)</th>
    </tr>
    <tr>
        <td><b>DPAPI Vault</b></td>
        <td>Calls native Windows <code>CryptProtectData</code> in <code>Crypt32.dll</code>. Cryptographic keys are bound to the logged-in Windows user's SID and local TPM hardware.</td>
    </tr>
    <tr>
        <td><b>Zero Plaintext</b></td>
        <td>Access tokens, refresh tokens, and device UUIDs are never stored in plain text JSON. Memory structures are wiped upon application shutdown.</td>
    </tr>
    <tr>
        <td><b>Anti-Clone Protection</b></td>
        <td>Hardware UUID fingerprint is transmitted in API headers. Copying the SQLite database or executable to another computer immediately invalidates the cryptographic trust.</td>
    </tr>
</table>

<div class="footer">
    CtrlBooks Engineering Whitepaper &copy; 2026. Generated automatically via CtrlBooks Core Architecture Engine.
</div>

</body>
</html>
"""

def main():
    print("=================================================================")
    print(" Generating Technical Deep-Dive Scenarios PDF & HTML")
    print("=================================================================")

    html_content = build_technical_html()

    out_html = DESKTOP / "CtrlBooks_Technical_Deep_Dive_Scenarios.html"
    with open(out_html, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"[OK] HTML created at: {out_html}")

    app = QGuiApplication.instance()
    if not app:
        app = QGuiApplication(sys.argv)

    doc = QTextDocument()
    doc.setHtml(html_content)

    out_pdf = DESKTOP / "CtrlBooks_Technical_Deep_Dive_Scenarios.pdf"
    writer = QPdfWriter(str(out_pdf))
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setResolution(300)

    layout = QPageLayout()
    layout.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    layout.setMargins(QMarginsF(12, 14, 12, 14))
    writer.setPageLayout(layout)

    doc.print_(writer)

    if out_pdf.exists():
        size_kb = out_pdf.stat().st_size / 1024
        print(f"[OK] PDF created successfully on Desktop!")
        print(f"Path: {out_pdf}")
        print(f"Size: {size_kb:.1f} KB")
    else:
        print("[!] Error generating PDF.")
        sys.exit(1)

if __name__ == "__main__":
    main()

