

from abc import ABC, abstractmethod
from typing import Dict, Any, List

class BaseConnectorAdapter(ABC):
    @property
    @abstractmethod
    def connector_type(self) -> str:
        """Returns the uppercase string code of the connector type (e.g., TALLY)."""
        pass

    @abstractmethod
    def validate_configuration(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validates structural input configuration against Pydantic schema.
        Returns cleaned, validated configuration dictionary or raises ValidationError.
        """
        pass

    @abstractmethod
    def test_connection(self, config: Dict[str, Any], timeout: int = 5) -> Dict[str, Any]:
        """
        Executes truthful connection test against target software/port/path.
        Returns dict containing status (CONNECTED, FAILED, NOT_IMPLEMENTED), message, and latency.
        """
        pass

    @abstractmethod
    def get_health(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Returns health status dictionary for this connector configuration."""
        pass

    async def discover_companies(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Queries open companies in running connector instance. Default raises NotImplementedError."""
        raise NotImplementedError("discover_companies is not supported by this connector.")

    async def discover_metadata(self, config: Dict[str, Any], metadata_type: str) -> List[Dict[str, Any]]:
        """Queries metadata from connector instance for requested metadata type. Default raises NotImplementedError."""
        raise NotImplementedError("discover_metadata is not supported by this connector.")

