"""
CtrlBooks - API Gateway (Port 8000)
-----------------------------------------------
Single local API Gateway entry point under apps/backend/gateway/
Routes incoming client/UI/Agent requests to internal microservices:
- Connection Service (8001)
- Tally Adapter (8002)
- Normalization Service (8004)
- Sync Service (8005)
- Change Detection (8006)
- Storage Service (8007)
- Audit Service (8008)
- Company Service (8009)

Integrated with Module 1 Foundation: Centralized Config, Structured Logging,
Global Exception Handling, Request Correlation ID, and Real Health Monitoring.
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.middleware.gzip import GZipMiddleware
import os
from pathlib import Path
from contextlib import asynccontextmanager
import httpx
from typing import Optional

from shared.logging_config import setup_logging, get_logger
from shared.exceptions import register_exception_handlers, ServiceUnavailableException
from shared.middleware import add_request_id_middleware
from shared.lifecycle import ApplicationLifecycle
from shared.health import get_system_health, get_app_info
from shared.models import CompanyCreate, SyncRequest, SourceRecord

setup_logging("api_gateway")
logger = get_logger("app.gateway")
lifecycle = ApplicationLifecycle("api_gateway")

_http_client: Optional[httpx.AsyncClient] = None

def get_gateway_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(
            timeout=20.0,
            limits=httpx.Limits(max_keepalive_connections=50, max_connections=100, keepalive_expiry=30.0)
        )
    return _http_client

@asynccontextmanager
async def lifespan(app: FastAPI):
    lifecycle.startup()
    get_gateway_http_client()
    yield
    global _http_client
    if _http_client and not _http_client.is_closed:
        await _http_client.aclose()
        _http_client = None
    lifecycle.shutdown()

app = FastAPI(
    title="CtrlBooks API Gateway",
    description="Unified API Gateway routing to Tally backend microservices",
    lifespan=lifespan
)

app.add_middleware(GZipMiddleware, minimum_size=1000)

from apps.backend.router.auth_routes import router as auth_router
from apps.backend.router.user_routes import router as user_router
from apps.backend.router.role_routes import router as role_router, permission_router
from apps.backend.router.connector_routes import router as connector_router
from apps.backend.router.metadata_routes import router as metadata_router
from apps.backend.router.mapping_routes import router as mapping_router
from apps.backend.router.extraction_routes import extraction_router
from apps.backend.router.website_api_routes import website_api_router
from apps.backend.router.system_routes import router as system_router

add_request_id_middleware(app)
register_exception_handlers(app)
app.include_router(auth_router)
app.include_router(user_router)
app.include_router(role_router)
app.include_router(permission_router)
app.include_router(connector_router)
app.include_router(metadata_router)
app.include_router(mapping_router)
app.include_router(extraction_router)
app.include_router(website_api_router)
app.include_router(system_router)

@app.get("/version")
@app.get("/api/version")
async def get_public_version():
    import json
    v_file = Path("version.json")
    if v_file.exists():
        try:
            with open(v_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    data["success"] = True
                    return data
        except Exception:
            pass

    from shared.config import get_settings
    curr_ver = get_settings().app_version
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

from fastapi.staticfiles import StaticFiles
_dl_dir = Path("dist")
if not _dl_dir.exists():
    _dl_dir = Path("downloads")
_dl_dir.mkdir(parents=True, exist_ok=True)
app.mount("/downloads", StaticFiles(directory=str(_dl_dir)), name="downloads")

URLS = {
    "connection": "http://127.0.0.1:8001",
    "tally": "http://127.0.0.1:8002",
    "normalization": "http://127.0.0.1:8004",
    "sync": "http://127.0.0.1:8005",
    "change": "http://127.0.0.1:8006",
    "storage": "http://127.0.0.1:8007",
    "audit": "http://127.0.0.1:8008",
    "company": "http://127.0.0.1:8009",
}

async def call_microservice(method: str, service: str, path: str, payload: Optional[dict] = None, request_id: str = ""):
    """Helper method to forward HTTP requests to internal microservices with Request ID propagation."""
    if service not in URLS:
        raise HTTPException(500, f"Unknown service '{service}'")

    target_url = URLS[service] + path
    headers = {"X-Request-ID": request_id} if request_id else {}
    try:
        client = get_gateway_http_client()
        res = await client.request(method, target_url, json=payload, headers=headers)
        res.raise_for_status()
        return res.json()
    except httpx.HTTPStatusError as err:
        raise HTTPException(err.response.status_code, f"Microservice '{service}' error: {err.response.text}")
    except Exception as exc:
        raise ServiceUnavailableException(f"Microservice '{service}' unavailable at {target_url}: {exc}")

@app.get("/health")
@app.get("/api/health")
async def gateway_health(request: Request):
    """Returns Gateway status, foundation component status, and microservices health."""
    req_id = getattr(request.state, "request_id", "")
    foundation_health = get_system_health(req_id)

    service_health = {}
    client = get_gateway_http_client()
    for name, base_url in URLS.items():
        try:
            r = await client.get(f"{base_url}/health", headers={"X-Request-ID": req_id}, timeout=3.0)
            service_health[name] = r.json() if r.status_code == 200 else {"status": "error", "code": r.status_code}
        except Exception as e:
            service_health[name] = {"status": "offline", "error": str(e)}

    data = foundation_health.get("data", {})
    data["gateway"] = "online"
    data["microservices"] = service_health
    foundation_health["data"] = data
    return foundation_health

@app.get("/api/app/info")
async def app_info_endpoint(request: Request):
    """Returns real application information, environment, and configuration state."""
    req_id = getattr(request.state, "request_id", "")
    return get_app_info(req_id)

@app.get("/website", response_class=HTMLResponse, summary="Website Data Viewer Dashboard")
async def website_dashboard():
    """Renders interactive Web Dashboard for inspecting stored Tally data via Website REST APIs."""
    static_file = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "static", "website_dashboard.html"))
    if os.path.exists(static_file):
        with open(static_file, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>CtrlBooks Website Dashboard</h1><p>Website static dashboard file not found.</p>")

@app.get("/api/status")
async def accounting_software_status(request: Request):
    """Returns connectivity status for Tally software."""
    req_id = getattr(request.state, "request_id", "")
    return await call_microservice("GET", "connection", "/status/all", request_id=req_id)

@app.get("/api/companies")
async def list_companies(request: Request, source: Optional[str] = None, organization_id: Optional[str] = None):
    """List registered companies from Tally optionally filtered by organization_id."""
    req_id = getattr(request.state, "request_id", "")
    params = []
    if source:
        params.append(f"source={source}")
    if organization_id:
        params.append(f"organization_id={organization_id}")
    path = "/companies" + (("?" + "&".join(params)) if params else "")
    return await call_microservice("GET", "company", path, request_id=req_id)

@app.post("/api/companies")
async def create_company(request: Request, data: CompanyCreate):
    """Register a new Tally company."""
    req_id = getattr(request.state, "request_id", "")
    return await call_microservice("POST", "company", "/companies", data.model_dump(mode="json"), request_id=req_id)

@app.delete("/api/companies/{company_id}")
async def delete_company(request: Request, company_id: int):
    """Deletes a registered company by ID."""
    req_id = getattr(request.state, "request_id", "")
    return await call_microservice("DELETE", "company", f"/companies/{company_id}", request_id=req_id)

@app.post("/api/sync/start")
async def start_sync_job(request: Request, data: SyncRequest):
    """Trigger a background sync pipeline job for a Tally company."""
    req_id = getattr(request.state, "request_id", "")
    return await call_microservice("POST", "sync", "/jobs", data.model_dump(mode="json"), request_id=req_id)

@app.get("/api/sync/jobs")
async def list_sync_jobs(request: Request):
    """List recent sync job executions."""
    req_id = getattr(request.state, "request_id", "")
    return await call_microservice("GET", "sync", "/jobs", request_id=req_id)

@app.get("/api/sync/jobs/{job_id}")
async def get_sync_job(request: Request, job_id: str):
    """Get progress and status of a specific sync job."""
    req_id = getattr(request.state, "request_id", "")
    return await call_microservice("GET", "sync", f"/jobs/{job_id}", request_id=req_id)

@app.post("/api/pipeline/record")
async def process_single_record(request: Request, record: SourceRecord):
    """
    Manually process a single record (from Tally) through the full microservice pipeline:
    Normalize -> Change Detect -> Persist to Storage.
    """
    req_id = getattr(request.state, "request_id", "")
    record_json = record.model_dump(mode="json")
    normalized = await call_microservice("POST", "normalization", "/normalize", record_json, request_id=req_id)
    change = await call_microservice("POST", "change", "/detect", normalized, request_id=req_id)
    stored = None
    if change.get("event_type") in ("created", "updated"):
        stored = await call_microservice("POST", "storage", "/records", normalized, request_id=req_id)
    return {
        "status": "success",
        "source": record.source.value,
        "normalized": normalized,
        "change_event": change,
        "storage_result": stored
    }

@app.get("/api/records")
async def list_records(request: Request, company_name: Optional[str] = None, source: Optional[str] = None, record_type: Optional[str] = None):
    """Retrieve normalized accounting records from SQLite storage."""
    req_id = getattr(request.state, "request_id", "")
    params = []
    if company_name:
        params.append(f"company_name={company_name}")
    if source:
        params.append(f"source={source}")
    if record_type:
        params.append(f"record_type={record_type}")

    path = "/records" + ("?" + "&".join(params) if params else "")
    return await call_microservice("GET", "storage", path, request_id=req_id)

@app.get("/api/audit")
async def list_audit_events(request: Request, limit: int = 100):
    """Retrieve system audit logs."""
    req_id = getattr(request.state, "request_id", "")
    return await call_microservice("GET", "audit", f"/events?limit={limit}", request_id=req_id)

@app.post("/api/v1/connector/invoices/import")
@app.post("/api/v1/connector/vouchers")
async def import_voucher_gateway(request: Request, payload: dict):
    """Import a voucher/invoice into Tally."""
    req_id = getattr(request.state, "request_id", "")
    return await call_microservice("POST", "tally", "/import/voucher", payload, request_id=req_id)
