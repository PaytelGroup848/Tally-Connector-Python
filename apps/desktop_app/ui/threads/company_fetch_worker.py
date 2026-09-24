import logging
import xml.etree.ElementTree as ET
from PySide6.QtCore import QObject, Signal

logger = logging.getLogger("app.desktop.company_fetch_worker")


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
    
    # On shared servers with multiple Tally instances, if a custom port is set or auto_connect is disabled,
    # strictly query only the configured port to prevent hijacking another user's Tally on port 9000.
    if not auto_connect or configured_port != 9000:
        candidate_ports = [configured_port]
    else:
        candidate_ports = [configured_port, 9000, 9001, 9002, 9003, 9004]
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
            h_res = httpx.post(f"http://{t_host}:{p}/", content=xml_req, headers={"Content-Type": "text/xml"}, timeout=2.5)
            if h_res.status_code == 200 and h_res.text:
                comp_dicts = parse_company_list(h_res.text)
                if comp_dicts:
                    comps = [{"name": c["name"], "path": c.get("path", "C:\\TallyPrime\\Data"), "guid": c.get("guid", "")} for c in comp_dicts if c.get("name")]
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
        t_port = settings.tally_port

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

        # Retrieve real statistics for all discovered companies
        for c in tally_comps:
            c["stats"] = fetch_tally_company_statistics(c.get("name", ""), host=settings.tally_host, port=t_port)

        for c in registered_companies:
            c_name = c.get("name") or c.get("company_name") or c.get("tallyCompanyName") or ""
            tally_match = next((tc for tc in tally_comps if tc.get("name", "").strip().lower() == c_name.strip().lower()), None)
            if tally_match and "stats" in tally_match:
                c["stats"] = tally_match["stats"]
            else:
                c["stats"] = fetch_tally_company_statistics(c_name, host=settings.tally_host, port=t_port)

    except Exception as exc:
        logger.debug(f"Error fetching companies: {exc}")

    return registered_companies, tally_comps, tally_ok, t_port


MASTER_NAMES = {
    "groups", "ledgers", "stock groups", "stock items", "stock categories",
    "voucher types", "units", "currencies", "attendance/production types",
    "employee groups", "employees", "cost centres", "cost categories", "godowns"
}


def fetch_tally_company_statistics(company_name: str, host: str = "127.0.0.1", port: int = 9000, timeout: float = 3.0) -> dict:
    """
    Directly queries Tally Prime's built-in Statistics report for truthful counts
    of total Ledgers, Stock Items, and Vouchers in milliseconds.
    """
    if not company_name:
        return {"ledgers": 0, "vouchers": 0, "items": 0}

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
    Queries local MongoDB or SQLite for total synced ledgers, vouchers, and stock items.
    """
    stats = {"ledgers": 0, "vouchers": 0, "items": 0}
    if not company_name:
        return stats

    clean_name = company_name.strip()
    try:
        from shared.db.mongo_client import get_collection
        c_filter = {"$or": [
            {"company_name": clean_name},
            {"companyName": clean_name},
            {"tallyCompanyName": clean_name},
            {"name": clean_name}
        ]}
        l_count = get_collection("ledgers").count_documents(c_filter)
        v_count = get_collection("vouchers").count_documents(c_filter)
        i_count = get_collection("stock_items").count_documents(c_filter)
        if not i_count:
            i_count = get_collection("items").count_documents(c_filter)

        stats["ledgers"] = l_count
        stats["vouchers"] = v_count
        stats["items"] = i_count
    except Exception as exc:
        logger.debug(f"DB stats lookup notice for '{company_name}': {exc}")

    return stats


class CompanyFetchWorker(QObject):
    """QObject wrapper for backwards compatibility and signal emission."""
    companies_fetched = Signal(list, list, bool, int)

    def __init__(self, parent=None):
        super().__init__(parent)

    def _fetch_real_tally_companies(self, settings) -> tuple:
        return fetch_real_tally_companies(settings)
