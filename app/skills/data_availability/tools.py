"""Tool implementations for data_availability skill."""

import re
from pathlib import Path
from typing import Any

from app.connectors.datasphere import DatasphereConnector, DatasphereQueryError

# Module-level connector cache
_connector: DatasphereConnector | None = None

# Module-level config cache
_source_config: Any | None = None

# Pattern for valid SQL identifiers (column/table names)
_VALID_IDENTIFIER = re.compile(r'^[a-zA-Z0-9_/."]+$')


def _get_connector(connector: Any) -> DatasphereConnector:
    """Get or cache the Datasphere connector."""
    global _connector
    if connector is not None:
        _connector = connector
    if _connector is None:
        raise ValueError("Datasphere connector not configured")
    return _connector


def _get_source_config():
    """Get or load the investigation source configuration."""
    global _source_config
    if _source_config is None:
        from app.skills.data_availability.source_config import load_investigation_config

        _source_config = load_investigation_config(Path("config/investigation_sources.yaml"))
    return _source_config


def _validate_identifier(name: str) -> bool:
    """Validate a SQL identifier to prevent injection."""
    return bool(_VALID_IDENTIFIER.match(name))


def list_investigation_sources(connector: Any = None) -> dict[str, Any]:
    """List all configured investigation sources."""
    if connector is not None:
        _get_connector(connector)

    config = _get_source_config()

    reports = []
    for name, report in config.reports.items():
        reports.append(
            {
                "name": name,
                "description": report.description,
                "versions": [
                    {"code": v.code, "name": v.name, "table": v.table} for v in report.versions
                ],
                "check_dimensions": [
                    {"column": d.column, "aliases": d.aliases} for d in report.check_dimensions
                ],
                "default_group_by": report.default_group_by,
            }
        )

    tables = []
    for name, table_cfg in config.tables.items():
        tables.append(
            {
                "name": name,
                "description": table_cfg.description,
                "table": table_cfg.table,
                "check_dimensions": [
                    {"column": d.column, "aliases": d.aliases} for d in table_cfg.check_dimensions
                ],
                "default_group_by": table_cfg.default_group_by,
            }
        )

    return {
        "reports": reports,
        "tables": tables,
        "scope_values": config.scope_values,
        "all_table_names": config.get_all_table_names(),
    }


async def check_data_availability(
    table: str,
    filters: dict[str, str] | None = None,
    group_by: list[str] | None = None,
    connector: Any = None,
) -> dict[str, Any]:
    """Check if data exists in a Datasphere table for given filter criteria."""
    conn = _get_connector(connector)
    config = _get_source_config()

    # Validate table name
    if not _validate_identifier(table):
        return {"error": f"Invalid table name: {table}", "data_found": False}

    # Look up default group_by from config if not provided
    if group_by is None:
        table_info = config.get_table_info(table)
        if table_info:
            group_by = table_info["default_group_by"]
        else:
            group_by = []

    # Validate group_by columns
    for col in group_by:
        if not _validate_identifier(col):
            return {"error": f"Invalid column name: {col}", "data_found": False}

    # Build SQL query
    schema = config.schema_name
    group_cols = ", ".join(f'"{col}"' for col in group_by)

    if group_cols:
        select_clause = f'{group_cols}, COUNT(*) as "ROW_COUNT"'
        group_clause = f"GROUP BY {group_cols}"
    else:
        select_clause = 'COUNT(*) as "ROW_COUNT"'
        group_clause = ""

    # Build WHERE clause from filters
    where_parts: list[str] = []
    if filters:
        for col, value in filters.items():
            if not _validate_identifier(col):
                return {"error": f"Invalid filter column: {col}", "data_found": False}
            # Escape single quotes in values
            safe_value = str(value).replace("'", "''")
            where_parts.append(f"\"{col}\" = '{safe_value}'")

    where_clause = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""

    query = f"""
SELECT {select_clause}
FROM "{schema}"."{table}"
{where_clause}
{group_clause}
""".strip()

    try:
        results = await conn.execute_sql(query)
        total_rows = sum(r.get("ROW_COUNT", 0) for r in results)

        return {
            "table": table,
            "data_found": len(results) > 0,
            "total_rows": total_rows,
            "group_count": len(results),
            "groups": results,
            "filters_applied": filters or {},
            "group_by": group_by,
            "query": query,
        }
    except DatasphereQueryError as e:
        return {
            "error": str(e),
            "table": table,
            "data_found": False,
            "groups": [],
            "filters_applied": filters or {},
        }
