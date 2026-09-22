import subprocess
import sys
import hashlib
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def calculate_sha256(filepath: Path) -> str:
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()

def main():
    start_time = time.time()
    print("======================================================================")
    print("      CTRLBOOKS - PRODUCTION RELEASE BUILD PIPELINE        ")
    print("======================================================================")
    print(f"[*] Workspace Root: {ROOT}")
    print(f"[*] Python Runtime: {sys.executable} (v{sys.version.split()[0]})")

    # Step 1: Run PyInstaller Desktop Build
    print("\n----------------------------------------------------------------------")
    print("[1/2] Compiling Standalone Desktop Application with PyInstaller...")
    print("----------------------------------------------------------------------")
    build_desktop_py = ROOT / "scripts" / "build_desktop.py"
    res_pyi = subprocess.run([sys.executable, str(build_desktop_py)], cwd=str(ROOT))
    if res_pyi.returncode != 0:
        print(f"\n[!] PyInstaller build failed with exit code {res_pyi.returncode}.")
        sys.exit(res_pyi.returncode)

    dist_exe = ROOT / "dist" / "ctrlbooks" / "ctrlbooks.exe"
    if not dist_exe.exists():
        print(f"\n[!] Error: Expected binary not found at {dist_exe}")
        sys.exit(1)

    dist_exe_size = dist_exe.stat().st_size / (1024 * 1024)
    print(f"[+] Application binary generated successfully: {dist_exe} ({dist_exe_size:.2f} MB)")

    # Step 2: Run Inno Setup Compiler
    print("\n----------------------------------------------------------------------")
    print("[2/2] Packaging Professional Windows Setup Installer (setup.exe)...")
    print("----------------------------------------------------------------------")
    build_installer_py = ROOT / "scripts" / "build_installer.py"
    res_iss = subprocess.run([sys.executable, str(build_installer_py)], cwd=str(ROOT))
    if res_iss.returncode != 0:
        print(f"\n[!] Inno Setup compilation failed with exit code {res_iss.returncode}.")
        sys.exit(res_iss.returncode)

    setup_exe = ROOT / "dist" / "CtrlBooks_Setup_v1.0.1.exe"
    if not setup_exe.exists():
        print(f"\n[!] Error: Installer setup executable not found at {setup_exe}")
        sys.exit(1)

    setup_size = setup_exe.stat().st_size / (1024 * 1024)
    setup_hash = calculate_sha256(setup_exe)
    elapsed = time.time() - start_time

    print("\n======================================================================")
    print("                    RELEASE BUILD SUCCESSFUL!                         ")
    print("======================================================================")
    print(f" Installer Binary : {setup_exe.name}")
    print(f" Absolute Path    : {setup_exe}")
    print(f" File Size        : {setup_size:.2f} MB")
    print(f" SHA-256 Checksum : {setup_hash}")
    print(f" Total Build Time : {elapsed:.1f} seconds")
    print("======================================================================\n")

if __name__ == "__main__":
    main()

