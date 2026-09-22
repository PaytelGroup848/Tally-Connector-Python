

import httpx
import uuid

def verify_health_endpoints(services):
    print("\n[3/8] Testing Health Endpoints on Ports 8000-8009...")
    for name, _, port in services:
        res = httpx.get(f"http://127.0.0.1:{port}/health", timeout=15)
        assert res.status_code == 200
        print(f"  [PASS] {name:<25} (Port {port}): OK")

def verify_auth_and_mgmt(headers):
    print("\n[5/8] Testing User, Role, and Connector Management APIs...")
    u = httpx.get("http://127.0.0.1:8000/api/users", headers=headers, timeout=10)
    assert u.status_code == 200 and u.json()["success"] is True

    r = httpx.get("http://127.0.0.1:8000/api/roles", headers=headers, timeout=10)
    assert r.status_code == 200 and r.json()["success"] is True

    p = httpx.get("http://127.0.0.1:8000/api/permissions", headers=headers, timeout=10)
    assert p.status_code == 200 and p.json()["success"] is True

def verify_connectors_and_metadata(headers):
    c_name = f"Delhi Tally {uuid.uuid4().hex[:4]}"
    c_payload = {"name": c_name, "connector_type": "TALLY", "configuration": {"host": "127.0.0.1", "port": 9000}}
    create_c = httpx.post("http://127.0.0.1:8000/api/connectors", json=c_payload, headers=headers, timeout=10)
    assert create_c.status_code == 200

    search_meta = httpx.get("http://127.0.0.1:8000/api/metadata/search?query=test", headers=headers, timeout=10)
    assert search_meta.status_code == 200
    print("  [PASS] User, Role, Connector, Tally & Metadata APIs verified!")

def verify_pipeline_execution(headers):
    print("\n[6/8] Testing Tally Pipeline Execution...")
    tally_rec = {
        "source": "tally", "record_type": "ledger",
        "external_id": f"t-led-{uuid.uuid4().hex[:4]}", "company_name": "Test Tally Enterprise",
        "data": {"name": "State Bank of India", "closing_balance": 750000.0}
    }
    r_tally = httpx.post("http://127.0.0.1:8000/api/pipeline/record", json=tally_rec, headers=headers, timeout=10)
    assert r_tally.status_code == 200 and r_tally.json()["status"] == "success"
    print("  [PASS] Tally pipeline executed successfully!")
