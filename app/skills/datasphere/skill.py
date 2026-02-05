"""SAP Datasphere skill for data analysis and comparison."""

from pathlib import Path

from app.connectors.datasphere import DatasphereConnector
from app.core.tool import Tool
from app.skills.datasphere.tools import (
    CompareEntitiesInput,
    DatasphereTools,
    ExecuteSQLInput,
    GetEntityMetadataInput,
    ListEntitiesInput,
    QueryEntityInput,
)


class DatasphereSkill:
    """Skill for querying and analyzing SAP Datasphere data.

    Provides tools for:
    - Listing available entities (views/tables)
    - Querying entities via OData
    - Executing SQL queries
    - Comparing data between entities
    - Retrieving metadata
    """

    def __init__(self, connector: DatasphereConnector):
        self._connector = connector
        self._tool_impl = DatasphereTools(connector)
        self._tools = self._build_tools()

    def _build_tools(self) -> list[Tool]:
        """Build the list of available tools."""
        return [
            Tool(
                name="ds_list_entities",
                description=(
                    "List all available entities (views and tables) in the "
                    "SAP Datasphere space. Use this first to discover what data "
                    "is available for querying."
                ),
                function=self._tool_impl.list_entities,
                input_schema=ListEntitiesInput,
            ),
            Tool(
                name="ds_query_entity",
                description=(
                    "Query a SAP Datasphere entity (view or table) using OData. "
                    "Supports field selection, filtering, ordering, and pagination. "
                    "Use this for exploring data and retrieving specific records."
                ),
                function=self._tool_impl.query_entity,
                input_schema=QueryEntityInput,
            ),
            Tool(
                name="ds_execute_sql",
                description=(
                    "Execute a SQL SELECT query against SAP Datasphere. "
                    "Use this for complex queries that require joins, "
                    "aggregations, or features not available via OData. "
                    "Only SELECT statements are allowed."
                ),
                function=self._tool_impl.execute_sql,
                input_schema=ExecuteSQLInput,
            ),
            Tool(
                name="ds_get_metadata",
                description=(
                    "Get metadata for a specific entity including field names, "
                    "data types, and descriptions. Use this to understand the "
                    "structure of an entity before querying."
                ),
                function=self._tool_impl.get_entity_metadata,
                input_schema=GetEntityMetadataInput,
            ),
            Tool(
                name="ds_compare_entities",
                description=(
                    "Compare a numeric measure between two entities. "
                    "Useful for data reconciliation, finding discrepancies, "
                    "and validating data across different sources or time periods. "
                    "Returns differences and percentage variances."
                ),
                function=self._tool_impl.compare_entities,
                input_schema=CompareEntitiesInput,
            ),
        ]

    @property
    def name(self) -> str:
        return "datasphere"

    @property
    def description(self) -> str:
        return (
            "SAP Datasphere skill for querying, analyzing, and comparing "
            "enterprise data stored in Datasphere views and tables."
        )

    @property
    def tools(self) -> list[Tool]:
        return self._tools

    @property
    def system_prompt(self) -> str:
        return """You are an expert in SAP Datasphere data analysis. When helping users:

1. **Discovery First**: Always start by listing available entities if the user
   doesn't specify which data to query. Use ds_list_entities to discover the schema.

2. **Understand Structure**: Before querying, use ds_get_metadata to understand
   field names, data types, and relationships.

3. **Query Efficiently**:
   - Use OData (ds_query_entity) for simple queries with filters
   - Use SQL (ds_execute_sql) for complex joins and aggregations
   - Always apply filters to avoid retrieving too much data

4. **Data Comparison**: When users want to reconcile or validate data:
   - Identify the reference entity and comparison entity
   - Determine the measure to compare and dimensions to align on
   - Use ds_compare_entities to find discrepancies
   - Explain differences clearly, focusing on significant variances

5. **SAP Terminology**: Users may use SAP terms like:
   - InfoObject → Dimension or Characteristic
   - Key Figure → Measure
   - InfoProvider → Entity/View
   - Request → Data load batch

6. **Common Analysis Patterns**:
   - Period-over-period comparison (filter by CALMONTH/FISCPER)
   - Source-to-target reconciliation
   - Aggregation verification (detail vs. summary)
   - Data quality checks (nulls, outliers)

Always explain your findings clearly and suggest next steps for investigation."""

    @property
    def knowledge_paths(self) -> list[str]:
        return [str(Path(__file__).parent / "knowledge")]

    def get_tool(self, name: str) -> Tool | None:
        for tool in self._tools:
            if tool.name == name:
                return tool
        return None
