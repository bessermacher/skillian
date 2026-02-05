"""Tool implementations for Datasphere skill."""

from typing import Any

from pydantic import BaseModel, Field

from app.connectors.datasphere import DatasphereConnector, DatasphereQueryError

# ============================================================================
# Tool Input Schemas
# ============================================================================


class ListEntitiesInput(BaseModel):
    """Input for listing available entities."""


class QueryEntityInput(BaseModel):
    """Input for querying a Datasphere entity via OData."""

    entity: str = Field(description="Name of the entity (view/table) to query")
    select: list[str] | None = Field(
        default=None,
        description="Fields to return. If not specified, all fields are returned.",
    )
    filter_expr: str | None = Field(
        default=None,
        description="OData filter expression, e.g., \"CALMONTH eq '202401'\"",
    )
    top: int | None = Field(
        default=100, description="Maximum number of rows to return (default: 100)"
    )
    orderby: str | None = Field(default=None, description="Order by field, e.g., 'AMOUNT desc'")


class ExecuteSQLInput(BaseModel):
    """Input for executing raw SQL against Datasphere."""

    query: str = Field(description="SQL query to execute. Use SELECT statements only.")


class GetEntityMetadataInput(BaseModel):
    """Input for retrieving entity metadata."""

    entity: str = Field(description="Name of the entity to get metadata for")


class CompareEntitiesInput(BaseModel):
    """Input for comparing data between two entities."""

    entity_a: str = Field(description="First entity name (reference)")
    entity_b: str = Field(description="Second entity name (to compare)")
    measure: str = Field(description="Measure/numeric field to compare")
    group_by: list[str] | None = Field(
        default=None, description="Dimensions to group and align comparison on"
    )
    filter_expr: str | None = Field(
        default=None, description="OData filter to apply to both entities"
    )


# ============================================================================
# Tool Implementation Class
# ============================================================================


class DatasphereTools:
    """Tool implementations for Datasphere skill."""

    def __init__(self, connector: DatasphereConnector):
        self._connector = connector

    async def list_entities(self) -> dict[str, Any]:
        """List all available entities in the Datasphere space."""
        try:
            entities = await self._connector.list_entities()
            return {
                "entities": entities,
                "count": len(entities),
                "space": self._connector.space,
            }
        except DatasphereQueryError as e:
            return {"error": str(e), "entities": []}

    async def query_entity(
        self,
        entity: str,
        select: list[str] | None = None,
        filter_expr: str | None = None,
        top: int | None = 100,
        orderby: str | None = None,
    ) -> dict[str, Any]:
        """Query a Datasphere entity using OData."""
        try:
            results = await self._connector.execute_odata(
                entity=entity,
                select=select,
                filter_expr=filter_expr,
                top=top,
                orderby=orderby,
            )

            return {
                "entity": entity,
                "row_count": len(results),
                "rows": results,
                "truncated": len(results) == top,
                "filter_applied": filter_expr,
            }
        except DatasphereQueryError as e:
            return {
                "error": str(e),
                "entity": entity,
                "row_count": 0,
                "rows": [],
            }

    async def execute_sql(self, query: str) -> dict[str, Any]:
        """Execute a SQL query against Datasphere."""
        # Basic safety check - only allow SELECT
        query_upper = query.strip().upper()
        if not query_upper.startswith("SELECT"):
            return {
                "error": "Only SELECT queries are allowed for safety",
                "query": query,
                "rows": [],
            }

        try:
            results = await self._connector.execute_sql(query)
            return {
                "query": query,
                "row_count": len(results),
                "rows": results[:500],  # Limit response size
                "truncated": len(results) > 500,
            }
        except DatasphereQueryError as e:
            return {
                "error": str(e),
                "query": query,
                "rows": [],
            }

    async def get_entity_metadata(self, entity: str) -> dict[str, Any]:
        """Get metadata for a specific entity."""
        try:
            metadata = await self._connector.get_metadata(entity)
            return {
                "entity": entity,
                "metadata": metadata,
            }
        except DatasphereQueryError as e:
            return {
                "error": str(e),
                "entity": entity,
                "metadata": {},
            }

    async def compare_entities(
        self,
        entity_a: str,
        entity_b: str,
        measure: str,
        group_by: list[str] | None = None,
        filter_expr: str | None = None,
    ) -> dict[str, Any]:
        """Compare a measure between two entities."""
        try:
            # Query both entities
            select_fields = [measure]
            if group_by:
                select_fields = group_by + [measure]

            results_a = await self._connector.execute_odata(
                entity=entity_a,
                select=select_fields,
                filter_expr=filter_expr,
                top=1000,
            )

            results_b = await self._connector.execute_odata(
                entity=entity_b,
                select=select_fields,
                filter_expr=filter_expr,
                top=1000,
            )

            # Build comparison
            comparison = self._build_comparison(results_a, results_b, measure, group_by or [])

            return {
                "entity_a": entity_a,
                "entity_b": entity_b,
                "measure": measure,
                "group_by": group_by,
                "comparison": comparison,
                "summary": self._summarize_comparison(comparison, measure),
            }
        except DatasphereQueryError as e:
            return {
                "error": str(e),
                "entity_a": entity_a,
                "entity_b": entity_b,
            }

    def _build_comparison(
        self,
        results_a: list[dict],
        results_b: list[dict],
        measure: str,
        group_by: list[str],
    ) -> list[dict]:
        """Build comparison records between two result sets."""
        if not group_by:
            # Simple total comparison
            total_a = sum(r.get(measure, 0) or 0 for r in results_a)
            total_b = sum(r.get(measure, 0) or 0 for r in results_b)
            diff = total_b - total_a
            pct = (diff / total_a * 100) if total_a else 0

            return [
                {
                    "value_a": total_a,
                    "value_b": total_b,
                    "difference": diff,
                    "difference_pct": round(pct, 2),
                }
            ]

        # Group-by comparison
        def make_key(row: dict) -> tuple:
            return tuple(row.get(dim) for dim in group_by)

        index_a = {make_key(r): r.get(measure, 0) for r in results_a}
        index_b = {make_key(r): r.get(measure, 0) for r in results_b}

        all_keys = set(index_a.keys()) | set(index_b.keys())
        comparison = []

        for key in sorted(all_keys):
            val_a = index_a.get(key, 0) or 0
            val_b = index_b.get(key, 0) or 0
            diff = val_b - val_a
            pct = (diff / val_a * 100) if val_a else 0

            record = {
                **dict(zip(group_by, key)),
                "value_a": val_a,
                "value_b": val_b,
                "difference": diff,
                "difference_pct": round(pct, 2),
            }
            comparison.append(record)

        return comparison

    def _summarize_comparison(
        self,
        comparison: list[dict],
        measure: str,
    ) -> dict[str, Any]:
        """Generate summary statistics for a comparison."""
        total_a = sum(c["value_a"] for c in comparison)
        total_b = sum(c["value_b"] for c in comparison)
        total_diff = total_b - total_a
        total_pct = (total_diff / total_a * 100) if total_a else 0

        mismatches = [c for c in comparison if abs(c["difference_pct"]) > 1]

        return {
            "total_a": total_a,
            "total_b": total_b,
            "total_difference": total_diff,
            "total_difference_pct": round(total_pct, 2),
            "records_compared": len(comparison),
            "mismatches_over_1pct": len(mismatches),
            "largest_differences": sorted(
                comparison, key=lambda x: abs(x["difference"]), reverse=True
            )[:5],
        }
