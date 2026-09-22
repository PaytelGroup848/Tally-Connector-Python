

import subprocess
import sys
import time
import httpx
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.verify_helpers import (
    verify_health_endpoints, verify_auth_and_mgmt,
    verify_connectors_and_metadata, verify_pipeline_execution
)

PY = sys.executable

SERVICES = [
    ("connection_service", "apps.backend.services.connection_service.main:app", 8001),
    ("tally_adapter", "apps.backend.services.tally_adapter.main:app", 8002),
    ("normalization_service", "apps.backend.services.normalization_service.main:app", 8004),
    ("sync_service", "apps.backend.services.sync_service.main:app", 8005),
    ("change_detection_service", "apps.backend.services.change_detection_service.main:app", 8006),
    ("storage_service", "apps.backend.services.storage_service.main:app", 8007),
    ("audit_service", "apps.backend.services.audit_service.main:app", 8008),
    ("company_service", "apps.backend.services.company_service.main:app", 8009),
    ("api_gateway", "apps.backend.gateway.main:app", 8000),
]

def main():
    print("=========================================================")
    print(" CtrlBooks - Automated Verification Suite")
    print("=========================================================")

    print("[0/8] Running Foundation Unit & Integration Test Suites...")
    r_unit = subprocess.run([PY, "-m", "unittest", "discover", "-s", "tests/unit"], cwd=str(ROOT))
    r_int = subprocess.run([PY, "-m", "unittest", "discover", "-s", "tests/integration"], cwd=str(ROOT))
    assert r_unit.returncode == 0 and r_int.returncode == 0
    print("  [PASS] All unit and integration tests passed!\n")

    print("[1/8] Bootstrapping RBAC & Administrator Account...")
    subprocess.run([PY, "scripts/seed_rbac.py"], cwd=str(ROOT))
    subprocess.run([PY, "scripts/create_admin.py", "--username", "admin", "--password", "Admin@123"], cwd=str(ROOT))

    processes = []
    try:
        print("[2/8] Launching Microservices...")
        for name, module, port in SERVICES:
            p = subprocess.Popen([PY, "-m", "uvicorn", module, "--host", "127.0.0.1", "--port", str(port), "--log-level", "error"], cwd=str(ROOT))
            processes.append(p)
        time.sleep(3)

        verify_health_endpoints(SERVICES)

        print("\n[4/8] Testing Authentication API (POST /api/auth/login)...")
        login_res = httpx.post("http://127.0.0.1:8000/api/auth/login", json={"username": "admin", "password": "Admin@123"}, timeout=10)
        assert login_res.status_code == 200
        token = login_res.json()["data"]["session"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print("  [PASS] Authentication successful!")

        verify_auth_and_mgmt(headers)
        verify_connectors_and_metadata(headers)
        verify_pipeline_execution(headers)

        print("\n[7/8] Querying Stored Records...")
        res_records = httpx.get("http://127.0.0.1:8000/api/records", headers=headers, timeout=10)
        assert res_records.status_code == 200

        print("\n=========================================================")
        print(" ALL VERIFICATION TESTS PASSED SUCCESSFULLY! ")
        print("=========================================================")
    finally:
        for p in processes:
            p.terminate()
            p.wait()

if __name__ == "__main__":
    main()
