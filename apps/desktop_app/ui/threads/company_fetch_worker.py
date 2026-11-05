import logging
import xml.etree.ElementTree as ET
from typing import Optional, List, Dict, Any, Tuple
from PySide6.QtCore import QObject, Signal

logger = logging.getLogger("app.desktop.company_fetch_worker")

# In-memory cache of fetched companies (cleared on logout)
_FETCHED_COMPANIES_CACHE: Dict[str, Any] = {}


def clear_fetched_companies_cache() -> None:
    """Clear in-memory fetched companies cache on logout."""
    _FETCHED_COMPANIES_CACHE.clear()


def fetch_real_tally_companies(settings=None, return_port: bool = False) -> tuple:
    """Fetch active companies list from local Tally extractor or direct XML port."""
    if settings is None:
        from shared.config import get_settings
        settings = get_settings()

    from shared.connection_config import load_connection_config
    cfg = load_connection_config()
    configured_port = int(cfg.get("tally_port") or getattr(settings, "tally_port", 9000) or 9000)
    t_host = str(cfg.get("tally_host") or getattr(settings, "tally_host", "127.0.0.1") or "127.0.0.1").strip()
    if t_host.lower() == "localhost":
        t_host = "127.0.0.1"

    auto_connect = bool(cfg.get("auto_connect", True))
    from shared.connection_config import resolve_active_tally_port
    _, active_resolved_port = resolve_active_tally_port()

    # On shared servers with multiple Tally instances, if auto_connect is disabled,
    # strictly query only the configured port to prevent hijacking another user's Tally.
    if not auto_connect:
        candidate_ports = [configured_port]
    else:
        candidate_ports = [active_resolved_port, configured_port, 9047, 9025, 9000, 9001, 9002, 9003, 9004]
        # Deduplicate while preserving order
        seen = set()
        candidate_ports = [p for p in candidate_ports if not (p in seen or seen.add(p))]

    import socket
    import httpx
    from apps.backend.adapters.tally.request_builder import build_company_list_xml
    from apps.backend.adapters.tally.response_parser import parse_company_list

    xml_req = build_company_list_xml()

    # 1. Primary: Direct Tally Prime Collection query across candidate ports
    for p in candidate_ports:
        # Fast TCP ping
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.6)
            res = sock.connect_ex((t_host, p))
            sock.close()
            if res != 0:
                continue
        except Exception:
            continue

        # Port is open! Query companies with valid TDL collection
        try:
            from shared.tally_lock import get_tally_lock
            with get_tally_lock():
                h_res = httpx.post(f"http://{t_host}:{p}/", content=xml_req, headers={"Content-Type": "text/xml"}, timeout=3.5)
            if h_res.status_code == 200 and h_res.text:
                comp_dicts = parse_company_list(h_res.text)
                if comp_dicts:
                    import uuid
                    comps = []
                    for c in comp_dicts:
                        if not c.get("name"):
                            continue
                        c_n = str(c["name"]).strip()
                        raw_guid = str(c.get("guid") or "").strip()
                        if not raw_guid or len(raw_guid) < 16 or raw_guid.lower() in ("none", "null", "undefined"):
                            raw_guid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"ctrlbooks.tally.{c_n.lower()}"))
                        comps.append({
                            "name": c_n,
                            "path": c.get("path", "C:\\TallyPrime\\Data"),
                            "guid": raw_guid
                        })
                    return (comps, True, p) if return_port else (comps, True)
                # If Tally responded 200 but no company is open:
                return ([], True, p) if return_port else ([], True)
        except Exception as exc:
            logger.debug(f"Direct probe failed on port {p}: {exc}")

    # 2. Try local extractor service if running (development mode)
    try:
        host = getattr(settings, "host", "127.0.0.1")
        res = httpx.get(f"http://{host}:8002/extract/companies", timeout=1.0)
        if res.status_code == 200 and res.json().get("companies"):
            comps = [
                {"name": c.get("name"), "path": c.get("path", "C:\\TallyPrime\\Data"), "guid": c.get("guid", "")}
                for c in res.json()["companies"]
            ]
            return (comps, True, configured_port) if return_port else (comps, True)
    except Exception:
        pass

    return ([], False, configured_port) if return_port else ([], False)


def fetch_all_companies() -> tuple:
    """Fetches both Cloud registered companies and local Tally companies."""
    registered_companies = []
    tally_comps = []
    tally_ok = False
    t_port = 9000

    try:
        from shared.auth.cloud_auth_service import cloud_auth_service
        from shared.config import get_settings
        settings = get_settings()
        from shared.connection_config import load_connection_config
        cfg = load_connection_config()
        configured_port = int(cfg.get("tally_port") or getattr(settings, "tally_port", 9000) or 9000)
        t_port = configured_port
        t_host = str(cfg.get("tally_host") or getattr(settings, "tally_host", "127.0.0.1") or "127.0.0.1").strip()
        if t_host.lower() == "localhost":
            t_host = "127.0.0.1"

        org_id = cloud_auth_service.get_organization_id()
        device_id = cloud_auth_service.device_id
        user_email = (
            cloud_auth_service.current_user.get("email")
            or getattr(cloud_auth_service, "email", "")
            or ""
        ).strip().lower()

        # 1. Cloud API
        if cloud_auth_service.access_token:
            try:
                ok, cloud_c_list = cloud_auth_service.get_cloud_companies()
                if ok and cloud_c_list:
                    registered_companies = cloud_c_list
            except Exception as exc:
                logger.debug(f"Cloud companies API lookup notice: {exc}")

        # 2. Local / Mongo fallback
        if not registered_companies and (org_id or device_id or user_email):
            try:
                from shared.repositories.company_repository import get_all_company_configs
                registered_companies = get_all_company_configs(
                    organization_id=org_id,
                    device_id=device_id,
                    email=user_email
                )
            except Exception as exc:
                logger.debug(f"Local company config lookup notice: {exc}")

        # 3. Real Tally instance
        tally_comps, tally_ok, detected_port = fetch_real_tally_companies(settings, return_port=True)
        if tally_ok and detected_port:
            t_port = detected_port

        # Retrieve statistics for all discovered companies: Check live Tally Prime statistics report first, fallback to DB
        import time
        for c in tally_comps:
            c_name = c.get("name", "")
            t_s = fetch_tally_company_statistics(c_name, host=t_host, port=t_port, timeout=5.0)
            if t_s and any(t_s.values()):
                c["stats"] = t_s
            else:
                c["stats"] = fetch_db_company_statistics(c_name)
            time.sleep(0.04)

        for c in registered_companies:
            c_name = c.get("name") or c.get("company_name") or c.get("tallyCompanyName") or ""
            tally_match = next((tc for tc in tally_comps if tc.get("name", "").strip().lower() == c_name.strip().lower()), None)
            if tally_match and "stats" in tally_match:
                c["stats"] = tally_match["stats"]
            else:
                t_s = fetch_tally_company_statistics(c_name, host=t_host, port=t_port, timeout=5.0)
                if t_s and any(t_s.values()):
                    c["stats"] = t_s
                else:
                    c["stats"] = fetch_db_company_statistics(c_name)
                time.sleep(0.04)

    except Exception as exc:
        logger.debug(f"Error fetching companies: {exc}")

    return registered_companies, tally_comps, tally_ok, t_port


MASTER_NAMES = {
    "groups", "ledgers", "stock groups", "stock items", "stock categories",
    "voucher types", "units", "currencies", "attendance/production types",
    "employee groups", "employees", "cost centres", "cost categories", "godowns"
}


def fetch_tally_company_statistics(company_name: str, host: str = "127.0.0.1", port: Optional[int] = None, timeout: float = 5.0) -> dict:
    """
    Directly queries Tally Prime's built-in Statistics report for truthful counts
    of total Ledgers, Stock Items, and Vouchers in milliseconds.
    Guaranteed thread-safe and non-blocking with TALLY_LOCK to avoid memory access violations.
    """
    if not company_name:
        return {"ledgers": 0, "vouchers": 0, "items": 0}

    if port is None or port == 9000:
        try:
            from shared.connection_config import load_connection_config
            cfg = load_connection_config()
            cfg_p = cfg.get("tally_port")
            if cfg_p:
                port = int(cfg_p)
            cfg_h = cfg.get("tally_host")
            if cfg_h and host == "127.0.0.1":
                host = str(cfg_h).strip()
        except Exception:
            pass
    if port is None:
        port = 9000

    clean_comp = (
        company_name.strip()
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    stat_xml = (
        f"<ENVELOPE><HEADER><TALLYREQUEST>Export Data</TALLYREQUEST></HEADER>"
        f"<BODY><EXPORTDATA><REQUESTDESC><REPORTNAME>Statistics</REPORTNAME>"
        f"<STATICVARIABLES><SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>"
        f"<SVCURRENTCOMPANY>{clean_comp}</SVCURRENTCOMPANY>"
        f"</STATICVARIABLES></REQUESTDESC></EXPORTDATA></BODY></ENVELOPE>"
    )

    try:
        import httpx
        from shared.tally_lock import get_tally_lock
        with get_tally_lock():
            res = httpx.post(f"http://{host}:{port}/", content=stat_xml, timeout=timeout)
        if res.status_code == 200 and res.text:
            root = ET.fromstring(res.text)
            stat_names = [e.text or "" for e in root.findall(".//STATNAME")]
            stat_vals = []
            for val_tag in root.findall(".//STATVALUE"):
                direct = val_tag.findtext("STATDIRECT") or "0"
                try:
                    stat_vals.append(int(direct.strip().replace(",", "")))
                except ValueError:
                    stat_vals.append(0)

            total_ledgers = 0
            total_items = 0
            total_vouchers = 0

            for name, val in zip(stat_names, stat_vals):
                n_low = name.strip().lower()
                if n_low == "ledgers":
                    total_ledgers = val
                elif n_low in ("stock items", "stock item"):
                    total_items = val
                elif n_low in MASTER_NAMES:
                    continue
                else:
                    total_vouchers += val

            return {
                "ledgers": total_ledgers,
                "vouchers": total_vouchers,
                "items": total_items
            }
    except Exception as exc:
        logger.debug(f"Tally stats fetch error for '{company_name}': {exc}")

    # Fallback to local DB if Tally query didn't return
    return fetch_db_company_statistics(company_name)


def fetch_db_company_statistics(company_name: str) -> dict:
    """
    Retrieves synced statistics from local checkpoint JSON (pure cloud mode).
    """
    stats = {"ledgers": 0, "vouchers": 0, "items": 0}
    if not company_name:
        return stats

    clean_name = company_name.strip()
    try:
        from shared.cloud.helpers import get_local_checkpoint
        cp = get_local_checkpoint(clean_name)
        if cp and isinstance(cp.get("stats"), dict):
            c_stats = cp["stats"]
            stats["ledgers"] = int(c_stats.get("ledgers", 0) or 0)
            stats["vouchers"] = int(c_stats.get("vouchers", 0) or 0)
            stats["items"] = int(c_stats.get("items", 0) or 0)
            return stats
    except Exception as exc:
        logger.debug(f"Local checkpoint stats lookup notice for '{company_name}': {exc}")

    return stats


class CompanyFetchWorker(QObject):
    """QObject wrapper for backwards compatibility and signal emission."""
    companies_fetched = Signal(list, list, bool, int)

    def __init__(self, parent=None):
        super().__init__(parent)

    def _fetch_real_tally_companies(self, settings) -> tuple:
        return fetch_real_tally_companies(settings)


__all__ = [
    "fetch_real_tally_companies",
    "fetch_all_companies",
    "fetch_tally_company_statistics",
    "fetch_db_company_statistics",
    "CompanyFetchWorker",
    "_FETCHED_COMPANIES_CACHE",
    "clear_fetched_companies_cache",
]
