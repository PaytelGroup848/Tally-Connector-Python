"""
CtrlBooks - Windows Startup & Registry Integration
----------------------------------------------------------------
Manages Windows Registry run key (HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run)
to toggle 'Start with Windows on Boot' functionality for the CtrlBooks Desktop Application.
"""

import sys
import os
from typing import Optional
from shared.logging_config import get_logger

logger = get_logger("shared.system_startup")

REG_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
DEFAULT_APP_NAME = "CtrlBooks"


def enable_run_on_startup(app_name: str = DEFAULT_APP_NAME, app_path: Optional[str] = None) -> bool:
    """
    Enables Windows auto-start on boot by writing executable path to Windows Registry.
    """
    if os.name != "nt":
        logger.warning("Startup registry modification is only supported on Windows OS.")
        return False

    import winreg

    executable = app_path or sys.executable
    clean_path = f'"{os.path.abspath(executable)}"'

    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            REG_KEY_PATH,
            0,
            winreg.KEY_SET_VALUE
        )
        winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, clean_path)
        winreg.CloseKey(key)
        logger.info(f"Enabled Windows startup registry key '{app_name}' -> {clean_path}")
        return True
    except Exception as exc:
        logger.error(f"Failed to enable Windows startup registry key: {exc}")
        return False


def disable_run_on_startup(app_name: str = DEFAULT_APP_NAME) -> bool:
    """
    Disables Windows auto-start on boot by deleting executable key from Windows Registry.
    """
    if os.name != "nt":
        return False

    import winreg

    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            REG_KEY_PATH,
            0,
            winreg.KEY_SET_VALUE
        )
        winreg.DeleteValue(key, app_name)
        winreg.CloseKey(key)
        logger.info(f"Disabled Windows startup registry key '{app_name}'")
        return True
    except FileNotFoundError:
        return True
    except Exception as exc:
        logger.error(f"Failed to disable Windows startup registry key: {exc}")
        return False


def is_startup_enabled(app_name: str = DEFAULT_APP_NAME) -> bool:
    """
    Checks if Windows auto-start on boot is currently enabled in Windows Registry.
    """
    if os.name != "nt":
        return False

    import winreg

    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            REG_KEY_PATH,
            0,
            winreg.KEY_READ
        )
        val, _ = winreg.QueryValueEx(key, app_name)
        winreg.CloseKey(key)
        return bool(val)
    except FileNotFoundError:
        return False
    except Exception as exc:
        logger.warning(f"Unable to read Windows startup registry key: {exc}")
        return False
