"""Tests for connectors."""

import pytest

from app.connectors import (
    Connector,
    DataNotFoundError,
    MockConnector,
    QueryNotSupportedError,
)


class TestMockConnector:
    @pytest.fixture
    def connector(self):
        return MockConnector()

    def test_implements_protocol(self, connector):
        assert isinstance(connector, Connector)

    def test_name(self, connector):
        assert connector.name == "mock"

    @pytest.mark.asyncio
    async def test_health_check(self, connector):
        result = await connector.health_check()
        assert result is True

    @pytest.mark.asyncio
    async def test_query_cost_center(self, connector):
        result = await connector.execute_query(
            "cost_center",
            {"cost_center_id": "CC-1001", "fiscal_year": 2024},
        )

        assert result["id"] == "CC-1001"
        assert result["name"] == "IT Operations"
        assert result["budget"] == 500000
        assert result["actuals"] == 425000
        assert "available" in result

    @pytest.mark.asyncio
    async def test_query_cost_center_not_found(self, connector):
        with pytest.raises(DataNotFoundError):
            await connector.execute_query(
                "cost_center",
                {"cost_center_id": "INVALID"},
            )

    @pytest.mark.asyncio
    async def test_query_cost_center_list(self, connector):
        result = await connector.execute_query(
            "cost_center_list",
            {"fiscal_year": 2024},
        )

        assert "cost_centers" in result
        assert result["count"] >= 1

    @pytest.mark.asyncio
    async def test_query_cost_center_list_with_department(self, connector):
        result = await connector.execute_query(
            "cost_center_list",
            {"fiscal_year": 2024, "department": "Information Technology"},
        )

        assert result["count"] == 1
        assert result["cost_centers"][0]["id"] == "CC-1001"

    @pytest.mark.asyncio
    async def test_query_profit_center(self, connector):
        result = await connector.execute_query(
            "profit_center",
            {"profit_center_id": "PC-2001"},
        )

        assert result["id"] == "PC-2001"
        assert result["name"] == "North America"
        assert "revenue_ytd" in result

    @pytest.mark.asyncio
    async def test_query_transactions(self, connector):
        result = await connector.execute_query(
            "transactions",
            {"cost_center": "CC-1001"},
        )

        assert "transactions" in result
        assert result["count"] >= 1
        assert all(t["cost_center"] == "CC-1001" for t in result["transactions"])

    @pytest.mark.asyncio
    async def test_query_transactions_with_filters(self, connector):
        result = await connector.execute_query(
            "transactions",
            {
                "start_date": "2024-02-01",
                "end_date": "2024-02-28",
            },
        )

        assert "transactions" in result
        for txn in result["transactions"]:
            assert txn["date"] >= "2024-02-01"
            assert txn["date"] <= "2024-02-28"

    @pytest.mark.asyncio
    async def test_unsupported_query_type(self, connector):
        with pytest.raises(QueryNotSupportedError):
            await connector.execute_query("invalid_type", {})

    def test_add_custom_data(self, connector):
        connector.add_data(
            "cost_centers",
            "CC-TEST",
            {
                "id": "CC-TEST",
                "name": "Test Center",
                "manager": "Test Manager",
                "department": "Test",
                "fiscal_years": {2024: {"budget": 100, "actuals": 50, "committed": 10}},
            },
        )

        assert "CC-TEST" in connector._data["cost_centers"]

    @pytest.mark.asyncio
    async def test_query_custom_data(self, connector):
        connector.add_data(
            "cost_centers",
            "CC-CUSTOM",
            {
                "id": "CC-CUSTOM",
                "name": "Custom Center",
                "manager": "Custom Manager",
                "department": "Custom",
                "fiscal_years": {2024: {"budget": 999, "actuals": 111, "committed": 0}},
            },
        )

        result = await connector.execute_query(
            "cost_center",
            {"cost_center_id": "CC-CUSTOM"},
        )

        assert result["id"] == "CC-CUSTOM"
        assert result["budget"] == 999