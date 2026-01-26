"""Mock connector for development and testing."""

from dataclasses import dataclass, field
from typing import Any

from app.connectors.protocol import (
    ConnectorError,
    DataNotFoundError,
    QueryNotSupportedError,
)


@dataclass
class MockConnector:
    """Mock SAP BW connector with sample data.

    Provides realistic sample data for development without
    requiring SAP connectivity.
    """

    name: str = "mock"
    _data: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Initialize with sample data."""
        self._data = self._create_sample_data()

    def _create_sample_data(self) -> dict[str, Any]:
        """Create sample SAP BW data."""
        return {
            "cost_centers": {
                "CC-1001": {
                    "id": "CC-1001",
                    "name": "IT Operations",
                    "manager": "John Smith",
                    "department": "Information Technology",
                    "fiscal_years": {
                        2024: {"budget": 500000, "actuals": 425000, "committed": 50000},
                        2023: {"budget": 450000, "actuals": 448000, "committed": 0},
                    },
                },
                "CC-1002": {
                    "id": "CC-1002",
                    "name": "Marketing",
                    "manager": "Jane Doe",
                    "department": "Marketing",
                    "fiscal_years": {
                        2024: {"budget": 750000, "actuals": 620000, "committed": 80000},
                        2023: {"budget": 700000, "actuals": 695000, "committed": 0},
                    },
                },
                "CC-1003": {
                    "id": "CC-1003",
                    "name": "Sales Operations",
                    "manager": "Bob Johnson",
                    "department": "Sales",
                    "fiscal_years": {
                        2024: {"budget": 1200000, "actuals": 890000, "committed": 150000},
                        2023: {"budget": 1100000, "actuals": 1050000, "committed": 0},
                    },
                },
            },
            "profit_centers": {
                "PC-2001": {
                    "id": "PC-2001",
                    "name": "North America",
                    "revenue_ytd": 5500000,
                    "cost_ytd": 4200000,
                    "margin_pct": 23.6,
                },
                "PC-2002": {
                    "id": "PC-2002",
                    "name": "Europe",
                    "revenue_ytd": 3200000,
                    "cost_ytd": 2800000,
                    "margin_pct": 12.5,
                },
            },
            "transactions": [
                {
                    "id": "TXN-001",
                    "date": "2024-01-15",
                    "cost_center": "CC-1001",
                    "amount": 15000,
                    "description": "Server infrastructure",
                    "type": "expense",
                },
                {
                    "id": "TXN-002",
                    "date": "2024-01-20",
                    "cost_center": "CC-1002",
                    "amount": 25000,
                    "description": "Q1 Campaign",
                    "type": "expense",
                },
                {
                    "id": "TXN-003",
                    "date": "2024-02-01",
                    "cost_center": "CC-1001",
                    "amount": 8500,
                    "description": "Software licenses",
                    "type": "expense",
                },
                {
                    "id": "TXN-004",
                    "date": "2024-02-10",
                    "cost_center": "CC-1003",
                    "amount": 45000,
                    "description": "Sales conference",
                    "type": "expense",
                },
            ],
            "gl_accounts": {
                "400000": {"name": "Revenue", "type": "income"},
                "500000": {"name": "Cost of Goods Sold", "type": "expense"},
                "600000": {"name": "Operating Expenses", "type": "expense"},
                "700000": {"name": "Personnel Costs", "type": "expense"},
            },
        }

    async def execute_query(
        self,
        query_type: str,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a mock query.

        Supported query types:
        - cost_center: Get cost center by ID
        - cost_center_list: List all cost centers
        - profit_center: Get profit center by ID
        - transactions: Search transactions
        - gl_account: Get GL account by ID
        """
        match query_type:
            case "cost_center":
                return self._query_cost_center(parameters)
            case "cost_center_list":
                return self._query_cost_center_list(parameters)
            case "profit_center":
                return self._query_profit_center(parameters)
            case "transactions":
                return self._query_transactions(parameters)
            case "gl_account":
                return self._query_gl_account(parameters)
            case _:
                raise QueryNotSupportedError(
                    f"Query type '{query_type}' is not supported",
                    query_type=query_type,
                )

    def _query_cost_center(self, params: dict[str, Any]) -> dict[str, Any]:
        """Get a single cost center."""
        cost_center_id = params.get("cost_center_id")
        fiscal_year = params.get("fiscal_year", 2024)

        if not cost_center_id:
            raise ConnectorError("cost_center_id is required")

        cc = self._data["cost_centers"].get(cost_center_id)
        if not cc:
            raise DataNotFoundError(
                f"Cost center '{cost_center_id}' not found",
                query_type="cost_center",
            )

        fy_data = cc["fiscal_years"].get(fiscal_year, {})
        return {
            "id": cc["id"],
            "name": cc["name"],
            "manager": cc["manager"],
            "department": cc["department"],
            "fiscal_year": fiscal_year,
            "budget": fy_data.get("budget", 0),
            "actuals": fy_data.get("actuals", 0),
            "committed": fy_data.get("committed", 0),
            "available": fy_data.get("budget", 0)
            - fy_data.get("actuals", 0)
            - fy_data.get("committed", 0),
        }

    def _query_cost_center_list(self, params: dict[str, Any]) -> dict[str, Any]:
        """List all cost centers."""
        fiscal_year = params.get("fiscal_year", 2024)
        department = params.get("department")

        results = []
        for cc_id, cc in self._data["cost_centers"].items():
            if department and cc["department"] != department:
                continue

            fy_data = cc["fiscal_years"].get(fiscal_year, {})
            results.append({
                "id": cc["id"],
                "name": cc["name"],
                "department": cc["department"],
                "budget": fy_data.get("budget", 0),
                "actuals": fy_data.get("actuals", 0),
            })

        return {"cost_centers": results, "count": len(results)}

    def _query_profit_center(self, params: dict[str, Any]) -> dict[str, Any]:
        """Get a single profit center."""
        profit_center_id = params.get("profit_center_id")

        if not profit_center_id:
            raise ConnectorError("profit_center_id is required")

        pc = self._data["profit_centers"].get(profit_center_id)
        if not pc:
            raise DataNotFoundError(
                f"Profit center '{profit_center_id}' not found",
                query_type="profit_center",
            )

        return pc

    def _query_transactions(self, params: dict[str, Any]) -> dict[str, Any]:
        """Search transactions with filters."""
        cost_center = params.get("cost_center")
        start_date = params.get("start_date")
        end_date = params.get("end_date")
        min_amount = params.get("min_amount")

        results = []
        for txn in self._data["transactions"]:
            # Apply filters
            if cost_center and txn["cost_center"] != cost_center:
                continue
            if start_date and txn["date"] < start_date:
                continue
            if end_date and txn["date"] > end_date:
                continue
            if min_amount and txn["amount"] < min_amount:
                continue

            results.append(txn)

        total = sum(t["amount"] for t in results)
        return {"transactions": results, "count": len(results), "total_amount": total}

    def _query_gl_account(self, params: dict[str, Any]) -> dict[str, Any]:
        """Get a GL account."""
        account_id = params.get("account_id")

        if not account_id:
            raise ConnectorError("account_id is required")

        account = self._data["gl_accounts"].get(account_id)
        if not account:
            raise DataNotFoundError(
                f"GL account '{account_id}' not found",
                query_type="gl_account",
            )

        return {"id": account_id, **account}

    async def health_check(self) -> bool:
        """Mock health check always returns True."""
        return True

    def add_data(self, data_type: str, key: str, data: dict[str, Any]) -> None:
        """Add custom data for testing.

        Args:
            data_type: The data category (e.g., 'cost_centers').
            key: The data key/ID.
            data: The data to add.
        """
        if data_type not in self._data:
            self._data[data_type] = {}
        self._data[data_type][key] = data