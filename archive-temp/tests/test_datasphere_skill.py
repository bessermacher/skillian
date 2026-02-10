"""Tests for Datasphere skill."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.skill_loader import SkillLoader
from app.skills.datasphere import tools as datasphere_tools


@pytest.fixture
def mock_connector():
    connector = MagicMock()
    connector.space = "TEST_SPACE"
    connector.list_entities = AsyncMock(return_value=["view1", "view2"])
    connector.execute_odata = AsyncMock(return_value=[{"id": 1, "value": 100}])
    connector.execute_sql = AsyncMock(return_value=[{"id": 1, "value": 100}])
    connector.get_metadata = AsyncMock(return_value={"fields": []})
    return connector


@pytest.fixture
def skill_loader(mock_connector):
    """Create skill loader with mock connector."""
    return SkillLoader(
        skills_dir=Path("app/skills"),
        connector_factory={"datasphere": mock_connector},
    )


@pytest.fixture
def skill(skill_loader):
    """Load the datasphere skill."""
    return skill_loader.load_skill("datasphere")


class TestDatasphereSkill:
    def test_skill_name(self, skill):
        assert skill.name == "datasphere"

    def test_skill_description(self, skill):
        assert "Datasphere" in skill.description
        assert "querying" in skill.description.lower()

    def test_skill_has_tools(self, skill):
        assert len(skill.tools) == 5

    def test_tool_names(self, skill):
        tool_names = [t.name for t in skill.tools]
        assert "ds_list_entities" in tool_names
        assert "ds_query_entity" in tool_names
        assert "ds_execute_sql" in tool_names
        assert "ds_get_metadata" in tool_names
        assert "ds_compare_entities" in tool_names

    def test_get_tool(self, skill):
        tool = skill.get_tool("ds_list_entities")
        assert tool is not None
        assert tool.name == "ds_list_entities"

    def test_get_tool_not_found(self, skill):
        tool = skill.get_tool("nonexistent_tool")
        assert tool is None

    def test_system_prompt_not_empty(self, skill):
        assert len(skill.system_prompt) > 100
        assert "Datasphere" in skill.system_prompt

    def test_knowledge_paths(self, skill):
        paths = skill.knowledge_paths
        # knowledge dir may or may not exist
        assert isinstance(paths, list)


class TestDatasphereToolFunctions:
    """Test standalone tool functions."""

    @pytest.fixture(autouse=True)
    def setup_connector(self, mock_connector):
        """Set up the module-level connector for tests."""
        # Reset the module-level connector
        datasphere_tools._connector = mock_connector
        yield
        datasphere_tools._connector = None

    @pytest.mark.asyncio
    async def test_list_entities(self, mock_connector):
        result = await datasphere_tools.list_entities(connector=mock_connector)

        assert result["count"] == 2
        assert "view1" in result["entities"]
        assert "view2" in result["entities"]
        assert result["space"] == "TEST_SPACE"

    @pytest.mark.asyncio
    async def test_query_entity(self, mock_connector):
        result = await datasphere_tools.query_entity(
            entity="test_view",
            top=10,
            connector=mock_connector,
        )

        assert result["entity"] == "test_view"
        assert result["row_count"] == 1
        assert len(result["rows"]) == 1

        mock_connector.execute_odata.assert_called_once_with(
            entity="test_view",
            select=None,
            filter_expr=None,
            top=10,
            orderby=None,
        )

    @pytest.mark.asyncio
    async def test_query_entity_with_filter(self, mock_connector):
        result = await datasphere_tools.query_entity(
            entity="test_view",
            filter_expr="MATERIAL eq 'MAT001'",
            select=["MATERIAL", "AMOUNT"],
            top=50,
            orderby="AMOUNT desc",
            connector=mock_connector,
        )

        mock_connector.execute_odata.assert_called_once_with(
            entity="test_view",
            select=["MATERIAL", "AMOUNT"],
            filter_expr="MATERIAL eq 'MAT001'",
            top=50,
            orderby="AMOUNT desc",
        )

    @pytest.mark.asyncio
    async def test_execute_sql(self, mock_connector):
        result = await datasphere_tools.execute_sql(
            query="SELECT * FROM test_view",
            connector=mock_connector,
        )

        assert result["row_count"] == 1
        mock_connector.execute_sql.assert_called_once_with("SELECT * FROM test_view")

    @pytest.mark.asyncio
    async def test_execute_sql_rejects_non_select(self, mock_connector):
        result = await datasphere_tools.execute_sql(
            query="DELETE FROM test_view",
            connector=mock_connector,
        )

        assert "error" in result
        assert "SELECT" in result["error"]
        mock_connector.execute_sql.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_entity_metadata(self, mock_connector):
        result = await datasphere_tools.get_entity_metadata(
            entity="test_view",
            connector=mock_connector,
        )

        assert result["entity"] == "test_view"
        assert "metadata" in result
        mock_connector.get_metadata.assert_called_once_with("test_view")

    @pytest.mark.asyncio
    async def test_compare_entities(self, mock_connector):
        mock_connector.execute_odata = AsyncMock(
            side_effect=[
                [{"MATERIAL": "M1", "AMOUNT": 100}, {"MATERIAL": "M2", "AMOUNT": 200}],
                [{"MATERIAL": "M1", "AMOUNT": 110}, {"MATERIAL": "M2", "AMOUNT": 190}],
            ]
        )

        result = await datasphere_tools.compare_entities(
            entity_a="source_view",
            entity_b="target_view",
            measure="AMOUNT",
            group_by=["MATERIAL"],
            connector=mock_connector,
        )

        assert result["entity_a"] == "source_view"
        assert result["entity_b"] == "target_view"
        assert "comparison" in result
        assert "summary" in result

    @pytest.mark.asyncio
    async def test_compare_entities_without_group_by(self, mock_connector):
        mock_connector.execute_odata = AsyncMock(
            side_effect=[
                [{"AMOUNT": 100}, {"AMOUNT": 200}],
                [{"AMOUNT": 150}, {"AMOUNT": 180}],
            ]
        )

        result = await datasphere_tools.compare_entities(
            entity_a="source_view",
            entity_b="target_view",
            measure="AMOUNT",
            connector=mock_connector,
        )

        # Without group_by, it should sum totals
        assert len(result["comparison"]) == 1
        assert result["comparison"][0]["value_a"] == 300
        assert result["comparison"][0]["value_b"] == 330


class TestComparisonHelpers:
    def test_build_comparison_with_group_by(self):
        results_a = [
            {"MATERIAL": "M1", "AMOUNT": 100},
            {"MATERIAL": "M2", "AMOUNT": 200},
        ]
        results_b = [
            {"MATERIAL": "M1", "AMOUNT": 110},
            {"MATERIAL": "M2", "AMOUNT": 190},
        ]

        comparison = datasphere_tools._build_comparison(results_a, results_b, "AMOUNT", ["MATERIAL"])

        assert len(comparison) == 2

        m1_record = next(c for c in comparison if c["MATERIAL"] == "M1")
        assert m1_record["value_a"] == 100
        assert m1_record["value_b"] == 110
        assert m1_record["difference"] == 10

        m2_record = next(c for c in comparison if c["MATERIAL"] == "M2")
        assert m2_record["value_a"] == 200
        assert m2_record["value_b"] == 190
        assert m2_record["difference"] == -10

    def test_summarize_comparison(self):
        comparison = [
            {
                "MATERIAL": "M1",
                "value_a": 100,
                "value_b": 110,
                "difference": 10,
                "difference_pct": 10.0,
            },
            {
                "MATERIAL": "M2",
                "value_a": 200,
                "value_b": 190,
                "difference": -10,
                "difference_pct": -5.0,
            },
        ]

        summary = datasphere_tools._summarize_comparison(comparison, "AMOUNT")

        assert summary["total_a"] == 300
        assert summary["total_b"] == 300
        assert summary["total_difference"] == 0
        assert summary["records_compared"] == 2
        assert summary["mismatches_over_1pct"] == 2
