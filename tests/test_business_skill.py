"""Tests for Business skill."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core import Skill, SkillRegistry
from app.skills.business import BusinessSkill


class TestBusinessSkill:
    @pytest.fixture
    def mock_connector(self):
        """Create a mock connector for testing."""
        connector = MagicMock()
        connector.name = "mock"
        connector.execute_query = AsyncMock()
        return connector

    @pytest.fixture
    def skill(self, mock_connector):
        return BusinessSkill(mock_connector)

    def test_implements_protocol(self, skill):
        assert isinstance(skill, Skill)

    def test_name(self, skill):
        assert skill.name == "business"

    def test_description(self, skill):
        assert "SAP BW" in skill.description
        assert "business" in skill.description.lower()

    def test_has_tools(self, skill):
        assert len(skill.tools) == 8
        tool_names = [t.name for t in skill.tools]
        assert "get_fi_transactions" in tool_names
        assert "get_fi_summary" in tool_names
        assert "get_consolidation" in tool_names
        assert "get_bpc_data" in tool_names
        assert "get_company_revenue" in tool_names
        assert "compare_versions" in tool_names
        assert "get_gl_account_balance" in tool_names
        assert "get_intercompany" in tool_names

    def test_has_system_prompt(self, skill):
        assert skill.system_prompt is not None
        assert "business" in skill.system_prompt.lower()
        assert "SAP BW" in skill.system_prompt

    def test_has_knowledge_paths(self, skill):
        assert len(skill.knowledge_paths) == 1
        assert "business/knowledge" in skill.knowledge_paths[0]

    def test_registers_with_registry(self, skill):
        registry = SkillRegistry()
        registry.register(skill)

        assert registry.skill_count == 1
        assert registry.tool_count == 8

    def test_get_tool_found(self, skill):
        tool = skill.get_tool("get_fi_transactions")
        assert tool is not None
        assert tool.name == "get_fi_transactions"

    def test_get_tool_not_found(self, skill):
        tool = skill.get_tool("nonexistent")
        assert tool is None


class TestBusinessSkillTools:
    @pytest.fixture
    def mock_connector(self):
        connector = MagicMock()
        connector.name = "mock"
        connector.execute_query = AsyncMock()
        return connector

    @pytest.fixture
    def skill(self, mock_connector):
        return BusinessSkill(mock_connector)

    @pytest.mark.asyncio
    async def test_get_fi_transactions_tool(self, skill, mock_connector):
        mock_connector.execute_query.return_value = {
            "query_type": "fi_transactions",
            "count": 2,
            "transactions": [
                {"fiscper": "001", "compcode": "1000", "cs_trn_lc": 10000},
                {"fiscper": "001", "compcode": "1000", "cs_trn_lc": 5000},
            ],
        }

        tool = skill.get_tool("get_fi_transactions")
        result = await tool.aexecute(company_code="1000", fiscal_year=2024)

        assert result["query_type"] == "fi_transactions"
        assert result["count"] == 2
        mock_connector.execute_query.assert_called_once_with(
            "fi_transactions",
            {"company_code": "1000", "fiscal_year": 2024, "limit": 100},
        )

    @pytest.mark.asyncio
    async def test_get_fi_summary_tool(self, skill, mock_connector):
        mock_connector.execute_query.return_value = {
            "query_type": "fi_summary",
            "group_by": ["compcode", "fiscper"],
            "count": 3,
            "summary": [
                {"compcode": "1000", "fiscper": "001", "total_amount_lc": 50000},
            ],
        }

        tool = skill.get_tool("get_fi_summary")
        result = await tool.aexecute(company_code="1000")

        assert result["query_type"] == "fi_summary"
        mock_connector.execute_query.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_consolidation_tool(self, skill, mock_connector):
        mock_connector.execute_query.return_value = {
            "query_type": "consolidation",
            "count": 1,
            "data": [{"fiscper": "012", "compcode": "1000", "version": "ACTUAL"}],
        }

        tool = skill.get_tool("get_consolidation")
        result = await tool.aexecute(company_code="1000", version="ACTUAL")

        assert result["query_type"] == "consolidation"
        mock_connector.execute_query.assert_called_once_with(
            "consolidation",
            {"company_code": "1000", "version": "ACTUAL", "limit": 100},
        )

    @pytest.mark.asyncio
    async def test_get_bpc_data_tool(self, skill, mock_connector):
        mock_connector.execute_query.return_value = {
            "query_type": "bpc_data",
            "count": 1,
            "data": [{"fiscper": "012", "version": "BUDGET"}],
        }

        tool = skill.get_tool("get_bpc_data")
        result = await tool.aexecute(version="BUDGET")

        assert result["query_type"] == "bpc_data"
        mock_connector.execute_query.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_company_revenue_tool(self, skill, mock_connector):
        mock_connector.execute_query.return_value = {
            "query_type": "company_revenue",
            "count": 1,
            "revenue": [
                {"compcode": "1000", "revenue_lc": 1000000, "revenue_gc": 1100000}
            ],
        }

        tool = skill.get_tool("get_company_revenue")
        result = await tool.aexecute(company_code="1000")

        assert result["query_type"] == "company_revenue"
        mock_connector.execute_query.assert_called_once_with(
            "company_revenue",
            {"company_code": "1000", "version": "ACTUAL"},
        )

    @pytest.mark.asyncio
    async def test_compare_versions_tool(self, skill, mock_connector):
        mock_connector.execute_query.return_value = {
            "query_type": "version_comparison",
            "company_code": "1000",
            "compare_version": "BUDGET",
            "count": 2,
            "comparison": [
                {"grpacct": "G4000000", "actual_amount": 100000, "compare_amount": 90000},
                {"grpacct": "G5000000", "actual_amount": 50000, "compare_amount": 60000},
            ],
        }

        tool = skill.get_tool("compare_versions")
        result = await tool.aexecute(company_code="1000", compare_version="BUDGET")

        assert result["query_type"] == "version_comparison"
        assert "summary" in result
        assert result["summary"]["total_actual"] == 150000
        assert result["summary"]["total_budget"] == 150000
        assert result["summary"]["total_variance"] == 0

    @pytest.mark.asyncio
    async def test_compare_versions_favorable_variance(self, skill, mock_connector):
        mock_connector.execute_query.return_value = {
            "query_type": "version_comparison",
            "company_code": "1000",
            "compare_version": "BUDGET",
            "count": 1,
            "comparison": [
                {"actual_amount": 120000, "compare_amount": 100000},
            ],
        }

        tool = skill.get_tool("compare_versions")
        result = await tool.aexecute(company_code="1000")

        assert result["summary"]["status"] == "FAVORABLE"
        assert result["summary"]["variance_pct"] == 20.0

    @pytest.mark.asyncio
    async def test_compare_versions_unfavorable_variance(self, skill, mock_connector):
        mock_connector.execute_query.return_value = {
            "query_type": "version_comparison",
            "company_code": "1000",
            "compare_version": "BUDGET",
            "count": 1,
            "comparison": [
                {"actual_amount": 90000, "compare_amount": 100000},
            ],
        }

        tool = skill.get_tool("compare_versions")
        result = await tool.aexecute(company_code="1000")

        assert result["summary"]["status"] == "UNFAVORABLE"
        assert result["summary"]["variance_pct"] == -10.0

    @pytest.mark.asyncio
    async def test_get_gl_account_balance_tool(self, skill, mock_connector):
        mock_connector.execute_query.return_value = {
            "query_type": "gl_account_balance",
            "count": 1,
            "balances": [
                {
                    "gl_acct": "400000",
                    "debit_total": 100000,
                    "credit_total": 0,
                    "net_balance": 100000,
                }
            ],
        }

        tool = skill.get_tool("get_gl_account_balance")
        result = await tool.aexecute(gl_account="400000", company_code="1000")

        assert result["query_type"] == "gl_account_balance"
        mock_connector.execute_query.assert_called_once_with(
            "gl_account_balance",
            {"gl_account": "400000", "company_code": "1000"},
        )

    @pytest.mark.asyncio
    async def test_get_intercompany_tool(self, skill, mock_connector):
        mock_connector.execute_query.return_value = {
            "query_type": "intercompany",
            "count": 2,
            "transactions": [
                {"compcode": "1000", "partner_company": "2000", "amount_lc": 50000},
                {"compcode": "2000", "partner_company": "1000", "amount_lc": -50000},
            ],
        }

        tool = skill.get_tool("get_intercompany")
        result = await tool.aexecute(company_code="1000", partner_company="2000")

        assert result["query_type"] == "intercompany"
        assert result["count"] == 2
        mock_connector.execute_query.assert_called_once_with(
            "intercompany",
            {"company_code": "1000", "partner_company": "2000"},
        )


class TestBusinessSkillInputValidation:
    @pytest.fixture
    def mock_connector(self):
        connector = MagicMock()
        connector.name = "mock"
        connector.execute_query = AsyncMock(return_value={"count": 0, "data": []})
        return connector

    @pytest.fixture
    def skill(self, mock_connector):
        return BusinessSkill(mock_connector)

    @pytest.mark.asyncio
    async def test_fi_transactions_default_limit(self, skill, mock_connector):
        tool = skill.get_tool("get_fi_transactions")
        await tool.aexecute()

        call_args = mock_connector.execute_query.call_args
        assert call_args[0][1]["limit"] == 100

    @pytest.mark.asyncio
    async def test_fi_transactions_custom_limit(self, skill, mock_connector):
        tool = skill.get_tool("get_fi_transactions")
        await tool.aexecute(limit=50)

        call_args = mock_connector.execute_query.call_args
        assert call_args[0][1]["limit"] == 50

    @pytest.mark.asyncio
    async def test_company_revenue_default_version(self, skill, mock_connector):
        tool = skill.get_tool("get_company_revenue")
        await tool.aexecute()

        call_args = mock_connector.execute_query.call_args
        assert call_args[0][1]["version"] == "ACTUAL"

    @pytest.mark.asyncio
    async def test_compare_versions_default_values(self, skill, mock_connector):
        mock_connector.execute_query.return_value = {"comparison": []}

        tool = skill.get_tool("compare_versions")
        await tool.aexecute()

        call_args = mock_connector.execute_query.call_args
        assert call_args[0][1]["company_code"] == "1000"
        assert call_args[0][1]["compare_version"] == "BUDGET"
