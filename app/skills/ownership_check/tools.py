"""Tool implementations for ownership_check skill."""

from typing import Any

from app.connectors.datasphere import DatasphereConnector, DatasphereQueryError


_connector: DatasphereConnector | None = None


def _get_connector(connector: Any) -> DatasphereConnector:
    """Get or cache the Datasphere connector."""
    global _connector
    if connector is not None:
        _connector = connector
    if _connector is None:
        raise ValueError("Datasphere connector not configured")
    return _connector


async def check_ownership(
    param_fiscper: str,
    param_cocd: str,
    connector: Any = None,
) -> dict[str, Any]:
    """Check if a company code is present in the defined scope and fiscal period."""
    conn = _get_connector(connector)




    query = f"""
SELECT * FROM "BW2AI"."CV_ZBC_AA08Z"
WHERE "FISCPER" = '{param_fiscper}'
 AND "/BIC/ZCOMPCODE" = '{param_cocd}'
 AND (("/BIC/ZSCOPE" IN ('S_LEGAL', 'S_LEGAL_DKK', 'S_LEGAL_SPECIAL') AND "/BIC/ZVERSION" = '001')
 OR ("/BIC/ZSCOPE" = 'S_LEGAL' AND "/BIC/ZVERSION" = '021'))
""".strip()

    try:
        results = await conn.execute_sql(query)
        found = len(results) > 0
        return {
            "result": found,
            "rows_found": len(results),
            "param_fiscper": param_fiscper,
            "param_cocd": param_cocd,
            "columns": print(results)
        }
    except DatasphereQueryError as e:
        return {
            "error": str(e),
            "result": None,
            "param_fiscper": param_fiscper,
            "param_cocd": param_cocd,
        }
