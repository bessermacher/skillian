"""Business skill tools for SAP BW data analysis."""

from pydantic import BaseModel, Field

from app.connectors import Connector

# Input Schemas


class GetFITransactionsInput(BaseModel):
    """Input for get_fi_transactions tool."""

    company_code: str | None = Field(
        default=None,
        description="SAP company code (e.g., '1000')",
    )
    fiscal_year: int | None = Field(
        default=None,
        description="Fiscal year (e.g., 2024)",
    )
    fiscal_period: str | None = Field(
        default=None,
        description="Fiscal period (e.g., '001' for January)",
    )
    gl_account: str | None = Field(
        default=None,
        description="GL account number",
    )
    profit_center: str | None = Field(
        default=None,
        description="Profit center ID",
    )
    cost_center: str | None = Field(
        default=None,
        description="Cost center ID",
    )
    limit: int = Field(
        default=100,
        description="Maximum number of transactions to return",
    )


class GetFISummaryInput(BaseModel):
    """Input for get_fi_summary tool."""

    company_code: str | None = Field(
        default=None,
        description="SAP company code to filter by",
    )
    fiscal_year: int | None = Field(
        default=None,
        description="Fiscal year to filter by",
    )
    group_by: list[str] = Field(
        default=["compcode", "fiscper"],
        description=(
            "Dimensions to group by: compcode, fiscper, fiscyear, gl_acct, "
            "prof_ctr, segment, funcarea, costctr"
        ),
    )


class GetConsolidationInput(BaseModel):
    """Input for get_consolidation tool."""

    company_code: str | None = Field(
        default=None,
        description="SAP company code",
    )
    fiscal_period: str | None = Field(
        default=None,
        description="Fiscal period",
    )
    version: str | None = Field(
        default=None,
        description="Data version (e.g., 'ACTUAL', 'BUDGET')",
    )
    segment: str | None = Field(
        default=None,
        description="Business segment",
    )
    limit: int = Field(
        default=100,
        description="Maximum number of records to return",
    )


class GetBPCDataInput(BaseModel):
    """Input for get_bpc_data tool."""

    company_code: str | None = Field(
        default=None,
        description="SAP company code",
    )
    fiscal_period: str | None = Field(
        default=None,
        description="Fiscal period",
    )
    version: str | None = Field(
        default=None,
        description="Data version (e.g., 'ACTUAL', 'BUDGET', 'FORECAST')",
    )
    scope: str | None = Field(
        default=None,
        description="BPC scope",
    )
    limit: int = Field(
        default=100,
        description="Maximum number of records to return",
    )


class GetCompanyRevenueInput(BaseModel):
    """Input for get_company_revenue tool."""

    company_code: str | None = Field(
        default=None,
        description="SAP company code (omit for all companies)",
    )
    fiscal_period: str | None = Field(
        default=None,
        description="Fiscal period (e.g., '012' for December)",
    )
    version: str = Field(
        default="ACTUAL",
        description="Data version (ACTUAL, BUDGET, FORECAST)",
    )


class CompareVersionsInput(BaseModel):
    """Input for compare_versions tool."""

    company_code: str = Field(
        default="1000",
        description="SAP company code",
    )
    fiscal_period: str | None = Field(
        default=None,
        description="Fiscal period to compare",
    )
    compare_version: str = Field(
        default="BUDGET",
        description="Version to compare against ACTUAL (BUDGET or FORECAST)",
    )


class GetGLAccountBalanceInput(BaseModel):
    """Input for get_gl_account_balance tool."""

    gl_account: str | None = Field(
        default=None,
        description="GL account number",
    )
    company_code: str | None = Field(
        default=None,
        description="SAP company code",
    )
    fiscal_year: int | None = Field(
        default=None,
        description="Fiscal year",
    )


class GetIntercompanyInput(BaseModel):
    """Input for get_intercompany tool."""

    company_code: str | None = Field(
        default=None,
        description="SAP company code",
    )
    partner_company: str | None = Field(
        default=None,
        description="Partner company code",
    )
    fiscal_period: str | None = Field(
        default=None,
        description="Fiscal period",
    )
    version: str | None = Field(
        default=None,
        description="Data version (ACTUAL, BUDGET)",
    )


# Tool Functions


def create_business_tools(connector: Connector) -> dict:
    """Create business tool functions bound to a connector.

    Args:
        connector: The data connector to use.

    Returns:
        Dictionary of tool functions.
    """

    async def get_fi_transactions(
        company_code: str | None = None,
        fiscal_year: int | None = None,
        fiscal_period: str | None = None,
        gl_account: str | None = None,
        profit_center: str | None = None,
        cost_center: str | None = None,
        limit: int = 100,
    ) -> dict:
        """Query FI reporting transactions with various filters.

        Use this tool to retrieve detailed financial transactions from SAP FI.
        You can filter by company, period, GL account, or cost/profit centers.
        """
        params: dict = {"limit": limit}
        if company_code:
            params["company_code"] = company_code
        if fiscal_year:
            params["fiscal_year"] = fiscal_year
        if fiscal_period:
            params["fiscal_period"] = fiscal_period
        if gl_account:
            params["gl_account"] = gl_account
        if profit_center:
            params["profit_center"] = profit_center
        if cost_center:
            params["cost_center"] = cost_center

        return await connector.execute_query("fi_transactions", params)

    async def get_fi_summary(
        company_code: str | None = None,
        fiscal_year: int | None = None,
        group_by: list[str] | None = None,
    ) -> dict:
        """Get aggregated FI data grouped by specified dimensions.

        Use this tool to get high-level summaries of financial data.
        You can group by company, period, GL account, segment, etc.
        """
        params: dict = {}
        if company_code:
            params["company_code"] = company_code
        if fiscal_year:
            params["fiscal_year"] = fiscal_year
        if group_by:
            params["group_by"] = group_by

        return await connector.execute_query("fi_summary", params)

    async def get_consolidation(
        company_code: str | None = None,
        fiscal_period: str | None = None,
        version: str | None = None,
        segment: str | None = None,
        limit: int = 100,
    ) -> dict:
        """Query consolidation mart data for BPC consolidation.

        Use this tool to retrieve consolidated financial data used
        in SAP BPC for group reporting and eliminations.
        """
        params: dict = {"limit": limit}
        if company_code:
            params["company_code"] = company_code
        if fiscal_period:
            params["fiscal_period"] = fiscal_period
        if version:
            params["version"] = version
        if segment:
            params["segment"] = segment

        return await connector.execute_query("consolidation", params)

    async def get_bpc_data(
        company_code: str | None = None,
        fiscal_period: str | None = None,
        version: str | None = None,
        scope: str | None = None,
        limit: int = 100,
    ) -> dict:
        """Query BPC reporting data for planning and consolidation.

        Use this tool to retrieve data from SAP Business Planning
        and Consolidation (BPC) for budgeting, forecasting, and reporting.
        """
        params: dict = {"limit": limit}
        if company_code:
            params["company_code"] = company_code
        if fiscal_period:
            params["fiscal_period"] = fiscal_period
        if version:
            params["version"] = version
        if scope:
            params["scope"] = scope

        return await connector.execute_query("bpc_data", params)

    async def get_company_revenue(
        company_code: str | None = None,
        fiscal_period: str | None = None,
        version: str = "ACTUAL",
    ) -> dict:
        """Get revenue summary by company code.

        Use this tool to analyze revenue performance across companies
        or for a specific company. Returns aggregated revenue data.
        """
        params: dict = {"version": version}
        if company_code:
            params["company_code"] = company_code
        if fiscal_period:
            params["fiscal_period"] = fiscal_period

        return await connector.execute_query("company_revenue", params)

    async def compare_versions(
        company_code: str = "1000",
        fiscal_period: str | None = None,
        compare_version: str = "BUDGET",
    ) -> dict:
        """Compare actual vs budget or forecast with variance analysis.

        Use this tool to analyze budget performance, identify variances,
        and compare actual results against planned figures.
        """
        params: dict = {
            "company_code": company_code,
            "compare_version": compare_version,
        }
        if fiscal_period:
            params["fiscal_period"] = fiscal_period

        result = await connector.execute_query("version_comparison", params)

        # Add summary analysis
        if result.get("comparison"):
            total_actual = sum(row.get("actual_amount", 0) for row in result["comparison"])
            total_compare = sum(row.get("compare_amount", 0) for row in result["comparison"])
            total_variance = total_actual - total_compare
            variance_pct = (
                round(total_variance / abs(total_compare) * 100, 2) if total_compare != 0 else None
            )

            result["summary"] = {
                "total_actual": total_actual,
                f"total_{compare_version.lower()}": total_compare,
                "total_variance": total_variance,
                "variance_pct": variance_pct,
                "status": _get_variance_status(variance_pct),
            }

        return result

    async def get_gl_account_balance(
        gl_account: str | None = None,
        company_code: str | None = None,
        fiscal_year: int | None = None,
    ) -> dict:
        """Get GL account balances with debit/credit breakdown.

        Use this tool to check account balances, understand debit/credit
        activity, and analyze posting patterns for specific GL accounts.
        """
        params: dict = {}
        if gl_account:
            params["gl_account"] = gl_account
        if company_code:
            params["company_code"] = company_code
        if fiscal_year:
            params["fiscal_year"] = fiscal_year

        return await connector.execute_query("gl_account_balance", params)

    async def get_intercompany(
        company_code: str | None = None,
        partner_company: str | None = None,
        fiscal_period: str | None = None,
        version: str | None = None,
    ) -> dict:
        """Query intercompany transactions and eliminations.

        Use this tool to analyze transactions between group companies,
        identify elimination entries, and reconcile intercompany balances.
        """
        params: dict = {}
        if company_code:
            params["company_code"] = company_code
        if partner_company:
            params["partner_company"] = partner_company
        if fiscal_period:
            params["fiscal_period"] = fiscal_period
        if version:
            params["version"] = version

        return await connector.execute_query("intercompany", params)

    return {
        "get_fi_transactions": get_fi_transactions,
        "get_fi_summary": get_fi_summary,
        "get_consolidation": get_consolidation,
        "get_bpc_data": get_bpc_data,
        "get_company_revenue": get_company_revenue,
        "compare_versions": compare_versions,
        "get_gl_account_balance": get_gl_account_balance,
        "get_intercompany": get_intercompany,
    }


def _get_variance_status(variance_pct: float | None) -> str:
    """Determine variance status based on percentage."""
    if variance_pct is None:
        return "UNKNOWN"
    if variance_pct > 10:
        return "FAVORABLE"
    if variance_pct > -5:
        return "ON_TARGET"
    if variance_pct > -15:
        return "UNFAVORABLE"
    return "CRITICAL"
