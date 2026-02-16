"""Tool implementations for data_investigation skill."""

from datetime import UTC, datetime
from typing import Any

from app.connectors.datasphere import DatasphereConnector

# Module-level connector cache
_connector: DatasphereConnector | None = None

# In-memory investigation state (conversation-scoped).
# Replaced when a new investigation starts.
_current_investigation: dict[str, Any] | None = None


def _get_connector(connector: Any) -> DatasphereConnector:
    """Get or cache the Datasphere connector."""
    global _connector
    if connector is not None:
        _connector = connector
    if _connector is None:
        raise ValueError("Datasphere connector not configured")
    return _connector


_VERSION_TABLE_MAP = {
    "001": "CV_ZBC_AA61",
    "002": "CV_ZBC_AA61",
    "003": "CV_ZBC_AA61",
    "004": "CV_ZBC_AA61",
    "021": "CV_ZBC_AA62",
}


def _build_next_step(inv: dict[str, Any]) -> dict[str, Any]:
    """Build the next_step directive from an investigation's state."""
    version = inv.get("version", "001")
    table = _VERSION_TABLE_MAP.get(version, "CV_ZBC_AA61")
    filters: dict[str, str] = {}
    if inv.get("company_code"):
        filters["ZCOMPCODE"] = inv["company_code"]
    if inv.get("fiscal_period"):
        filters["FISCPER"] = inv["fiscal_period"]
    return {"action": "call check_data_availability now", "table": table, "filters": filters}


def start_investigation(
    problem_description: str,
    report_name: str | None = None,
    company_code: str | None = None,
    fiscal_period: str | None = None,
    version: str | None = None,
    connector: Any = None,
) -> dict[str, Any]:
    """Start a new data investigation."""
    global _current_investigation

    if connector is not None:
        _get_connector(connector)

    # Guard: refuse to restart if an investigation is already in progress.
    # This prevents the LLM from looping on start_investigation instead of
    # proceeding with the playbook.
    if _current_investigation is not None and _current_investigation["status"] == "in_progress":
        return {
            "error": "Investigation already in progress. Do NOT call start_investigation again.",
            "investigation_id": _current_investigation["id"],
            "instruction": (
                "Continue the current investigation. "
                "Call check_data_availability NOW with the table and filters below."
            ),
            "next_step": _build_next_step(_current_investigation),
        }

    version = version or "001"

    _current_investigation = {
        "id": f"inv_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S_%f')}",
        "started_at": datetime.now(UTC).isoformat(),
        "problem_description": problem_description,
        "report_name": report_name,
        "company_code": company_code,
        "fiscal_period": fiscal_period,
        "version": version,
        "findings": [],
        "status": "in_progress",
    }

    return {
        "investigation_id": _current_investigation["id"],
        "status": "started",
        "next_step": _build_next_step(_current_investigation),
    }


def record_finding(
    step_name: str,
    result_summary: str,
    conclusion: str,
    tool_used: str | None = None,
    status: str | None = None,
    connector: Any = None,
) -> dict[str, Any]:
    """Record a finding from an investigation step."""
    global _current_investigation

    if connector is not None:
        _get_connector(connector)

    if _current_investigation is None:
        return {
            "error": "No active investigation. Call start_investigation first.",
        }

    finding = {
        "step_number": len(_current_investigation["findings"]) + 1,
        "step_name": step_name,
        "tool_used": tool_used,
        "result_summary": result_summary,
        "conclusion": conclusion,
        "status": status or "needs_further_check",
        "recorded_at": datetime.now(UTC).isoformat(),
    }

    _current_investigation["findings"].append(finding)

    return {
        "recorded": True,
        "step_number": finding["step_number"],
        "step_name": step_name,
        "total_findings": len(_current_investigation["findings"]),
    }


def get_investigation_summary(
    connector: Any = None,
) -> dict[str, Any]:
    """Get complete investigation summary."""
    if connector is not None:
        _get_connector(connector)

    if _current_investigation is None:
        return {
            "error": "No active investigation.",
            "findings": [],
        }

    inv = _current_investigation
    finding_statuses = [f["status"] for f in inv["findings"]]

    if "issue_found" in finding_statuses:
        overall_status = "issues_identified"
    elif finding_statuses and all(s == "normal" for s in finding_statuses):
        overall_status = "no_issues_found"
    else:
        overall_status = "investigation_in_progress"

    return {
        "investigation_id": inv["id"],
        "problem_description": inv["problem_description"],
        "context": {
            "report_name": inv["report_name"],
            "company_code": inv["company_code"],
            "fiscal_period": inv["fiscal_period"],
        },
        "started_at": inv["started_at"],
        "status": overall_status,
        "total_findings": len(inv["findings"]),
        "findings": inv["findings"],
    }
