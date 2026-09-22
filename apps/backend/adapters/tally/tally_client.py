

import httpx
import time
import asyncio
from typing import Tuple, Optional, Dict
from shared.exceptions import ValidationError
from shared.logging_config import get_logger

logger = get_logger("app.adapters.tally.client")

class TallyClient:
    def __init__(self, connect_timeout: float = 10.0, read_timeout: float = 60.0):
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout
        self._limits = httpx.Limits(max_keepalive_connections=50, max_connections=100, keepalive_expiry=60.0)
        self._client: Optional[httpx.Client] = None
        self._async_client: Optional[httpx.AsyncClient] = None
        self._locks: Dict[str, asyncio.Lock] = {}

    def get_lock(self, host: str, port: int, company_name: Optional[str] = None) -> asyncio.Lock:
        """Returns an asyncio.Lock per Tally instance / company to serialize concurrent requests."""
        key = f"{host}:{port}:{company_name or 'GLOBAL'}"
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    def _get_client(self, timeout_config: httpx.Timeout) -> httpx.Client:
        if self._client is None or self._client.is_closed:
            self._client = httpx.Client(timeout=timeout_config, limits=self._limits)
        return self._client

    def _get_async_client(self, timeout_config: httpx.Timeout) -> httpx.AsyncClient:
        if self._async_client is None or self._async_client.is_closed:
            self._async_client = httpx.AsyncClient(timeout=timeout_config, limits=self._limits)
        return self._async_client

    def close(self):
        if self._client and not self._client.is_closed:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None

    async def aclose(self):
        if self._async_client and not self._async_client.is_closed:
            try:
                await self._async_client.aclose()
            except Exception:
                pass
            self._async_client = None

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    def validate_host_and_port(self, host: str, port: int) -> Tuple[str, int]:
        clean_host = (host or "").strip()
        if not clean_host or "://" in clean_host or "/" in clean_host or " " in clean_host:
            raise ValidationError(f"Invalid host '{clean_host}'. Provide only IP address or domain name.")
        try:
            clean_port = int(port)
            if clean_port < 1 or clean_port > 65535:
                raise ValidationError(f"Tally port '{port}' out of valid range (1-65535).")
        except ValueError:
            raise ValidationError(f"Invalid Tally port '{port}'.")
        return clean_host, clean_port

    async def send_xml_request_async(
        self,
        host: str,
        port: int,
        xml_content: str,
        timeout: Optional[float] = None,
        serialize_company: Optional[str] = None
    ) -> Tuple[bool, int, str, Optional[str]]:
        c_host, c_port = self.validate_host_and_port(host, port)
        url = f"http://{c_host}:{c_port}/"
        req_timeout = timeout or self.read_timeout
        timeout_config = httpx.Timeout(req_timeout, connect=self.connect_timeout)

        lock = self.get_lock(c_host, c_port, serialize_company) if serialize_company else None

        async def _execute():
            max_attempts = 3
            last_error = None

            for attempt in range(1, max_attempts + 1):
                try:
                    start_time = time.perf_counter()
                    client = self._get_async_client(timeout_config)
                    response = await client.post(url, content=xml_content, headers={"Content-Type": "text/xml"}, timeout=timeout_config)

                    elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
                    logger.info(f"Tally XML request to {url} succeeded HTTP {response.status_code} ({elapsed_ms}ms)")

                    if response.status_code == 200:
                        return True, 200, response.text, None
                    return False, response.status_code, response.text, f"HTTP {response.status_code}"

                except httpx.ConnectError:
                    last_error = f"Unable to connect to Tally Prime at {url}. Ensure Tally Prime is running."
                except httpx.TimeoutException:
                    last_error = f"Connection timeout ({req_timeout}s) waiting for Tally Prime response at {url}."
                except Exception as exc:
                    last_error = f"Network error communicating with Tally: {exc}"

                if attempt < max_attempts:
                    await asyncio.sleep(0.5 * (2 ** (attempt - 1)))

            return False, 0, "", last_error or "Tally server unreachable"

        if lock:
            async with lock:
                return await _execute()
        return await _execute()

    def send_xml_request(self, host: str, port: int, xml_content: str, timeout: Optional[float] = None) -> Tuple[bool, int, str, Optional[str]]:
        c_host, c_port = self.validate_host_and_port(host, port)
        url = f"http://{c_host}:{c_port}/"
        req_timeout = timeout or self.read_timeout
        timeout_config = httpx.Timeout(req_timeout, connect=self.connect_timeout)

        max_attempts = 3
        last_error = None

        for attempt in range(1, max_attempts + 1):
            try:
                start_time = time.perf_counter()
                client = self._get_client(timeout_config)
                response = client.post(url, content=xml_content, headers={"Content-Type": "text/xml"}, timeout=timeout_config)

                elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)
                logger.info(f"Tally XML request to {url} succeeded HTTP {response.status_code} ({elapsed_ms}ms)")

                if response.status_code == 200:
                    return True, 200, response.text, None
                return False, response.status_code, response.text, f"HTTP {response.status_code}"

            except httpx.ConnectError:
                last_error = f"Unable to connect to Tally Prime at {url}. Ensure Tally Prime is running."
            except httpx.TimeoutException:
                last_error = f"Connection timeout ({req_timeout}s) waiting for Tally Prime response at {url}."
            except Exception as exc:
                last_error = f"Network error communicating with Tally: {exc}"

            if attempt < max_attempts:
                time.sleep(0.5 * (2 ** (attempt - 1)))

        return False, 0, "", last_error or "Tally server unreachable"

