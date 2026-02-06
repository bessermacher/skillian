"""Tests for data analyst skill."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core import ConfiguredSkill
from app.core.skill_loader import SkillLoader
from app.skills.data_analyst.comparison_engine import ComparisonResult, DiffStatus, RowComparison
from app.skills.data_analyst.query_engine import QueryResult
from app.skills.data_analyst.source_registry import (
    ComparisonConfig,
    ComparisonThreshold,
    DimensionDef,
    MeasureDef,
    SourceDef,
    SourceRegistry,
)
from app.skills.data_analyst.tools import DataAnalystTools


@pytest.fixture
def mock_registry():
    """Mock source registry."""
    registry = MagicMock(spec=SourceRegistry)
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
def tool_impl(mock_registry, mock_query_engine, mock_comparison_engine):
    """Create tool implementation with mocks."""
    return DataAnalystTools(mock_registry, mock_query_engine, mock_comparison_engine)


@pytest.fixture
def mock_connector():
    """Mock database connector."""
    connector = MagicMock()
    return connector


@pytest.fixture
def skill_loader(mock_connector):
    """Create skill loader with mock connector."""
    return SkillLoader(
        skills_dir=Path("app/skills"),
        connector_factory={"business": mock_connector},
    )


class TestDataAnalystSkillLoading:
    """Test loading data_analyst skill via SkillLoader."""

    def test_skill_discovered(self, skill_loader):
        """Test skill is discovered."""
        skills = skill_loader.discover_skills()
        assert "data_analyst" in skills

    def test_skill_metadata(self, skill_loader):
        """Test loading skill metadata."""
        skill = skill_loader.load_skill_metadata("data_analyst")
        assert skill.name == "data_analyst"
        assert "compare" in skill.description.lower() or "analyze" in skill.description.lower()


class TestDataAnalystTools:
    """Test DataAnalystTools class directly."""

    def test_list_sources(self, tool_impl, mock_registry):
        """Test list_sources tool."""
        result = tool_impl.list_sources()

        assert "sources" in result
        assert len(result["sources"]) == 2
        assert result["total_count"] == 2
        assert "available_comparisons" in result

    def test_list_sources_shows_comparison_pairs(self, tool_impl):
        """Test list_sources shows valid comparison pairs."""
        result = tool_impl.list_sources()

        pairs = result["available_comparisons"]
        assert len(pairs) == 1
        assert pairs[0]["source_a"] == "source_a"
        assert pairs[0]["source_b"] == "source_b"
        assert "common_dimensions" in pairs[0]

    @pytest.mark.asyncio
    async def test_query_source(self, tool_impl, mock_query_engine):
        """Test query_source tool."""
        result = await tool_impl.query_source(source="source_a")

        assert result["source"] == "source_a"
        assert result["row_count"] == 2
        assert len(result["rows"]) == 2

    @pytest.mark.asyncio
    async def test_query_source_with_filters(self, tool_impl, mock_query_engine):
        """Test query_source with filters."""
        await tool_impl.query_source(
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

    @pytest.mark.asyncio
    async def test_compare_sources(self, tool_impl, mock_comparison_engine):
        """Test compare_sources tool."""
        result = await tool_impl.compare_sources(
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
    async def test_compare_sources_with_align_on(self, tool_impl, mock_comparison_engine):
        """Test compare_sources with custom alignment."""
        await tool_impl.compare_sources(
            source_a="source_a",
            source_b="source_b",
            measure="amount",
            align_on=["company"],
        )

        mock_comparison_engine.compare.assert_called_once()
        call_kwargs = mock_comparison_engine.compare.call_args[1]
        assert call_kwargs["align_on"] == ["company"]

    @pytest.mark.asyncio
    async def test_compare_sources_top_differences(self, tool_impl):
        """Test that top differences are properly formatted."""
        result = await tool_impl.compare_sources(
            source_a="source_a", source_b="source_b", measure="amount"
        )

        # Should show the major diff at the top
        assert len(result["top_differences"]) == 1
        diff = result["top_differences"][0]
        assert diff["key"]["company"] == "2000"
        assert diff["diff"] == 1000.0
        assert diff["status"] == "major_diff"
