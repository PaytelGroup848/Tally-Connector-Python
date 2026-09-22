

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC_FILE = ROOT / "apps" / "desktop_app" / "ctrlbooks.spec"

def main():
    print("=========================================================")
    print(" Building Standalone Desktop Executable: ctrlbooks.exe")
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
        dist_exe = ROOT / "dist" / "ctrlbooks" / "ctrlbooks.exe"
        print("\n=========================================================")
        print(f" BUILD SUCCESSFUL! Desktop App generated at:\n {dist_exe}")
        print("=========================================================")
    else:
        print(f"\n[!] Build failed with exit code: {res.returncode}")
        sys.exit(res.returncode)

if __name__ == "__main__":
    main()
