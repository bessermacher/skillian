"""Main agent orchestration."""

import json
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


@dataclass
class AgentResponse:
    """Response from agent processing."""

    content: str
    tool_calls_made: list[dict[str, Any]] = field(default_factory=list)
    finished: bool = True


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
        max_iterations: int = 10,
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

    async def process(self, user_message: str) -> AgentResponse:
        """Process a user message and return a response.

        Args:
            user_message: The user's input message.

        Returns:
            AgentResponse with the assistant's response.
        """
        self.conversation.add_user(user_message)

        tool_calls_made: list[dict[str, Any]] = []
        iterations = 0

        while iterations < self.max_iterations:
            iterations += 1

            # Get LLM response
            lc_messages = self._convert_to_langchain_messages()
            response = await self.model.ainvoke(lc_messages)

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
                    result = await self._execute_tool(tool_name, tool_args)

                    # Add tool result to conversation
                    self.conversation.add_tool_result(result, tool_id)

                    # Track tool call
                    tool_calls_made.append({
                        "tool": tool_name,
                        "args": tool_args,
                        "result": result,
                    })

                # Continue loop to get next response
                continue

            # No tool calls - we have a final response
            content = response.content or ""
            self.conversation.add_assistant(content)

            return AgentResponse(
                content=content,
                tool_calls_made=tool_calls_made,
                finished=True,
            )

        # Max iterations reached
        return AgentResponse(
            content="I couldn't complete the request within the allowed iterations.",
            tool_calls_made=tool_calls_made,
            finished=False,
        )

    def reset(self) -> None:
        """Reset the conversation, keeping only the system prompt."""
        system_msg = self.conversation.messages[0] if self.conversation.messages else None
        self.conversation.clear()
        if system_msg and system_msg.role == MessageRole.SYSTEM:
            self.conversation.add(system_msg)