

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
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

processes = []

def main():
    print("=========================================================")
    print(" Starting CtrlBooks Backend Microservices (Tally Prime)")
    print("=========================================================")
    try:
        for name, module, port in SERVICES:
            print(f"[+] Launching {name:<25} on http://127.0.0.1:{port}")
            p = subprocess.Popen(
                [PY, "-m", "uvicorn", module, "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
                cwd=str(ROOT)
            )
            processes.append(p)

        print("\nAll Microservices successfully launched!")
        print("API Gateway Documentation: http://127.0.0.1:8000/docs")
        print("Press Ctrl+C to terminate all services gracefully.\n")

        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nStopping all microservices...")
    finally:
        for p in processes:
            p.terminate()
        for p in processes:
            p.wait()
        print("[+] All microservices stopped cleanly.")

if __name__ == "__main__":
    main()
