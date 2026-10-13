import httpx
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime, timezone
from shared.config import get_settings
from shared.logging_config import get_logger


logger = get_logger("app.cloud.command_client")


class CloudCommandClient:
    """Handles cloud remote command polling, ACK reporting, and telemetry heartbeats."""

    def __init__(self, auth_service):
        self.auth = auth_service

    @property
    def base_url(self) -> str:
        return self.auth.base_url

    @property
    def access_token(self) -> Optional[str]:
        return self.auth.access_token

    @property
    def refresh_token_val(self) -> Optional[str]:
        return self.auth.refresh_token_val

    @property
    def _device_id(self) -> str:
        return self.auth._device_id

    def _get_client(self, timeout: float = 30.0) -> httpx.Client:
        return self.auth._get_client(timeout)

    def refresh_token(self):
        return self.auth.refresh_token()

    def _extract_error_message(self, res: httpx.Response, data: Dict[str, Any], default_msg: str) -> str:
        return self.auth._extract_error_message(res, data, default_msg)

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
        res_data = dict(result or {})
        t_ext = (
            res_data.get("tallyExternalId")
            or res_data.get("guid")
            or res_data.get("tally_guid")
            or res_data.get("externalId")
            or res_data.get("id")
        )
        if t_ext and "tallyExternalId" not in res_data:
            res_data["tallyExternalId"] = str(t_ext)

        payload: Dict[str, Any] = {
            "status": status.upper(),
            "result": res_data,
            "resultPayload": res_data,
        }
        if t_ext:
            payload["tallyExternalId"] = str(t_ext)
        if error_message and str(error_message).strip():
            payload["errorMessage"] = str(error_message).strip()
        headers = {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}
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
        from shared.connection_config import resolve_active_tally_port
        target_host, target_port = resolve_active_tally_port(preferred_port=port, preferred_host=host)
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
            "connectorVersion": get_settings().app_version,
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

