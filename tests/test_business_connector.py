"""Tests for Business Database Connector."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import Settings
from app.connectors import (
    BusinessDatabaseConnector,
    Connector,
    DataNotFoundError,
    QueryNotSupportedError,
    create_business_connector,
)

# Check if test database is available
BUSINESS_DB_URL = os.environ.get(
    "TEST_BUSINESS_DATABASE_URL",
    "postgresql://business:business@localhost:5433/business_db",
)


class TestBusinessDatabaseConnectorUnit:
    """Unit tests for BusinessDatabaseConnector using mocks."""

    @pytest.fixture
    def connector(self):
        """Create connector with test URL."""
        return BusinessDatabaseConnector(database_url=BUSINESS_DB_URL)

    def test_implements_protocol(self, connector):
        """Verify connector implements the Connector protocol."""
        assert isinstance(connector, Connector)

    def test_name(self, connector):
        """Verify connector name."""
        assert connector.name == "business"

    def test_database_url_stored(self, connector):
        """Verify database URL is stored."""
        assert connector.database_url == BUSINESS_DB_URL

    @pytest.mark.asyncio
    async def test_unsupported_query_type(self, connector):
        """Verify unsupported query types raise error."""
        with patch.object(connector, "_get_pool"):
            with pytest.raises(QueryNotSupportedError) as exc_info:
                await connector.execute_query("invalid_query_type", {})

            assert "invalid_query_type" in str(exc_info.value)
            assert exc_info.value.query_type == "invalid_query_type"

    @pytest.mark.asyncio
    async def test_health_check_success(self, connector):
        """Test health check with mocked successful connection."""
        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock(return_value=1)

        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock(return_value=AsyncMock())
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock()

        with patch.object(connector, "_get_pool", return_value=mock_pool):
            result = await connector.health_check()
            assert result is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self, connector):
        """Test health check with connection failure."""
        with patch.object(
            connector, "_get_pool", side_effect=Exception("Connection failed")
        ):
            result = await connector.health_check()
            assert result is False


class TestBusinessDatabaseConnectorQueryTypes:
    """Test query type handling with mocked database responses."""

    @pytest.fixture
    def connector(self):
        return BusinessDatabaseConnector(database_url=BUSINESS_DB_URL)

    @pytest.fixture
    def mock_pool(self):
        """Create a mock connection pool."""
        mock_conn = AsyncMock()
        mock_pool = AsyncMock()
        mock_pool.acquire = MagicMock(return_value=AsyncMock())
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock()
        return mock_pool, mock_conn

    @pytest.mark.asyncio
    async def test_fi_transactions_with_results(self, connector, mock_pool):
        """Test FI transactions query returns data."""
        pool, conn = mock_pool
        mock_row = {
            "fiscper": "2024001",
            "fiscyear": "2024",
            "compcode": "1000",
            "gl_acct": "4000000",
            "prof_ctr": "PC1001",
            "segment": "SEG01",
            "funcarea": "SALES",
            "customer": "CUST001",
            "vendor": None,
            "material": "MAT001",
            "postxt": "Product A Sales",
            "dochdtxt": "Invoice",
            "fidbcrin": "S",
            "cs_trn_lc": 125000.00,
            "curkey_lc": "EUR",
            "amnt_dc": 125000.00,
            "doc_currcy": "EUR",
            "quantity": 500.0,
            "unit": "PC",
            "pst_date": "2024-01-15",
            "doc_date": "2024-01-15",
        }
        conn.fetch = AsyncMock(return_value=[mock_row])

        with patch.object(connector, "_get_pool", return_value=pool):
            result = await connector.execute_query(
                "fi_transactions",
                {"company_code": "1000", "fiscal_year": "2024"},
            )

        assert result["query_type"] == "fi_transactions"
        assert result["count"] == 1
        assert len(result["transactions"]) == 1
        assert result["transactions"][0]["compcode"] == "1000"

    @pytest.mark.asyncio
    async def test_fi_transactions_not_found(self, connector, mock_pool):
        """Test FI transactions with no results raises error."""
        pool, conn = mock_pool
        conn.fetch = AsyncMock(return_value=[])

        with patch.object(connector, "_get_pool", return_value=pool):
            with pytest.raises(DataNotFoundError):
                await connector.execute_query(
                    "fi_transactions",
                    {"company_code": "9999"},
                )

    @pytest.mark.asyncio
    async def test_fi_summary_query(self, connector, mock_pool):
        """Test FI summary aggregation query."""
        pool, conn = mock_pool
        mock_row = {
            "compcode": "1000",
            "fiscper": "2024001",
            "total_amount_lc": 125000.00,
            "total_quantity": 500.0,
            "transaction_count": 2,
        }
        conn.fetch = AsyncMock(return_value=[mock_row])

        with patch.object(connector, "_get_pool", return_value=pool):
            result = await connector.execute_query(
                "fi_summary",
                {"company_code": "1000", "group_by": ["compcode", "fiscper"]},
            )

        assert result["query_type"] == "fi_summary"
        assert result["group_by"] == ["compcode", "fiscper"]
        assert len(result["summary"]) == 1

    @pytest.mark.asyncio
    async def test_consolidation_query(self, connector, mock_pool):
        """Test consolidation mart query."""
        pool, conn = mock_pool
        mock_row = {
            "fiscper": "2024001",
            "compcode": "1000",
            "version": "ACTUAL",
            "grpacct": "G4000000",
            "gl_acct": "4000000",
            "prof_ctr": "PC1001",
            "segment": "SEG01",
            "pc_area": "EMEA",
            "ppc_area": None,
            "pcompcd": None,
            "pcompany": None,
            "spec": "REV",
            "funcarea": "SALES",
            "prodh1": "PROD_A",
            "prodh2": "HARDWARE",
            "bpc_src": "FI",
            "cs_ytd_qty": 500.0,
            "cs_trn_qty": 500.0,
            "unit": "PC",
            "cs_ytd_lc": 125000.00,
            "cs_trn_lc": 125000.00,
            "curkey_lc": "EUR",
        }
        conn.fetch = AsyncMock(return_value=[mock_row])

        with patch.object(connector, "_get_pool", return_value=pool):
            result = await connector.execute_query(
                "consolidation",
                {"company_code": "1000", "version": "ACTUAL"},
            )

        assert result["query_type"] == "consolidation"
        assert len(result["data"]) == 1

    @pytest.mark.asyncio
    async def test_bpc_data_query(self, connector, mock_pool):
        """Test BPC reporting query."""
        pool, conn = mock_pool
        mock_row = {
            "fiscper": "2024001",
            "compcode": "1000",
            "version": "ACTUAL",
            "scope": "CONSOL",
            "grpacct": "G4000000",
            "funcarea": "SALES",
            "spec": "REVENUE",
            "dsource": "FI_DATA",
            "pc_area": "EMEA",
            "ppc_area": None,
            "pcompcd": None,
            "cs_trn_lc": 125000.00,
            "cs_trn_gc": 125000.00,
        }
        conn.fetch = AsyncMock(return_value=[mock_row])

        with patch.object(connector, "_get_pool", return_value=pool):
            result = await connector.execute_query(
                "bpc_data",
                {"company_code": "1000", "scope": "CONSOL"},
            )

        assert result["query_type"] == "bpc_data"
        assert len(result["data"]) == 1

    @pytest.mark.asyncio
    async def test_company_revenue_query(self, connector, mock_pool):
        """Test company revenue summary query."""
        pool, conn = mock_pool
        mock_row = {
            "compcode": "1000",
            "fiscper": "2024001",
            "version": "ACTUAL",
            "pc_area": "EMEA",
            "revenue_lc": 125000.00,
            "revenue_gc": 125000.00,
        }
        conn.fetch = AsyncMock(return_value=[mock_row])

        with patch.object(connector, "_get_pool", return_value=pool):
            result = await connector.execute_query(
                "company_revenue",
                {"company_code": "1000"},
            )

        assert result["query_type"] == "company_revenue"
        assert len(result["revenue"]) == 1

    @pytest.mark.asyncio
    async def test_version_comparison_query(self, connector, mock_pool):
        """Test actual vs budget comparison query."""
        pool, conn = mock_pool
        mock_row = {
            "compcode": "1000",
            "fiscper": "2024001",
            "grpacct": "G4000000",
            "funcarea": "SALES",
            "actual_amount": 125000.00,
            "compare_amount": 112500.00,
            "variance": 12500.00,
            "variance_pct": 11.11,
        }
        conn.fetch = AsyncMock(return_value=[mock_row])

        with patch.object(connector, "_get_pool", return_value=pool):
            result = await connector.execute_query(
                "version_comparison",
                {"company_code": "1000", "compare_version": "BUDGET"},
            )

        assert result["query_type"] == "version_comparison"
        assert result["compare_version"] == "BUDGET"
        assert len(result["comparison"]) == 1

    @pytest.mark.asyncio
    async def test_gl_account_balance_query(self, connector, mock_pool):
        """Test GL account balance query."""
        pool, conn = mock_pool
        mock_row = {
            "gl_acct": "4000000",
            "compcode": "1000",
            "fiscyear": "2024",
            "debit_total": 125000.00,
            "credit_total": -125000.00,
            "net_balance": 0.00,
            "currency": "EUR",
            "posting_count": 2,
        }
        conn.fetch = AsyncMock(return_value=[mock_row])

        with patch.object(connector, "_get_pool", return_value=pool):
            result = await connector.execute_query(
                "gl_account_balance",
                {"gl_account": "4000000", "company_code": "1000"},
            )

        assert result["query_type"] == "gl_account_balance"
        assert len(result["balances"]) == 1

    @pytest.mark.asyncio
    async def test_intercompany_query(self, connector, mock_pool):
        """Test intercompany transactions query."""
        pool, conn = mock_pool
        mock_row = {
            "compcode": "1000",
            "partner_company": "2000",
            "fiscper": "2024001",
            "version": "ACTUAL",
            "grpacct": "G4100000",
            "spec": "IC_REV",
            "pc_area": "EMEA",
            "partner_pc_area": "AMER",
            "amount_lc": 50000.00,
            "currency": "EUR",
        }
        conn.fetch = AsyncMock(return_value=[mock_row])

        with patch.object(connector, "_get_pool", return_value=pool):
            result = await connector.execute_query(
                "intercompany",
                {"company_code": "1000"},
            )

        assert result["query_type"] == "intercompany"
        assert len(result["transactions"]) == 1


class TestBusinessConnectorFactory:
    """Test the business connector factory function."""

    def test_create_business_connector_success(self):
        """Test factory creates connector with valid settings."""
        settings = Settings(
            business_database_url="postgresql://test:test@localhost:5433/test_db"
        )
        connector = create_business_connector(settings)

        assert isinstance(connector, BusinessDatabaseConnector)
        assert connector.database_url == "postgresql://test:test@localhost:5433/test_db"

    def test_create_business_connector_default_url(self):
        """Test factory uses default URL from settings."""
        settings = Settings()
        connector = create_business_connector(settings)

        assert isinstance(connector, BusinessDatabaseConnector)
        assert "business" in connector.database_url


# Integration tests - only run if database is available
@pytest.mark.integration
class TestBusinessDatabaseConnectorIntegration:
    """Integration tests that require a real database connection.

    These tests are skipped by default. Run with:
    pytest -m integration tests/test_business_connector.py
    """

    @pytest.fixture
    async def connector(self):
        """Create connector and ensure cleanup."""
        conn = BusinessDatabaseConnector(database_url=BUSINESS_DB_URL)
        yield conn
        await conn.close()

    @pytest.mark.asyncio
    async def test_real_health_check(self, connector):
        """Test actual database connectivity."""
        result = await connector.health_check()
        assert result is True

    @pytest.mark.asyncio
    async def test_real_fi_transactions(self, connector):
        """Query real FI transactions data."""
        result = await connector.execute_query(
            "fi_transactions",
            {"company_code": "1000", "fiscal_year": "2024", "limit": 5},
        )

        assert result["query_type"] == "fi_transactions"
        assert result["count"] <= 5

    @pytest.mark.asyncio
    async def test_real_consolidation(self, connector):
        """Query real consolidation data."""
        result = await connector.execute_query(
            "consolidation",
            {"company_code": "1000", "version": "ACTUAL", "limit": 5},
        )

        assert result["query_type"] == "consolidation"

    @pytest.mark.asyncio
    async def test_real_bpc_data(self, connector):
        """Query real BPC reporting data."""
        result = await connector.execute_query(
            "bpc_data",
            {"company_code": "1000", "version": "ACTUAL", "limit": 5},
        )

        assert result["query_type"] == "bpc_data"

    @pytest.mark.asyncio
    async def test_real_version_comparison(self, connector):
        """Test real actual vs budget comparison."""
        result = await connector.execute_query(
            "version_comparison",
            {"company_code": "1000", "fiscal_period": "2024001"},
        )

        assert result["query_type"] == "version_comparison"
        assert "comparison" in result
