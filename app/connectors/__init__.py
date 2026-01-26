"""SAP BW connector module."""

from app.connectors.business import BusinessDatabaseConnector
from app.connectors.factory import (
    ConnectorFactoryError,
    create_business_connector,
    create_connector,
)
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
    "BusinessDatabaseConnector",
    # Factory
    "create_connector",
    "create_business_connector",
    "ConnectorFactoryError",
]