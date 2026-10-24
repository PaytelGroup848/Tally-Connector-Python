import httpx
import uuid
import json
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime, timezone

from shared.config import get_settings
from shared.logging_config import get_logger
from shared.cloud.helpers import (
    _safe_get_collection,
    _get_writable_data_file,
    get_or_create_device_id,
    format_tally_date,
    classify_ledger_type,
    AUTH_SESSION_FILE,
    DEVICE_CONFIG_FILE,
)
from shared.cloud.cloud_sync_client import CloudSyncClient
from shared.cloud.cloud_command_client import CloudCommandClient

logger = get_logger("app.auth.cloud")

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

        # Composite delegate clients
        self._sync_client = CloudSyncClient(self)
        self._command_client = CloudCommandClient(self)

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
        """Loads authenticated session, prioritizing Windows Credential Manager with 24-hr TTL enforcement."""
        # 1. Primary: Native Windows Credential Manager (Encrypted at rest by Windows DPAPI)
        try:
            from shared.auth.win_credential_store import load_persisted_session
            win_session = load_persisted_session()
            if win_session and win_session.get("access_token"):
                self.access_token = win_session.get("access_token")
                self.refresh_token_val = win_session.get("refresh_token")
                self.current_user = win_session.get("user") or {}
                win_dev = win_session.get("device_id")
                if win_dev:
                    self.device_id = str(win_dev)
                elif not self.device_id and self.current_user.get("deviceId"):
                    self.device_id = str(self.current_user.get("deviceId"))
                logger.info(f"Restored active 15-day session from Windows Credential Manager for user '{win_session.get('username')}'")
                return
        except Exception as exc:
            logger.warning(f"Error checking Windows Credential Manager: {exc}")

        # 2. Fallback: Local auth_session.json (if present and valid)
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
                    f_dev = data.get("deviceId")
                    if f_dev:
                        self.device_id = str(f_dev)
                    elif not self.device_id and self.current_user.get("deviceId"):
                        self.device_id = str(self.current_user.get("deviceId"))
            except Exception as exc:
                logger.warning(f"Error loading auth session file: {exc}")

    def save_session(self, access_token: str, refresh_token: Optional[str] = None, user: Optional[Dict[str, Any]] = None) -> None:
        """Persists access token and user info to Windows Credential Manager (15-day TTL) and disk fallback."""
        self.access_token = access_token
        if refresh_token:
            self.refresh_token_val = refresh_token
        if user:
            self.current_user = user

        # 1. Primary: Save to Windows Credential Manager with 15-day expiration
        try:
            from shared.auth.win_credential_store import save_persisted_session, SESSION_LIFETIME_SECONDS
            uname = self.get_email() or (user.get("email") if user else None) or (user.get("username") if user else None) or "default_user"
            save_persisted_session(
                username=uname,
                access_token=self.access_token,
                refresh_token=self.refresh_token_val,
                user_dict=self.current_user,
                ttl_seconds=SESSION_LIFETIME_SECONDS,  # 15 Days
                device_id=self.device_id,
            )
        except Exception as exc:
            logger.warning(f"Could not persist session to Windows Credential Manager: {exc}")

        # 2. Local fallback storage
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
        org_id = None
        if self.current_user and isinstance(self.current_user, dict):
            org_id = (
                self.current_user.get("organizationId")
                or self.current_user.get("organization_id")
                or self.current_user.get("connector", {}).get("organizationId")
                or self.current_user.get("connector", {}).get("organization_id")
            )
        if not org_id and self.access_token:
            try:
                import base64
                parts = self.access_token.split(".")
                if len(parts) >= 2:
                    padding = "=" * (4 - len(parts[1]) % 4)
                    claims = json.loads(base64.urlsafe_b64decode(parts[1] + padding).decode("utf-8"))
                    org_id = claims.get("organizationId") or claims.get("organization_id")
            except Exception:
                pass
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
        if self.access_token:
            try:
                import base64
                parts = self.access_token.split(".")
                if len(parts) >= 2:
                    padding = "=" * (4 - len(parts[1]) % 4)
                    claims = json.loads(base64.urlsafe_b64decode(parts[1] + padding).decode("utf-8"))
                    em = claims.get("email") or claims.get("userEmail")
                    if em:
                        return str(em).strip().lower()
            except Exception:
                pass
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
    def device_id(self, val: Any) -> None:
        if val:
            self._device_id = str(val).strip()

    def sync_user_to_mongodb(self, user_data: Dict[str, Any]) -> None:
        try:
            col = _safe_get_collection("user_profile")
            if col is None:
                return

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
            "connectorVersion": get_settings().app_version,
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

        # Clear from Windows Credential Manager
        try:
            from shared.auth.win_credential_store import clear_persisted_session
            clear_persisted_session()
        except Exception:
            pass

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
        import uuid
        clean_name = str(company_name or "").strip()
        eff_guid = str(company_guid or "").strip()
        if not eff_guid or len(eff_guid) < 16 or eff_guid.lower() in ("none", "null", "undefined"):
            eff_guid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"ctrlbooks.tally.{clean_name.lower()}"))

        payload = {
            "tallyCompanyName": clean_name,
            "tallyCompanyGuid": eff_guid,
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
                    col = _safe_get_collection("companies")
                    if col is not None:
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
                        col = _safe_get_collection("companies")
                        if col is not None:
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


    # --- Cloud Batch Sync Delegations ---
    def sync_start(
        self,
        company_name: str,
        company_guid: str = "",
        sync_type: str = "INCREMENTAL",
        total_records: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
        company_id: Optional[str] = None
    ) -> Tuple[bool, str, Dict[str, Any]]:
        return self._sync_client.sync_start(
            company_name, company_guid, sync_type, total_records, metadata, company_id
        )

    def sync_batch(
        self,
        sync_id: str,
        company_name: str,
        entity_type: str,
        items: list[Dict[str, Any]],
        batch_number: int = 1,
        is_last_batch: bool = False
    ) -> Tuple[bool, str, Dict[str, Any]]:
        return self._sync_client.sync_batch(
            sync_id, company_name, entity_type, items, batch_number, is_last_batch
        )

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
        return self._sync_client.sync_complete(
            sync_id, company_name, status, total_synced, last_alter_id, summary
        )

    # --- Remote Command & Telemetry Delegations ---
    def get_pending_commands(self) -> Tuple[bool, str, List[Dict[str, Any]]]:
        return self._command_client.get_pending_commands()

    def send_command_result(
        self,
        command_id: str,
        status: str = "DONE",
        result: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None
    ) -> Tuple[bool, str, Dict[str, Any]]:
        return self._command_client.send_command_result(
            command_id, status, result, error_message
        )

    def get_remote_config(self) -> Tuple[bool, str, Dict[str, Any]]:
        return self._command_client.get_remote_config()

    def get_connector_version(self) -> Tuple[bool, str, Dict[str, Any]]:
        return self._command_client.get_connector_version()

    def is_tally_online(self, host: Optional[str] = None, port: Optional[int] = None) -> bool:
        return self._command_client.is_tally_online(host, port)

    def send_heartbeat(self, tally_connected: Optional[bool] = None) -> Tuple[bool, str, Dict[str, Any]]:
        return self._command_client.send_heartbeat(tally_connected)


cloud_auth_service: CloudAuthService = CloudAuthService()

__all__ = [
    "CloudAuthService",
    "cloud_auth_service",
    "get_or_create_device_id",
    "format_tally_date",
    "classify_ledger_type",
    "AUTH_SESSION_FILE",
    "DEVICE_CONFIG_FILE",
    "_get_writable_data_file",
    "_safe_get_collection",
]
