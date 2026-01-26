"""Connector factory for creating data connectors."""

from typing import Literal

from app.config import Settings
from app.connectors.mock import MockConnector
from app.connectors.protocol import Connector

ConnectorType = Literal["mock", "hana", "rfc"]


class ConnectorFactoryError(Exception):
    """Raised when connector factory cannot create a connector."""


def create_connector(settings: Settings) -> Connector:
    """Create a connector based on settings.

    Currently only mock connector is implemented.
    Future: Add HANA and RFC connectors.

    Args:
        settings: Application settings.

    Returns:
        Configured connector instance.
    """
    # For MVP, always use mock connector
    # TODO: Add connector_type to settings and implement other connectors
    return MockConnector()