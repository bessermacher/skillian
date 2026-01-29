"""Data analyst skill for comparing and analyzing data sources."""

from pathlib import Path

from app.core.comparison_engine import ComparisonEngine
from app.core.query_engine import QueryEngine
from app.core.source_registry import SourceRegistry
from app.core.tool import Tool
from app.skills.data_analyst.tools import (
    CompareSourcesInput,
    DataAnalystTools,
    ListSourcesInput,
    QuerySourceInput,
)


class DataAnalystSkill:
    """Skill for comparing and analyzing data from multiple sources.

    Implements the Skill protocol to provide data comparison capabilities
    using consolidated, well-documented tools following Anthropic best practices.
    """

    def __init__(
        self,
        registry: SourceRegistry,
        query_engine: QueryEngine,
        comparison_engine: ComparisonEngine,
    ):
        """Initialize the data analyst skill.

        Args:
            registry: Source registry for definitions.
            query_engine: Engine for executing queries.
            comparison_engine: Engine for comparing sources.
        """
        self._registry = registry
        self._tool_impl = DataAnalystTools(registry, query_engine, comparison_engine)
        self._tools = self._build_tools()

    def _build_tools(self) -> list[Tool]:
        """Build the tool list."""
        return [
            Tool(
                name="list_sources",
                description=(
                    "List all available data sources.\n\n"
                    "Returns information about each configured data source including:\n"
                    "- Source name and description\n"
                    "- Available dimensions (grouping fields)\n"
                    "- Available measures (aggregatable values)\n"
                    "- Valid comparison pairs based on common dimensions\n\n"
                    "Use this tool first to understand what data sources are available "
                    "before querying or comparing them."
                ),
                function=self._tool_impl.list_sources,
                input_schema=ListSourcesInput,
            ),
            Tool(
                name="query_source",
                description=(
                    "Query a single data source with aggregation.\n\n"
                    "Executes a query against one data source, grouping by specified "
                    "dimensions and aggregating measures. Use this to:\n"
                    "- Explore data in a single source\n"
                    "- Get totals by specific dimensions\n"
                    "- Filter data before analysis\n\n"
                    "Parameters:\n"
                    "- source: Name of the source (from list_sources)\n"
                    "- dimensions: Fields to group by (optional, uses defaults)\n"
                    "- measures: Values to aggregate (optional, uses all)\n"
                    "- filters: Conditions to filter data\n\n"
                    "Returns rows with dimension values and aggregated measures."
                ),
                function=self._tool_impl.query_source,
                input_schema=QuerySourceInput,
            ),
            Tool(
                name="compare_sources",
                description=(
                    "Compare measure values between two data sources.\n\n"
                    "This is the primary tool for data reconciliation. It aligns rows "
                    "from two sources on common dimensions and compares a specified "
                    "measure. Differences are classified as:\n"
                    "- match: Within configured tolerance\n"
                    "- minor_diff: Notable but acceptable difference\n"
                    "- major_diff: Significant discrepancy requiring investigation\n\n"
                    "Parameters:\n"
                    "- source_a: Reference source (source of truth)\n"
                    "- source_b: Source to compare against\n"
                    "- measure: The value to compare (e.g., 'amount')\n"
                    "- align_on: Dimensions to match rows on (optional)\n"
                    "- filters: Conditions to apply to both sources\n\n"
                    "Returns summary statistics, top differences, and a cache key "
                    "for follow-up queries on the same comparison."
                ),
                function=self._tool_impl.compare_sources,
                input_schema=CompareSourcesInput,
            ),
        ]

    @property
    def name(self) -> str:
        """Unique identifier for this skill."""
        return "data_analyst"

    @property
    def description(self) -> str:
        """Human-readable description of the skill."""
        return "Compare and analyze data from multiple sources to identify discrepancies"

    @property
    def tools(self) -> list[Tool]:
        """List of tools available in this skill."""
        return self._tools

    @property
    def system_prompt(self) -> str:
        """System prompt providing domain context to the LLM."""
        return (
            "You are a data analyst assistant helping users compare "
            "and reconcile data from multiple sources.\n\n"
            "Your role is to:\n"
            "1. Help users understand available data sources and their structure\n"
            "2. Execute comparisons between sources to identify discrepancies\n"
            "3. Explain differences and suggest possible causes\n"
            "4. Guide users through drilling down into specific differences\n\n"
            "When analyzing comparisons:\n"
            "- Focus on the most significant differences first (major_diff)\n"
            "- Consider both absolute and percentage differences\n"
            "- Look for patterns (e.g., all differences in one company/period)\n"
            "- Suggest follow-up queries to investigate root causes\n\n"
            "When differences are found:\n"
            "- Don't assume which source is \"correct\" - present the facts\n"
            "- Suggest possible explanations (timing, cut-off dates, transformations)\n"
            "- Recommend specific filters or drill-down queries for investigation\n\n"
            "Use the cache_key from comparison results to reference previous "
            "comparisons when the user asks follow-up questions about the same data.\n\n"
            "Always be precise with numbers and avoid rounding unless explicitly asked."
        )

    @property
    def knowledge_paths(self) -> list[str]:
        """Paths to knowledge documents for RAG."""
        return [str(Path(__file__).parent / "knowledge")]

    def get_tool(self, name: str) -> Tool | None:
        """Get a specific tool by name."""
        for tool in self._tools:
            if tool.name == name:
                return tool
        return None
