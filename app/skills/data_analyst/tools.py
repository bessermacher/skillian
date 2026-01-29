"""Data analyst skill tools.

Tools for comparing and querying data sources. Each tool is designed
following Anthropic best practices: consolidated functionality,
clear documentation-style descriptions, and meaningful responses.
"""

from typing import Any

from pydantic import BaseModel, Field

from app.core.comparison_engine import ComparisonEngine, ComparisonResult
from app.core.query_engine import QueryEngine
from app.core.source_registry import SourceRegistry


class ListSourcesInput(BaseModel):
    """Input for list_sources tool - no parameters needed."""

    pass


class QuerySourceInput(BaseModel):
    """Input for querying a single data source.

    Parameters:
        source: Name of the source to query (e.g., 'fi_reporting', 'bpc_reporting')
        dimensions: List of dimensions to group by. If not specified, uses source defaults.
        measures: List of measures to aggregate. If not specified, uses all measures.
        filters: Filter conditions as dimension:value pairs.
    """

    source: str = Field(description="Name of the source to query")
    dimensions: list[str] | None = Field(
        default=None, description="Dimensions to group by (uses defaults if not specified)"
    )
    measures: list[str] | None = Field(
        default=None, description="Measures to aggregate (uses all if not specified)"
    )
    filters: dict[str, str] | None = Field(
        default=None, description="Filter conditions as dimension:value pairs"
    )


class CompareSourcesInput(BaseModel):
    """Input for comparing two data sources.

    Parameters:
        source_a: First source name (reference/expected)
        source_b: Second source name (to compare against)
        measure: The measure to compare (e.g., 'amount', 'quantity')
        align_on: Dimensions to align the comparison on. If not specified, uses configured defaults.
        filters: Filter conditions to apply to both sources.
    """

    source_a: str = Field(description="First source name (reference)")
    source_b: str = Field(description="Second source name (to compare)")
    measure: str = Field(description="Measure to compare (e.g., 'amount')")
    align_on: list[str] | None = Field(
        default=None, description="Dimensions to align on (uses defaults if not specified)"
    )
    filters: dict[str, str] | None = Field(
        default=None, description="Filters to apply to both sources"
    )


def _format_comparison_result(result: ComparisonResult) -> dict[str, Any]:
    """Format comparison result for LLM-friendly output."""
    # Identify key differences
    major_diffs = [r for r in result.rows if r.status.value == "major_diff"]
    minor_diffs = [r for r in result.rows if r.status.value == "minor_diff"]

    # Format top differences
    top_diffs = []
    for row in sorted(major_diffs + minor_diffs, key=lambda r: r.absolute_diff, reverse=True)[:5]:
        top_diffs.append({
            "key": row.key,
            "source_a": row.source_a_value,
            "source_b": row.source_b_value,
            "diff": row.absolute_diff,
            "pct_diff": f"{row.percentage_diff:.1f}%" if row.percentage_diff else "N/A",
            "status": row.status.value,
        })

    return {
        "summary": {
            "source_a": result.source_a,
            "source_b": result.source_b,
            "measure": result.measure,
            "aligned_on": result.align_on,
            "total_rows": result.total_rows,
            "matches": result.summary.get("match_count", 0),
            "minor_differences": result.summary.get("minor_diff_count", 0),
            "major_differences": result.summary.get("major_diff_count", 0),
            "total_source_a": result.summary.get("total_source_a"),
            "total_source_b": result.summary.get("total_source_b"),
            "total_diff": result.summary.get("total_absolute_diff"),
        },
        "top_differences": top_diffs,
        "cache_key": result.cache_key,
        "interpretation": _generate_interpretation(result),
    }


def _generate_interpretation(result: ComparisonResult) -> str:
    """Generate human-readable interpretation of comparison."""
    total = result.total_rows
    match_pct = (result.match_count / total * 100) if total > 0 else 0
    major_count = result.summary.get("major_diff_count", 0)

    if match_pct == 100:
        return (
            f"All {total} rows match perfectly between "
            f"{result.source_a} and {result.source_b}."
        )
    elif match_pct >= 90:
        return (
            f"Good alignment ({match_pct:.1f}% match). "
            f"{major_count} rows have major differences."
        )
    elif match_pct >= 50:
        return (
            f"Moderate alignment ({match_pct:.1f}% match). "
            f"{major_count} rows have major differences requiring investigation."
        )
    else:
        return (
            f"Poor alignment ({match_pct:.1f}% match). "
            "Significant discrepancies between sources. Review data quality."
        )


class DataAnalystTools:
    """Tool implementations for data analyst skill.

    Provides consolidated tools following Anthropic's recommendations:
    - Few powerful tools rather than many small ones
    - Clear, documentation-style descriptions
    - Meaningful, structured responses
    """

    def __init__(
        self,
        registry: SourceRegistry,
        query_engine: QueryEngine,
        comparison_engine: ComparisonEngine,
    ):
        """Initialize tools with required engines.

        Args:
            registry: Source registry for definitions.
            query_engine: Engine for executing queries.
            comparison_engine: Engine for comparing sources.
        """
        self._registry = registry
        self._query_engine = query_engine
        self._comparison_engine = comparison_engine

    def list_sources(self) -> dict[str, Any]:
        """List all available data sources with their descriptions and fields.

        Returns a structured overview of all configured data sources,
        including available dimensions and measures for each.

        Returns:
            Dictionary with sources list and metadata.
        """
        sources_info = self._registry.get_source_info()

        return {
            "sources": sources_info,
            "total_count": len(sources_info),
            "available_comparisons": self._get_comparison_pairs(sources_info),
        }

    def _get_comparison_pairs(self, sources: list[dict]) -> list[dict]:
        """Generate valid comparison pairs based on common dimensions."""
        pairs = []
        source_names = [s["name"] for s in sources]

        for i, name_a in enumerate(source_names):
            for name_b in source_names[i + 1:]:
                common = self._registry.get_common_dimensions(name_a, name_b)
                if common:
                    pairs.append({
                        "source_a": name_a,
                        "source_b": name_b,
                        "common_dimensions": common,
                    })

        return pairs

    async def query_source(
        self,
        source: str,
        dimensions: list[str] | None = None,
        measures: list[str] | None = None,
        filters: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Query a single data source with optional grouping and filtering.

        Executes an aggregation query against the specified source,
        grouping by dimensions and calculating measure aggregates.

        Args:
            source: Source name to query.
            dimensions: Dimensions to group by.
            measures: Measures to aggregate.
            filters: Filter conditions.

        Returns:
            Query results with rows and metadata.
        """
        source_def = self._registry.get(source)
        result = await self._query_engine.query(
            source_def,
            dimensions=dimensions,
            measures=measures,
            filters=filters,
        )

        return {
            "source": result.source_name,
            "row_count": result.row_count,
            "dimensions_used": result.dimensions_used,
            "measures_used": result.measures_used,
            "rows": result.rows[:100],  # Limit to first 100 rows
            "truncated": result.row_count > 100,
        }

    async def compare_sources(
        self,
        source_a: str,
        source_b: str,
        measure: str,
        align_on: list[str] | None = None,
        filters: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Compare measure values between two data sources.

        Aligns rows from both sources on common dimensions and compares
        the specified measure values. Classifies differences as match,
        minor, or major based on configured thresholds.

        Args:
            source_a: Reference source name.
            source_b: Comparison source name.
            measure: Measure to compare.
            align_on: Dimensions to align on.
            filters: Filters to apply to both sources.

        Returns:
            Structured comparison result with summary, top differences,
            and cache key for drill-down queries.
        """
        result = await self._comparison_engine.compare(
            source_a_name=source_a,
            source_b_name=source_b,
            measure=measure,
            align_on=align_on,
            filters=filters,
        )

        return _format_comparison_result(result)
