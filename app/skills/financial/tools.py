"""Financial skill tools for SAP BW data analysis."""

from pydantic import BaseModel, Field

from app.connectors import Connector


# Input Schemas

class GetCostCenterInput(BaseModel):
    """Input for get_cost_center tool."""

    cost_center_id: str = Field(
        description="The SAP cost center ID (e.g., 'CC-1001')"
    )
    fiscal_year: int = Field(
        default=2024,
        description="Fiscal year for the query (e.g., 2024)",
    )


class ListCostCentersInput(BaseModel):
    """Input for list_cost_centers tool."""

    fiscal_year: int = Field(
        default=2024,
        description="Fiscal year for the query",
    )
    department: str | None = Field(
        default=None,
        description="Optional department filter",
    )


class GetProfitCenterInput(BaseModel):
    """Input for get_profit_center tool."""

    profit_center_id: str = Field(
        description="The SAP profit center ID (e.g., 'PC-2001')"
    )


class SearchTransactionsInput(BaseModel):
    """Input for search_transactions tool."""

    cost_center: str | None = Field(
        default=None,
        description="Filter by cost center ID",
    )
    start_date: str | None = Field(
        default=None,
        description="Start date (YYYY-MM-DD format)",
    )
    end_date: str | None = Field(
        default=None,
        description="End date (YYYY-MM-DD format)",
    )
    min_amount: float | None = Field(
        default=None,
        description="Minimum transaction amount",
    )


class CompareBudgetInput(BaseModel):
    """Input for compare_budget tool."""

    cost_center_id: str = Field(
        description="The cost center to analyze"
    )
    fiscal_year: int = Field(
        default=2024,
        description="Fiscal year for comparison",
    )


# Tool Functions

def create_financial_tools(connector: Connector) -> dict:
    """Create financial tool functions bound to a connector.

    Args:
        connector: The data connector to use.

    Returns:
        Dictionary of tool functions.
    """

    async def get_cost_center(cost_center_id: str, fiscal_year: int = 2024) -> dict:
        """Retrieve detailed cost center information including budget and actuals.

        Use this tool when you need to look up a specific cost center's
        financial data, including budget, actual spend, and committed amounts.
        """
        return await connector.execute_query(
            "cost_center",
            {"cost_center_id": cost_center_id, "fiscal_year": fiscal_year},
        )

    async def list_cost_centers(
        fiscal_year: int = 2024,
        department: str | None = None,
    ) -> dict:
        """List all cost centers with summary financial data.

        Use this tool to get an overview of all cost centers,
        optionally filtered by department.
        """
        params = {"fiscal_year": fiscal_year}
        if department:
            params["department"] = department
        return await connector.execute_query("cost_center_list", params)

    async def get_profit_center(profit_center_id: str) -> dict:
        """Retrieve profit center information including revenue and margins.

        Use this tool to look up profitability data for a specific profit center.
        """
        return await connector.execute_query(
            "profit_center",
            {"profit_center_id": profit_center_id},
        )

    async def search_transactions(
        cost_center: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        min_amount: float | None = None,
    ) -> dict:
        """Search for financial transactions with various filters.

        Use this tool to find transactions matching specific criteria.
        Results include transaction details and totals.
        """
        params = {}
        if cost_center:
            params["cost_center"] = cost_center
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        if min_amount:
            params["min_amount"] = min_amount

        return await connector.execute_query("transactions", params)

    async def compare_budget(cost_center_id: str, fiscal_year: int = 2024) -> dict:
        """Compare budget vs actuals for a cost center with variance analysis.

        Use this tool to analyze budget performance and identify
        potential overspend or underspend situations.
        """
        data = await connector.execute_query(
            "cost_center",
            {"cost_center_id": cost_center_id, "fiscal_year": fiscal_year},
        )

        budget = data.get("budget", 0)
        actuals = data.get("actuals", 0)
        committed = data.get("committed", 0)
        available = data.get("available", 0)

        variance = budget - actuals
        variance_pct = (variance / budget * 100) if budget > 0 else 0
        utilization_pct = ((actuals + committed) / budget * 100) if budget > 0 else 0

        # Determine status
        if utilization_pct > 100:
            status = "OVER_BUDGET"
        elif utilization_pct > 90:
            status = "AT_RISK"
        elif utilization_pct > 75:
            status = "ON_TRACK"
        else:
            status = "UNDER_UTILIZED"

        return {
            "cost_center_id": cost_center_id,
            "cost_center_name": data.get("name"),
            "fiscal_year": fiscal_year,
            "budget": budget,
            "actuals": actuals,
            "committed": committed,
            "available": available,
            "variance": variance,
            "variance_pct": round(variance_pct, 2),
            "utilization_pct": round(utilization_pct, 2),
            "status": status,
            "analysis": _generate_budget_analysis(
                data.get("name", cost_center_id),
                budget,
                actuals,
                committed,
                status,
            ),
        }

    return {
        "get_cost_center": get_cost_center,
        "list_cost_centers": list_cost_centers,
        "get_profit_center": get_profit_center,
        "search_transactions": search_transactions,
        "compare_budget": compare_budget,
    }


def _generate_budget_analysis(
    name: str,
    budget: float,
    actuals: float,
    committed: float,
    status: str,
) -> str:
    """Generate a human-readable budget analysis."""
    total_obligated = actuals + committed
    remaining = budget - total_obligated

    match status:
        case "OVER_BUDGET":
            return (
                f"{name} is over budget. Total obligations ({total_obligated:,.0f}) "
                f"exceed budget ({budget:,.0f}) by {abs(remaining):,.0f}."
            )
        case "AT_RISK":
            return (
                f"{name} is at risk of exceeding budget. "
                f"Only {remaining:,.0f} remains with {committed:,.0f} committed."
            )
        case "ON_TRACK":
            return (
                f"{name} is on track. {remaining:,.0f} available "
                f"({remaining/budget*100:.1f}% of budget)."
            )
        case "UNDER_UTILIZED":
            return (
                f"{name} appears under-utilized. {remaining:,.0f} remains "
                f"({remaining/budget*100:.1f}% of budget still available)."
            )
        case _:
            return f"{name}: Budget {budget:,.0f}, Actuals {actuals:,.0f}."