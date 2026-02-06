"""Tests for comparison engine."""

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.skills.data_analyst.comparison_engine import (
    ComparisonCache,
    ComparisonEngine,
    ComparisonResult,
    DiffStatus,
    RowComparison,
)
from app.skills.data_analyst.query_engine import QueryResult
from app.skills.data_analyst.source_registry import (
    ComparisonConfig,
    ComparisonThreshold,
    DimensionDef,
    MeasureDef,
    SourceDef,
)


@pytest.fixture
def source_a():
    """First source definition."""
    return SourceDef(
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


@pytest.fixture
def source_b():
    """Second source definition."""
    return SourceDef(
        name="source_b",
        description="Source B",
        table="table_b",
        dimensions={
            "company": DimensionDef(column="company_id"),
            "period": DimensionDef(column="period_id"),
        },
        measures={
            "amount": MeasureDef(column="value", aggregation="sum"),
        },
        defaults={"dimensions": ["company", "period"]},
    )


@pytest.fixture
def comparison_config():
    """Comparison config with thresholds."""
    return ComparisonConfig(
        default_align_on=["company", "period"],
        thresholds={
            "match": ComparisonThreshold(absolute=100, percentage=1.0),
            "minor_diff": ComparisonThreshold(absolute=500, percentage=5.0),
        },
        cache_ttl_seconds=3600,
    )


@pytest.fixture
def mock_registry(source_a, source_b, comparison_config):
    """Mock source registry."""
    registry = MagicMock()
    registry.get.side_effect = lambda name: source_a if name == "source_a" else source_b
    registry.comparison_config = comparison_config
    return registry


@pytest.fixture
def mock_query_engine():
    """Mock query engine."""
    engine = AsyncMock()
    engine.query = AsyncMock()
    return engine


@pytest.fixture
def comparison_engine(mock_registry, mock_query_engine):
    """Comparison engine with mocks."""
    return ComparisonEngine(mock_registry, mock_query_engine)


class TestComparisonCache:
    def test_set_and_get(self):
        """Test basic cache set and get."""
        cache = ComparisonCache(ttl_seconds=3600)
        result = ComparisonResult(
            source_a="a",
            source_b="b",
            measure="amount",
            align_on=["company"],
            rows=[],
            summary={},
            cache_key="test_key",
        )

        cache.set(result)
        retrieved = cache.get("test_key")

        assert retrieved is not None
        assert retrieved.cache_key == "test_key"

    def test_get_nonexistent(self):
        """Test get returns None for missing key."""
        cache = ComparisonCache()
        assert cache.get("nonexistent") is None

    def test_ttl_expiry(self):
        """Test cache entry expires after TTL."""
        cache = ComparisonCache(ttl_seconds=1)
        result = ComparisonResult(
            source_a="a",
            source_b="b",
            measure="amount",
            align_on=["company"],
            rows=[],
            summary={},
            cache_key="test_key",
            timestamp=time.time() - 2,  # 2 seconds ago
        )

        cache.set(result)
        assert cache.get("test_key") is None

    def test_clear(self):
        """Test cache clear."""
        cache = ComparisonCache()
        result = ComparisonResult(
            source_a="a",
            source_b="b",
            measure="amount",
            align_on=["company"],
            rows=[],
            summary={},
            cache_key="test_key",
        )

        cache.set(result)
        assert cache.size() == 1

        cache.clear()
        assert cache.size() == 0


class TestComparisonEngine:
    @pytest.mark.asyncio
    async def test_compare_matching_data(
        self, comparison_engine, mock_query_engine, source_a, source_b
    ):
        """Test comparison with matching data."""
        mock_query_engine.query.side_effect = [
            QueryResult(
                source_name="source_a",
                rows=[
                    {"company": "1000", "period": "2024001", "amount": 1000.0},
                ],
                dimensions_used=["company", "period"],
                measures_used=["amount"],
                row_count=1,
            ),
            QueryResult(
                source_name="source_b",
                rows=[
                    {"company": "1000", "period": "2024001", "amount": 1000.0},
                ],
                dimensions_used=["company", "period"],
                measures_used=["amount"],
                row_count=1,
            ),
        ]

        result = await comparison_engine.compare(
            "source_a", "source_b", "amount", align_on=["company", "period"]
        )

        assert result.source_a == "source_a"
        assert result.source_b == "source_b"
        assert result.total_rows == 1
        assert result.match_count == 1
        assert result.diff_count == 0

    @pytest.mark.asyncio
    async def test_compare_with_differences(
        self, comparison_engine, mock_query_engine
    ):
        """Test comparison with differences."""
        mock_query_engine.query.side_effect = [
            QueryResult(
                source_name="source_a",
                rows=[
                    {"company": "1000", "period": "2024001", "amount": 1000.0},
                    {"company": "2000", "period": "2024001", "amount": 5000.0},
                ],
                dimensions_used=["company", "period"],
                measures_used=["amount"],
                row_count=2,
            ),
            QueryResult(
                source_name="source_b",
                rows=[
                    {"company": "1000", "period": "2024001", "amount": 1050.0},
                    {"company": "2000", "period": "2024001", "amount": 10000.0},
                ],
                dimensions_used=["company", "period"],
                measures_used=["amount"],
                row_count=2,
            ),
        ]

        result = await comparison_engine.compare(
            "source_a", "source_b", "amount", align_on=["company", "period"]
        )

        assert result.total_rows == 2

        # First row: diff of 50, percentage is 5% (within minor_diff threshold)
        row1 = next(r for r in result.rows if r.key["company"] == "1000")
        assert row1.status == DiffStatus.MINOR_DIFF

        # Second row: diff of 5000, percentage is 100% (major diff)
        row2 = next(r for r in result.rows if r.key["company"] == "2000")
        assert row2.status == DiffStatus.MAJOR_DIFF

    @pytest.mark.asyncio
    async def test_compare_with_missing_rows(
        self, comparison_engine, mock_query_engine
    ):
        """Test comparison where one source has rows the other doesn't."""
        mock_query_engine.query.side_effect = [
            QueryResult(
                source_name="source_a",
                rows=[
                    {"company": "1000", "period": "2024001", "amount": 1000.0},
                    {"company": "2000", "period": "2024001", "amount": 2000.0},
                ],
                dimensions_used=["company", "period"],
                measures_used=["amount"],
                row_count=2,
            ),
            QueryResult(
                source_name="source_b",
                rows=[
                    {"company": "1000", "period": "2024001", "amount": 1000.0},
                    # Missing company 2000
                    {"company": "3000", "period": "2024001", "amount": 3000.0},
                ],
                dimensions_used=["company", "period"],
                measures_used=["amount"],
                row_count=2,
            ),
        ]

        result = await comparison_engine.compare(
            "source_a", "source_b", "amount", align_on=["company", "period"]
        )

        # Should have 3 unique keys
        assert result.total_rows == 3

        # Check missing in source_b
        row_2000 = next(r for r in result.rows if r.key["company"] == "2000")
        assert row_2000.source_a_value == 2000.0
        assert row_2000.source_b_value is None

        # Check missing in source_a
        row_3000 = next(r for r in result.rows if r.key["company"] == "3000")
        assert row_3000.source_a_value is None
        assert row_3000.source_b_value == 3000.0

    @pytest.mark.asyncio
    async def test_compare_uses_cache(
        self, comparison_engine, mock_query_engine
    ):
        """Test that subsequent calls use cache."""
        mock_query_engine.query.side_effect = [
            QueryResult(
                source_name="source_a",
                rows=[{"company": "1000", "period": "2024001", "amount": 1000.0}],
                dimensions_used=["company", "period"],
                measures_used=["amount"],
                row_count=1,
            ),
            QueryResult(
                source_name="source_b",
                rows=[{"company": "1000", "period": "2024001", "amount": 1000.0}],
                dimensions_used=["company", "period"],
                measures_used=["amount"],
                row_count=1,
            ),
        ]

        # First call
        result1 = await comparison_engine.compare(
            "source_a", "source_b", "amount", align_on=["company", "period"]
        )

        # Second call should use cache
        result2 = await comparison_engine.compare(
            "source_a", "source_b", "amount", align_on=["company", "period"]
        )

        # Query engine should only be called twice (first call)
        assert mock_query_engine.query.call_count == 2
        assert result1.cache_key == result2.cache_key

    @pytest.mark.asyncio
    async def test_compare_invalid_measure(self, comparison_engine, mock_registry):
        """Test error when measure not found in source."""
        with pytest.raises(ValueError, match="not found in source_a"):
            await comparison_engine.compare(
                "source_a", "source_b", "invalid_measure"
            )

    def test_generate_cache_key_deterministic(self, comparison_engine):
        """Test cache key generation is deterministic."""
        key1 = comparison_engine._generate_cache_key(
            "a", "b", "amount", ["company", "period"], {"company": "1000"}
        )
        key2 = comparison_engine._generate_cache_key(
            "a", "b", "amount", ["company", "period"], {"company": "1000"}
        )

        assert key1 == key2

    def test_generate_cache_key_different_for_different_inputs(
        self, comparison_engine
    ):
        """Test different inputs produce different cache keys."""
        key1 = comparison_engine._generate_cache_key(
            "a", "b", "amount", ["company"], None
        )
        key2 = comparison_engine._generate_cache_key(
            "a", "b", "amount", ["period"], None
        )

        assert key1 != key2


class TestComparisonResult:
    def test_properties(self):
        """Test ComparisonResult computed properties."""
        rows = [
            RowComparison(
                key={"company": "1"},
                source_a_value=100,
                source_b_value=100,
                absolute_diff=0,
                percentage_diff=0,
                status=DiffStatus.MATCH,
            ),
            RowComparison(
                key={"company": "2"},
                source_a_value=100,
                source_b_value=200,
                absolute_diff=100,
                percentage_diff=100,
                status=DiffStatus.MAJOR_DIFF,
            ),
        ]

        result = ComparisonResult(
            source_a="a",
            source_b="b",
            measure="amount",
            align_on=["company"],
            rows=rows,
            summary={},
            cache_key="test",
        )

        assert result.total_rows == 2
        assert result.match_count == 1
        assert result.diff_count == 1
