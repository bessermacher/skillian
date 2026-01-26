"""Financial domain skill for SAP BW analysis."""

from app.connectors import Connector
from app.core import BaseSkill, Tool
from app.skills.financial.tools import (
    CompareBudgetInput,
    GetCostCenterInput,
    GetProfitCenterInput,
    ListCostCentersInput,
    SearchTransactionsInput,
    create_financial_tools,
)


class FinancialSkill(BaseSkill):
    """Financial analysis skill for SAP BW data.

    Provides tools for:
    - Cost center analysis
    - Profit center analysis
    - Budget vs actuals comparison
    - Transaction search

    Example:
        connector = MockConnector()
        skill = FinancialSkill(connector)
        registry.register(skill)
    """

    def __init__(self, connector: Connector):
        """Initialize with a data connector.

        Args:
            connector: The data connector for SAP BW access.
        """
        self._connector = connector
        self._tool_funcs = create_financial_tools(connector)

    @property
    def name(self) -> str:
        return "financial"

    @property
    def description(self) -> str:
        return "Analyze financial data including cost centers, profit centers, budgets, and transactions in SAP BW"

    @property
    def tools(self) -> list[Tool]:
        return [
            Tool(
                name="get_cost_center",
                description="Retrieve detailed cost center information including budget, actuals, and available funds",
                function=self._tool_funcs["get_cost_center"],
                input_schema=GetCostCenterInput,
            ),
            Tool(
                name="list_cost_centers",
                description="List all cost centers with summary financial data, optionally filtered by department",
                function=self._tool_funcs["list_cost_centers"],
                input_schema=ListCostCentersInput,
            ),
            Tool(
                name="get_profit_center",
                description="Retrieve profit center information including revenue, costs, and margin",
                function=self._tool_funcs["get_profit_center"],
                input_schema=GetProfitCenterInput,
            ),
            Tool(
                name="search_transactions",
                description="Search financial transactions by cost center, date range, or amount",
                function=self._tool_funcs["search_transactions"],
                input_schema=SearchTransactionsInput,
            ),
            Tool(
                name="compare_budget",
                description="Analyze budget vs actuals with variance analysis and status assessment",
                function=self._tool_funcs["compare_budget"],
                input_schema=CompareBudgetInput,
            ),
        ]

    @property
    def system_prompt(self) -> str:
        return """You are a financial analyst expert in SAP BW data.

When analyzing financial data:
- Always check budget utilization when asked about cost centers
- Flag any cost centers that are over budget or at risk
- Provide specific numbers and percentages
- Suggest actions when issues are found

Common financial terms:
- Actuals: Money already spent
- Committed: Money obligated but not yet spent
- Available: Budget minus actuals and committed
- Variance: Difference between budget and actuals
"""

    @property
    def knowledge_paths(self) -> list[str]:
        return ["app/skills/financial/knowledge/"]