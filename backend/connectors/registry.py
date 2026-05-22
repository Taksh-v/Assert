import logging
from typing import Dict, Type
from backend.connectors.base import BaseConnector

logger = logging.getLogger(__name__)

class ConnectorRegistry:
    """
    Central registry for mapping connector type strings to their implementation classes.
    """
    def __init__(self):
        self._registry: Dict[str, Type[BaseConnector]] = {}

    def register(self, connector_type: str, connector_class: Type[BaseConnector]):
        """Register a connector implementation."""
        if connector_type in self._registry:
            logger.warning(f"Overwriting existing connector registration for type: {connector_type}")
        self._registry[connector_type] = connector_class
        logger.debug(f"Registered connector: {connector_type} -> {connector_class.__name__}")

    def get_connector(self, connector_type: str) -> Type[BaseConnector]:
        """Get the connector class by type string."""
        if connector_type not in self._registry:
            raise ValueError(f"No connector registered for type: {connector_type}")
        return self._registry[connector_type]

    def list_connectors(self) -> Dict[str, str]:
        """List all available connector types and their classes."""
        return {k: v.__name__ for k, v in self._registry.items()}

# Singleton registry instance
connector_registry = ConnectorRegistry()
