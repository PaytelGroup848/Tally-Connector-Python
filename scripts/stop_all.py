

import subprocess
import re
import sys

PORTS = [8000, 8001, 8002, 8004, 8005, 8006, 8007, 8008, 8009]

def stop_services():
    print("Finding and stopping existing backend services...")
    killed_pids = set()

    for port in PORTS:
        try:
            output = subprocess.check_output(f"netstat -ano | findstr :{port}", shell=True, text=True)
            for line in output.strip().splitlines():
                parts = re.split(r'\s+', line.strip())
                if len(parts) >= 5 and "LISTENING" in line:
                    pid = parts[-1]
                    if pid and pid.isdigit() and int(pid) > 0 and pid not in killed_pids:
                        killed_pids.add(pid)
                        print(f"[+] Stopping process on Port {port} (PID: {pid})...")
                        subprocess.run(f"taskkill /F /PID {pid}", shell=True, capture_output=True)
        except Exception:
            pass

    if killed_pids:
        print(f"[✓] Stopped {len(killed_pids)} process(es). Ports 8000-8009 are now free!")
    else:
        print("[i] No background services were occupying ports 8000-8009.")

if __name__ == "__main__":
    stop_services()

