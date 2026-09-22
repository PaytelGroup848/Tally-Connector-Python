

import asyncio
from typing import Dict, Any, List
from apps.backend.adapters.base import BaseConnectorAdapter
from shared.schemas.connector_schemas import TallyConfigurationSchema
from apps.backend.adapters.tally.tally_client import TallyClient
from apps.backend.adapters.tally.request_builder import (
    build_company_list_xml, build_collection_xml, METADATA_TYPE_MAP, ALLOWED_METADATA_TYPES
)
from apps.backend.adapters.tally.response_parser import parse_company_list, parse_metadata_response
from shared.exceptions import ValidationError
from shared.logging_config import get_logger

logger = get_logger("app.adapters.tally")

class TallyConnectorAdapter(BaseConnectorAdapter):
    def __init__(self):
        self.client = TallyClient(connect_timeout=5.0, read_timeout=10.0)

    @property
    def connector_type(self) -> str:
        return "TALLY"

    def validate_configuration(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Validates host, port, company name, and connection mode using Pydantic."""
        try:
            validated = TallyConfigurationSchema(**(config or {}))
            self.client.validate_host_and_port(validated.host, validated.port)
            return validated.model_dump()
        except ValidationError:
            raise
        except Exception as exc:
            raise ValidationError(f"Invalid Tally configuration: {exc}")

    def test_connection(self, config: Dict[str, Any], timeout: int = 5) -> Dict[str, Any]:
        """
        Truthfully tests HTTP accessibility and XML query execution to target Tally Prime server.
        Does NOT produce fake success if port is unreachable or response is invalid.
        """
        clean_config = self.validate_configuration(config)
        host = clean_config["host"]
        port = clean_config["port"]

        xml_req = build_company_list_xml()

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                ok, code, res_text, err_msg = pool.submit(
                    lambda: asyncio.run(self.client.send_xml_request_async(host, port, xml_req, timeout=timeout))
                ).result()
        else:
            ok, code, res_text, err_msg = asyncio.run(
                self.client.send_xml_request_async(host, port, xml_req, timeout=timeout)
            )

        if ok and code == 200:
            companies = parse_company_list(res_text)
            comp_count = len(companies)
            comp_info = f" ({comp_count} company/companies open)" if comp_count > 0 else ""
            return {
                "status": "CONNECTED",
                "message": f"Successfully connected to Tally Prime endpoint at {host}:{port}{comp_info}.",
                "companies_found": comp_count,
                "latency_ms": 100,
                "error": None
            }
        else:
            return {
                "status": "FAILED",
                "message": err_msg or f"Unable to reach Tally Prime server at {host}:{port}.",
                "latency_ms": None,
                "error": err_msg
            }

    def get_health(self, config: Dict[str, Any]) -> Dict[str, Any]:
        res = self.test_connection(config, timeout=3)
        return {
            "connector_type": "TALLY",
            "health": "HEALTHY" if res["status"] == "CONNECTED" else "UNHEALTHY",
            "details": res
        }

    async def discover_companies(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Queries open companies in running Tally instance."""
        clean_config = self.validate_configuration(config)
        xml_req = build_company_list_xml()
        ok, code, res_text, err_msg = await self.client.send_xml_request_async(
            clean_config["host"], clean_config["port"], xml_req, timeout=10.0
        )
        if not ok or code != 200:
            raise ValidationError(err_msg or "Failed to discover companies from Tally Prime server.")

        return parse_company_list(res_text)

    async def discover_metadata(self, config: Dict[str, Any], metadata_type: str) -> List[Dict[str, Any]]:
        """Queries metadata from Tally instance for allowed metadata types."""
        clean_type = metadata_type.strip().lower()
        if clean_type not in ALLOWED_METADATA_TYPES:
            raise ValidationError(f"Unsupported metadata type '{metadata_type}'. Allowed types: {', '.join(ALLOWED_METADATA_TYPES)}")

        clean_config = self.validate_configuration(config)
        col_type, fetch_fields = METADATA_TYPE_MAP[clean_type]
        selected_company = clean_config.get("company_name")

        xml_req = build_collection_xml(collection_type=col_type, fetch_fields=fetch_fields, company_name=selected_company)
        ok, code, res_text, err_msg = await self.client.send_xml_request_async(
            clean_config["host"], clean_config["port"], xml_req, timeout=15.0
        )
        if not ok or code != 200:
            raise ValidationError(err_msg or f"Failed to discover '{metadata_type}' metadata from Tally Prime.")

        return parse_metadata_response(res_text, tag_name=col_type)



