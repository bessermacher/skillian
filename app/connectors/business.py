"""Business database connector for SAP BW data stored in PostgreSQL."""

from dataclasses import dataclass, field
from typing import Any

import asyncpg

from app.connectors.protocol import (
    ConnectionError,
    DataNotFoundError,
    QueryNotSupportedError,
)


@dataclass
class BusinessDatabaseConnector:
    """Connector for SAP BW business data stored in PostgreSQL.

    This connector provides access to:
    - fi_reporting: Financial transactions from SAP BW FI module
    - consolidation_mart: Aggregated data for BPC consolidation
    - bpc_reporting: Business Planning and Consolidation data

    Supported query types:
    - fi_transactions: Query FI reporting data with filters
    - fi_summary: Aggregate FI data by dimensions
    - consolidation: Query consolidation mart data
    - bpc_data: Query BPC reporting data
    - company_revenue: Get revenue by company code
    - version_comparison: Compare actual vs budget/forecast
    """

    database_url: str
    _pool: asyncpg.Pool | None = field(default=None, init=False, repr=False)

    @property
    def name(self) -> str:
        """Connector name."""
        return "business"

    async def _get_pool(self) -> asyncpg.Pool:
        """Get or create connection pool."""
        if self._pool is None:
            try:
                self._pool = await asyncpg.create_pool(
                    self.database_url,
                    min_size=2,
                    max_size=10,
                )
            except Exception as e:
                raise ConnectionError(f"Failed to connect to business database: {e}")
        return self._pool

    async def close(self) -> None:
        """Close the connection pool."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def execute_query(
        self,
        query_type: str,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a query against the business database.

        Args:
            query_type: Type of query to execute.
            parameters: Query parameters for filtering.

        Returns:
            Query results as a dictionary.

        Raises:
            QueryNotSupportedError: If query type is not supported.
            ConnectionError: If database connection fails.
            DataNotFoundError: If no data matches the criteria.
        """
        match query_type:
            case "fi_transactions":
                return await self._query_fi_transactions(parameters)
            case "fi_summary":
                return await self._query_fi_summary(parameters)
            case "consolidation":
                return await self._query_consolidation(parameters)
            case "bpc_data":
                return await self._query_bpc_data(parameters)
            case "company_revenue":
                return await self._query_company_revenue(parameters)
            case "version_comparison":
                return await self._query_version_comparison(parameters)
            case "gl_account_balance":
                return await self._query_gl_account_balance(parameters)
            case "intercompany":
                return await self._query_intercompany(parameters)
            case _:
                raise QueryNotSupportedError(
                    f"Query type '{query_type}' is not supported",
                    query_type=query_type,
                )

    async def health_check(self) -> bool:
        """Check if the database connection is healthy."""
        try:
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            return True
        except Exception:
            return False

    async def _query_fi_transactions(
        self,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """Query FI reporting transactions with filters."""
        pool = await self._get_pool()

        # Build WHERE clause dynamically
        conditions: list[str] = []
        values: list[Any] = []
        param_idx = 1

        if compcode := parameters.get("company_code"):
            conditions.append(f"compcode = ${param_idx}")
            values.append(compcode)
            param_idx += 1

        if fiscper := parameters.get("fiscal_period"):
            conditions.append(f"fiscper = ${param_idx}")
            values.append(fiscper)
            param_idx += 1

        if fiscyear := parameters.get("fiscal_year"):
            conditions.append(f"fiscyear = ${param_idx}")
            values.append(fiscyear)
            param_idx += 1

        if gl_acct := parameters.get("gl_account"):
            conditions.append(f"gl_acct = ${param_idx}")
            values.append(gl_acct)
            param_idx += 1

        if prof_ctr := parameters.get("profit_center"):
            conditions.append(f"prof_ctr = ${param_idx}")
            values.append(prof_ctr)
            param_idx += 1

        if costctr := parameters.get("cost_center"):
            conditions.append(f"costctr = ${param_idx}")
            values.append(costctr)
            param_idx += 1

        if funcarea := parameters.get("functional_area"):
            conditions.append(f"funcarea = ${param_idx}")
            values.append(funcarea)
            param_idx += 1

        if version := parameters.get("version"):
            conditions.append(f"version = ${param_idx}")
            values.append(version)
            param_idx += 1

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        limit = parameters.get("limit", 100)

        query = f"""
            SELECT
                fiscper, fiscyear, compcode, gl_acct, prof_ctr, segment,
                funcarea, customer, vendor, material,
                postxt, dochdtxt, fidbcrin,
                cs_trn_lc, curkey_lc, amnt_dc, doc_currcy,
                quantity, unit, pst_date, doc_date
            FROM fi_reporting
            WHERE {where_clause}
            ORDER BY pst_date DESC, ac_docnr
            LIMIT ${param_idx}
        """
        values.append(limit)

        async with pool.acquire() as conn:
            rows = await conn.fetch(query, *values)

        if not rows:
            raise DataNotFoundError(
                "No FI transactions found matching criteria",
                query_type="fi_transactions",
            )

        return {
            "query_type": "fi_transactions",
            "count": len(rows),
            "transactions": [dict(row) for row in rows],
        }

    async def _query_fi_summary(
        self,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """Get aggregated FI data by specified dimensions."""
        pool = await self._get_pool()

        # Determine grouping dimensions
        group_by = parameters.get("group_by", ["compcode", "fiscper"])
        valid_dimensions = {
            "compcode", "fiscper", "fiscyear", "gl_acct", "prof_ctr",
            "segment", "funcarea", "costctr", "customer", "vendor",
        }

        # Validate dimensions
        group_by = [d for d in group_by if d in valid_dimensions]
        if not group_by:
            group_by = ["compcode", "fiscper"]

        group_columns = ", ".join(group_by)

        # Build WHERE clause
        conditions: list[str] = []
        values: list[Any] = []
        param_idx = 1

        if compcode := parameters.get("company_code"):
            conditions.append(f"compcode = ${param_idx}")
            values.append(compcode)
            param_idx += 1

        if fiscyear := parameters.get("fiscal_year"):
            conditions.append(f"fiscyear = ${param_idx}")
            values.append(fiscyear)
            param_idx += 1

        if version := parameters.get("version"):
            conditions.append(f"version = ${param_idx}")
            values.append(version)
            param_idx += 1

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        query = f"""
            SELECT
                {group_columns},
                SUM(cs_trn_lc) as total_amount_lc,
                SUM(quantity) as total_quantity,
                COUNT(*) as transaction_count
            FROM fi_reporting
            WHERE {where_clause}
            GROUP BY {group_columns}
            ORDER BY {group_columns}
        """

        async with pool.acquire() as conn:
            rows = await conn.fetch(query, *values)

        return {
            "query_type": "fi_summary",
            "group_by": group_by,
            "count": len(rows),
            "summary": [dict(row) for row in rows],
        }

    async def _query_consolidation(
        self,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """Query consolidation mart data."""
        pool = await self._get_pool()

        conditions: list[str] = []
        values: list[Any] = []
        param_idx = 1

        if compcode := parameters.get("company_code"):
            conditions.append(f"compcode = ${param_idx}")
            values.append(compcode)
            param_idx += 1

        if fiscper := parameters.get("fiscal_period"):
            conditions.append(f"fiscper = ${param_idx}")
            values.append(fiscper)
            param_idx += 1

        if version := parameters.get("version"):
            conditions.append(f"version = ${param_idx}")
            values.append(version)
            param_idx += 1

        if grpacct := parameters.get("group_account"):
            conditions.append(f"grpacct = ${param_idx}")
            values.append(grpacct)
            param_idx += 1

        if segment := parameters.get("segment"):
            conditions.append(f"segment = ${param_idx}")
            values.append(segment)
            param_idx += 1

        if spec := parameters.get("spec"):
            conditions.append(f"spec = ${param_idx}")
            values.append(spec)
            param_idx += 1

        if pc_area := parameters.get("pc_area"):
            conditions.append(f"pc_area = ${param_idx}")
            values.append(pc_area)
            param_idx += 1

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        limit = parameters.get("limit", 100)

        query = f"""
            SELECT
                fiscper, compcode, version, grpacct, gl_acct,
                prof_ctr, segment, pc_area, ppc_area,
                pcompcd, pcompany, spec, funcarea,
                prodh1, prodh2, bpc_src,
                cs_ytd_qty, cs_trn_qty, unit,
                cs_ytd_lc, cs_trn_lc, curkey_lc
            FROM consolidation_mart
            WHERE {where_clause}
            ORDER BY fiscper, compcode
            LIMIT ${param_idx}
        """
        values.append(limit)

        async with pool.acquire() as conn:
            rows = await conn.fetch(query, *values)

        if not rows:
            raise DataNotFoundError(
                "No consolidation data found matching criteria",
                query_type="consolidation",
            )

        return {
            "query_type": "consolidation",
            "count": len(rows),
            "data": [dict(row) for row in rows],
        }

    async def _query_bpc_data(
        self,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """Query BPC reporting data."""
        pool = await self._get_pool()

        conditions: list[str] = []
        values: list[Any] = []
        param_idx = 1

        if compcode := parameters.get("company_code"):
            conditions.append(f"compcode = ${param_idx}")
            values.append(compcode)
            param_idx += 1

        if fiscper := parameters.get("fiscal_period"):
            conditions.append(f"fiscper = ${param_idx}")
            values.append(fiscper)
            param_idx += 1

        if version := parameters.get("version"):
            conditions.append(f"version = ${param_idx}")
            values.append(version)
            param_idx += 1

        if scope := parameters.get("scope"):
            conditions.append(f"scope = ${param_idx}")
            values.append(scope)
            param_idx += 1

        if grpacct := parameters.get("group_account"):
            conditions.append(f"grpacct = ${param_idx}")
            values.append(grpacct)
            param_idx += 1

        if funcarea := parameters.get("functional_area"):
            conditions.append(f"funcarea = ${param_idx}")
            values.append(funcarea)
            param_idx += 1

        if dsource := parameters.get("data_source"):
            conditions.append(f"dsource = ${param_idx}")
            values.append(dsource)
            param_idx += 1

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        limit = parameters.get("limit", 100)

        query = f"""
            SELECT
                fiscper, compcode, version, scope,
                grpacct, funcarea, spec, dsource,
                pc_area, ppc_area, pcompcd,
                cs_trn_lc, cs_trn_gc
            FROM bpc_reporting
            WHERE {where_clause}
            ORDER BY fiscper, compcode
            LIMIT ${param_idx}
        """
        values.append(limit)

        async with pool.acquire() as conn:
            rows = await conn.fetch(query, *values)

        if not rows:
            raise DataNotFoundError(
                "No BPC data found matching criteria",
                query_type="bpc_data",
            )

        return {
            "query_type": "bpc_data",
            "count": len(rows),
            "data": [dict(row) for row in rows],
        }

    async def _query_company_revenue(
        self,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """Get revenue summary by company code."""
        pool = await self._get_pool()

        conditions: list[str] = ["grpacct = 'G4000000'"]  # Revenue account
        values: list[Any] = []
        param_idx = 1

        if compcode := parameters.get("company_code"):
            conditions.append(f"compcode = ${param_idx}")
            values.append(compcode)
            param_idx += 1

        if fiscper := parameters.get("fiscal_period"):
            conditions.append(f"fiscper = ${param_idx}")
            values.append(fiscper)
            param_idx += 1

        if version := parameters.get("version"):
            conditions.append(f"version = ${param_idx}")
            values.append(version)
            param_idx += 1
        else:
            conditions.append(f"version = ${param_idx}")
            values.append("ACTUAL")
            param_idx += 1

        where_clause = " AND ".join(conditions)

        query = f"""
            SELECT
                compcode,
                fiscper,
                version,
                pc_area,
                SUM(cs_trn_lc) as revenue_lc,
                SUM(cs_trn_gc) as revenue_gc
            FROM bpc_reporting
            WHERE {where_clause}
            GROUP BY compcode, fiscper, version, pc_area
            ORDER BY compcode, fiscper
        """

        async with pool.acquire() as conn:
            rows = await conn.fetch(query, *values)

        if not rows:
            raise DataNotFoundError(
                "No revenue data found for specified criteria",
                query_type="company_revenue",
            )

        return {
            "query_type": "company_revenue",
            "count": len(rows),
            "revenue": [dict(row) for row in rows],
        }

    async def _query_version_comparison(
        self,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """Compare actual vs budget/forecast data."""
        pool = await self._get_pool()

        compcode = parameters.get("company_code", "1000")
        fiscper = parameters.get("fiscal_period")
        compare_version = parameters.get("compare_version", "BUDGET")

        conditions = ["compcode = $1"]
        values: list[Any] = [compcode]
        param_idx = 2

        if fiscper:
            conditions.append(f"fiscper = ${param_idx}")
            values.append(fiscper)
            param_idx += 1

        where_clause = " AND ".join(conditions)

        query = f"""
            WITH actual_data AS (
                SELECT
                    compcode, fiscper, grpacct, funcarea,
                    SUM(cs_trn_lc) as actual_amount,
                    SUM(cs_trn_gc) as actual_gc
                FROM bpc_reporting
                WHERE {where_clause} AND version = 'ACTUAL'
                GROUP BY compcode, fiscper, grpacct, funcarea
            ),
            compare_data AS (
                SELECT
                    compcode, fiscper, grpacct, funcarea,
                    SUM(cs_trn_lc) as compare_amount,
                    SUM(cs_trn_gc) as compare_gc
                FROM bpc_reporting
                WHERE {where_clause} AND version = ${param_idx}
                GROUP BY compcode, fiscper, grpacct, funcarea
            )
            SELECT
                COALESCE(a.compcode, c.compcode) as compcode,
                COALESCE(a.fiscper, c.fiscper) as fiscper,
                COALESCE(a.grpacct, c.grpacct) as grpacct,
                COALESCE(a.funcarea, c.funcarea) as funcarea,
                COALESCE(a.actual_amount, 0) as actual_amount,
                COALESCE(c.compare_amount, 0) as compare_amount,
                COALESCE(a.actual_amount, 0) - COALESCE(c.compare_amount, 0) as variance,
                CASE
                    WHEN COALESCE(c.compare_amount, 0) != 0
                    THEN ROUND(((COALESCE(a.actual_amount, 0) - COALESCE(c.compare_amount, 0))
                           / ABS(c.compare_amount) * 100)::numeric, 2)
                    ELSE NULL
                END as variance_pct
            FROM actual_data a
            FULL OUTER JOIN compare_data c
                ON a.compcode = c.compcode
                AND a.fiscper = c.fiscper
                AND a.grpacct = c.grpacct
                AND a.funcarea = c.funcarea
            ORDER BY fiscper, grpacct
        """
        values.append(compare_version)

        async with pool.acquire() as conn:
            rows = await conn.fetch(query, *values)

        return {
            "query_type": "version_comparison",
            "company_code": compcode,
            "compare_version": compare_version,
            "count": len(rows),
            "comparison": [dict(row) for row in rows],
        }

    async def _query_gl_account_balance(
        self,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """Get GL account balances."""
        pool = await self._get_pool()

        conditions: list[str] = []
        values: list[Any] = []
        param_idx = 1

        if gl_acct := parameters.get("gl_account"):
            conditions.append(f"gl_acct = ${param_idx}")
            values.append(gl_acct)
            param_idx += 1

        if compcode := parameters.get("company_code"):
            conditions.append(f"compcode = ${param_idx}")
            values.append(compcode)
            param_idx += 1

        if fiscyear := parameters.get("fiscal_year"):
            conditions.append(f"fiscyear = ${param_idx}")
            values.append(fiscyear)
            param_idx += 1

        if not conditions:
            conditions.append("1=1")

        where_clause = " AND ".join(conditions)

        query = f"""
            SELECT
                gl_acct,
                compcode,
                fiscyear,
                SUM(CASE WHEN fidbcrin = 'S' THEN cs_trn_lc ELSE 0 END) as debit_total,
                SUM(CASE WHEN fidbcrin = 'H' THEN cs_trn_lc ELSE 0 END) as credit_total,
                SUM(cs_trn_lc) as net_balance,
                curkey_lc as currency,
                COUNT(*) as posting_count
            FROM fi_reporting
            WHERE {where_clause}
            GROUP BY gl_acct, compcode, fiscyear, curkey_lc
            ORDER BY gl_acct, compcode, fiscyear
        """

        async with pool.acquire() as conn:
            rows = await conn.fetch(query, *values)

        if not rows:
            raise DataNotFoundError(
                "No GL account data found",
                query_type="gl_account_balance",
            )

        return {
            "query_type": "gl_account_balance",
            "count": len(rows),
            "balances": [dict(row) for row in rows],
        }

    async def _query_intercompany(
        self,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """Query intercompany transactions and eliminations."""
        pool = await self._get_pool()

        conditions = ["pcompcd IS NOT NULL"]
        values: list[Any] = []
        param_idx = 1

        if compcode := parameters.get("company_code"):
            conditions.append(f"compcode = ${param_idx}")
            values.append(compcode)
            param_idx += 1

        if partner := parameters.get("partner_company"):
            conditions.append(f"pcompcd = ${param_idx}")
            values.append(partner)
            param_idx += 1

        if fiscper := parameters.get("fiscal_period"):
            conditions.append(f"fiscper = ${param_idx}")
            values.append(fiscper)
            param_idx += 1

        if version := parameters.get("version"):
            conditions.append(f"version = ${param_idx}")
            values.append(version)
            param_idx += 1

        where_clause = " AND ".join(conditions)

        query = f"""
            SELECT
                compcode,
                pcompcd as partner_company,
                fiscper,
                version,
                grpacct,
                spec,
                pc_area,
                ppc_area as partner_pc_area,
                cs_trn_lc as amount_lc,
                curkey_lc as currency
            FROM consolidation_mart
            WHERE {where_clause}
            ORDER BY compcode, pcompcd, fiscper
        """

        async with pool.acquire() as conn:
            rows = await conn.fetch(query, *values)

        if not rows:
            raise DataNotFoundError(
                "No intercompany data found",
                query_type="intercompany",
            )

        return {
            "query_type": "intercompany",
            "count": len(rows),
            "transactions": [dict(row) for row in rows],
        }
