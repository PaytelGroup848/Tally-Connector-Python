import os
import sys
import re
from datetime import datetime

# 1. READ MONGODB URL DIRECTLY FROM .env (NO pydantic / dotenv REQUIRED)
def get_db_url():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_file = os.path.join(base_dir, ".env")
    if os.path.exists(env_file):
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("CTRLBOOKS_DB_URL="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
                elif line.startswith("MONGODB_URI="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    return os.environ.get("CTRLBOOKS_DB_URL") or os.environ.get("MONGODB_URI") or "mongodb://datacloude8_db_user:6ru82Z0uNhMhoz5u@ac-twlm6pz-shard-00-00.xcqrnjz.mongodb.net:27017,ac-twlm6pz-shard-00-01.xcqrnjz.mongodb.net:27017,ac-twlm6pz-shard-00-02.xcqrnjz.mongodb.net:27017/?ssl=true&replicaSet=atlas-h0mo8s-shard-0&authSource=admin&appName=CloudedataConnect"

try:
    from pymongo import MongoClient
except ImportError:
    print("\n[!] ERROR: 'pymongo' library is not installed.")
    print("    Please run:")
    print("    pip3 install pymongo --break-system-packages\n")
    sys.exit(1)

def run_health_check():
    db_url = get_db_url()
    print("\n" + "=" * 70)
    print("      CTRLBOOKS SERVER & CUSTOMER HEALTH DIAGNOSTIC DASHBOARD")
    print("=" * 70)
    print("Connecting to MongoDB Atlas...")

    try:
        client = MongoClient(db_url, serverSelectionTimeoutMS=10000)
        db = client["test"]
    except Exception as exc:
        print(f"[!] Database connection failed: {exc}")
        sys.exit(1)

    # 1. TOTAL REGISTERED USERS & ORGANIZATIONS
    total_users = db.users.count_documents({})
    total_orgs = db.organizations.count_documents({})
    total_companies = db.companies.count_documents({})
    total_connectors = db.connectors.count_documents({})
    online_connectors = db.connectors.count_documents({"status": "ONLINE"})

    print(f"\n[1] PLATFORM OVERVIEW:")
    print(f"  * Total Registered Users    : {total_users}")
    print(f"  * Total Customer Orgs       : {total_orgs}")
    print(f"  * Total Synced Companies    : {total_companies}")
    print(f"  * Total Installed Connectors: {total_connectors} ({online_connectors} Currently ONLINE)")

    # 2. CUSTOMER / ORGANIZATION BREAKDOWN
    print(f"\n[2] TOP CUSTOMERS / ORGANIZATIONS USAGE:")
    print(f"  {'-'*66}")
    print(f"  {'Organization Name':<32} | {'Companies':<10} | {'Connectors':<10}")
    print(f"  {'-'*66}")
    for org in db.organizations.find().limit(15):
        org_id = org.get("_id")
        name = str(org.get("name") or org.get("companyName") or "Unnamed Org")[:30]
        c_cnt = db.companies.count_documents({"organizationId": org_id})
        d_cnt = db.connectors.count_documents({"organizationId": org_id})
        print(f"  {name:<32} | {c_cnt:<10} | {d_cnt:<10}")

    # 3. CONNECTORS & DEVICES LIVE STATUS
    print(f"\n[3] RECENT ACTIVE CONNECTORS (DEVICES):")
    print(f"  {'-'*66}")
    print(f"  {'Device Name':<20} | {'Status':<8} | {'Ver':<6} | {'Last Heartbeat'}")
    print(f"  {'-'*66}")
    for con in db.connectors.find().sort("lastHeartbeatAt", -1).limit(10):
        d_name = str(con.get("deviceName", "Unknown"))[:20]
        stat = con.get("status", "UNKNOWN")
        ver = str(con.get("connectorVersion", "1.0.0"))[:6]
        hb = con.get("lastHeartbeatAt")
        hb_str = hb.strftime("%Y-%m-%d %H:%M") if isinstance(hb, datetime) else str(hb)
        print(f"  {d_name:<20} | {stat:<8} | {ver:<6} | {hb_str}")

    # 4. RECENT FAILED VOUCHERS / COMMAND ISSUES
    failed_cmds = list(db.commands.find({"status": "FAILED"}).sort("_id", -1).limit(8))
    print(f"\n[4] RECENT CUSTOMER VOUCHER ISSUES / FAILURES ({len(failed_cmds)} showing):")
    if not failed_cmds:
        print("  ✅ No failed voucher commands found! Everything running smoothly.")
    else:
        for idx, cmd in enumerate(failed_cmds, 1):
            c_id = cmd.get("_id")
            payload = cmd.get("payload") or {}
            v_type = cmd.get("type") or payload.get("voucher_type") or "Voucher"
            comp = payload.get("company_name") or cmd.get("company") or "N/A"
            party = payload.get("party_ledger") or payload.get("name") or "N/A"
            amt = payload.get("amount") or payload.get("total_amount") or 0.0
            err_msg = cmd.get("errorMessage") or (cmd.get("result") or {}).get("reason") or "Unknown error"
            
            print(f"\n  ({idx}) Command #{c_id} [{v_type}]")
            print(f"      Company : {comp} | Party: {party} | Amount: Rs. {amt}")
            print(f"      Issue   : {err_msg}")

    # 5. PENDING VOUCHER QUEUE
    pending_cnt = db.pending_voucher_queue.count_documents({"status": "PENDING"})
    print(f"\n[5] PENDING VOUCHER QUEUE STATUS:")
    print(f"  * Total Vouchers in Wait Queue: {pending_cnt}")
    if pending_cnt > 0:
        for p in db.pending_voucher_queue.find({"status": "PENDING"}).limit(5):
            print(f"    - Target Company: {p.get('target_company')} | Reason: {p.get('last_error') or 'Waiting for company to open'}")

    print("\n" + "=" * 70 + "\n")

if __name__ == "__main__":
    run_health_check()
