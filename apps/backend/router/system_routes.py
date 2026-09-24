from fastapi import APIRouter
import psutil
import sys
import httpx
from pydantic import BaseModel
from shared.config import get_settings

router = APIRouter(prefix="/api/system", tags=["System Checks & Settings"])

class ConnectionSettingsPayload(BaseModel):
    host: str = "localhost"
    port: int = 9000
    auto_connect: bool = True
    sync_interval_minutes: int = 2

current_settings = ConnectionSettingsPayload()

@router.get("/check")
async def system_check():
    
    total_ram_gb = round(psutil.virtual_memory().total / (1024 ** 3), 1)
    
    tally_ok = False
    try:
        async with httpx.AsyncClient(timeout=1.5) as client:
            res = await client.get(f"http://{current_settings.host}:{current_settings.port}/")
            tally_ok = res.status_code < 500
    except Exception:
        pass

    overall_status = "GOOD" if tally_ok else "NOT_OK"

    return {
        "status": overall_status,
        "checks": {
            "os_compatible": True,
            "os_name": sys.platform,
            "ram_total_gb": total_ram_gb,
            "ram_compatible": total_ram_gb >= 4.0,
            "tally_connected": tally_ok,
        },
        "version": get_settings().app_version
    }

@router.get("/settings/connection")
async def get_connection_settings():
    return current_settings

@router.post("/settings/connection")
async def update_connection_settings(payload: ConnectionSettingsPayload):
    global current_settings
    current_settings = payload
    return {"success": True, "settings": current_settings}

@router.get("/version")
async def get_version_info():
    settings = get_settings()
    curr_ver = settings.app_version
    return {
        "success": True,
        "version": curr_ver,
        "latestVersion": curr_ver,
        "latest_version": curr_ver,
        "minVersion": "1.0.0",
        "releaseNotes": "Shared Cloud Server multi-Tally support & manual ODBC port configuration.",
        "downloadUrl": f"http://191.44.87.205:8000/downloads/CtrlBooks_Setup_v{curr_ver}.exe",
        "download_url": f"http://191.44.87.205:8000/downloads/CtrlBooks_Setup_v{curr_ver}.exe",
        "mandatory": False,
    }

