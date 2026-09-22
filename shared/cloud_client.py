
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
from typing import Dict, Any, List, Optional, Union
from shared.logging_config import get_logger
from shared.exceptions import AppException

logger = get_logger("shared.cloud_client")

class CloudClientError(AppException):
    """Exception raised when an unrecoverable error occurs communicating with Cloud Server."""
    def __init__(self, message: str):
        super().__init__(message)

class CloudClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        auth_token: Optional[str] = None,
        client_id: Optional[str] = None,
        max_retries: int = 3,
        connect_timeout: float = 5.0,
        read_timeout: float = 30.0,
    ):
        from shared.config import get_settings
        default_url = get_settings().cloud_api_base_url
        self.base_url = (base_url or default_url).rstrip("/")

        self.auth_token = auth_token
        self.client_id = client_id or "default-client-id"
        self.max_retries = max_retries
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout
        self.timeout = (connect_timeout, read_timeout)

        self.session = requests.Session()
        self._configure_session()

    def _configure_session(self) -> None:
        """Configures HTTP session headers, Bearer Token, X-Client-Id, and retry adapter."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Client-Id": self.client_id,
            "User-Agent": "LR-Analyst-Connector/1.0.0",
        }
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"

        self.session.headers.update(headers)

        retry_strategy = Retry(
            total=self.max_retries,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST", "PUT", "DELETE"],
            raise_on_status=False,
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def update_auth(self, auth_token: str, client_id: Optional[str] = None) -> None:
        """Dynamically updates authentication token and client ID headers."""
        self.auth_token = auth_token
        self.session.headers["Authorization"] = f"Bearer {auth_token}"
        if client_id:
            self.client_id = client_id
            self.session.headers["X-Client-Id"] = client_id

    def _request(self, method: str, endpoint: str, **kwargs) -> Any:
        """Helper method to execute HTTP requests with timeout enforcement and error handling."""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        if "timeout" not in kwargs:
            kwargs["timeout"] = self.timeout

        try:
            response = self.session.request(method, url, **kwargs)
            logger.info(f"CloudClient {method.upper()} {url} -> Status {response.status_code}")

            if response.status_code >= 400:
                error_detail = response.text
                try:
                    err_json = response.json()
                    error_detail = err_json.get("detail") or err_json.get("error") or err_json.get("message") or response.text
                except Exception:
                    pass

                msg = f"Cloud Server API Error HTTP {response.status_code}: {error_detail}"
                logger.error(msg)
                raise CloudClientError(msg)

            if response.status_code == 204 or not response.text:
                return {}

            return response.json()

        except requests.exceptions.Timeout as exc:
            msg = f"Timeout connecting to Cloud Server at {url}: {exc}"
            logger.error(msg)
            raise CloudClientError(msg) from exc

        except requests.exceptions.ConnectionError as exc:
            msg = f"Network connection error contacting Cloud Server at {url}: {exc}"
            logger.error(msg)
            raise CloudClientError(msg) from exc

        except requests.exceptions.RequestException as exc:
            msg = f"HTTP Request failed for Cloud Server endpoint {url}: {exc}"
            logger.error(msg)
            raise CloudClientError(msg) from exc

    def sync_masters(
        self, masters_data: Union[Dict[str, Any], List[Dict[str, Any]]], company_identifier: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        POST /api/v1/connector/sync-masters
        Pushes extracted master records (Ledgers, Stock Items, Groups) to Central Cloud Server.
        """
        payload = masters_data if isinstance(masters_data, dict) else {"masters": masters_data}
        if company_identifier and "company_identifier" not in payload:
            payload["company_identifier"] = company_identifier

        return self._request("POST", "/api/v1/connector/sync-masters", json=payload)

    def sync_vouchers(
        self, vouchers_data: Union[Dict[str, Any], List[Dict[str, Any]]], company_identifier: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        POST /api/v1/connector/sync-vouchers
        Pushes extracted voucher records (Sales, Receipts, Daybook) to Central Cloud Server.
        """
        payload = vouchers_data if isinstance(vouchers_data, dict) else {"vouchers": vouchers_data}
        if company_identifier and "company_identifier" not in payload:
            payload["company_identifier"] = company_identifier

        return self._request("POST", "/api/v1/connector/sync-vouchers", json=payload)

    def get_pending_invoices(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        GET /api/v1/connector/invoices/pending
        Fetches list of pending web orders/invoices awaiting import into local Tally/BUSY.
        """
        params = {"limit": limit}
        res = self._request("GET", "/api/v1/connector/invoices/pending", params=params)

        if isinstance(res, list):
            return res
        if isinstance(res, dict) and "invoices" in res:
            return res["invoices"]
        if isinstance(res, dict) and "data" in res:
            return res["data"]
        return []

    def acknowledge_invoice(
        self,
        invoice_id: str,
        status: str,
        voucher_number: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        POST /api/v1/connector/invoices/{id}/ack
        Sends success or failure status report back to Cloud Server after attempting voucher creation.
        """
        clean_id = str(invoice_id).strip()
        endpoint = f"/api/v1/connector/invoices/{clean_id}/ack"

        payload = {
            "invoice_id": clean_id,
            "status": status.upper(),
            "voucher_number": voucher_number,
            "error_message": error_message,
        }

        return self._request("POST", endpoint, json=payload)

    def send_heartbeat(self, telemetry_payload: Dict[str, Any]) -> Dict[str, Any]:
       
        return self._request("POST", "/api/v1/connector/heartbeat", json=telemetry_payload)

