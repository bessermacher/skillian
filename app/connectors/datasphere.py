"""SAP Datasphere connector with OAuth2 authentication."""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import httpx


class DatasphereError(Exception):
    """Base exception for Datasphere operations."""


class DatasphereAuthError(DatasphereError):
    """Authentication failed."""


class DatasphereQueryError(DatasphereError):
    """Query execution failed."""


@dataclass
class OAuthToken:
    """OAuth2 token with expiry tracking."""

    access_token: str
    expires_at: datetime
    token_type: str = "Bearer"

    @property
    def is_expired(self) -> bool:
        """Check if token is expired (with 60s buffer)."""
        return datetime.now() >= self.expires_at - timedelta(seconds=60)


@dataclass
class DatasphereConnector:
    """Async connector for SAP Datasphere.

    Handles OAuth2 authentication and query execution via OData/SQL endpoints.
    Uses connection pooling for efficient resource usage.

    Example:
        connector = DatasphereConnector(
            host="your-tenant.datasphere.cloud.sap",
            space="YOUR_SPACE",
            client_id="...",
            client_secret="...",
            token_url="https://your-tenant.authentication.sap.hana.ondemand.com/oauth/token",
        )
        await connector.connect()
        results = await connector.execute_sql("SELECT * FROM view_name LIMIT 10")
        await connector.close()
    """

    host: str
    space: str
    client_id: str
    client_secret: str
    token_url: str
    port: int = 443
    timeout: int = 60
    max_connections: int = 10

    _client: httpx.AsyncClient | None = field(default=None, init=False, repr=False)
    _token: OAuthToken | None = field(default=None, init=False, repr=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)

    @property
    def base_url(self) -> str:
        """Base URL for Datasphere API."""
        return f"https://{self.host}:{self.port}"

    @property
    def odata_url(self) -> str:
        """OData service URL."""
        return f"{self.base_url}/api/v1/dwc/consumption/relational/{self.space}"

    @property
    def sql_url(self) -> str:
        """SQL execution endpoint."""
        return f"{self.base_url}/api/v1/dwc/sql/{self.space}"

    async def connect(self) -> None:
        """Initialize the HTTP client and authenticate."""
        if self._client is not None:
            return

        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout),
            limits=httpx.Limits(
                max_connections=self.max_connections,
                max_keepalive_connections=self.max_connections // 2,
            ),
        )

        await self._refresh_token()

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
            self._token = None

    async def _refresh_token(self) -> None:
        """Obtain or refresh OAuth2 token."""
        if self._client is None:
            raise DatasphereError("Connector not connected. Call connect() first.")

        async with self._lock:
            # Double-check after acquiring lock
            if self._token and not self._token.is_expired:
                return

            try:
                response = await self._client.post(
                    self.token_url,
                    data={
                        "grant_type": "client_credentials",
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                response.raise_for_status()

                data = response.json()
                expires_in = data.get("expires_in", 3600)

                self._token = OAuthToken(
                    access_token=data["access_token"],
                    expires_at=datetime.now() + timedelta(seconds=expires_in),
                    token_type=data.get("token_type", "Bearer"),
                )

            except httpx.HTTPStatusError as e:
                raise DatasphereAuthError(
                    f"Authentication failed: {e.response.status_code} - {e.response.text}"
                ) from e
            except Exception as e:
                raise DatasphereAuthError(f"Authentication failed: {e}") from e

    async def _get_headers(self) -> dict[str, str]:
        """Get request headers with valid auth token."""
        if self._token is None or self._token.is_expired:
            await self._refresh_token()

        return {
            "Authorization": f"{self._token.token_type} {self._token.access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def execute_sql(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Execute a SQL query against Datasphere.

        Args:
            query: SQL query string
            parameters: Optional query parameters for prepared statements

        Returns:
            List of result rows as dictionaries

        Raises:
            DatasphereQueryError: If query execution fails
        """
        if self._client is None:
            raise DatasphereError("Connector not connected. Call connect() first.")

        headers = await self._get_headers()

        payload = {"query": query}
        if parameters:
            payload["parameters"] = parameters

        try:
            response = await self._client.post(
                self.sql_url,
                json=payload,
                headers=headers,
            )
            response.raise_for_status()

            data = response.json()
            return data.get("results", [])

        except httpx.HTTPStatusError as e:
            raise DatasphereQueryError(
                f"Query failed: {e.response.status_code} - {e.response.text}"
            ) from e
        except Exception as e:
            raise DatasphereQueryError(f"Query failed: {e}") from e

    async def execute_odata(
        self,
        entity: str,
        select: list[str] | None = None,
        filter_expr: str | None = None,
        top: int | None = None,
        skip: int | None = None,
        orderby: str | None = None,
    ) -> list[dict[str, Any]]:
        """Execute an OData query against a Datasphere view/table.

        Args:
            entity: Entity set name (view or table name)
            select: Fields to select
            filter_expr: OData filter expression
            top: Maximum number of results
            skip: Number of results to skip
            orderby: Order by expression

        Returns:
            List of result entities as dictionaries
        """
        if self._client is None:
            raise DatasphereError("Connector not connected. Call connect() first.")

        headers = await self._get_headers()

        # Build OData query parameters
        params: dict[str, str] = {}
        if select:
            params["$select"] = ",".join(select)
        if filter_expr:
            params["$filter"] = filter_expr
        if top:
            params["$top"] = str(top)
        if skip:
            params["$skip"] = str(skip)
        if orderby:
            params["$orderby"] = orderby

        url = f"{self.odata_url}/{entity}"

        try:
            response = await self._client.get(url, params=params, headers=headers)
            response.raise_for_status()

            data = response.json()
            return data.get("value", [])

        except httpx.HTTPStatusError as e:
            raise DatasphereQueryError(
                f"OData query failed: {e.response.status_code} - {e.response.text}"
            ) from e
        except Exception as e:
            raise DatasphereQueryError(f"OData query failed: {e}") from e

    async def get_metadata(self, entity: str | None = None) -> dict[str, Any]:
        """Retrieve metadata for entities in the space.

        Args:
            entity: Specific entity name, or None for all metadata

        Returns:
            Metadata dictionary
        """
        if self._client is None:
            raise DatasphereError("Connector not connected. Call connect() first.")

        headers = await self._get_headers()

        url = f"{self.odata_url}/$metadata"
        if entity:
            url = f"{self.odata_url}/{entity}/$metadata"

        try:
            response = await self._client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()

        except httpx.HTTPStatusError as e:
            raise DatasphereQueryError(f"Metadata query failed: {e.response.status_code}") from e

    async def list_entities(self) -> list[str]:
        """List available entities (views/tables) in the space."""
        metadata = await self.get_metadata()
        # Parse entity names from metadata
        # Structure depends on Datasphere's metadata format
        entities = []
        for schema in metadata.get("schemas", []):
            for entity in schema.get("entityTypes", []):
                entities.append(entity.get("name"))
        return entities

    async def health_check(self) -> bool:
        """Check if Datasphere connection is healthy."""
        try:
            if self._client is None:
                return False
            await self._refresh_token()
            return True
        except Exception:
            return False
