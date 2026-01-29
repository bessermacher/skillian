"""Tests for data analyst skill."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.comparison_engine import ComparisonResult, DiffStatus, RowComparison
from app.core.query_engine import QueryResult
from app.core.source_registry import (
    ComparisonConfig,
    ComparisonThreshold,
    DimensionDef,
    MeasureDef,
    SourceDef,
)
from app.skills.data_analyst import (
    CompareSourcesInput,
    DataAnalystSkill,
    ListSourcesInput,
    QuerySourceInput,
)


@pytest.fixture
def mock_registry():
    """Mock source registry."""
    registry = MagicMock()
    registry.get_source_info.return_value = [
        {
            "name": "source_a",
            "description": "Source A",
            "dimensions": ["company", "period"],
            "measures": ["amount"],
        },
        {
            "name": "source_b",
            "description": "Source B",
            "dimensions": ["company", "period"],
            "measures": ["amount"],
        },
    ]
    registry.get_common_dimensions.return_value = ["company", "period"]
    registry.get.return_value = SourceDef(
        name="source_a",
        description="Source A",
        table="table_a",
        dimensions={
            "company": DimensionDef(column="comp_code"),
            "period": DimensionDef(column="fiscal_period"),
        },
        measures={
            "amount": MeasureDef(column="amount_lc", aggregation="sum"),
        },
        defaults={"dimensions": ["company", "period"]},
    )
    registry.comparison_config = ComparisonConfig(
        default_align_on=["company", "period"],
        thresholds={
            "match": ComparisonThreshold(absolute=100, percentage=1.0),
            "minor_diff": ComparisonThreshold(absolute=500, percentage=5.0),
        },
        cache_ttl_seconds=3600,
    )
    return registry


@pytest.fixture
def mock_query_engine():
    """Mock query engine."""
    engine = AsyncMock()
    engine.query = AsyncMock(
        return_value=QueryResult(
            source_name="source_a",
            rows=[
                {"company": "1000", "period": "2024001", "amount": 1000.0},
                {"company": "2000", "period": "2024001", "amount": 2000.0},
            ],
            dimensions_used=["company", "period"],
            measures_used=["amount"],
            row_count=2,
        )
    )
    return engine


@pytest.fixture
def mock_comparison_engine():
    """Mock comparison engine."""
    engine = AsyncMock()
    engine.compare = AsyncMock(
        return_value=ComparisonResult(
            source_a="source_a",
            source_b="source_b",
            measure="amount",
            align_on=["company", "period"],
            rows=[
                RowComparison(
                    key={"company": "1000", "period": "2024001"},
                    source_a_value=1000.0,
                    source_b_value=1000.0,
                    absolute_diff=0,
                    percentage_diff=0,
                    status=DiffStatus.MATCH,
                ),
                RowComparison(
                    key={"company": "2000", "period": "2024001"},
                    source_a_value=2000.0,
                    source_b_value=3000.0,
                    absolute_diff=1000.0,
                    percentage_diff=50.0,
                    status=DiffStatus.MAJOR_DIFF,
                ),
            ],
            summary={
                "measure": "amount",
                "total_rows": 2,
                "match_count": 1,
                "minor_diff_count": 0,
                "major_diff_count": 1,
                "total_source_a": 3000.0,
                "total_source_b": 4000.0,
                "total_absolute_diff": 1000.0,
            },
            cache_key="abc123",
        )
    )
    return engine


@pytest.fixture
def skill(mock_registry, mock_query_engine, mock_comparison_engine):
    """Create skill with mocks."""
    return DataAnalystSkill(mock_registry, mock_query_engine, mock_comparison_engine)


class TestDataAnalystSkill:
    def test_skill_name(self, skill):
        """Test skill has correct name."""
        assert skill.name == "data_analyst"

    def test_skill_description(self, skill):
        """Test skill has description."""
        assert "compare" in skill.description.lower()

    def test_skill_has_three_tools(self, skill):
        """Test skill provides exactly 3 tools."""
        assert len(skill.tools) == 3
        tool_names = [t.name for t in skill.tools]
        assert "list_sources" in tool_names
        assert "query_source" in tool_names
        assert "compare_sources" in tool_names

    def test_get_tool_by_name(self, skill):
        """Test getting tool by name."""
        tool = skill.get_tool("compare_sources")
        assert tool is not None
        assert tool.name == "compare_sources"

    def test_get_tool_not_found(self, skill):
        """Test getting non-existent tool returns None."""
        assert skill.get_tool("nonexistent") is None

    def test_system_prompt_not_empty(self, skill):
        """Test system prompt is provided."""
        assert len(skill.system_prompt) > 0

    def test_knowledge_paths(self, skill):
        """Test knowledge paths are provided."""
        assert len(skill.knowledge_paths) > 0


class TestListSourcesTool:
    def test_list_sources(self, skill, mock_registry):
        """Test list_sources tool."""
        tool = skill.get_tool("list_sources")
        result = tool.execute()

        assert "sources" in result
        assert len(result["sources"]) == 2
        assert result["total_count"] == 2
        assert "available_comparisons" in result

    def test_list_sources_shows_comparison_pairs(self, skill):
        """Test list_sources shows valid comparison pairs."""
        tool = skill.get_tool("list_sources")
        result = tool.execute()

        pairs = result["available_comparisons"]
        assert len(pairs) == 1
        assert pairs[0]["source_a"] == "source_a"
        assert pairs[0]["source_b"] == "source_b"
        assert "common_dimensions" in pairs[0]


class TestQuerySourceTool:
    @pytest.mark.asyncio
    async def test_query_source(self, skill, mock_query_engine):
        """Test query_source tool."""
        tool = skill.get_tool("query_source")
        result = await tool.aexecute(source="source_a")

        assert result["source"] == "source_a"
        assert result["row_count"] == 2
        assert len(result["rows"]) == 2

    @pytest.mark.asyncio
    async def test_query_source_with_filters(self, skill, mock_query_engine):
        """Test query_source with filters."""
        tool = skill.get_tool("query_source")
        await tool.aexecute(
            source="source_a",
            dimensions=["company"],
            measures=["amount"],
            filters={"company": "1000"},
        )

        mock_query_engine.query.assert_called_once()
        call_kwargs = mock_query_engine.query.call_args[1]
        assert call_kwargs["dimensions"] == ["company"]
        assert call_kwargs["measures"] == ["amount"]
        assert call_kwargs["filters"] == {"company": "1000"}


class TestCompareSourcesTool:
    @pytest.mark.asyncio
    async def test_compare_sources(self, skill, mock_comparison_engine):
        """Test compare_sources tool."""
        tool = skill.get_tool("compare_sources")
        result = await tool.aexecute(
            source_a="source_a", source_b="source_b", measure="amount"
        )

        assert "summary" in result
        assert result["summary"]["source_a"] == "source_a"
        assert result["summary"]["source_b"] == "source_b"
        assert result["summary"]["total_rows"] == 2
        assert "top_differences" in result
        assert "cache_key" in result
        assert "interpretation" in result

    @pytest.mark.asyncio
    async def test_compare_sources_with_align_on(self, skill, mock_comparison_engine):
        """Test compare_sources with custom alignment."""
        tool = skill.get_tool("compare_sources")
        await tool.aexecute(
            source_a="source_a",
            source_b="source_b",
            measure="amount",
            align_on=["company"],
        )

        mock_comparison_engine.compare.assert_called_once()
        call_kwargs = mock_comparison_engine.compare.call_args[1]
        assert call_kwargs["align_on"] == ["company"]

    @pytest.mark.asyncio
    async def test_compare_sources_top_differences(self, skill):
        """Test that top differences are properly formatted."""
        tool = skill.get_tool("compare_sources")
        result = await tool.aexecute(
            source_a="source_a", source_b="source_b", measure="amount"
        )

        # Should show the major diff at the top
        assert len(result["top_differences"]) == 1
        diff = result["top_differences"][0]
        assert diff["key"]["company"] == "2000"
        assert diff["diff"] == 1000.0
        assert diff["status"] == "major_diff"


class TestInputSchemas:
    def test_list_sources_input(self):
        """Test ListSourcesInput schema."""
        schema = ListSourcesInput()
        assert schema is not None

    def test_query_source_input(self):
        """Test QuerySourceInput schema."""
        schema = QuerySourceInput(source="test")
        assert schema.source == "test"
        assert schema.dimensions is None
        assert schema.measures is None
        assert schema.filters is None

    def test_compare_sources_input(self):
        """Test CompareSourcesInput schema."""
        schema = CompareSourcesInput(
            source_a="a", source_b="b", measure="amount"
        )
        assert schema.source_a == "a"
        assert schema.source_b == "b"
        assert schema.measure == "amount"
        assert schema.align_on is None
