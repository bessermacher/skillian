"""Main agent orchestration."""

import json
import logging
import re
import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from app.core.messages import Conversation, Message, MessageRole
from app.core.registry import SkillRegistry

logger = logging.getLogger(__name__)

_TOOL_CALL_NUDGE = (
    "You appear to have described tool calls in your text response instead of "
    "invoking them. Do NOT output tool call JSON as text. You MUST use the "
    "proper tool calling mechanism to invoke tools. Please proceed with the "
    "investigation by making the actual tool calls now."
)

_CONTINUE_NUDGE = (
    "You described what you intend to do instead of actually doing it. "
    "Do NOT explain or narrate — call the tool NOW. "
    "Use the structured tool calling mechanism to invoke the next tool."
)

_INVESTIGATION_NUDGE_PREFIX = (
    "Do NOT start a new investigation — continue the current one. "
    "Do NOT respond with text until the workflow is complete. "
)


@dataclass
class AgentResponse:
    """Response from agent processing."""

    content: str
    tool_calls_made: list[dict[str, Any]] = field(default_factory=list)
    finished: bool = True
    timing: dict[str, Any] = field(default_factory=dict)


class Agent:
    """Main agent for processing user queries with skills.

    The agent:
    1. Binds all skill tools to the LLM
    2. Processes user messages
    3. Executes tool calls when requested by LLM
    4. Returns responses to the user

    Example:
        agent = Agent(chat_model, registry)
        response = await agent.process("What's the budget for CC-1001?")
        print(response.content)
    """

    def __init__(
        self,
        chat_model: BaseChatModel,
        registry: SkillRegistry,
        max_iterations: int = 15,
    ):
        """Initialize the agent.

        Args:
            chat_model: LangChain chat model to use.
            registry: Skill registry with available tools.
            max_iterations: Maximum tool call iterations to prevent loops.
        """
        self.registry = registry
        self.max_iterations = max_iterations
        self.conversation = Conversation()

        # Bind tools to the model
        tools = registry.get_all_tools()
        if tools:
            langchain_tools = [t.to_langchain_tool() for t in tools]
            self.model = chat_model.bind_tools(langchain_tools)
        else:
            self.model = chat_model

        # Set up system prompt
        self._setup_system_prompt()

    def _setup_system_prompt(self) -> None:
        """Set up the system prompt with skill context."""
        base_prompt = """You are Skillian, an AI assistant specialized in \
diagnosing SAP BW data issues.

You have access to tools that can query SAP BW data. Use these tools to help users:
- Analyze financial data (cost centers, profit centers, budgets)
- Investigate data discrepancies
- Generate reports and summaries

When asked about data, use the appropriate tools to fetch real information.
Be concise and accurate in your responses.

IMPORTANT: Always proceed with the full diagnostic autonomously. Do NOT ask \
the user for confirmation between steps. Call all necessary tools in sequence \
and present the final findings when done.

When investigating data issues, you MUST execute every playbook step by calling \
the appropriate tools. Do NOT stop after a single tool call to summarize or \
explain — complete the entire investigation workflow via tool calls first, then \
present the final summary as text.
"""
        skill_context = self.registry.get_combined_system_prompt()

        if skill_context:
            full_prompt = f"{base_prompt}\n\n{skill_context}"
        else:
            full_prompt = base_prompt

        self.conversation.add(Message.system(full_prompt))

    def _convert_to_langchain_messages(self) -> list[BaseMessage]:
        """Convert conversation to LangChain message format."""
        lc_messages: list[BaseMessage] = []

        for msg in self.conversation.messages:
            match msg.role:
                case MessageRole.SYSTEM:
                    lc_messages.append(SystemMessage(content=msg.content))
                case MessageRole.USER:
                    lc_messages.append(HumanMessage(content=msg.content))
                case MessageRole.ASSISTANT:
                    if msg.tool_calls:
                        lc_messages.append(
                            AIMessage(content=msg.content, tool_calls=msg.tool_calls)
                        )
                    else:
                        lc_messages.append(AIMessage(content=msg.content))
                case MessageRole.TOOL:
                    lc_messages.append(
                        ToolMessage(content=msg.content, tool_call_id=msg.tool_call_id or "")
                    )

        return lc_messages

    async def _execute_tool(self, tool_name: str, tool_args: dict[str, Any]) -> str:
        """Execute a tool and return the result as a string.

        Args:
            tool_name: Name of the tool to execute.
            tool_args: Arguments for the tool.

        Returns:
            Tool result as a JSON string.
        """
        try:
            tool = self.registry.get_tool(tool_name)
            result = await tool.aexecute(**tool_args)

            # Convert result to JSON string for LLM
            if isinstance(result, str):
                return result
            return json.dumps(result, indent=2, default=str)

        except Exception as e:
            return json.dumps({"error": str(e)})

    def _mentions_tools(self, content: str) -> bool:
        """Check if text response mentions registered tool names.

        Used to detect when the LLM describes calling a tool instead of
        actually invoking it via the structured tool calling mechanism.
        """
        if not content:
            return False

        known_tools = {t.name for t in self.registry.get_all_tools()}
        content_lower = content.lower()
        return any(tool_name in content_lower for tool_name in known_tools)

    def _looks_like_tool_calls(self, content: str) -> bool:
        """Detect if LLM response text contains tool call JSON instead of proper tool_calls.

        Looks for patterns like {"name": "tool_name", ...} where tool_name
        matches a registered tool.
        """
        if not content:
            return False

        known_tools = {t.name for t in self.registry.get_all_tools()}
        if not known_tools:
            return False

        pattern = r'\{\s*"name"\s*:\s*"([^"]+)"'
        matches = re.findall(pattern, content)
        return any(match in known_tools for match in matches)

    def _investigation_incomplete(self, tool_calls_made: list[dict[str, Any]]) -> bool:
        """Check if an investigation was started but not completed.

        Returns True when start_investigation was called but
        get_investigation_summary was not, meaning the LLM is trying
        to respond with text before completing the workflow.
        """
        tools_called = {tc["tool"] for tc in tool_calls_made}
        return (
            "start_investigation" in tools_called
            and "get_investigation_summary" not in tools_called
        )

    def _investigation_completed(self, tool_calls_made: list[dict[str, Any]]) -> bool:
        """Check if an investigation workflow was fully completed.

        Returns True when both start_investigation and
        get_investigation_summary were called. Used to suppress
        the _mentions_tools nudge on the final summary text,
        which naturally references tool names.
        """
        tools_called = {tc["tool"] for tc in tool_calls_made}
        return (
            "start_investigation" in tools_called
            and "get_investigation_summary" in tools_called
        )

    _LEGAL_SCOPES = {"S_LEGAL", "S_LEGAL_DKK", "S_LEGAL_SPECIAL"}

    async def _auto_execute_tool(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        tool_calls_made: list[dict[str, Any]],
        tool_timings: list[dict[str, Any]],
    ) -> str:
        """Execute a tool as part of auto-chaining and track it.

        Adds the synthetic tool call and result to the conversation
        so the LLM can see it on subsequent turns.

        Returns the tool result as a JSON string.
        """
        call_id = f"auto_{tool_name}_{len(tool_calls_made)}"

        self.conversation.add_assistant(
            content="",
            tool_calls=[{
                "name": tool_name,
                "args": tool_args,
                "id": call_id,
            }],
        )

        tool_start = time.perf_counter()
        result = await self._execute_tool(tool_name, tool_args)
        tool_duration = time.perf_counter() - tool_start

        tool_timings.append({
            "tool": tool_name,
            "duration_seconds": round(tool_duration, 3),
        })

        self.conversation.add_tool_result(result, call_id)

        tool_calls_made.append({
            "tool": tool_name,
            "args": tool_args,
            "result": result,
            "duration_seconds": round(tool_duration, 3),
        })

        logger.info("Auto-chained %s", tool_name)
        return result

    async def _try_auto_chain(
        self,
        tool_name: str,
        result: str,
        tool_calls_made: list[dict[str, Any]],
        tool_timings: list[dict[str, Any]],
    ) -> bool:
        """Run the full investigation playbook deterministically.

        After start_investigation returns a next_step, this method
        auto-executes the entire playbook (check data, record findings,
        branch, and summarise) so the LLM only needs to present
        the final text response.

        Returns True if auto-chaining was executed.
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

        # --- Step 1: check_data_availability on reporting table ---
        check_args: dict[str, Any] = {"table": table}
        if filters:
            check_args["filters"] = filters

        check_result_str = await self._auto_execute_tool(
            "check_data_availability", check_args,
            tool_calls_made, tool_timings,
        )

        try:
            check_result = json.loads(check_result_str)
        except (json.JSONDecodeError, TypeError):
            check_result = {}

        data_found = check_result.get("data_found", False)
        groups = check_result.get("groups", [])
        totals = check_result.get("totals", {})
        scopes = [g.get("ZSCOPE") for g in groups if g.get("ZSCOPE")]
        has_legal = any(s in self._LEGAL_SCOPES for s in scopes)
        all_s_none = scopes and all(s == "S_NONE" for s in scopes)

        # --- Branch based on Step 1 result ---
        if data_found and has_legal:
            # Data found with expected legal scope — END
            scope_list = ", ".join(scopes)
            await self._auto_execute_tool(
                "record_finding", {
                    "step_name": "Check reporting table",
                    "tool_used": "check_data_availability",
                    "result_summary": (
                        f"Data found in {table} for CoCd {company_code}, "
                        f"period {fiscal_period}. "
                        f"{len(groups)} scope groups: {scope_list}. "
                        f"Totals: {totals}"
                    ),
                    "conclusion": (
                        "Data exists with expected legal consolidation scope "
                        f"({', '.join(s for s in scopes if s in self._LEGAL_SCOPES)}). "
                        "Issue may be in report configuration or user filters."
                    ),
                    "status": "normal",
                },
                tool_calls_made, tool_timings,
            )

        elif data_found and all_s_none:
            # Only S_NONE — consolidation stopped → Step 2A: check ownership
            await self._auto_execute_tool(
                "record_finding", {
                    "step_name": "Check reporting table",
                    "tool_used": "check_data_availability",
                    "result_summary": (
                        f"Data found in {table} but only S_NONE scope. "
                        f"CoCd {company_code}, period {fiscal_period}. "
                        f"Totals: {totals}"
                    ),
                    "conclusion": (
                        "Currency conversion ran but consolidation stopped. "
                        "Checking ownership next."
                    ),
                    "status": "needs_further_check",
                },
                tool_calls_made, tool_timings,
            )

            ownership_str = await self._auto_execute_tool(
                "check_ownership", {
                    "param_fiscper": fiscal_period,
                    "param_cocd": company_code,
                },
                tool_calls_made, tool_timings,
            )

            try:
                ownership = json.loads(ownership_str)
            except (json.JSONDecodeError, TypeError):
                ownership = {}

            if ownership.get("result"):
                await self._auto_execute_tool(
                    "record_finding", {
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
                    tool_calls_made, tool_timings,
                )
            else:
                await self._auto_execute_tool(
                    "record_finding", {
                        "step_name": "Check ownership",
                        "tool_used": "check_ownership",
                        "result_summary": (
                            f"No ownership found for CoCd {company_code}, "
                            f"period {fiscal_period}."
                        ),
                        "conclusion": (
                            "Company was removed from scope for this period. "
                            "Check with consolidation team whether this is "
                            "intentional."
                        ),
                        "status": "issue_found",
                    },
                    tool_calls_made, tool_timings,
                )

        elif not data_found:
            # No data at all → Step 2B: check BPC mart
            await self._auto_execute_tool(
                "record_finding", {
                    "step_name": "Check reporting table",
                    "tool_used": "check_data_availability",
                    "result_summary": (
                        f"No data found in {table} for CoCd {company_code}, "
                        f"period {fiscal_period}."
                    ),
                    "conclusion": (
                        "Data missing from reporting table entirely. "
                        "Checking BPC mart next."
                    ),
                    "status": "needs_further_check",
                },
                tool_calls_made, tool_timings,
            )

            bpc_str = await self._auto_execute_tool(
                "check_data_availability", {
                    "table": "CV_ZFI_AA01",
                    "filters": {
                        "ZCOMPCODE": company_code,
                        "FISCPER": fiscal_period,
                    },
                    "group_by": ["ZCOMPCODE", "FISCPER"],
                },
                tool_calls_made, tool_timings,
            )

            try:
                bpc_result = json.loads(bpc_str)
            except (json.JSONDecodeError, TypeError):
                bpc_result = {}

            if bpc_result.get("data_found"):
                await self._auto_execute_tool(
                    "record_finding", {
                        "step_name": "Check BPC mart",
                        "tool_used": "check_data_availability",
                        "result_summary": (
                            f"Data found in CV_ZFI_AA01 for "
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
                    tool_calls_made, tool_timings,
                )
            else:
                await self._auto_execute_tool(
                    "record_finding", {
                        "step_name": "Check BPC mart",
                        "tool_used": "check_data_availability",
                        "result_summary": (
                            f"No data found in CV_ZFI_AA01 for "
                            f"CoCd {company_code}, period {fiscal_period}."
                        ),
                        "conclusion": (
                            "Data missing from consolidation entirely. "
                            "The issue is upstream of the BPC mart. "
                            "Recommend: Check source data loads into BPC."
                        ),
                        "status": "issue_found",
                    },
                    tool_calls_made, tool_timings,
                )

        else:
            # Data found with mixed/unknown scopes
            scope_list = ", ".join(scopes) if scopes else "none"
            await self._auto_execute_tool(
                "record_finding", {
                    "step_name": "Check reporting table",
                    "tool_used": "check_data_availability",
                    "result_summary": (
                        f"Data found in {table} with scopes: {scope_list}. "
                        f"CoCd {company_code}, period {fiscal_period}. "
                        f"Totals: {totals}"
                    ),
                    "conclusion": (
                        f"Data exists with non-standard scopes ({scope_list}). "
                        "Further manual investigation may be needed."
                    ),
                    "status": "needs_further_check",
                },
                tool_calls_made, tool_timings,
            )

        # --- Final: get_investigation_summary ---
        await self._auto_execute_tool(
            "get_investigation_summary", {},
            tool_calls_made, tool_timings,
        )

        return True

    def _get_investigation_nudge(self, tool_calls_made: list[dict[str, Any]]) -> str:
        """Build a context-aware nudge based on investigation progress.

        Returns a specific instruction pointing to the next required tool
        in the investigation workflow sequence.
        """
        tools_called = {tc["tool"] for tc in tool_calls_made}

        if "check_data_availability" not in tools_called:
            return (
                _INVESTIGATION_NUDGE_PREFIX
                + "Call check_data_availability NOW using the table and filters "
                "from the next_step directive returned by start_investigation."
            )
        if "record_finding" not in tools_called:
            return (
                _INVESTIGATION_NUDGE_PREFIX
                + "Call record_finding NOW to record your analysis of the "
                "check_data_availability results."
            )
        return (
            _INVESTIGATION_NUDGE_PREFIX
            + "Call get_investigation_summary NOW to present the final results."
        )

    async def process(self, user_message: str) -> AgentResponse:
        """Process a user message and return a response.

        Args:
            user_message: The user's input message.

        Returns:
            AgentResponse with the assistant's response.
        """
        request_start = time.perf_counter()
        self.conversation.add_user(user_message)

        tool_calls_made: list[dict[str, Any]] = []
        llm_timings: list[dict[str, Any]] = []
        tool_timings: list[dict[str, Any]] = []
        iterations = 0

        while iterations < self.max_iterations:
            iterations += 1

            # Get LLM response
            lc_messages = self._convert_to_langchain_messages()
            llm_start = time.perf_counter()
            response = await self.model.ainvoke(lc_messages)
            llm_duration = time.perf_counter() - llm_start
            llm_timings.append(
                {"iteration": iterations, "duration_seconds": round(llm_duration, 3)}
            )

            # Check for tool calls
            if hasattr(response, "tool_calls") and response.tool_calls:
                # Add assistant message with tool calls
                self.conversation.add_assistant(
                    content=response.content or "",
                    tool_calls=response.tool_calls,
                )

                # Execute each tool call
                for tool_call in response.tool_calls:
                    tool_name = tool_call["name"]
                    tool_args = tool_call["args"]
                    tool_id = tool_call["id"]

                    # Execute tool
                    tool_start = time.perf_counter()
                    result = await self._execute_tool(tool_name, tool_args)
                    tool_duration = time.perf_counter() - tool_start

                    tool_timings.append(
                        {
                            "tool": tool_name,
                            "duration_seconds": round(tool_duration, 3),
                        }
                    )

                    # Add tool result to conversation
                    self.conversation.add_tool_result(result, tool_id)

                    # Track tool call
                    tool_calls_made.append(
                        {
                            "tool": tool_name,
                            "args": tool_args,
                            "result": result,
                            "duration_seconds": round(tool_duration, 3),
                        }
                    )

                    # Auto-chain: if start_investigation returned next_step,
                    # call check_data_availability automatically
                    await self._try_auto_chain(
                        tool_name, result, tool_calls_made, tool_timings
                    )

                # Continue loop to get next response
                continue

            content = response.content or ""

            # Check for invalid (malformed) tool calls that LangChain detected
            # but couldn't fully parse
            if hasattr(response, "invalid_tool_calls") and response.invalid_tool_calls:
                invalid_names = [
                    tc.get("name", "unknown") for tc in response.invalid_tool_calls
                ]
                logger.warning(
                    "Iteration %d: LLM made invalid tool calls: %s. Nudging to retry.",
                    iterations,
                    invalid_names,
                )
                self.conversation.add_assistant(content)
                self.conversation.add_user(
                    "Your tool call(s) were malformed and could not be parsed "
                    f"(tools: {', '.join(invalid_names)}). Please retry the "
                    "tool call(s) with correct JSON arguments."
                )
                continue

            # Check if the LLM wrote tool calls as text instead of using
            # the structured tool calling mechanism
            if self._looks_like_tool_calls(content):
                logger.warning(
                    "Iteration %d: LLM output tool-call-like text instead of "
                    "structured tool calls. Nudging to retry.",
                    iterations,
                )
                self.conversation.add_assistant(content)
                self.conversation.add_user(_TOOL_CALL_NUDGE)
                continue

            # Check if an investigation was started but not completed.
            # This takes priority over the generic _mentions_tools check
            # because it provides a context-aware nudge pointing to the
            # exact next tool in the workflow.
            if self._investigation_incomplete(tool_calls_made):
                nudge = self._get_investigation_nudge(tool_calls_made)
                logger.warning(
                    "Iteration %d: Investigation incomplete. Nudging: %s",
                    iterations,
                    nudge,
                )
                self.conversation.add_assistant(content)
                self.conversation.add_user(nudge)
                continue

            # Check if the LLM described a tool call instead of making one
            # (e.g. "Let's call check_data_availability" without actually calling it).
            # Skip when the investigation is already complete — the final
            # summary text naturally references tool names.
            if (
                tool_calls_made
                and self._mentions_tools(content)
                and not self._investigation_completed(tool_calls_made)
            ):
                logger.warning(
                    "Iteration %d: LLM mentioned tools in text after prior tool "
                    "calls. Nudging to continue.",
                    iterations,
                )
                self.conversation.add_assistant(content)
                self.conversation.add_user(_CONTINUE_NUDGE)
                continue

            # No tool calls - we have a final response
            self.conversation.add_assistant(content)

            total_duration = time.perf_counter() - request_start
            return AgentResponse(
                content=content,
                tool_calls_made=tool_calls_made,
                finished=True,
                timing={
                    "total_seconds": round(total_duration, 3),
                    "llm_calls": llm_timings,
                    "tool_calls": tool_timings,
                },
            )

        # Max iterations reached
        total_duration = time.perf_counter() - request_start
        return AgentResponse(
            content="I couldn't complete the request within the allowed iterations.",
            tool_calls_made=tool_calls_made,
            finished=False,
            timing={
                "total_seconds": round(total_duration, 3),
                "llm_calls": llm_timings,
                "tool_calls": tool_timings,
            },
        )

    async def process_stream(self, user_message: str) -> AsyncGenerator[dict]:
        """Process a user message, yielding SSE events as work happens.

        Yields dicts with keys: event (str), data (dict).
        The final event is always "done".
        """
        request_start = time.perf_counter()
        self.conversation.add_user(user_message)

        tool_calls_made: list[dict[str, Any]] = []
        llm_timings: list[dict[str, Any]] = []
        tool_timings: list[dict[str, Any]] = []
        iterations = 0

        while iterations < self.max_iterations:
            iterations += 1

            yield {"event": "thinking", "data": {"iteration": iterations}}

            lc_messages = self._convert_to_langchain_messages()
            llm_start = time.perf_counter()
            response = await self.model.ainvoke(lc_messages)
            llm_duration = round(time.perf_counter() - llm_start, 3)
            llm_timings.append(
                {"iteration": iterations, "duration_seconds": llm_duration}
            )

            yield {
                "event": "llm_response",
                "data": {
                    "iteration": iterations,
                    "duration_seconds": llm_duration,
                },
            }

            if hasattr(response, "tool_calls") and response.tool_calls:
                self.conversation.add_assistant(
                    content=response.content or "",
                    tool_calls=response.tool_calls,
                )

                for tool_call in response.tool_calls:
                    tool_name = tool_call["name"]
                    tool_args = tool_call["args"]
                    tool_id = tool_call["id"]

                    yield {
                        "event": "tool_call",
                        "data": {"tool": tool_name, "args": tool_args},
                    }

                    tool_start = time.perf_counter()
                    result = await self._execute_tool(tool_name, tool_args)
                    tool_duration = round(time.perf_counter() - tool_start, 3)

                    tool_timings.append(
                        {"tool": tool_name, "duration_seconds": tool_duration}
                    )

                    self.conversation.add_tool_result(result, tool_id)

                    tool_calls_made.append(
                        {
                            "tool": tool_name,
                            "args": tool_args,
                            "result": result,
                            "duration_seconds": tool_duration,
                        }
                    )

                    yield {
                        "event": "tool_result",
                        "data": {
                            "tool": tool_name,
                            "result": result,
                            "duration_seconds": tool_duration,
                        },
                    }

                    # Auto-chain: run full playbook if start_investigation
                    pre_chain_count = len(tool_calls_made)
                    chained = await self._try_auto_chain(
                        tool_name, result, tool_calls_made, tool_timings
                    )
                    if chained:
                        for rec in tool_calls_made[pre_chain_count:]:
                            yield {
                                "event": "tool_call",
                                "data": {
                                    "tool": rec["tool"],
                                    "args": rec["args"],
                                },
                            }
                            yield {
                                "event": "tool_result",
                                "data": {
                                    "tool": rec["tool"],
                                    "result": rec["result"],
                                    "duration_seconds": rec[
                                        "duration_seconds"
                                    ],
                                },
                            }

                continue

            content = response.content or ""

            # Check for invalid (malformed) tool calls
            if hasattr(response, "invalid_tool_calls") and response.invalid_tool_calls:
                invalid_names = [
                    tc.get("name", "unknown") for tc in response.invalid_tool_calls
                ]
                logger.warning(
                    "Iteration %d: LLM made invalid tool calls: %s. Nudging to retry.",
                    iterations,
                    invalid_names,
                )
                self.conversation.add_assistant(content)
                self.conversation.add_user(
                    "Your tool call(s) were malformed and could not be parsed "
                    f"(tools: {', '.join(invalid_names)}). Please retry the "
                    "tool call(s) with correct JSON arguments."
                )
                continue

            # Check if the LLM wrote tool calls as text
            if self._looks_like_tool_calls(content):
                logger.warning(
                    "Iteration %d: LLM output tool-call-like text instead of "
                    "structured tool calls. Nudging to retry.",
                    iterations,
                )
                self.conversation.add_assistant(content)
                self.conversation.add_user(_TOOL_CALL_NUDGE)
                continue

            # Check if an investigation was started but not completed.
            # Priority over generic _mentions_tools — provides workflow-
            # specific nudge pointing to the exact next tool.
            if self._investigation_incomplete(tool_calls_made):
                nudge = self._get_investigation_nudge(tool_calls_made)
                logger.warning(
                    "Iteration %d: Investigation incomplete. Nudging: %s",
                    iterations,
                    nudge,
                )
                self.conversation.add_assistant(content)
                self.conversation.add_user(nudge)
                continue

            # Check if the LLM described a tool call instead of making one.
            # Skip when the investigation is already complete — the final
            # summary text naturally references tool names.
            if (
                tool_calls_made
                and self._mentions_tools(content)
                and not self._investigation_completed(tool_calls_made)
            ):
                logger.warning(
                    "Iteration %d: LLM mentioned tools in text after prior tool "
                    "calls. Nudging to continue.",
                    iterations,
                )
                self.conversation.add_assistant(content)
                self.conversation.add_user(_CONTINUE_NUDGE)
                continue

            self.conversation.add_assistant(content)

            total_duration = round(time.perf_counter() - request_start, 3)
            timing = {
                "total_seconds": total_duration,
                "llm_calls": llm_timings,
                "tool_calls": tool_timings,
            }

            yield {"event": "text_delta", "data": {"content": content}}
            yield {
                "event": "done",
                "data": {
                    "response": content,
                    "tool_calls": tool_calls_made,
                    "finished": True,
                    "timing": timing,
                },
            }
            return

        total_duration = round(time.perf_counter() - request_start, 3)
        timing = {
            "total_seconds": total_duration,
            "llm_calls": llm_timings,
            "tool_calls": tool_timings,
        }
        yield {
            "event": "done",
            "data": {
                "response": "I couldn't complete the request within the allowed iterations.",
                "tool_calls": tool_calls_made,
                "finished": False,
                "timing": timing,
            },
        }

    def reset(self) -> None:
        """Reset the conversation, keeping only the system prompt."""
        system_msg = self.conversation.messages[0] if self.conversation.messages else None
        self.conversation.clear()
        if system_msg and system_msg.role == MessageRole.SYSTEM:
            self.conversation.add(system_msg)
