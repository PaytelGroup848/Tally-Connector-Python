

from typing import Dict, List
from apps.backend.adapters.base import BaseConnectorAdapter
from apps.backend.adapters.tally_adapter import TallyConnectorAdapter
from shared.exceptions import ValidationError
from shared.logging_config import get_logger

logger = get_logger("app.adapters.registry")

class ConnectorRegistry:
    def __init__(self):
        self._adapters: Dict[str, BaseConnectorAdapter] = {}
        self.register(TallyConnectorAdapter())

    def register(self, adapter: BaseConnectorAdapter) -> None:
        """Register a connector adapter instance by its connector_type code."""
        code = adapter.connector_type.strip().upper()
        self._adapters[code] = adapter
        logger.info(f"Registered connector adapter for type '{code}' ({adapter.__class__.__name__})")

    def get_adapter(self, connector_type: str) -> BaseConnectorAdapter:
        """Fetch registered adapter instance or raise ValidationError if unregistered."""
        clean_type = connector_type.strip().upper()
        adapter = self._adapters.get(clean_type)
        if not adapter:
            supported = ", ".join(self.list_registered_types())
            raise ValidationError(f"Unsupported or unregistered connector type '{connector_type}'. Registered types: [{supported}]")
        return adapter

    def list_registered_types(self) -> List[str]:
        """Returns list of registered connector type strings."""
        return list(self._adapters.keys())

    def is_registered(self, connector_type: str) -> bool:
        """Returns True if connector_type is registered."""
        return connector_type.strip().upper() in self._adapters

connector_registry = ConnectorRegistry()
