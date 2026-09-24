"""
CtrlBooks - Connection Configuration Manager
--------------------------------------------
Provides persistent local storage for Tally connection parameters (host, port, sync intervals).
Ensures that custom ODBC ports (e.g. on shared cloud servers with 50+ Tally instances)
are reliably saved across app restarts and strictly honored without unwanted auto-scanning.
"""

import os
import json
import socket
from pathlib import Path
from typing import Dict, Any, Tuple, List, Optional
from shared.logging_config import get_logger

logger = get_logger("shared.connection_config")

def _get_writable_data_file(filename: str) -> Path:
    """Returns a writable Path for app data storage across local and packaged environments."""
    local_path = Path("data") / filename
    try:
        local_path.parent.mkdir(parents=True, exist_ok=True)
        test_file = local_path.parent / ".perm_check"
        test_file.touch(exist_ok=True)
        test_file.unlink(missing_ok=True)
        return local_path
    except Exception:
        pass

    local_app_data = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    fallback = Path(local_app_data) / "CtrlBooks" / "data" / filename
    try:
        fallback.parent.mkdir(parents=True, exist_ok=True)
        return fallback
    except Exception:
        import tempfile
        tmp = Path(tempfile.gettempdir()) / "CtrlBooks" / "data" / filename
        tmp.parent.mkdir(parents=True, exist_ok=True)
        return tmp

CONFIG_FILE = _get_writable_data_file("connection_config.json")

DEFAULT_CONFIG: Dict[str, Any] = {
    "tally_host": "127.0.0.1",
    "tally_port": 9000,
    "sync_interval_minutes": "5 mins",
    "auto_connect": True,
    "start_with_windows": True,
}

def load_connection_config() -> Dict[str, Any]:
    """Loads saved connection config from disk, falling back to defaults."""
    config = dict(DEFAULT_CONFIG)
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    config.update(data)
        except Exception as exc:
            logger.warning(f"Failed to read {CONFIG_FILE}: {exc}")

    # Synchronize in-memory settings
    try:
        from shared.config import get_settings
        settings = get_settings()
        port = int(config.get("tally_port", 9000))
        host = str(config.get("tally_host", "127.0.0.1")).strip() or "127.0.0.1"
        settings.tally_port = port
        settings.tally_host = host
    except Exception:
        pass

    return config

def save_connection_config(
    host: str = "127.0.0.1",
    port: int = 9000,
    sync_interval_minutes: str = "5 mins",
    auto_connect: bool = True,
    start_with_windows: Optional[bool] = None,
) -> bool:
    """Persists connection parameters to disk and updates runtime settings."""
    clean_host = (host or "127.0.0.1").strip()
    if clean_host.lower() == "localhost":
        clean_host = "127.0.0.1"

    try:
        clean_port = int(port)
    except (ValueError, TypeError):
        clean_port = 9000

    cfg = load_connection_config()
    cfg["tally_host"] = clean_host
    cfg["tally_port"] = clean_port
    cfg["sync_interval_minutes"] = sync_interval_minutes
    cfg["auto_connect"] = bool(auto_connect)
    if start_with_windows is not None:
        cfg["start_with_windows"] = bool(start_with_windows)

    try:
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        logger.info(f"Saved connection config to {CONFIG_FILE}: host={clean_host}, port={clean_port}")
    except Exception as exc:
        logger.error(f"Failed to write connection config: {exc}")
        return False

    # Update in-memory settings singleton
    try:
        from shared.config import get_settings
        settings = get_settings()
        settings.tally_port = clean_port
        settings.tally_host = clean_host
    except Exception:
        pass

    return True

def get_configured_port() -> int:
    """Returns currently saved Tally ODBC port."""
    cfg = load_connection_config()
    try:
        return int(cfg.get("tally_port", 9000))
    except Exception:
        return 9000

def get_configured_host() -> str:
    """Returns currently saved Tally host."""
    cfg = load_connection_config()
    return str(cfg.get("tally_host", "127.0.0.1"))

def test_tally_port(host: str = "127.0.0.1", port: int = 9000, timeout: float = 2.0) -> Tuple[bool, List[str], str]:
    """
    Performs direct socket + TDL XML probe against the specified port.
    Returns (is_online, [open_company_names], status_message).
    """
    clean_host = (host or "127.0.0.1").strip()
    if clean_host.lower() == "localhost":
        clean_host = "127.0.0.1"

    try:
        port_num = int(port)
    except Exception:
        return False, [], "Invalid port number"

    # 1. Quick TCP socket probe
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(min(timeout, 1.0))
        res = sock.connect_ex((clean_host, port_num))
        sock.close()
        if res != 0:
            return False, [], f"Port {port_num} is not responding (connection refused)"
    except Exception as exc:
        return False, [], f"Socket error: {exc}"

    # 2. TDL XML Collection request
    try:
        import httpx
        from apps.backend.adapters.tally.request_builder import build_company_list_xml
        from apps.backend.adapters.tally.response_parser import parse_company_list

        xml_req = build_company_list_xml()
        h_res = httpx.post(
            f"http://{clean_host}:{port_num}/",
            content=xml_req,
            headers={"Content-Type": "text/xml"},
            timeout=timeout,
        )
        if h_res.status_code == 200 and h_res.text:
            comp_dicts = parse_company_list(h_res.text)
            names = [c["name"] for c in comp_dicts if c.get("name")]
            return True, names, f"Connected ({len(names)} companies open)"
        return True, [], "Tally port open (no company currently loaded)"
    except Exception as exc:
        return False, [], f"Tally XML probe failed: {exc}"

