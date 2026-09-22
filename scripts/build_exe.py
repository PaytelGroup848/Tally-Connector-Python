

import sys
import subprocess
from pathlib import Path

def run_build():
    root = Path(__file__).resolve().parents[1]
    print(f"[+] Packaging CtrlBooks standalone executable from {root}...")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--windowed",
        "--name", "CtrlBooks",
        "--add-data", f"{root / 'apps'}{';'}apps",
        "--add-data", f"{root / 'shared'}{';'}shared",
        "--hidden-import", "PySide6",
        "--hidden-import", "httpx",
        "--hidden-import", "sqlalchemy",
        "--hidden-import", "fastapi",
        "--hidden-import", "uvicorn",
        str(root / "apps" / "desktop_app" / "main.py")
    ]

    print("[+] Executing command:", " ".join(cmd))
    res = subprocess.run(cmd, cwd=root)
    if res.returncode == 0:
        print("[✓] Build completed successfully! Output binary located in dist/CtrlBooks/")
    else:
        print("[✕] Build failed with exit code:", res.returncode)

if __name__ == "__main__":
    run_build()
