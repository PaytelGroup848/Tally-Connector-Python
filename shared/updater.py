"""
CtrlBooks - Automatic OTA Update Service
---------------------------------------------------
Handles Over-The-Air (OTA) update checking against Cloud API (GET /api/v1/connector/version/check),
semantic version comparisons, chunked file downloading with progress callbacks, SHA256 checksum
verification, and background batch script replacement with application relaunch.
"""

import os
import sys
import hashlib
import tempfile
import subprocess
import requests
from typing import Dict, Any, Tuple, Optional, Callable
from shared.config import get_settings
from shared.logging_config import get_logger
from shared.cloud_client import CloudClient

logger = get_logger("shared.updater")

def parse_version_tuple(version_str: str) -> Tuple[int, ...]:
    """Converts version string like '1.2.3' or 'v1.2.3' into tuple of integers (1, 2, 3)."""
    if not version_str:
        return (0, 0, 0)
    clean_v = str(version_str).strip().lstrip("vV")
    parts = []
    for part in clean_v.split("."):
        try:
            parts.append(int(part.split("-")[0].split("+")[0]))
        except ValueError:
            parts.append(0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)

def compute_file_sha256(filepath: str) -> str:
    """Computes SHA256 checksum hex string for a given local file."""
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(65536), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest().lower()

class OTAUpdater:
    def __init__(self, cloud_client: Optional[CloudClient] = None):
        self.settings = get_settings()
        self.cloud_client = cloud_client or CloudClient()

    def check_for_updates(self, current_version: Optional[str] = None) -> Dict[str, Any]:
        """
        Queries Cloud API (GET /version) to inspect available cloud release version.
        Compares latest version against current version.
        """
        curr_ver = current_version or self.settings.app_version
        logger.info(f"Checking for updates. Current version: v{curr_ver}")

        try:
            from shared.auth.cloud_auth_service import cloud_auth_service
            ok, msg, res = cloud_auth_service.get_connector_version()

            if not ok or not isinstance(res, dict):
                # Fallback to direct client query
                try:
                    res = self.cloud_client._request("GET", "/version")
                except Exception:
                    pass

            if not isinstance(res, dict):
                res = {}

            latest_version = (
                res.get("latestVersion")
                or res.get("latest_version")
                or res.get("version")
                or curr_ver
            )
            download_url = (
                res.get("downloadUrl")
                or res.get("download_url")
                or res.get("url")
            )
            if not download_url:
                web_base = (self.settings.web_portal_url or "https://connector.cloudedata.com").rstrip("/")
                download_url = f"{web_base}/downloads/CtrlBooks_Setup.exe"
            expected_sha256 = (
                res.get("sha256")
                or res.get("checksum")
            )
            release_notes = (
                res.get("releaseNotes")
                or res.get("release_notes")
                or res.get("notes")
                or res.get("changelog")
                or "New features, performance enhancements, and bug fixes."
            )
            min_ver = res.get("minVersion") or res.get("min_version")
            mandatory = bool(res.get("mandatory", False))
            if min_ver and parse_version_tuple(min_ver) > parse_version_tuple(curr_ver):
                mandatory = True

            is_newer = parse_version_tuple(latest_version) > parse_version_tuple(curr_ver)

            return {
                "update_available": is_newer,
                "current_version": curr_ver,
                "latest_version": latest_version,
                "download_url": download_url,
                "sha256": expected_sha256,
                "release_notes": release_notes,
                "mandatory": mandatory,
                "error": None,
            }

        except Exception as exc:
            logger.warning(f"Failed to check for OTA updates: {exc}")
            return {
                "update_available": False,
                "current_version": curr_ver,
                "latest_version": curr_ver,
                "download_url": None,
                "sha256": None,
                "release_notes": None,
                "mandatory": False,
                "error": str(exc),
            }

    def download_update(
        self,
        download_url: str,
        expected_sha256: Optional[str] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Downloads update file from download_url to temporary directory in chunks.
        Reports progress via callback(downloaded_bytes, total_bytes).
        Verifies SHA256 checksum after download completes.
        Returns (success: bool, file_path: str|None, error_msg: str|None).
        """
        if not download_url:
            return False, None, "Invalid download URL provided."

        temp_dir = tempfile.gettempdir()
        filename = download_url.split("/")[-1].split("?")[0] or "ctrlbooks_update.exe"
        dest_path = os.path.join(temp_dir, f"ctrlbooks_update_{filename}")

        try:
            logger.info(f"Starting update download from {download_url} -> {dest_path}")
            response = requests.get(download_url, stream=True, timeout=30.0)
            if response.status_code != 200:
                return False, None, f"Download failed with HTTP status {response.status_code}"

            total_size = int(response.headers.get("content-length", 0))
            downloaded = 0

            with open(dest_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=1048576):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback:
                            try:
                                progress_callback(downloaded, total_size)
                            except Exception:
                                pass

            logger.info(f"Download complete: {dest_path} ({downloaded} bytes)")

            if expected_sha256 and expected_sha256.strip():
                clean_expected = expected_sha256.strip().lower()
                computed_hash = compute_file_sha256(dest_path)
                if computed_hash != clean_expected:
                    logger.error(f"SHA256 mismatch! Computed: {computed_hash}, Expected: {clean_expected}")
                    try:
                        os.remove(dest_path)
                    except Exception:
                        pass
                    return False, None, (
                        f"SHA256 checksum verification failed (computed: {computed_hash[:8]}... vs expected: {clean_expected[:8]}...)"
                    )

            return True, dest_path, None

        except Exception as exc:
            logger.error(f"Error during update file download: {exc}")
            if os.path.exists(dest_path):
                try:
                    os.remove(dest_path)
                except Exception:
                    pass
            return False, None, f"Download error: {exc}"

    def launch_batch_update_and_restart(
        self, installer_path: str, target_exe_path: Optional[str] = None
    ) -> bool:
        """
        Creates a Windows .bat script in temp directory that waits for current process to exit,
        replaces binary executable with downloaded file, and launches the new executable.
        """
        if not target_exe_path:
            target_exe_path = sys.executable

        temp_dir = tempfile.gettempdir()
        bat_path = os.path.join(temp_dir, "ctrlbooks_ota_replace.bat")

        clean_installer = os.path.abspath(installer_path).replace("/", "\\")
        clean_target = os.path.abspath(target_exe_path).replace("/", "\\")

        bat_content = f"""@echo off
timeout /t 2 /nobreak > NUL
copy /y "{clean_installer}" "{clean_target}"
start "" "{clean_target}"
del "%~f0"
"""

        try:
            with open(bat_path, "w", encoding="utf-8") as f:
                f.write(bat_content)

            logger.info(f"Created batch replacer script at {bat_path}. Launching background replacement...")
            subprocess.Popen(
                ["cmd.exe", "/c", bat_path],
                creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0,
                close_fds=True,
            )
            return True
        except Exception as exc:
            logger.error(f"Failed to launch batch update script: {exc}")
            return False

    def install_and_restart(self, downloaded_path: str) -> bool:
        """
        Executes downloaded update file and prepares app update.
        If file is a setup installer (.exe), launches it directly.
        Otherwise falls back to batch file binary replacement.
        """
        if not downloaded_path or not os.path.exists(downloaded_path):
            logger.error(f"Cannot install update: file not found at {downloaded_path}")
            return False

        clean_path = os.path.abspath(downloaded_path).replace("/", "\\")
        file_lower = clean_path.lower()

        try:
            if "setup" in file_lower or file_lower.endswith(".exe"):
                logger.info(f"Launching setup installer executable: {clean_path}")
                if os.name == "nt":
                    os.startfile(clean_path)
                else:
                    subprocess.Popen([clean_path], shell=True)
                return True
            else:
                return self.launch_batch_update_and_restart(clean_path)
        except Exception as exc:
            logger.error(f"Failed to execute update installer: {exc}")
            return False

updater_service = OTAUpdater()
