"""Tests for Financial skill."""

import pytest

from app.connectors import MockConnector
from app.core import Skill, SkillRegistry
from app.skills.financial import FinancialSkill


class TestFinancialSkill:
    @pytest.fixture
    def connector(self):
        return MockConnector()

    @pytest.fixture
    def skill(self, connector):
        return FinancialSkill(connector)

    def test_implements_protocol(self, skill):
        assert isinstance(skill, Skill)

    def test_name(self, skill):
        assert skill.name == "financial"

    def test_has_tools(self, skill):
        assert len(skill.tools) == 5
        tool_names = [t.name for t in skill.tools]
        assert "get_cost_center" in tool_names
        assert "list_cost_centers" in tool_names
        assert "get_profit_center" in tool_names
        assert "search_transactions" in tool_names
        assert "compare_budget" in tool_names

    def test_has_system_prompt(self, skill):
        assert skill.system_prompt is not None
        assert "financial" in skill.system_prompt.lower()

    def test_registers_with_registry(self, skill):
        registry = SkillRegistry()
        registry.register(skill)

        assert registry.skill_count == 1
        assert registry.tool_count == 5

    @pytest.mark.asyncio
    async def test_get_cost_center_tool(self, skill):
        tool = skill.get_tool("get_cost_center")
        assert tool is not None

        result = await tool.aexecute(cost_center_id="CC-1001", fiscal_year=2024)

        assert result["id"] == "CC-1001"
        assert result["budget"] == 500000

    @pytest.mark.asyncio
    async def test_list_cost_centers_tool(self, skill):
        tool = skill.get_tool("list_cost_centers")
        result = await tool.aexecute(fiscal_year=2024)

        assert "cost_centers" in result
        assert result["count"] >= 1

    @pytest.mark.asyncio
    async def test_compare_budget_tool(self, skill):
        tool = skill.get_tool("compare_budget")
        result = await tool.aexecute(cost_center_id="CC-1001", fiscal_year=2024)

        assert "variance" in result
        assert "variance_pct" in result
        assert "utilization_pct" in result
        assert "status" in result
        assert "analysis" in result

    @pytest.mark.asyncio
    async def test_compare_budget_over_budget_status(self, connector, skill):
        # Add a cost center that's over budget
        connector.add_data(
            "cost_centers",
            "CC-OVER",
            {
                "id": "CC-OVER",
                "name": "Over Budget Center",
                "manager": "Test",
                "department": "Test",
                "fiscal_years": {
                    2024: {"budget": 100000, "actuals": 110000, "committed": 5000}
                },
            },
        )

        tool = skill.get_tool("compare_budget")
        result = await tool.aexecute(cost_center_id="CC-OVER", fiscal_year=2024)

        assert result["status"] == "OVER_BUDGET"
        assert result["utilization_pct"] > 100

    @pytest.mark.asyncio
    async def test_search_transactions_tool(self, skill):
        tool = skill.get_tool("search_transactions")
        result = await tool.aexecute(cost_center="CC-1001")

        assert "transactions" in result
        assert "count" in result
        assert "total_amount" in result