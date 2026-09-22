

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC_FILE = ROOT / "apps" / "agent" / "ctrlbooks_agent.spec"

def main():
    print("=========================================================")
    print(" Building Standalone Local Sync Agent Executable: ctrlbooks_agent.exe")
    print("=========================================================")

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--clean",
        "--noconfirm",
        str(SPEC_FILE)
    ]

    print(f"Executing: {' '.join(cmd)}")
    res = subprocess.run(cmd, cwd=str(ROOT))

    if res.returncode == 0:
        dist_exe = ROOT / "dist" / "ctrlbooks_agent" / "ctrlbooks_agent.exe"
        print("\n=========================================================")
        print(f" BUILD SUCCESSFUL! Local Agent generated at:\n {dist_exe}")
        print("=========================================================")
    else:
        print(f"\n[!] Build failed with exit code: {res.returncode}")
        sys.exit(res.returncode)

if __name__ == "__main__":
    main()
