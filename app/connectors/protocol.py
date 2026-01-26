"""Connector protocol for SAP BW data access."""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Connector(Protocol):
    """Protocol for SAP BW data connectors.

    Connectors abstract the data access layer, allowing:
    - Mock data for development
    - HANA direct connection for production
    - RFC connection for legacy systems
    """

    @property
    def name(self) -> str:
        """Connector name (e.g., 'mock', 'hana', 'rfc')."""
        ...

    async def execute_query(
        self,
        query_type: str,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a query against SAP BW.

        Args:
            query_type: Type of query (e.g., 'cost_center', 'profit_center').
            parameters: Query parameters.

        Returns:
            Query results as a dictionary.

        Raises:
            ConnectorError: If the query fails.
        """
        ...

    async def health_check(self) -> bool:
        """Check if the connector is healthy and can connect.

        Returns:
            True if healthy, False otherwise.
        """
        ...


class ConnectorError(Exception):
    """Base exception for connector errors."""

    def __init__(self, message: str, query_type: str | None = None):
        self.query_type = query_type
        super().__init__(message)


class QueryNotSupportedError(ConnectorError):
    """Raised when a query type is not supported."""


class ConnectionError(ConnectorError):
    """Raised when connection to SAP fails."""


class DataNotFoundError(ConnectorError):
    """Raised when requested data is not found."""