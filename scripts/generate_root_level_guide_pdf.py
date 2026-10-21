"""
CtrlBooks - Root Level System Design & Function Workflow PDF Generator
Generates a beginner-friendly, visual, step-by-step guide explaining every function and workflow from scratch.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESKTOP = Path("C:/Users/Sales/Desktop")
sys.path.insert(0, str(ROOT))

from PySide6.QtGui import QGuiApplication, QTextDocument, QPdfWriter, QPageSize, QPageLayout
from PySide6.QtCore import QMarginsF

def build_guide_html():
    return """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>CtrlBooks - Complete Root-Level System Workflow Guide</title>
<style>
    body {
        font-family: 'Segoe UI', Arial, Helvetica, sans-serif;
        color: #1E293B;
        margin: 15px 25px;
        line-height: 1.5;
        font-size: 9.5pt;
    }
    .header {
        border-bottom: 3px solid #10B981;
        padding-bottom: 12px;
        margin-bottom: 18px;
    }
    .main-title {
        font-size: 22pt;
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
        font-size: 13pt;
        font-weight: 800;
        color: #0F172A;
        border-bottom: 1.5px solid #E2E8F0;
        padding-bottom: 5px;
        margin-top: 22px;
        margin-bottom: 10px;
    }
    h3 {
        font-size: 10.5pt;
        font-weight: 700;
        color: #1E293B;
        margin-top: 14px;
        margin-bottom: 6px;
    }
    p {
        margin: 6px 0;
        color: #334155;
    }
    .box-card {
        background-color: #F8FAFC;
        border: 1.5px solid #CBD5E1;
        border-radius: 8px;
        padding: 10px 14px;
        margin: 10px 0;
    }
    .box-green {
        background-color: #F0FDF4;
        border: 1.5px solid #A7F3D0;
        border-radius: 8px;
        padding: 10px 14px;
        margin: 10px 0;
    }
    .box-blue {
        background-color: #F0F9FF;
        border: 1.5px solid #BAE6FD;
        border-radius: 8px;
        padding: 10px 14px;
        margin: 10px 0;
    }
    .box-amber {
        background-color: #FFFBEB;
        border: 1.5px solid #FDE68A;
        border-radius: 8px;
        padding: 10px 14px;
        margin: 10px 0;
    }
    table {
        width: 100%;
        border-collapse: collapse;
        margin: 10px 0 16px 0;
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
    .diagram-table {
        width: 100%;
        margin: 12px 0;
        border: none;
    }
    .diagram-table td {
        border: none;
        padding: 4px;
        vertical-align: middle;
        text-align: center;
    }
    .step-box {
        background-color: #FFFFFF;
        border: 2px solid #059669;
        border-radius: 6px;
        padding: 8px 6px;
        font-weight: 700;
        font-size: 8pt;
        color: #0F172A;
    }
    .step-arrow {
        font-size: 16pt;
        font-weight: 900;
        color: #10B981;
    }
    .fn-tag {
        font-family: 'Consolas', monospace;
        font-weight: 700;
        color: #047857;
        background-color: #ECFDF5;
        padding: 1px 5px;
        border-radius: 3px;
        border: 1px solid #A7F3D0;
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
    <div class="main-title">CtrlBooks - Root-Level System Design & Workflow Guide</div>
    <div class="sub-title">Aasan Bhasha me: Kon Sa Function Kaise Kaam Karta Hai (Ground Zero se Top tak)</div>
    <div class="meta-bar">
        <span><b>Target Build:</b> v1.0.19</span> &nbsp;|&nbsp;
        <span class="badge-pill">Zero Prior Design Knowledge Required</span>
    </div>
</div>

<h2>1. Asli Kahani: CtrlBooks Karta Kya Hai? (Simple Bhasha Me)</h2>
<p>
    Tally Prime ek <b>offline desktop software</b> hai jo user ke computer par chalta hai. 
    Dusri taraf, <b>ctrlbooks.com</b> ek <b>cloud website</b> hai jise aap mobile ya kisi bhi computer se open kar sakte hain.
</p>
<p>
    <b>CtrlBooks Connector ka ek hi sabse bada kaam hai:</b><br>
    Website aur Tally Prime ke beech me ek <b>"Super-Fast Delivery Boy (Bridge)"</b> ban kar khada rehna. 
    Jab website par invoice bane, to Tally me daal dena. Aur jab Tally me koi entry kare, to use website par dikha dena!
</p>

<h2>2. Complete Visual Architecture (4 Bade Pillars)</h2>

<table class="diagram-table">
    <tr>
        <td style="width: 22%;">
            <div class="step-box" style="border-color: #3B82F6;">
                🌐 <b>Web Portal</b><br>
                ctrlbooks.com<br>
                <span style="font-size: 7.5pt; color: #64748B;">User Invoice Banata Hai</span>
            </div>
        </td>
        <td style="width: 4%;" class="step-arrow">➔</td>
        <td style="width: 22%;">
            <div class="step-box" style="border-color: #8B5CF6;">
                ☁️ <b>Cloud API Gateway</b><br>
                connector.cloudata.in<br>
                <span style="font-size: 7.5pt; color: #64748B;">Commands & Data Store</span>
            </div>
        </td>
        <td style="width: 4%;" class="step-arrow">➔</td>
        <td style="width: 24%;">
            <div class="step-box" style="border-color: #10B981;">
                💻 <b>CtrlBooks Desktop App</b><br>
                (command_worker & sync_worker)<br>
                <span style="font-size: 7.5pt; color: #64748B;">XML Converter Engine</span>
            </div>
        </td>
        <td style="width: 4%;" class="step-arrow">➔</td>
        <td style="width: 20%;">
            <div class="step-box" style="border-color: #F59E0B;">
                📊 <b>Tally Prime</b><br>
                Port 9000 / 9047<br>
                <span style="font-size: 7.5pt; color: #64748B;">Final Accounts & Ledger</span>
            </div>
        </td>
    </tr>
</table>

<h2>3. Workflow 1: User ne Website par Invoice banaya ➔ Tally me kaise pahuncha?</h2>

<p>Maan lijiye user ne website par <b>"Rahul Enterprises"</b> ko ₹50,000 ka ek Sales Invoice banaya. Ab dekhiye andar kya hota hai:</p>

<table>
    <tr>
        <th style="width: 6%;">Step</th>
        <th style="width: 22%;">Kon Sa Function?</th>
        <th style="width: 24%;">File Path</th>
        <th style="width: 48%;">Yeh Function Root Level Par Kya Karta Hai?</th>
    </tr>
    <tr>
        <td><b>1</b></td>
        <td><span class="fn-tag">POST /commands</span></td>
        <td>Cloud API Gateway</td>
        <td>User ne jaise hi website par "Save" dabaya, cloud server ne is invoice ko ek <b>Command (Type: CREATE_VOUCHER, Status: PENDING)</b> bana kar database me daal diya.</td>
    </tr>
    <tr>
        <td><b>2</b></td>
        <td><span class="fn-tag">get_pending_commands()</span></td>
        <td><code>command_worker.py</code></td>
        <td>Desktop App background me har 2 second me cloud se puchhta hai: <i>"Bhai mere liye koi naya kaam aaya hai kya?"</i> Cloud bolta hai: <i>"Haan, yeh lo Rahul Enterprises ka invoice!"</i></td>
    </tr>
    <tr>
        <td><b>3</b></td>
        <td><span class="fn-tag">process_voucher_command()</span></td>
        <td><code>voucher_command_handler.py</code></td>
        <td>Yeh function web se aayi command ko kholta hai aur fields ko check karta hai: Party name kya hai, GST kitna hai, Vehicle No kya hai, Pincode kya hai.</td>
    </tr>
    <tr>
        <td><b>4</b></td>
        <td><span class="fn-tag">import_voucher()</span></td>
        <td><code>importer_service.py</code></td>
        <td>Yeh sabse pehle Tally ko ping karta hai: <i>"Kya Tally chal raha hai? Aur kya sahi Company khuli hai?"</i> Agar Tally band hai, to yeh entry ko cancel nahi karta, balki <b>Offline Queue</b> me daal deta hai!</td>
    </tr>
    <tr>
        <td><b>5</b></td>
        <td><span class="fn-tag">ensure_ledgers_exist()</span></td>
        <td><code>tally_importer.py</code></td>
        <td><b>(Pre-Flight Check):</b> Yeh Tally se puchhta hai: <i>"Kya Tally me Rahul Enterprises naam ka ledger pehle se hai?"</i> Agar nahi hai, to yeh turant pehle Rahul Enterprises ka Ledger bana deta hai taaki invoice fail na ho!</td>
    </tr>
    <tr>
        <td><b>6</b></td>
        <td><span class="fn-tag">build_voucher_import_xml()</span></td>
        <td><code>voucher_builder.py</code></td>
        <td>Yeh pure invoice ko <b>Tally ki zubaan (XML format)</b> me convert karta hai: Debit party, Credit sales, CGST, SGST, Dispatch details, Consignee details sab tags me pack karta hai.</td>
    </tr>
    <tr>
        <td><b>7</b></td>
        <td><span class="fn-tag">send_xml_request()</span></td>
        <td><code>tally_client.py</code></td>
        <td>Yeh Tally ke local port (9000/9047) par HTTP request bhejta hai. Tally XML ko padh kar voucher ko Tally ke andar save kar leta hai!</td>
    </tr>
    <tr>
        <td><b>8</b></td>
        <td><span class="fn-tag">parse_tally_import_response()</span></td>
        <td><code>response_parser.py</code></td>
        <td>Tally se aate response ko check karta hai: Kya Tally ne <code>&lt;CREATED&gt;1&lt;/CREATED&gt;</code> bola? Agar haan, to Tally ka Voucher No aur GUID nikal leta hai.</td>
    </tr>
    <tr>
        <td><b>9</b></td>
        <td><span class="fn-tag">send_command_result()</span></td>
        <td><code>cloud_command_client.py</code></td>
        <td>Yeh wapas cloud ko report karta hai: <i>"Status: DONE! Tally Voucher #18 ban gaya!"</i> Website par user ko turant <b>Green Tick (DONE)</b> dikh jata hai.</td>
    </tr>
</table>

<h2>4. Workflow 2: Tally me Accountant ne entry ki ➔ Website par kaise aayi?</h2>

<p>Jab koi accountant direct Tally Prime me entry karta hai, to Connector use website par kaise bhejta hai:</p>

<div class="box-green">
    <p><b>1. SyncWorker Trigger:</b> <code>apps/desktop_app/ui/threads/sync_worker.py</code> background me har thodi der me wake up hota hai.</p>
    <p><b>2. Data Extraction:</b> <code>shared/extraction/tally_extractor.py</code> ka function <span class="fn-tag">extract_vouchers()</span> Tally se TDL query karke naye vouchers nikalta hai.</p>
    <p><b>3. XML to JSON:</b> <code>response_parser.py</code> Tally ke raw XML ko neat JSON me convert karta hai.</p>
    <p><b>4. Batch Upload:</b> <code>shared/cloud/cloud_sync_client.py</code> ka function <span class="fn-tag">push_batch_sync()</span> 50-50 vouchers ke batch bana kar cloud par bhej deta hai.</p>
    <p><b>5. Website Par Live:</b> Cloud server use MongoDB me update kar deta hai aur website ke dashboard par naya balance/invoice show ho jata hai.</p>
</div>

<h2>5. Agar Tally Band Ho Ya Company Closed Ho To Kya Hota Hai? (Offline Resilience)</h2>

<div class="box-amber">
    <p><b>Aapka Software Data Kabhi Lose Nahi Karta:</b></p>
    <p>Maan lijiye website se koi invoice create hua, lekin accountant ne Tally Prime band kar rakha tha. Aise me:</p>
    <ul>
        <li><code>importer_service.py</code> dekhta hai ki Tally band hai.</li>
        <li>Yeh error throw nahi karta! Balki <code>voucher_queue_repository.py</code> ka function <span class="fn-tag">enqueue_pending_voucher()</span> use local computer ke SQLite database (<code>data/ctrlbooks.db</code>) me save kar leta hai.</li>
        <li>Cloud ko bolta hai: <code>WAITING_FOR_TALLY</code>.</li>
        <li>Background me Connector har 10 second me Tally ko probe karta rehta hai.</li>
        <li><b>Jaise hi accountant Tally open karega:</b> Connector foran detect karega aur saare queued invoices Tally ke andar bina kisi user effort ke automatic import kar dega!</li>
    </ul>
</div>

<h2>6. Login Aur Security Kaise Kaam Karti Hai?</h2>

<div class="box-blue">
    <p><b>1. Passwordless OTP:</b> <code>cloud_auth_service.py</code> ka function <span class="fn-tag">send_otp(email)</span> cloud ko bolta hai. Cloud Resend API se user ke email par 6-digit OTP bhejta hai.</p>
    <p><b>2. Token & Security:</b> OTP verify hote hi cloud ek secure JWT token deta hai.</p>
    <p><b>3. Windows DPAPI Encryption:</b> <code>win_credential_store.py</code> user ke token ko Windows ke <b>DPAPI encryption</b> se lock karke Windows Credential Manager me save karta hai. Agar koi computer se file chori bhi kar le, to bhi token read nahi kar sakta!</p>
</div>

<h2>7. Software Auto-Update Kaise Hota Hai?</h2>

<p>Jab hum server par naya version (jaise <code>v1.0.19</code>) dalte hain to user ke computer par kya hota hai:</p>
<div class="box-card">
    <p>1. <code>shared/updater.py</code> ka function <span class="fn-tag">check_for_updates()</span> server se version puchhta hai.</p>
    <p>2. Formula lagta hai: <code>latest_version > current_version</code>. Agar naya hai to UI par "New Version Available" popup aata hai.</p>
    <p>3. <span class="fn-tag">download_update()</span> naye installer ko stream download karta hai.</p>
    <p>4. <span class="fn-tag">compute_file_sha256()</span> download hone ke baad check karta hai ki file corrupt to nahi hui.</p>
    <p>5. <span class="fn-tag">install_and_restart()</span> purane app ko band karke background me naya setup install kar deta hai.</p>
</div>

<div class="footer">
    CtrlBooks System Design Architecture Guide &copy; 2026. Specially generated for CtrlBooks Core Team.
</div>

</body>
</html>
"""

def main():
    print("=================================================================")
    print(" Generating Root-Level Workflow Guide (PDF & HTML)")
    print("=================================================================")

    html_content = build_guide_html()

    out_html = DESKTOP / "CtrlBooks_Root_Level_System_Guide.html"
    with open(out_html, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"[OK] HTML created at: {out_html}")

    app = QGuiApplication.instance()
    if not app:
        app = QGuiApplication(sys.argv)

    doc = QTextDocument()
    doc.setHtml(html_content)

    out_pdf = DESKTOP / "CtrlBooks_Root_Level_System_Guide.pdf"
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

