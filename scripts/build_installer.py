

import subprocess
import sys
import glob
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ISS_FILE = ROOT / "installer" / "ctrlbooks_setup.iss"

def find_iscc() -> str:
    try:
        res = subprocess.run(["where", "iscc"], capture_output=True, text=True)
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip().splitlines()[0]
    except Exception:
        pass

    search_paths = [
        str(Path.home() / "AppData/Local/Programs/Inno Setup 6/ISCC.exe"),
        str(Path.home() / "AppData/Local/Programs/Inno Setup */ISCC.exe"),
        "C:/Users/*/AppData/Local/Programs/Inno Setup */ISCC.exe",
        "C:/Program Files (x86)/Inno Setup */ISCC.exe",
        "C:/Program Files/Inno Setup */ISCC.exe",
        "C:/Inno Setup */ISCC.exe"
    ]
    for pattern in search_paths:
        matches = glob.glob(pattern)
        if matches:
            return matches[0]

    return ""

def main():
    print("=========================================================")
    print(" Building Client Setup Installer: CtrlBooks_Setup_v1.0.1.exe")
    print("=========================================================")

    if not ISS_FILE.exists():
        print(f"[!] Error: Script file not found at {ISS_FILE}")
        sys.exit(1)

    iscc_path = find_iscc()
    if not iscc_path:
        print("\n[!] Inno Setup Compiler (ISCC.exe) was not found in PATH or standard Program Files.")
        print(f"[*] The installer specification script is fully prepared at:\n    {ISS_FILE}")
        print("[*] To compile into .exe setup, install Inno Setup (https://jrsoftware.org/isdl.php) and run:")
        print(f"    ISCC.exe {ISS_FILE}")
        return

    cmd = [iscc_path, str(ISS_FILE)]
    print(f"Executing: {' '.join(cmd)}")
    res = subprocess.run(cmd, cwd=str(ROOT))

    if res.returncode == 0:
        dist_setup = ROOT / "dist" / "CtrlBooks_Setup_v1.0.1.exe"
        print("\n=========================================================")
        print(f" INSTALLER BUILD SUCCESSFUL! Setup generated at:\n {dist_setup}")
        print("=========================================================")
    else:
        print(f"\n[!] Installer build failed with exit code: {res.returncode}")
        sys.exit(res.returncode)

if __name__ == "__main__":
    main()
