"""Tests for query engine."""

from unittest.mock import AsyncMock

import pytest

from app.skills.data_analyst.query_engine import QueryEngine, QueryResult
from app.skills.data_analyst.source_registry import DimensionDef, MeasureDef, SourceDef


@pytest.fixture
def sample_source():
    """Create a sample source definition."""
    return SourceDef(
        name="test_source",
        description="Test source",
        table="test_table",
        dimensions={
            "company": DimensionDef(column="comp_code"),
            "period": DimensionDef(column="fiscal_period"),
            "account": DimensionDef(column="gl_account"),
        },
        measures={
            "amount": MeasureDef(column="amount_lc", aggregation="sum"),
            "quantity": MeasureDef(column="qty", aggregation="sum"),
        },
        defaults={"dimensions": ["company", "period"]},
    )


@pytest.fixture
def mock_connector():
    """Create a mock PostgresConnector."""
    connector = AsyncMock()
    connector.execute = AsyncMock(
        return_value=[
            {"company": "1000", "period": "2024001", "amount": 1000.0},
            {"company": "1000", "period": "2024002", "amount": 2000.0},
        ]
    )
    return connector


@pytest.fixture
def engine(mock_connector):
    """Create query engine with mock connector."""
    return QueryEngine(mock_connector)


class TestQueryEngine:
    @pytest.mark.asyncio
    async def test_query_with_defaults(self, engine, sample_source, mock_connector):
        """Test query uses default dimensions when not specified."""
        result = await engine.query(sample_source)

        assert result.source_name == "test_source"
        assert result.dimensions_used == ["company", "period"]
        assert result.measures_used == ["amount", "quantity"]
        assert result.row_count == 2

        # Verify SQL was built correctly
        call_args = mock_connector.execute.call_args
        sql = call_args[0][0]
        assert "comp_code AS company" in sql
        assert "fiscal_period AS period" in sql
        assert "SUM(amount_lc) AS amount" in sql
        assert "SUM(qty) AS quantity" in sql
        assert "GROUP BY comp_code, fiscal_period" in sql

    @pytest.mark.asyncio
    async def test_query_with_specific_dimensions(
        self, engine, sample_source, mock_connector
    ):
        """Test query with explicitly specified dimensions."""
        result = await engine.query(
            sample_source, dimensions=["company", "account"], measures=["amount"]
        )

        assert result.dimensions_used == ["company", "account"]
        assert result.measures_used == ["amount"]

        sql = mock_connector.execute.call_args[0][0]
        assert "comp_code AS company" in sql
        assert "gl_account AS account" in sql
        assert "fiscal_period" not in sql

    @pytest.mark.asyncio
    async def test_query_with_filters(self, engine, sample_source, mock_connector):
        """Test query with filter conditions."""
        await engine.query(
            sample_source,
            dimensions=["period"],
            measures=["amount"],
            filters={"company": "1000"},
        )

        call_args = mock_connector.execute.call_args
        sql = call_args[0][0]
        params = call_args[0][1]

        assert "WHERE comp_code = $1" in sql
        assert params == ["1000"]

    @pytest.mark.asyncio
    async def test_query_with_multiple_filters(
        self, engine, sample_source, mock_connector
    ):
        """Test query with multiple filter conditions."""
        await engine.query(
            sample_source,
            dimensions=["account"],
            measures=["amount"],
            filters={"company": "1000", "period": "2024001"},
        )

        call_args = mock_connector.execute.call_args
        sql = call_args[0][0]
        params = call_args[0][1]

        assert "WHERE" in sql
        assert "$1" in sql
        assert "$2" in sql
        assert len(params) == 2

    @pytest.mark.asyncio
    async def test_query_unknown_dimension_raises(self, engine, sample_source):
        """Test that unknown dimension raises ValueError."""
        with pytest.raises(ValueError, match="Unknown dimension: unknown"):
            await engine.query(sample_source, dimensions=["unknown"])

    @pytest.mark.asyncio
    async def test_query_unknown_measure_raises(self, engine, sample_source):
        """Test that unknown measure raises ValueError."""
        with pytest.raises(ValueError, match="Unknown measure: unknown"):
            await engine.query(sample_source, measures=["unknown"])

    @pytest.mark.asyncio
    async def test_query_unknown_filter_dimension_raises(self, engine, sample_source):
        """Test that unknown filter dimension raises ValueError."""
        with pytest.raises(ValueError, match="Unknown filter dimension: unknown"):
            await engine.query(sample_source, filters={"unknown": "value"})

    def test_build_query_basic(self, engine, sample_source):
        """Test basic SQL query building."""
        sql, params = engine._build_query(
            sample_source,
            dimensions=["company"],
            measures=["amount"],
            filters=None,
        )

        assert sql == (
            "SELECT comp_code AS company, SUM(amount_lc) AS amount "
            "FROM test_table "
            "GROUP BY comp_code"
        )
        assert params == []

    def test_build_query_with_filter(self, engine, sample_source):
        """Test SQL query building with filters."""
        sql, params = engine._build_query(
            sample_source,
            dimensions=["company"],
            measures=["amount"],
            filters={"period": "2024001"},
        )

        assert "WHERE fiscal_period = $1" in sql
        assert params == ["2024001"]


class TestQueryResult:
    def test_query_result_creation(self):
        """Test QueryResult dataclass."""
        result = QueryResult(
            source_name="test",
            rows=[{"a": 1}],
            dimensions_used=["dim1"],
            measures_used=["measure1"],
            row_count=1,
        )

        assert result.source_name == "test"
        assert result.rows == [{"a": 1}]
        assert result.dimensions_used == ["dim1"]
        assert result.measures_used == ["measure1"]
        assert result.row_count == 1
