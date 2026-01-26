"""Business domain skill for SAP BW analysis."""

from app.connectors import Connector
from app.core import BaseSkill, Tool
from app.skills.business.tools import (
    CompareVersionsInput,
    GetBPCDataInput,
    GetCompanyRevenueInput,
    GetConsolidationInput,
    GetFISummaryInput,
    GetFITransactionsInput,
    GetGLAccountBalanceInput,
    GetIntercompanyInput,
    create_business_tools,
)


class BusinessSkill(BaseSkill):
    """Business analysis skill for SAP BW data.

    Provides tools for:
    - FI transaction queries and summaries
    - Consolidation and BPC data analysis
    - Revenue analysis by company
    - Budget vs actual comparisons
    - GL account balances
    - Intercompany transaction analysis

    Example:
        connector = BusinessDatabaseConnector(database_url)
        skill = BusinessSkill(connector)
        registry.register(skill)
    """

    def __init__(self, connector: Connector):
        """Initialize with a data connector.

        Args:
            connector: The data connector for SAP BW access.
        """
        self._connector = connector
        self._tool_funcs = create_business_tools(connector)

    @property
    def name(self) -> str:
        return "business"

    @property
    def description(self) -> str:
        return (
            "Analyze SAP BW business data including FI transactions, "
            "consolidation, BPC planning, revenue, and intercompany analysis"
        )

    @property
    def tools(self) -> list[Tool]:
        return [
            Tool(
                name="get_fi_transactions",
                description=(
                    "Query FI reporting transactions with filters for company, "
                    "period, GL account, and cost centers"
                ),
                function=self._tool_funcs["get_fi_transactions"],
                input_schema=GetFITransactionsInput,
            ),
            Tool(
                name="get_fi_summary",
                description=(
                    "Get aggregated FI data grouped by dimensions like company, "
                    "period, GL account, or segment"
                ),
                function=self._tool_funcs["get_fi_summary"],
                input_schema=GetFISummaryInput,
            ),
            Tool(
                name="get_consolidation",
                description=(
                    "Query consolidation mart data for BPC group reporting "
                    "and eliminations"
                ),
                function=self._tool_funcs["get_consolidation"],
                input_schema=GetConsolidationInput,
            ),
            Tool(
                name="get_bpc_data",
                description=(
                    "Query BPC reporting data for budgeting, forecasting, "
                    "and planning analysis"
                ),
                function=self._tool_funcs["get_bpc_data"],
                input_schema=GetBPCDataInput,
            ),
            Tool(
                name="get_company_revenue",
                description="Get revenue summary by company code with version filtering",
                function=self._tool_funcs["get_company_revenue"],
                input_schema=GetCompanyRevenueInput,
            ),
            Tool(
                name="compare_versions",
                description=(
                    "Compare actual vs budget/forecast with variance analysis "
                    "and status assessment"
                ),
                function=self._tool_funcs["compare_versions"],
                input_schema=CompareVersionsInput,
            ),
            Tool(
                name="get_gl_account_balance",
                description=(
                    "Get GL account balances with debit/credit breakdown "
                    "and posting counts"
                ),
                function=self._tool_funcs["get_gl_account_balance"],
                input_schema=GetGLAccountBalanceInput,
            ),
            Tool(
                name="get_intercompany",
                description=(
                    "Query intercompany transactions between group companies "
                    "for elimination analysis"
                ),
                function=self._tool_funcs["get_intercompany"],
                input_schema=GetIntercompanyInput,
            ),
        ]

    @property
    def system_prompt(self) -> str:
        return """You are a business analyst expert in SAP BW and BPC data.

When analyzing business data:
- Start with high-level summaries before drilling into details
- Compare actuals against budget to identify variances
- Flag significant deviations (>10% variance) for attention
- Consider intercompany eliminations when analyzing consolidated data
- Provide actionable insights, not just numbers

Key SAP BW concepts:
- FI Reporting: Detailed financial transactions from SAP FI module
- Consolidation Mart: Aggregated data for BPC group consolidation
- BPC Reporting: Business Planning and Consolidation data
- Version: ACTUAL (real data), BUDGET (planned), FORECAST (projections)
- Intercompany: Transactions between group companies requiring elimination

When presenting financial data:
- Always specify the currency and period context
- Use appropriate precision (thousands/millions for large amounts)
- Highlight trends and year-over-year comparisons when relevant
"""

    @property
    def knowledge_paths(self) -> list[str]:
        return ["app/skills/business/knowledge/"]
