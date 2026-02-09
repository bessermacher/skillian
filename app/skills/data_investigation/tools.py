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


def start_investigation(
    problem_description: str,
    report_name: str | None = None,
    company_code: str | None = None,
    fiscal_period: str | None = None,
    connector: Any = None,
) -> dict[str, Any]:
    """Start a new data investigation."""
    global _current_investigation

    if connector is not None:
        _get_connector(connector)

    _current_investigation = {
        "id": f"inv_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S_%f')}",
        "started_at": datetime.now(UTC).isoformat(),
        "problem_description": problem_description,
        "report_name": report_name,
        "company_code": company_code,
        "fiscal_period": fiscal_period,
        "findings": [],
        "status": "in_progress",
    }

    return {
        "investigation_id": _current_investigation["id"],
        "status": "started",
        "problem_description": problem_description,
        "context": {
            "report_name": report_name,
            "company_code": company_code,
            "fiscal_period": fiscal_period,
        },
        "message": "Investigation started. Follow the relevant playbook to diagnose the issue.",
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
