"""SAP BW connector module."""

from app.connectors.factory import ConnectorFactoryError, create_connector
from app.connectors.mock import MockConnector
from app.connectors.protocol import (
    ConnectionError,
    Connector,
    ConnectorError,
    DataNotFoundError,
    QueryNotSupportedError,
)

__all__ = [
    # Protocol
    "Connector",
    "ConnectorError",
    "QueryNotSupportedError",
    "ConnectionError",
    "DataNotFoundError",
    # Implementations
    "MockConnector",
    # Factory
    "create_connector",
    "ConnectorFactoryError",
]