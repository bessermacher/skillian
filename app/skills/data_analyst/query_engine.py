"""SQL query builder and executor for source definitions."""

from dataclasses import dataclass
from typing import Any

from app.connectors.postgres import PostgresConnector
from app.skills.data_analyst.source_registry import SourceDef


@dataclass
class QueryResult:
    """Result of a query execution."""

    source_name: str
    rows: list[dict[str, Any]]
    dimensions_used: list[str]
    measures_used: list[str]
    row_count: int


class QueryEngine:
    """Builds and executes SQL queries based on source definitions."""

    def __init__(self, connector: PostgresConnector):
        """Initialize with database connector.

        Args:
            connector: PostgresConnector instance.
        """
        self._connector = connector

    async def query(
        self,
        source: SourceDef,
        dimensions: list[str] | None = None,
        measures: list[str] | None = None,
        filters: dict[str, Any] | None = None,
    ) -> QueryResult:
        """Execute a query against a source.

        Args:
            source: Source definition.
            dimensions: Dimensions to group by (uses defaults if None).
            measures: Measures to aggregate (uses all if None).
            filters: Filter conditions as {dimension: value}.

        Returns:
            QueryResult with aggregated data.
        """
        # Use defaults if not specified
        if dimensions is None:
            dimensions = source.defaults.get("dimensions", [])
        if measures is None:
            measures = list(source.measures.keys())

        # Validate dimensions and measures exist
        for dim in dimensions:
            if dim not in source.dimensions:
                raise ValueError(f"Unknown dimension: {dim}")
        for measure in measures:
            if measure not in source.measures:
                raise ValueError(f"Unknown measure: {measure}")

        # Build query
        sql, params = self._build_query(source, dimensions, measures, filters)

        # Execute
        rows = await self._connector.execute(sql, params)

        return QueryResult(
            source_name=source.name,
            rows=rows,
            dimensions_used=dimensions,
            measures_used=measures,
            row_count=len(rows),
        )

    def _build_query(
        self,
        source: SourceDef,
        dimensions: list[str],
        measures: list[str],
        filters: dict[str, Any] | None,
    ) -> tuple[str, list[Any]]:
        """Build SQL query string and parameters.

        Args:
            source: Source definition.
            dimensions: Dimensions to group by.
            measures: Measures to aggregate.
            filters: Filter conditions.

        Returns:
            Tuple of (sql_string, parameters_list).
        """
        # SELECT clause
        select_parts = []
        for dim in dimensions:
            col = source.dimensions[dim].column
            select_parts.append(f"{col} AS {dim}")

        for measure in measures:
            measure_def = source.measures[measure]
            agg = measure_def.aggregation.upper()
            col = measure_def.column
            select_parts.append(f"{agg}({col}) AS {measure}")

        select_clause = ", ".join(select_parts)

        # FROM clause
        from_clause = source.table

        # WHERE clause
        where_parts = []
        params = []
        param_idx = 1

        if filters:
            for dim, value in filters.items():
                if dim not in source.dimensions:
                    raise ValueError(f"Unknown filter dimension: {dim}")
                col = source.dimensions[dim].column
                where_parts.append(f"{col} = ${param_idx}")
                params.append(value)
                param_idx += 1

        where_clause = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""

        # GROUP BY clause
        group_parts = [source.dimensions[dim].column for dim in dimensions]
        group_clause = f"GROUP BY {', '.join(group_parts)}" if group_parts else ""

        # Assemble query
        sql = f"SELECT {select_clause} FROM {from_clause}"
        if where_clause:
            sql = f"{sql} {where_clause}"
        if group_clause:
            sql = f"{sql} {group_clause}"

        return sql, params
