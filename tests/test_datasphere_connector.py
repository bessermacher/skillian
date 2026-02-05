"""Tests for Datasphere connector."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timedelta

from app.connectors.datasphere import (
    DatasphereConnector,
    DatasphereAuthError,
    DatasphereQueryError,
    OAuthToken,
)


@pytest.fixture
def connector():
    """Create test connector."""
    return DatasphereConnector(
        host="test.datasphere.cloud.sap",
        space="TEST_SPACE",
        client_id="test-client",
        client_secret="test-secret",
        token_url="https://test.auth.com/oauth/token",
    )


class TestOAuthToken:
    def test_is_expired_false(self):
        token = OAuthToken(
            access_token="test",
            expires_at=datetime.now() + timedelta(hours=1),
        )
        assert not token.is_expired

    def test_is_expired_true(self):
        token = OAuthToken(
            access_token="test",
            expires_at=datetime.now() - timedelta(seconds=1),
        )
        assert token.is_expired

    def test_is_expired_within_buffer(self):
        """Token is considered expired within 60s buffer."""
        token = OAuthToken(
            access_token="test",
            expires_at=datetime.now() + timedelta(seconds=30),
        )
        assert token.is_expired


class TestDatasphereConnector:
    def test_base_url(self, connector):
        assert connector.base_url == "https://test.datasphere.cloud.sap:443"

    def test_odata_url(self, connector):
        assert "TEST_SPACE" in connector.odata_url
        assert "/api/v1/dwc/consumption/relational/" in connector.odata_url

    def test_sql_url(self, connector):
        assert "TEST_SPACE" in connector.sql_url
        assert "/api/v1/dwc/sql/" in connector.sql_url

    @pytest.mark.asyncio
    async def test_connect_creates_client(self, connector):
        with patch("app.connectors.datasphere.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value = mock_instance

            # Mock token response
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "access_token": "test-token",
                "expires_in": 3600,
            }
            mock_response.raise_for_status = MagicMock()
            mock_instance.post.return_value = mock_response

            await connector.connect()

            assert connector._client is not None
            assert connector._token is not None
            assert connector._token.access_token == "test-token"

    @pytest.mark.asyncio
    async def test_connect_is_idempotent(self, connector):
        """Calling connect multiple times should be safe."""
        with patch("app.connectors.datasphere.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value = mock_instance

            mock_response = MagicMock()
            mock_response.json.return_value = {
                "access_token": "test-token",
                "expires_in": 3600,
            }
            mock_response.raise_for_status = MagicMock()
            mock_instance.post.return_value = mock_response

            await connector.connect()
            await connector.connect()  # Second call should be no-op

            # Client should only be created once
            mock_client.assert_called_once()

    @pytest.mark.asyncio
    async def test_close(self, connector):
        with patch("app.connectors.datasphere.httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_client.return_value = mock_instance

            mock_response = MagicMock()
            mock_response.json.return_value = {
                "access_token": "test-token",
                "expires_in": 3600,
            }
            mock_response.raise_for_status = MagicMock()
            mock_instance.post.return_value = mock_response

            await connector.connect()
            await connector.close()

            assert connector._client is None
            assert connector._token is None
            mock_instance.aclose.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_sql_without_connection(self, connector):
        """Should raise error if not connected."""
        from app.connectors.datasphere import DatasphereError

        with pytest.raises(DatasphereError, match="not connected"):
            await connector.execute_sql("SELECT * FROM test")

    @pytest.mark.asyncio
    async def test_execute_odata_without_connection(self, connector):
        """Should raise error if not connected."""
        from app.connectors.datasphere import DatasphereError

        with pytest.raises(DatasphereError, match="not connected"):
            await connector.execute_odata("test_entity")

    @pytest.mark.asyncio
    async def test_health_check_not_connected(self, connector):
        """Health check should return False if not connected."""
        result = await connector.health_check()
        assert result is False
