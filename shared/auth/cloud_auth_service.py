import httpx
import uuid
import json
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime, timezone

from shared.config import get_settings
from shared.db.mongo_client import get_collection
from shared.logging_config import get_logger

logger = get_logger("app.auth.cloud")

def _get_writable_data_file(filename: str) -> Path:
    """Returns a writable Path for app data storage across all environments."""
    local_path = Path("data") / filename
    try:
        local_path.parent.mkdir(parents=True, exist_ok=True)
        test_file = local_path.parent / ".perm_check"
        test_file.touch(exist_ok=True)
        test_file.unlink(missing_ok=True)
        return local_path
    except Exception:
        pass

    import os
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

AUTH_SESSION_FILE = _get_writable_data_file("auth_session.json")
DEVICE_CONFIG_FILE = _get_writable_data_file("device_id.json")

def get_or_create_device_id() -> str:
    """Returns persistent unique hardware device identifier."""
    target_file = DEVICE_CONFIG_FILE
    if not target_file.exists() and Path("data/device_id.json").exists():
        target_file = Path("data/device_id.json")

    if target_file.exists():
        try:
            with open(target_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                dev_id = data.get("deviceId") or data.get("device_id")
                if dev_id:
                    return str(dev_id)
        except Exception:
            pass

    new_device_id = str(uuid.uuid4())
    try:
        DEVICE_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(DEVICE_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({"deviceId": new_device_id, "created_at": datetime.now(timezone.utc).isoformat()}, f, indent=2)
    except Exception as exc:
        logger.warning(f"Could not persist device ID file: {exc}")

    return new_device_id

def format_tally_date(d_str: Optional[str]) -> str:
    """Formats Tally date string (YYYYMMDD, DD-Mon-YYYY, etc.) to YYYY-MM-DD."""
    if not d_str or not str(d_str).strip():
        return "2022-04-01"
    s = str(d_str).strip()
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    if len(s) == 10 and s[4] == '-' and s[7] == '-':
        return s
    for fmt in ("%d-%b-%Y", "%d-%b-%y", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except Exception:
            pass
    return s

def classify_ledger_type(parent: Optional[str], raw_type: Optional[str] = None) -> str:
    """Classifies ledger type into CUSTOMER, VENDOR, BANK, CASH, EXPENSE, INCOME, TAX, ASSET, LIABILITY, or GENERAL."""
    if raw_type and str(raw_type).strip():
        return str(raw_type).strip().upper()
    if not parent:
        return "GENERAL"
    p = str(parent).strip().lower()
    if "debtor" in p or "customer" in p:
        return "CUSTOMER"
    elif "creditor" in p or "supplier" in p or "vendor" in p:
        return "VENDOR"
    elif "bank" in p:
        return "BANK"
    elif "cash" in p:
        return "CASH"
    elif "sales" in p:
        return "SALES"
    elif "purchase" in p:
        return "PURCHASE"
    elif "expense" in p:
        return "EXPENSE"
    elif "income" in p or "revenue" in p:
        return "INCOME"
    elif "tax" in p or "duties" in p or "gst" in p or "vat" in p or "tds" in p:
        return "TAX"
    elif "asset" in p or "stock" in p or "deposit" in p or "investment" in p:
        return "ASSET"
    elif "liabilit" in p or "loan" in p or "capital" in p or "provision" in p:
        return "LIABILITY"
    return "GENERAL"

class CloudAuthService:
    def __init__(self, base_url: Optional[str] = None):
        settings = get_settings()
        self.base_url = (base_url or settings.cloud_api_base_url).rstrip("/")
        self._device_id = get_or_create_device_id()

        self.access_token: Optional[str] = None
        self.refresh_token_val: Optional[str] = None
        self.current_user: Dict[str, Any] = {}
        self._limits = httpx.Limits(max_keepalive_connections=20, max_connections=50, keepalive_expiry=30.0)
        self._client: Optional[httpx.Client] = None
        self.load_session()

    def _get_client(self, timeout: float = 30.0) -> httpx.Client:
        if self._client is None or self._client.is_closed:
            self._client = httpx.Client(timeout=httpx.Timeout(timeout, connect=10.0), limits=self._limits)
        return self._client

    def close(self) -> None:
        if self._client and not self._client.is_closed:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def load_session(self) -> None:
       
        target_file = AUTH_SESSION_FILE
        if not target_file.exists() and Path("data/auth_session.json").exists():
            target_file = Path("data/auth_session.json")

        if target_file.exists():
            try:
                with open(target_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.access_token = data.get("accessToken") or data.get("access_token")
                    self.refresh_token_val = data.get("refreshToken") or data.get("refresh_token")
                    self.current_user = data.get("user") or {}
            except Exception as exc:
                logger.warning(f"Error loading auth session: {exc}")

    def save_session(self, access_token: str, refresh_token: Optional[str] = None, user: Optional[Dict[str, Any]] = None) -> None:
        """Persists access token and user info to disk and memory."""
        self.access_token = access_token
        if refresh_token:
            self.refresh_token_val = refresh_token
        if user:
            self.current_user = user

        payload = {
            "accessToken": self.access_token,
            "refreshToken": self.refresh_token_val,
            "user": self.current_user,
            "deviceId": self.device_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

        try:
            AUTH_SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(AUTH_SESSION_FILE, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
        except Exception as exc:
            logger.error(f"Error saving auth session file: {exc}")

        if user:
            self.sync_user_to_mongodb(user)

    def get_organization_id(self) -> Optional[str]:
        """Extracts organizationId from current_user, connector, or session."""
        if not self.current_user or not isinstance(self.current_user, dict):
            return None
        org_id = (
            self.current_user.get("organizationId")
            or self.current_user.get("organization_id")
            or self.current_user.get("connector", {}).get("organizationId")
            or self.current_user.get("connector", {}).get("organization_id")
        )
        return str(org_id) if org_id else None

    @property
    def organization_id(self) -> Optional[str]:
        return self.get_organization_id()

    def get_email(self) -> str:
        """Extracts user email from current_user, connector, or local profile."""
        if isinstance(self.current_user, dict):
            email = (
                self.current_user.get("email")
                or self.current_user.get("userEmail")
                or self.current_user.get("connector", {}).get("email")
            )
            if email:
                return str(email).strip().lower()
        try:
            p_file = Path("data/profile.json")
            if not p_file.exists():
                p_file = _get_writable_data_file("profile.json")
            if p_file.exists():
                with open(p_file, "r", encoding="utf-8") as f:
                    p_data = json.load(f)
                    if p_data.get("email"):
                        return str(p_data["email"]).strip().lower()
        except Exception:
            pass
        return ""

    @property
    def email(self) -> str:
        return self.get_email()

    def get_device_id(self) -> str:
        """Extracts device identifier from connector session or hardware file."""
        if isinstance(self.current_user, dict):
            conn = self.current_user.get("connector") or {}
            d_id = conn.get("deviceId") or conn.get("device_id")
            if d_id:
                return str(d_id)
        if getattr(self, "_device_id", None):
            return self._device_id
        return get_or_create_device_id()

    @property
    def device_id(self) -> str:
        return self.get_device_id()

    @device_id.setter
    def device_id(self, val: str):
        self._device_id = val

    def sync_user_to_mongodb(self, user_data: Dict[str, Any]) -> None:
        try:
            col = get_collection("user_profile")

            connector_data = user_data.get("connector") or {}
            plan_data = user_data.get("plan") or {}
            sub_data = user_data.get("subscription") or {}
            permissions = user_data.get("permissions") or []

            user_email = (
                user_data.get("email")
                or getattr(self, "email", "")
                or (self.current_user.get("email") if isinstance(self.current_user, dict) else "")
                or ""
            ).strip().lower()

            profile_key = user_email if user_email else "current_user"

            # Check existing doc to preserve user-entered profile fields (name, mobile, location)
            existing_doc = col.find_one({"profile_id": profile_key})
            if not existing_doc and profile_key != "current_user":
                existing_doc = col.find_one({"profile_id": "current_user"})

            # Only overwrite name/mobile if new value from cloud is actually non-empty
            incoming_name = (user_data.get("name") or user_data.get("fullName") or "").strip()
            incoming_mobile = (user_data.get("mobile") or user_data.get("phone") or "").strip()

            final_name = incoming_name or (existing_doc.get("name") if existing_doc else "") or ""
            final_mobile = incoming_mobile or (existing_doc.get("mobile") if existing_doc else "") or ""
            final_postal_code = (existing_doc.get("postal_code") if existing_doc else "") or ""
            final_country_code = (existing_doc.get("country_code") if existing_doc else "🇮🇳 IN +91") or "🇮🇳 IN +91"

            org_id = self.get_organization_id()

            profile_doc = {
                "profile_id": profile_key,
                "user_id": str(user_data.get("id", user_data.get("_id", connector_data.get("id", "")))),
                "name": final_name,
                "email": user_email or (existing_doc.get("email") if existing_doc else ""),
                "mobile": final_mobile,
                "postal_code": final_postal_code,
                "country_code": final_country_code,
                "role": user_data.get("role", "USER"),
                "status": connector_data.get("status", user_data.get("status", "ACTIVE")),
                "organization_id": org_id,
                "organizationId": org_id,
                "connector": connector_data,
                "plan": plan_data,
                "subscription": sub_data,
                "permissions": permissions,
                "company_id": user_data.get("companyId", user_data.get("company_id")),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "raw": user_data,
            }
            col.update_one({"profile_id": profile_key}, {"$set": profile_doc}, upsert=True)
            if profile_key != "current_user":
                col.update_one({"profile_id": "current_user"}, {"$set": profile_doc}, upsert=True)
            logger.info(f"Synchronized user profile '{profile_key}' into MongoDB Atlas without wiping user details.")
        except Exception as exc:
            logger.error(f"MongoDB profile sync error: {exc}")

    def send_otp(self, email: str) -> Tuple[bool, str]:
       
        clean_email = email.strip().lower()
        url = f"{self.base_url}/auth/send-otp"
        logger.info(f"Calling Cloud Auth send-otp for: {clean_email}")

        try:
            client = self._get_client(10.0)
            res = client.post(url, json={"email": clean_email})
            data = res.json() if res.text else {}

            if res.status_code == 200 or data.get("success") is True:
                msg = data.get("message", "OTP sent successfully to your email.")
                return True, msg
            else:
                err_msg = data.get("message") or "Failed to send OTP. Please verify email."
                if "errors" in data and isinstance(data["errors"], list) and data["errors"]:
                    err_msg = data["errors"][0].get("message", err_msg)
                return False, err_msg

        except Exception as exc:
            logger.error(f"Error calling send-otp: {exc}")
            return False, f"Connection error contacting authentication server: {exc}"

    def verify_otp(self, email: str, otp: str) -> Tuple[bool, str, Dict[str, Any]]:
       
        clean_email = email.strip().lower()
        clean_otp = str(otp).strip()
        url = f"{self.base_url}/auth/verify-otp"
        import platform
        import os
        device_name = os.getenv("COMPUTERNAME", platform.node()) or "Desktop-Connector"

        device_id = self.device_id
        payload = {
            "email": clean_email,
            "otp": clean_otp,
            "deviceId": device_id,
            "deviceName": device_name,
            "connectorVersion": "1.0.0",
        }
        logger.info(f"Calling Cloud Auth verify-otp for {clean_email} (deviceId: {device_id}, deviceName: {device_name})")

        try:
            client = self._get_client(12.0)
            res = client.post(url, json=payload)
            data = res.json() if res.text else {}

            if res.status_code == 200 or data.get("success") is True:
                resp_data = data.get("data") or data
                access_token = resp_data.get("accessToken") or resp_data.get("token") or ""
                refresh_token = resp_data.get("refreshToken", "")
                user = resp_data.get("user") or {}

                if not user and "email" in resp_data:
                    user = resp_data

                self.save_session(access_token, refresh_token, user)
                return True, data.get("message", "Login successful!"), user
            else:
                err_msg = data.get("message") or "Invalid OTP or verification failed."
                if "errors" in data and isinstance(data["errors"], list) and data["errors"]:
                    err_msg = data["errors"][0].get("message", err_msg)
                return False, err_msg, {}

        except Exception as exc:
            logger.error(f"Error calling verify-otp: {exc}")
            return False, f"Connection error during OTP verification: {exc}", {}

    def refresh_token(self) -> Tuple[bool, str]:
       
        if not self.refresh_token_val:
            return False, "No refresh token available."

        url = f"{self.base_url}/auth/refresh"
        payload = {"refreshToken": self.refresh_token_val}

        try:
            client = self._get_client(10.0)
            res = client.post(url, json=payload)
            data = res.json() if res.text else {}

            if res.status_code == 200 or data.get("success") is True:
                resp_data = data.get("data") or data
                new_access_token = str(resp_data.get("accessToken") or resp_data.get("token") or "")
                new_refresh_token = str(resp_data.get("refreshToken") or self.refresh_token_val or "")
                if new_access_token:
                    self.save_session(new_access_token, new_refresh_token, self.current_user)
                    return True, "Token refreshed successfully."
                return False, "No access token in refresh response."
            else:
                return False, data.get("message", "Token refresh failed.")
        except Exception as exc:
            return False, f"Token refresh error: {exc}"

    def logout(self) -> Tuple[bool, str]:
    
        url = f"{self.base_url}/auth/logout"
        headers = {}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"

        try:
            client = self._get_client(8.0)
            res = client.post(url, headers=headers)
            res.json() if res.text else {}
        except Exception:
            pass

        self.access_token = None
        self.refresh_token_val = None
        self.current_user = {}
        if AUTH_SESSION_FILE.exists():
            try:
                AUTH_SESSION_FILE.unlink()
            except Exception:
                pass

        return True, "Logged out successfully."

    def get_me(self) -> Tuple[bool, Dict[str, Any]]:
        
        if not self.access_token:
            return False, {}

        url = f"{self.base_url}/me"
        headers = {"Authorization": f"Bearer {self.access_token}"}

        try:
            client = self._get_client(10.0)
            res = client.get(url, headers=headers)
            data = res.json() if res.text else {}

            if res.status_code == 401 and self.refresh_token_val:
                refreshed, _ = self.refresh_token()
                if refreshed and self.access_token:
                    headers["Authorization"] = f"Bearer {self.access_token}"
                    res = client.get(url, headers=headers)
                    data = res.json() if res.text else {}

            if res.status_code == 200 or data.get("success") is True:
                user_data = data.get("data") or data
                self.current_user = user_data
                self.sync_user_to_mongodb(user_data)
                return True, user_data
            else:
                return False, data
        except Exception as exc:
            logger.error(f"Error fetching /me profile: {exc}")
            return False, {}

    def link_company(self, company_name: str, company_guid: str = "", financial_year: str = "") -> Tuple[bool, str, Dict[str, Any]]:
        """Calls Cloud Link Company endpoint (/company/link)."""
        if not self.access_token:
            return False, "Not authenticated. Please login first.", {}

        url = f"{self.base_url}/company/link"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        payload = {
            "tallyCompanyName": company_name,
            "tallyCompanyGuid": company_guid or "",
        }
        logger.info(f"Calling Cloud Link Company for '{company_name}'...")

        try:
            client = self._get_client(12.0)
            res = client.post(url, json=payload, headers=headers)
            data = res.json() if res.text else {}

            if res.status_code == 401 and self.refresh_token_val:
                refreshed, _ = self.refresh_token()
                if refreshed and self.access_token:
                    headers["Authorization"] = f"Bearer {self.access_token}"
                    res = client.post(url, json=payload, headers=headers)
                    data = res.json() if res.text else {}

            if res.status_code == 200 or data.get("success") is True:
                resp_data = data.get("data") or data
                comp_obj = resp_data.get("company") if isinstance(resp_data, dict) and "company" in resp_data else resp_data
                comp_id_val = None
                if isinstance(comp_obj, dict):
                    comp_id_val = comp_obj.get("id") or comp_obj.get("_id")
                try:
                    col = get_collection("companies")
                    org_id = self.get_organization_id()
                    user_email = (
                        self.current_user.get("email")
                        or getattr(self, "email", "")
                        or ""
                    ).strip().lower()

                    set_data = {
                        "company_name": company_name,
                        "name": company_name,
                        "company_guid": company_guid,
                        "cloud_company_id": comp_id_val,
                        "deviceId": self.device_id,
                        "device_id": self.device_id,
                        "financial_year_from": financial_year or "01-Apr-2025",
                        "cloud_linked": True,
                        "is_sync_enabled": True,
                        "status": "CONNECTED",
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }
                    if org_id:
                        set_data["organizationId"] = org_id
                        set_data["organization_id"] = org_id
                    if user_email:
                        set_data["email"] = user_email

                    col.update_one(
                        {"company_name": company_name},
                        {"$set": set_data},
                        upsert=True
                    )
                except Exception as e:
                    logger.error(f"Error persisting linked company to MongoDB: {e}")

                res_comp = comp_obj if isinstance(comp_obj, dict) else {}
                return True, str(data.get("message", "Company linked to cloud successfully!")), res_comp
            else:
                err_msg = self._extract_error_message(res, data, "Failed to link company")
                return False, err_msg, {}
        except Exception as exc:
            logger.error(f"Error calling link company: {exc}")
            return False, f"Connection error linking company: {exc}", {}

    def get_cloud_companies(self) -> Tuple[bool, List[Dict[str, Any]]]:
        """Fetches linked companies from Cloud Server."""
        if not self.access_token:
            return False, []

        url = f"{self.base_url}/companies"
        headers = {"Authorization": f"Bearer {self.access_token}"}

        try:
            client = self._get_client(12.0)
            res = client.get(url, headers=headers)
            data = res.json() if res.text else {}

            if res.status_code == 401 and self.refresh_token_val:
                refreshed, _ = self.refresh_token()
                if refreshed and self.access_token:
                    headers["Authorization"] = f"Bearer {self.access_token}"
                    res = client.get(url, headers=headers)
                    data = res.json() if res.text else {}

            if res.status_code == 200 or data.get("success") is True:
                data_obj = data.get("data")
                if isinstance(data_obj, list):
                    companies_list = data_obj
                elif isinstance(data_obj, dict):
                    companies_list = data_obj.get("companies") or []
                else:
                    companies_list = data.get("companies") or []

                if isinstance(companies_list, list):

                    try:
                        col = get_collection("companies")
                        for c in companies_list:
                            c_name = c.get("tallyCompanyName") or c.get("companyName") or c.get("name")
                            if c_name:
                                col.update_one(
                                    {"company_name": c_name},
                                    {"$set": {
                                        "company_name": c_name,
                                        "company_guid": c.get("tallyCompanyGuid") or c.get("companyGuid"),
                                        "cloud_company_id": c.get("id") or c.get("_id"),
                                        "cloud_linked": True,
                                        "is_sync_enabled": c.get("isSyncEnabled", True),
                                        "status": c.get("status", "CONNECTED"),
                                        "updated_at": datetime.now(timezone.utc).isoformat()
                                    }},
                                    upsert=True
                                )
                    except Exception as e:
                        logger.error(f"Error syncing cloud companies to MongoDB: {e}")

                    return True, companies_list
                return True, []
            else:
                return False, []
        except Exception as exc:
            logger.error(f"Error fetching cloud companies: {exc}")
            return False, []

    def _extract_error_message(self, res: httpx.Response, data: Dict[str, Any], default_msg: str) -> str:
        """Extracts clear English error message from response or JSON payload."""
        if not data and res.text:
            return f"{default_msg} (HTTP {res.status_code}): {res.text[:200]}"
        detail = data.get("detail")
        if detail:
            if isinstance(detail, list):
                msgs = [f"{item.get('loc', ['field'])[-1]}: {item.get('msg', 'invalid')}" for item in detail if isinstance(item, dict)]
                if msgs:
                    return f"{default_msg}: " + "; ".join(msgs)
            elif isinstance(detail, str):
                return detail
        if "errors" in data and isinstance(data["errors"], list) and data["errors"]:
            msgs = [f"{item.get('field', 'field')}: {item.get('message', 'invalid')}" for item in data["errors"] if isinstance(item, dict)]
            if msgs:
                return f"{default_msg}: " + "; ".join(msgs)
        if data.get("message"):
            return str(data["message"])
        if data.get("error"):
            return str(data["error"])
        return f"{default_msg} (HTTP {res.status_code})"

    def sync_start(
        self,
        company_name: str,
        company_guid: str = "",
        sync_type: str = "INCREMENTAL",
        total_records: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
        company_id: Optional[str] = None
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """Calls Cloud Sync Start endpoint (/sync/start)."""
        if not self.access_token:
            return False, "Not authenticated. Please login first.", {}

        target_cid = company_id
        if not target_cid or len(str(target_cid)) < 12:
            ok_c, c_list = self.get_cloud_companies()
            if ok_c and c_list:
                for c in c_list:
                    c_n = c.get("tallyCompanyName") or c.get("companyName") or c.get("name") or ""
                    if c_n.strip().lower() == company_name.strip().lower():
                        target_cid = c.get("id") or c.get("_id")
                        break

        if not target_cid or len(str(target_cid)) < 12:
            link_ok, _, link_data = self.link_company(company_name, company_guid)
            if link_ok and link_data:
                target_cid = link_data.get("id") or link_data.get("_id")

        if not target_cid:
            target_cid = company_guid or company_name

        if target_cid and len(str(target_cid)) >= 8:
            try:
                col = get_collection("companies")
                col.update_one(
                    {"$or": [{"company_name": company_name}, {"name": company_name}, {"tallyCompanyName": company_name}]},
                    {"$set": {"cloud_company_id": str(target_cid)}},
                    upsert=True
                )
            except Exception:
                pass

        s_type = "INITIAL" if sync_type.upper() in ("INITIAL", "FULL") else "INCREMENTAL"

        url = f"{self.base_url}/sync/start"
        headers = {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}
        payload = {
            "companyId": str(target_cid),
            "type": s_type
        }
        logger.info(f"Calling Cloud Sync Start for '{company_name}' ({s_type}, companyId: {target_cid})")

        try:
            client = self._get_client(15.0)
            res = client.post(url, json=payload, headers=headers)
            data = res.json() if res.text else {}

            if res.status_code == 401 and self.refresh_token_val:
                refreshed, _ = self.refresh_token()
                if refreshed and self.access_token:
                    headers["Authorization"] = f"Bearer {self.access_token}"
                    res = client.post(url, json=payload, headers=headers)
                    data = res.json() if res.text else {}

            if res.status_code == 200 or data.get("success") is True:
                resp_data = data.get("data") or data
                msg = data.get("message", "Cloud sync session started successfully.")
                return True, msg, resp_data
            else:
                err_msg = self._extract_error_message(res, data, "Failed to start sync session")
                logger.warning(f"Cloud sync/start HTTP {res.status_code}: {err_msg}")
                return False, err_msg, {}
        except Exception as exc:
            logger.error(f"Error calling sync/start: {exc}")
            return False, f"Connection error starting sync session: {exc}", {}

    def sync_batch(
        self,
        sync_id: str,
        company_name: str,
        entity_type: str,
        items: list[Dict[str, Any]],
        batch_number: int = 1,
        is_last_batch: bool = False
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """Calls Cloud Sync Batch endpoint (/sync/batch)."""
        if not self.access_token:
            return False, "Not authenticated. Please login first.", {}

        url = f"{self.base_url}/sync/batch"
        headers = {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}
        
        u_type = str(entity_type).upper()
        if "LEDGER" in u_type:
            norm_entity = "LEDGER"
        elif "STOCK" in u_type:
            norm_entity = "STOCK"
        elif "SUPPLIER" in u_type or "VENDOR" in u_type:
            norm_entity = "SUPPLIER"
        elif "CUSTOMER" in u_type:
            norm_entity = "CUSTOMER"
        else:
            norm_entity = "VOUCHER"

        records_to_send = []
        if norm_entity == "STOCK":
            for r in items:
                if not isinstance(r, dict):
                    continue
                t_ext_id = r.get("tallyExternalId") or r.get("guid") or r.get("name") or ""
                item_name = r.get("itemName") or r.get("name") or ""
                item_ext_id = r.get("itemTallyExternalId") or r.get("guid") or t_ext_id
                godown_val = r.get("godown") or "Main Location"
                try:
                    qty = float(r.get("quantity", 0.0) or r.get("closingBalance", 0.0) or 0.0)
                except (ValueError, TypeError):
                    qty = 0.0
                try:
                    rate = float(r.get("rate", 0.0) or r.get("closingRate", 0.0) or 0.0)
                except (ValueError, TypeError):
                    rate = 0.0
                try:
                    val = float(r.get("value", 0.0) or r.get("closingValue", 0.0) or 0.0)
                except (ValueError, TypeError):
                    val = 0.0
                if val == 0.0 and qty != 0.0 and rate != 0.0:
                    val = round(qty * rate, 2)

                records_to_send.append({
                    "tallyExternalId": str(t_ext_id),
                    "itemName": str(item_name),
                    "itemTallyExternalId": str(item_ext_id),
                    "godown": str(godown_val),
                    "quantity": qty,
                    "rate": rate,
                    "value": val
                })
        elif norm_entity == "SUPPLIER":
            for r in items:
                if not isinstance(r, dict):
                    continue
                t_ext_id = r.get("tallyExternalId") or r.get("guid") or r.get("name") or ""
                name_val = r.get("name") or ""
                parent_val = r.get("parent") or "Sundry Creditors"
                group_val = r.get("group") or parent_val
                gstin_val = r.get("gstin") or ""
                email_val = r.get("email") or ""
                phone_val = r.get("phone") or ""
                address_val = r.get("address") or ""
                alt_id = int(r.get("alterId", 0) or r.get("alterid", 0) or 0)
                try:
                    op_bal = float(r.get("openingBalance", 0.0) or 0.0)
                except (ValueError, TypeError):
                    op_bal = 0.0
                try:
                    c_bal = float(r.get("closingBalance", 0.0) or 0.0)
                except (ValueError, TypeError):
                    c_bal = 0.0

                records_to_send.append({
                    "tallyExternalId": str(t_ext_id),
                    "name": str(name_val),
                    "parent": str(parent_val),
                    "group": str(group_val),
                    "gstin": str(gstin_val),
                    "email": str(email_val),
                    "phone": str(phone_val),
                    "address": str(address_val),
                    "openingBalance": op_bal,
                    "closingBalance": c_bal,
                    "ledgerType": "LIABILITY",
                    "alterId": alt_id
                })
        elif norm_entity == "LEDGER":
            for r in items:
                if not isinstance(r, dict):
                    continue
                raw_val = r.get("raw")
                raw_dict: Dict[str, Any] = dict(raw_val) if isinstance(raw_val, dict) else {}
                
                c_bal = r.get("closingBalance")
                if c_bal is None:
                    c_bal = r.get("closing_balance")
                if c_bal is None:
                    c_bal = raw_dict.get("closing_balance", raw_dict.get("closingbalance"))
                if c_bal is None:
                    c_bal = 0.0

                op_bal = r.get("openingBalance")
                if op_bal is None:
                    op_bal = r.get("opening_balance")
                if op_bal is None:
                    op_bal = raw_dict.get("opening_balance", raw_dict.get("openingbalance", 0.0))
                if op_bal is None:
                    op_bal = 0.0

                parent_val = r.get("parent") or raw_dict.get("parent") or ""
                group_val = r.get("group") or parent_val
                raw_ltype = r.get("ledgerType") or r.get("ledger_type") or raw_dict.get("ledger_type") or raw_dict.get("ledgerclassification")
                comp_ltype = classify_ledger_type(parent_val, raw_ltype)

                gstin_val = r.get("gstin") or raw_dict.get("gstin") or raw_dict.get("partygstin")
                t_ext_id = r.get("tallyExternalId") or r.get("guid") or raw_dict.get("guid") or r.get("name") or raw_dict.get("name") or ""
                name_val = r.get("name") or raw_dict.get("name") or ""

                records_to_send.append({
                    "tallyExternalId": str(t_ext_id),
                    "name": str(name_val),
                    "parent": str(parent_val),
                    "group": str(group_val),
                    "ledgerType": comp_ltype,
                    "openingBalance": float(op_bal),
                    "closingBalance": float(c_bal),
                    "gstin": str(gstin_val) if gstin_val else None
                })
        elif norm_entity == "VOUCHER":
            for r in items:
                if not isinstance(r, dict):
                    continue
                raw_val = r.get("raw")
                raw_dict: Dict[str, Any] = dict(raw_val) if isinstance(raw_val, dict) else {}
                
                v_num = str(r.get("voucherNumber") or r.get("voucher_number") or raw_dict.get("name") or raw_dict.get("vouchernumber") or "")
                v_type = str(r.get("voucherType") or r.get("voucher_type") or raw_dict.get("parent") or raw_dict.get("vouchertypename") or "Sales")
                v_party = str(r.get("partyLedger") or r.get("party_ledger") or raw_dict.get("party") or raw_dict.get("partyledgername") or "Cash")
                
                raw_amt = r.get("amount")
                if raw_amt is None:
                    raw_amt = raw_dict.get("amount", raw_dict.get("closing_balance", raw_dict.get("closingbalance", 0.0)))
                try:
                    amt_val = abs(float(raw_amt)) if raw_amt is not None else 0.0
                except (ValueError, TypeError):
                    amt_val = 0.0

                d_val = r.get("date") or raw_dict.get("date") or r.get("effectiveDate")
                formatted_date = format_tally_date(d_val) or "2023-04-01"
                v_narr = str(r.get("narration") or raw_dict.get("narration") or "")
                t_ext_id = str(r.get("voucherId") or r.get("tallyExternalId") or r.get("guid") or raw_dict.get("guid") or v_num)

                raw_obj = {
                    "voucherId": str(t_ext_id),
                    "name": str(raw_dict.get("name") or v_num),
                    "parent": str(raw_dict.get("parent") or v_type),
                    "party": str(raw_dict.get("party") or v_party),
                    "date": str(formatted_date),
                    "alterid": int(raw_dict.get("alterid") or r.get("alter_id") or r.get("alterId") or 0)
                }

                records_to_send.append({
                    "voucherId": str(t_ext_id),
                    "tallyExternalId": str(t_ext_id),
                    "voucherNumber": str(v_num),
                    "voucherType": str(v_type),
                    "date": str(formatted_date),
                    "amount": float(amt_val),
                    "partyLedger": str(v_party),
                    "narration": str(v_narr),
                    "lines": r.get("lines") or r.get("ledgerEntries") or [],
                    "billAllocations": r.get("billAllocations") or [],
                    "raw": raw_obj
                })
        else:
            records_to_send = items

        payload = {
            "syncJobId": sync_id,
            "batchNumber": batch_number,
            "entityType": norm_entity,
            "records": records_to_send,
            "isLastBatch": is_last_batch
        }
        logger.info(f"Calling Cloud Sync Batch #{batch_number} for '{company_name}' ({norm_entity}: {len(records_to_send)} items)")

        try:
            client = self._get_client(30.0)
            res = client.post(url, json=payload, headers=headers)
            data = res.json() if res.text else {}

            if res.status_code == 401 and self.refresh_token_val:
                refreshed, _ = self.refresh_token()
                if refreshed and self.access_token:
                    headers["Authorization"] = f"Bearer {self.access_token}"
                    res = client.post(url, json=payload, headers=headers)
                    data = res.json() if res.text else {}

            if res.status_code == 200 or data.get("success") is True:
                resp_data = data.get("data") or data
                msg = data.get("message", f"Batch #{batch_number} synced successfully.")
                return True, msg, resp_data
            else:
                err_msg = self._extract_error_message(res, data, f"Failed to sync batch #{batch_number}")
                logger.warning(f"Cloud sync/batch HTTP {res.status_code}: {err_msg}")
                return False, err_msg, {}
        except Exception as exc:
            return False, f"Connection error sending sync batch: {exc}", {}

    @property
    def is_authenticated(self) -> bool:
        """Returns True if a valid access token is present."""
        return bool(self.access_token)

    def sync_complete(
        self,
        sync_id: str,
        company_name: str = "",
        status: str = "COMPLETED",
        total_synced: int = 0,
        last_alter_id: int = 0,
        summary: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """Calls Cloud Sync Complete endpoint (/sync/complete)."""
        if not self.access_token:
            return False, "Not authenticated. Please login first.", {}

        url = f"{self.base_url}/sync/complete"
        headers = {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}
        payload = {
            "syncJobId": sync_id,
            "status": status.upper()
        }
        logger.info(f"Calling Cloud Sync Complete for '{company_name}' (Status: {status})")

        try:
            client = self._get_client(15.0)
            res = client.post(url, json=payload, headers=headers)
            data = res.json() if res.text else {}

            if res.status_code == 401 and self.refresh_token_val:
                refreshed, _ = self.refresh_token()
                if refreshed and self.access_token:
                    headers["Authorization"] = f"Bearer {self.access_token}"
                    res = client.post(url, json=payload, headers=headers)
                    data = res.json() if res.text else {}

            if res.status_code == 200 or data.get("success") is True:
                resp_data = data.get("data") or data
                msg = data.get("message", "Cloud sync session completed successfully.")
                return True, msg, resp_data
            else:
                err_msg = self._extract_error_message(res, data, "Failed to complete sync session")
                logger.warning(f"Cloud sync/complete HTTP {res.status_code}: {err_msg}")
                return False, err_msg, {}
        except Exception as exc:
            logger.error(f"Error calling sync/complete: {exc}")
            return False, f"Connection error completing sync session: {exc}", {}

    def get_pending_commands(self) -> Tuple[bool, str, List[Dict[str, Any]]]:
        """Fetches pending remote 2-way sync commands queued on the Cloud Server (GET /commands)."""
        if not self.access_token:
            return False, "Not authenticated. Please login first.", []

        url = f"{self.base_url}/commands"
        headers = {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}
        try:
            client = self._get_client(15.0)
            res = client.get(url, headers=headers)
            data = res.json() if res.text else {}

            if res.status_code == 401 and self.refresh_token_val:
                refreshed, _ = self.refresh_token()
                if refreshed and self.access_token:
                    headers["Authorization"] = f"Bearer {self.access_token}"
                    res = client.get(url, headers=headers)
                    data = res.json() if res.text else {}

            if res.status_code == 200 or data.get("success") is True:
                data_obj = data.get("data") or {}
                commands_list: List[Dict[str, Any]] = []
                if isinstance(data_obj, dict) and isinstance(data_obj.get("commands"), list):
                    commands_list = data_obj["commands"]
                elif isinstance(data.get("commands"), list):
                    commands_list = data["commands"]
                msg = str(data.get("message") or f"Retrieved {len(commands_list)} pending commands.")
                return True, msg, commands_list
            else:
                err_msg = self._extract_error_message(res, data, "Failed to retrieve pending commands")
                return False, err_msg, []
        except Exception as exc:
            logger.error(f"Error fetching commands: {exc}")
            return False, f"Connection error fetching commands: {exc}", []

    def send_command_result(
        self,
        command_id: str,
        status: str = "DONE",
        result: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """Sends command execution result back to Cloud Server (POST /commands/:commandId/result)."""
        if not self.access_token:
            return False, "Not authenticated. Please login first.", {}

        url = f"{self.base_url}/commands/{command_id}/result"
        headers = {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}
        payload: Dict[str, Any] = {
            "status": status.upper(),
            "result": result or {},
            "errorMessage": error_message
        }
        try:
            client = self._get_client(15.0)
            res = client.post(url, json=payload, headers=headers)
            data = res.json() if res.text else {}

            if res.status_code == 401 and self.refresh_token_val:
                refreshed, _ = self.refresh_token()
                if refreshed and self.access_token:
                    headers["Authorization"] = f"Bearer {self.access_token}"
                    res = client.post(url, json=payload, headers=headers)
                    data = res.json() if res.text else {}

            if res.status_code == 200 or data.get("success") is True:
                resp_data = data.get("data") or data
                msg = data.get("message", "Command result recorded.")
                return True, msg, resp_data
            else:
                err_msg = self._extract_error_message(res, data, "Failed to send command result")
                return False, err_msg, {}
        except Exception as exc:
            logger.error(f"Error sending command result: {exc}")
            return False, f"Connection error sending command result: {exc}", {}

    def get_remote_config(self) -> Tuple[bool, str, Dict[str, Any]]:
        """Fetches dynamic connector configuration from Cloud Server (GET /config)."""
        if not self.access_token:
            return False, "Not authenticated. Please login first.", {}

        url = f"{self.base_url}/config"
        headers = {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}
        try:
            client = self._get_client(15.0)
            res = client.get(url, headers=headers)
            data = res.json() if res.text else {}

            if res.status_code == 401 and self.refresh_token_val:
                refreshed, _ = self.refresh_token()
                if refreshed and self.access_token:
                    headers["Authorization"] = f"Bearer {self.access_token}"
                    res = client.get(url, headers=headers)
                    data = res.json() if res.text else {}

            if res.status_code == 200 or data.get("success") is True:
                resp_data = data.get("data") or data
                msg = data.get("message", "Connector config retrieved.")
                return True, msg, resp_data
            else:
                err_msg = self._extract_error_message(res, data, "Failed to retrieve connector config")
                return False, err_msg, {}
        except Exception as exc:
            logger.error(f"Error fetching connector config: {exc}")
            return False, f"Connection error fetching connector config: {exc}", {}

    def get_connector_version(self) -> Tuple[bool, str, Dict[str, Any]]:
        """Checks latest connector version and update download URL from Cloud Server (GET /version)."""
        url = f"{self.base_url}/version"
        headers = {"Content-Type": "application/json"}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"

        try:
            client = self._get_client(15.0)
            res = client.get(url, headers=headers)
            data = res.json() if res.text else {}
            if res.status_code == 200 or data.get("success") is True:
                resp_data = data.get("data") or data
                msg = data.get("message", "Version information retrieved.")
                return True, msg, resp_data
            else:
                err_msg = self._extract_error_message(res, data, "Failed to retrieve version information")
                return False, err_msg, {}
        except Exception as exc:
            logger.error(f"Error fetching connector version: {exc}")
            return False, f"Connection error fetching connector version: {exc}", {}

    def is_tally_online(self, host: Optional[str] = None, port: Optional[int] = None) -> bool:
        """Lightweight TCP probe to check if Tally Prime / ERP 9 is responding."""
        import socket
        settings = get_settings()
        target_host = host or settings.tally_host or "127.0.0.1"
        target_port = port or settings.tally_port or 9000
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1.0)
            res = sock.connect_ex((target_host, target_port))
            sock.close()
            return res == 0
        except Exception:
            return False

    def send_heartbeat(self, tally_connected: Optional[bool] = None) -> Tuple[bool, str, Dict[str, Any]]:
        """Sends periodic connector heartbeat to Cloud Server (POST /heartbeat)."""
        if not self.access_token:
            return False, "Not authenticated. Please login first.", {}

        if tally_connected is None:
            tally_connected = self.is_tally_online()

        url = f"{self.base_url}/heartbeat"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload: Dict[str, Any] = {
            "tallyConnected": bool(tally_connected),
            "status": "ONLINE",
            "connectorVersion": "1.0.1",
        }

        try:
            client = self._get_client(10.0)
            res = client.post(url, json=payload, headers=headers)
            data = res.json() if res.text else {}

            if res.status_code == 401 and self.refresh_token_val:
                refreshed, _ = self.refresh_token()
                if refreshed and self.access_token:
                    headers["Authorization"] = f"Bearer {self.access_token}"
                    res = client.post(url, json=payload, headers=headers)
                    data = res.json() if res.text else {}

            if res.status_code == 200 or data.get("success") is True:
                resp_data = data.get("data") or data
                return True, data.get("message", "Heartbeat recorded"), resp_data
            else:
                err_msg = self._extract_error_message(res, data, "Failed to send heartbeat")
                return False, err_msg, {}
        except Exception as exc:
            logger.debug(f"Heartbeat call warning (non-fatal): {exc}")
            return False, str(exc), {}

cloud_auth_service = CloudAuthService()
