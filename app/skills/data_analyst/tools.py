"""Data analyst skill tools.

Tools for comparing and querying data sources. Each tool is designed
following Anthropic best practices: consolidated functionality,
clear documentation-style descriptions, and meaningful responses.
"""

from pathlib import Path
from typing import Any

from app.skills.data_analyst.comparison_engine import ComparisonEngine, ComparisonResult
from app.skills.data_analyst.query_engine import QueryEngine
from app.skills.data_analyst.source_registry import SourceRegistry


def _format_comparison_result(result: ComparisonResult) -> dict[str, Any]:
    """Format comparison result for LLM-friendly output."""
    major_diffs = [r for r in result.rows if r.status.value == "major_diff"]
    minor_diffs = [r for r in result.rows if r.status.value == "minor_diff"]

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


# Module-level tools instance cache
_tools_instance: "DataAnalystTools | None" = None
_tools_connector: Any = None


class DataAnalystTools:
    """Tool implementations for data analyst skill."""

    def __init__(
        self,
        registry: SourceRegistry,
        query_engine: QueryEngine,
        comparison_engine: ComparisonEngine,
    ):
        self._registry = registry
        self._query_engine = query_engine
        self._comparison_engine = comparison_engine

    def list_sources(self) -> dict[str, Any]:
        """List all available data sources with their descriptions and fields."""
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
        """Query a single data source with optional grouping and filtering."""
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
            "rows": result.rows[:100],
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
        """Compare measure values between two data sources."""
        result = await self._comparison_engine.compare(
            source_a_name=source_a,
            source_b_name=source_b,
            measure=measure,
            align_on=align_on,
            filters=filters,
        )

        return _format_comparison_result(result)


def _get_tools_instance(connector: Any) -> DataAnalystTools:
    """Get or create the DataAnalystTools singleton."""
    global _tools_instance, _tools_connector

    if _tools_instance is None or _tools_connector is not connector:
        config_path = Path("config/sources.yaml")
        registry = SourceRegistry(config_path)
        query_engine = QueryEngine(connector)
        comparison_engine = ComparisonEngine(registry, query_engine)
        _tools_instance = DataAnalystTools(registry, query_engine, comparison_engine)
        _tools_connector = connector

    return _tools_instance


# Standalone tool functions for YAML loader


def list_sources(connector: Any = None) -> dict[str, Any]:
    """List all available data sources."""
    tools = _get_tools_instance(connector)
    return tools.list_sources()


async def query_source(
    source: str,
    dimensions: list[str] | None = None,
    measures: list[str] | None = None,
    filters: dict[str, str] | None = None,
    connector: Any = None,
) -> dict[str, Any]:
    """Query a single data source with aggregation."""
    tools = _get_tools_instance(connector)
    return await tools.query_source(
        source=source,
        dimensions=dimensions,
        measures=measures,
        filters=filters,
    )


async def compare_sources(
    source_a: str,
    source_b: str,
    measure: str,
    align_on: list[str] | None = None,
    filters: dict[str, str] | None = None,
    connector: Any = None,
) -> dict[str, Any]:
    """Compare measure values between two data sources."""
    tools = _get_tools_instance(connector)
    return await tools.compare_sources(
        source_a=source_a,
        source_b=source_b,
        measure=measure,
        align_on=align_on,
        filters=filters,
    )
