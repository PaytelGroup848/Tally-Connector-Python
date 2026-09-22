

from fastapi import FastAPI
import httpx
from shared.config import get_settings
from shared.logging_config import setup_logging, get_logger
from shared.exceptions import register_exception_handlers
from shared.middleware import add_request_id_middleware
from shared.models import SourceType, ConnectionStatus, ConnectionState

setup_logging("connection_service")
logger = get_logger("app.connection_service")
settings = get_settings()

app = FastAPI(
    title="CtrlBooks Connection Service",
    description="Probing and status tracking for Tally and BUSY integrations"
)

add_request_id_middleware(app)
register_exception_handlers(app)

tally_config = {"host": settings.tally_host, "port": settings.tally_port}

@app.get("/health")
async def health():
    return {"service": "connection_service", "status": "ok"}

@app.post("/configure/tally")
async def configure_tally(payload: dict):
    """Configure target host & port for Tally connection monitoring."""
    tally_config["host"] = payload.get("host", tally_config["host"])
    tally_config["port"] = int(payload.get("port", tally_config["port"]))
    logger.info(f"Tally configuration updated: {tally_config}")
    return {"configured": True, "tally_config": tally_config}

@app.get("/status/tally")
async def tally_status():
    """Probe Tally Prime HTTP server availability."""
    url = f"http://{tally_config['host']}:{tally_config['port']}/"
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            response = await client.get(url)
        state = ConnectionState.CONNECTED if response.status_code < 500 else ConnectionState.ERROR
        msg = f"Tally Prime HTTP Server detected and reachable at {url}"
        details = {"http_status": response.status_code}
    except Exception as exc:
        state = ConnectionState.DISCONNECTED
        msg = f"Tally Prime HTTP Server not reachable at {url} (Make sure Tally is open with ODBC/HTTP enabled on port {tally_config['port']})"
        details = {"error": str(exc)}

    return ConnectionStatus(
        source=SourceType.TALLY,
        state=state,
        message=msg,
        details=details
    ).model_dump(mode="json")

@app.get("/status/all")
async def all_statuses():
    """Combined connectivity report for accounting software systems."""
    t_status = await tally_status()
    return {
        "tally": t_status
    }
