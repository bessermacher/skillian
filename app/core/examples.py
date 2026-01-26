"""Example patterns for creating tools.

This file demonstrates the recommended patterns for creating
tools with Pydantic input schemas.
"""

from pydantic import BaseModel, Field

from app.core.tool import Tool


# Pattern 1: Simple tool with required parameters
class GetCostCenterInput(BaseModel):
    """Input schema for get_cost_center tool."""

    cost_center_id: str = Field(
        description="The SAP cost center ID (e.g., 'CC-1001')"
    )
    fiscal_year: int = Field(
        description="Fiscal year for the query (e.g., 2024)"
    )


def get_cost_center(cost_center_id: str, fiscal_year: int) -> dict:
    """Retrieve cost center data from SAP BW.

    Args:
        cost_center_id: The cost center identifier.
        fiscal_year: The fiscal year to query.

    Returns:
        Cost center data including budget and actuals.
    """
    # Implementation would call SAP connector
    return {
        "cost_center_id": cost_center_id,
        "fiscal_year": fiscal_year,
        "budget": 100000,
        "actuals": 75000,
    }


# Creating the tool
get_cost_center_tool = Tool(
    name="get_cost_center",
    description="Retrieve cost center budget and actuals from SAP BW",
    function=get_cost_center,
    input_schema=GetCostCenterInput,
)


# Pattern 2: Tool with optional parameters
class SearchTransactionsInput(BaseModel):
    """Input schema for search_transactions tool."""

    start_date: str = Field(
        description="Start date in YYYY-MM-DD format"
    )
    end_date: str = Field(
        description="End date in YYYY-MM-DD format"
    )
    cost_center: str | None = Field(
        default=None,
        description="Optional cost center filter",
    )
    min_amount: float | None = Field(
        default=None,
        description="Optional minimum amount filter",
    )


def search_transactions(
    start_date: str,
    end_date: str,
    cost_center: str | None = None,
    min_amount: float | None = None,
) -> list[dict]:
    """Search for transactions in SAP BW.

    Args:
        start_date: Query start date.
        end_date: Query end date.
        cost_center: Optional cost center filter.
        min_amount: Optional minimum amount filter.

    Returns:
        List of matching transactions.
    """
    # Implementation would call SAP connector
    return []


search_transactions_tool = Tool(
    name="search_transactions",
    description="Search for financial transactions with optional filters",
    function=search_transactions,
    input_schema=SearchTransactionsInput,
)


# Pattern 3: Tool with enum choices
from enum import StrEnum


class ReportType(StrEnum):
    SUMMARY = "summary"
    DETAILED = "detailed"
    VARIANCE = "variance"


class GenerateReportInput(BaseModel):
    """Input schema for generate_report tool."""

    report_type: ReportType = Field(
        description="Type of report to generate"
    )
    entity_id: str = Field(
        description="Entity ID (cost center, profit center, etc.)"
    )


def generate_report(report_type: ReportType, entity_id: str) -> dict:
    """Generate a financial report.

    Args:
        report_type: The type of report to generate.
        entity_id: The entity to report on.

    Returns:
        Generated report data.
    """
    return {"type": report_type, "entity": entity_id, "data": {}}


generate_report_tool = Tool(
    name="generate_report",
    description="Generate financial reports (summary, detailed, or variance)",
    function=generate_report,
    input_schema=GenerateReportInput,
)