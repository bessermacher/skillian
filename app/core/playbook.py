"""Investigation playbook for deterministic auto-chaining."""

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

# Scopes considered "legal" for consolidation checks
DEFAULT_LEGAL_SCOPES = frozenset({"S_LEGAL", "S_LEGAL_DKK", "S_LEGAL_SPECIAL"})

# Default BPC mart table for fallback checks
DEFAULT_BPC_MART_TABLE = "CV_ZFI_AA01"

# Type alias for the tool executor callback
ToolExecutor = Callable[[str, dict[str, Any]], Awaitable[str]]


def _format_totals_with_currency(
    totals: dict[str, Any],
    groups: list[dict[str, Any]],
) -> str:
    """Format totals dict with currency codes extracted from group data."""
    lc_currencies = {g.get("CURKEY_LC") for g in groups if g.get("CURKEY_LC")}
    gc_currencies = {g.get("CURKEY_GC") for g in groups if g.get("CURKEY_GC")}

    lc_label = ", ".join(sorted(lc_currencies)) if lc_currencies else "LC"
    gc_label = ", ".join(sorted(gc_currencies)) if gc_currencies else "GC"

    parts: list[str] = []
    if "CS_TRN_LC" in totals:
        parts.append(f"LC: {totals['CS_TRN_LC']:,.2f} {lc_label}")
    if "CS_TRN_GC" in totals:
        parts.append(f"GC: {totals['CS_TRN_GC']:,.2f} {gc_label}")
    for key, value in totals.items():
        if key not in ("CS_TRN_LC", "CS_TRN_GC"):
            parts.append(f"{key}: {value}")

    return "; ".join(parts) if parts else str(totals)


class InvestigationPlaybook:
    """Deterministic investigation playbook execution.

    After start_investigation returns a next_step, this class
    auto-executes the entire playbook (check data, record findings,
    branch, and summarise) so the LLM only needs to present
    the final text response.

    The playbook receives a ``execute_tool`` callback that handles
    conversation tracking and timing — it has no dependency on
    the Agent class internals.
    """

    def __init__(
        self,
        legal_scopes: frozenset[str] | None = None,
        bpc_mart_table: str | None = None,
    ):
        self.legal_scopes = legal_scopes or DEFAULT_LEGAL_SCOPES
        self.bpc_mart_table = bpc_mart_table or DEFAULT_BPC_MART_TABLE

    async def try_auto_chain(
        self,
        tool_name: str,
        result: str,
        execute_tool: ToolExecutor,
    ) -> bool:
        """Run the full investigation playbook deterministically.

        Args:
            tool_name: Name of the tool that just completed.
            result: JSON result string from the tool.
            execute_tool: Async callback ``(name, args) -> result_str``
                that executes a tool and tracks it.

        Returns:
            True if auto-chaining was executed.
        """
        if tool_name != "start_investigation":
            return False

        try:
            result_data = json.loads(result)
        except (json.JSONDecodeError, TypeError):
            return False

        next_step = result_data.get("next_step")
        if not next_step or "table" not in next_step:
            return False

        filters = next_step.get("filters", {})
        company_code = filters.get("ZCOMPCODE", "")
        fiscal_period = filters.get("FISCPER", "")
        table = next_step["table"]
        version = next_step.get("version", "001")
        version_name = next_step.get("version_name", f"Version {version}")

        # --- Step 1: check_data_availability on reporting table ---
        check_args: dict[str, Any] = {"table": table}
        if filters:
            check_args["filters"] = filters

        check_result_str = await execute_tool("check_data_availability", check_args)

        try:
            check_result = json.loads(check_result_str)
        except (json.JSONDecodeError, TypeError):
            check_result = {}

        data_found = check_result.get("data_found", False)
        groups = check_result.get("groups", [])
        totals = check_result.get("totals", {})
        scopes = [g.get("ZSCOPE") for g in groups if g.get("ZSCOPE")]
        has_legal = any(s in self.legal_scopes for s in scopes)
        all_s_none = scopes and all(s == "S_NONE" for s in scopes)

        formatted_totals = _format_totals_with_currency(totals, groups)

        if data_found and has_legal:
            await self._handle_legal_scope(
                execute_tool,
                table,
                company_code,
                fiscal_period,
                version,
                version_name,
                scopes,
                formatted_totals,
            )
        elif data_found and all_s_none:
            await self._handle_s_none(
                execute_tool,
                table,
                company_code,
                fiscal_period,
                version,
                version_name,
                formatted_totals,
            )
        elif not data_found:
            await self._handle_no_data(
                execute_tool,
                table,
                company_code,
                fiscal_period,
                version,
                version_name,
            )
        else:
            await self._handle_mixed_scopes(
                execute_tool,
                table,
                company_code,
                fiscal_period,
                version,
                version_name,
                scopes,
                formatted_totals,
            )

        # --- Final: get_investigation_summary ---
        await execute_tool("get_investigation_summary", {})

        return True

    # ------------------------------------------------------------------
    # Branch handlers
    # ------------------------------------------------------------------

    async def _handle_legal_scope(
        self,
        execute_tool: ToolExecutor,
        table: str,
        company_code: str,
        fiscal_period: str,
        version: str,
        version_name: str,
        scopes: list[str],
        formatted_totals: str,
    ) -> None:
        """Data found with expected legal scope — END."""
        scope_list = ", ".join(scopes)
        legal_scopes_found = ", ".join(s for s in scopes if s in self.legal_scopes)
        await execute_tool(
            "record_finding",
            {
                "step_name": "Check reporting table",
                "tool_used": "check_data_availability",
                "result_summary": (
                    f"Data found in {table} for CoCd {company_code}, "
                    f"period {fiscal_period}, version {version} ({version_name}). "
                    f"{len(scopes)} scope groups: {scope_list}. "
                    f"Totals: {formatted_totals}"
                ),
                "conclusion": (
                    "Data exists with expected legal consolidation scope "
                    f"({legal_scopes_found}). "
                    "Issue may be in report configuration or user filters."
                ),
                "status": "normal",
            },
        )

    async def _handle_s_none(
        self,
        execute_tool: ToolExecutor,
        table: str,
        company_code: str,
        fiscal_period: str,
        version: str,
        version_name: str,
        formatted_totals: str,
    ) -> None:
        """Only S_NONE — consolidation stopped → check ownership."""
        await execute_tool(
            "record_finding",
            {
                "step_name": "Check reporting table",
                "tool_used": "check_data_availability",
                "result_summary": (
                    f"Data found in {table} but only S_NONE scope. "
                    f"CoCd {company_code}, period {fiscal_period}, "
                    f"version {version} ({version_name}). "
                    f"Totals: {formatted_totals}"
                ),
                "conclusion": (
                    "Currency conversion ran but consolidation stopped. Checking ownership next."
                ),
                "status": "needs_further_check",
            },
        )

        ownership_str = await execute_tool(
            "check_ownership",
            {
                "param_fiscper": fiscal_period,
                "param_cocd": company_code,
            },
        )

        try:
            ownership = json.loads(ownership_str)
        except (json.JSONDecodeError, TypeError):
            ownership = {}

        if ownership.get("result"):
            await execute_tool(
                "record_finding",
                {
                    "step_name": "Check ownership",
                    "tool_used": "check_ownership",
                    "result_summary": (
                        f"Ownership found for CoCd {company_code}, "
                        f"period {fiscal_period}. "
                        f"{ownership.get('rows_found', 0)} rows."
                    ),
                    "conclusion": (
                        "Company IS in scope. Consolidation process "
                        "likely failed or was incomplete. "
                        "Recommend: Re-run consolidation for this period."
                    ),
                    "status": "issue_found",
                },
            )
        else:
            await execute_tool(
                "record_finding",
                {
                    "step_name": "Check ownership",
                    "tool_used": "check_ownership",
                    "result_summary": (
                        f"No ownership found for CoCd {company_code}, period {fiscal_period}."
                    ),
                    "conclusion": (
                        "Company was removed from scope for this period. "
                        "Check with consolidation team whether this is "
                        "intentional."
                    ),
                    "status": "issue_found",
                },
            )

    async def _handle_no_data(
        self,
        execute_tool: ToolExecutor,
        table: str,
        company_code: str,
        fiscal_period: str,
        version: str,
        version_name: str,
    ) -> None:
        """No data at all → check BPC mart."""
        await execute_tool(
            "record_finding",
            {
                "step_name": "Check reporting table",
                "tool_used": "check_data_availability",
                "result_summary": (
                    f"No data found in {table} for CoCd {company_code}, "
                    f"period {fiscal_period}, "
                    f"version {version} ({version_name})."
                ),
                "conclusion": (
                    "Data missing from reporting table entirely. Checking BPC mart next."
                ),
                "status": "needs_further_check",
            },
        )

        bpc_str = await execute_tool(
            "check_data_availability",
            {
                "table": self.bpc_mart_table,
                "filters": {
                    "ZCOMPCODE": company_code,
                    "FISCPER": fiscal_period,
                },
                "group_by": ["ZCOMPCODE", "FISCPER"],
            },
        )

        try:
            bpc_result = json.loads(bpc_str)
        except (json.JSONDecodeError, TypeError):
            bpc_result = {}

        if bpc_result.get("data_found"):
            await execute_tool(
                "record_finding",
                {
                    "step_name": "Check BPC mart",
                    "tool_used": "check_data_availability",
                    "result_summary": (
                        f"Data found in {self.bpc_mart_table} for "
                        f"CoCd {company_code}, period {fiscal_period}."
                    ),
                    "conclusion": (
                        "Data exists in BPC mart but not in reporting. "
                        "Reporting data load likely not triggered. "
                        "Recommend: Trigger reporting refresh or check "
                        "data load logs."
                    ),
                    "status": "issue_found",
                },
            )
        else:
            await execute_tool(
                "record_finding",
                {
                    "step_name": "Check BPC mart",
                    "tool_used": "check_data_availability",
                    "result_summary": (
                        f"No data found in {self.bpc_mart_table} for "
                        f"CoCd {company_code}, period {fiscal_period}."
                    ),
                    "conclusion": (
                        "Data missing from consolidation entirely. "
                        "The issue is upstream of the BPC mart. "
                        "Recommend: Check source data loads into BPC."
                    ),
                    "status": "issue_found",
                },
            )

    async def _handle_mixed_scopes(
        self,
        execute_tool: ToolExecutor,
        table: str,
        company_code: str,
        fiscal_period: str,
        version: str,
        version_name: str,
        scopes: list[str],
        formatted_totals: str,
    ) -> None:
        """Data found with mixed/unknown scopes."""
        scope_list = ", ".join(scopes) if scopes else "none"
        await execute_tool(
            "record_finding",
            {
                "step_name": "Check reporting table",
                "tool_used": "check_data_availability",
                "result_summary": (
                    f"Data found in {table} with scopes: {scope_list}. "
                    f"CoCd {company_code}, period {fiscal_period}, "
                    f"version {version} ({version_name}). "
                    f"Totals: {formatted_totals}"
                ),
                "conclusion": (
                    f"Data exists with non-standard scopes ({scope_list}). "
                    "Further manual investigation may be needed."
                ),
                "status": "needs_further_check",
            },
        )
