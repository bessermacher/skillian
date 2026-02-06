"""Tests for Agent."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import BaseModel

from app.core import Agent, ConfiguredSkill, SkillRegistry, Tool


class DummyInput(BaseModel):
    query: str


def dummy_tool_func(query: str) -> dict:
    return {"result": f"Processed: {query}"}


def create_dummy_skill() -> ConfiguredSkill:
    return ConfiguredSkill(
        name="dummy",
        description="Dummy skill for testing",
        system_prompt="You are a dummy assistant.",
        tools=[
            Tool(
                name="dummy_query",
                description="A dummy query tool",
                function=dummy_tool_func,
                input_schema=DummyInput,
            )
        ],
    )


class TestAgent:
    @pytest.fixture
    def registry(self):
        reg = SkillRegistry()
        reg.register(create_dummy_skill())
        return reg

    @pytest.fixture
    def mock_model(self):
        model = MagicMock()
        model.bind_tools = MagicMock(return_value=model)
        return model

    def test_agent_creates_with_empty_registry(self, mock_model):
        registry = SkillRegistry()
        agent = Agent(mock_model, registry)
        assert agent is not None
        # Should not call bind_tools with no tools
        mock_model.bind_tools.assert_not_called()

    def test_agent_binds_tools(self, mock_model, registry):
        _agent = Agent(mock_model, registry)  # noqa: F841
        mock_model.bind_tools.assert_called_once()

    def test_agent_has_system_prompt(self, mock_model, registry):
        agent = Agent(mock_model, registry)
        assert len(agent.conversation) == 1
        assert agent.conversation.messages[0].content is not None

    @pytest.mark.asyncio
    async def test_process_simple_response(self, mock_model, registry):
        # Mock a simple response without tool calls
        mock_response = MagicMock()
        mock_response.content = "Hello! How can I help?"
        mock_response.tool_calls = None

        mock_model.ainvoke = AsyncMock(return_value=mock_response)
        mock_model.bind_tools = MagicMock(return_value=mock_model)

        agent = Agent(mock_model, registry)
        response = await agent.process("Hello")

        assert response.content == "Hello! How can I help?"
        assert response.finished is True
        assert len(response.tool_calls_made) == 0

    @pytest.mark.asyncio
    async def test_process_with_tool_call(self, mock_model, registry):
        # First response has tool call
        tool_call_response = MagicMock()
        tool_call_response.content = ""
        tool_call_response.tool_calls = [
            {"id": "call_123", "name": "dummy_query", "args": {"query": "test"}}
        ]

        # Second response is final
        final_response = MagicMock()
        final_response.content = "The result is: Processed: test"
        final_response.tool_calls = None

        mock_model.ainvoke = AsyncMock(side_effect=[tool_call_response, final_response])
        mock_model.bind_tools = MagicMock(return_value=mock_model)

        agent = Agent(mock_model, registry)
        response = await agent.process("Query something")

        assert "Processed: test" in response.content
        assert response.finished is True
        assert len(response.tool_calls_made) == 1
        assert response.tool_calls_made[0]["tool"] == "dummy_query"

    def test_reset_keeps_system_prompt(self, mock_model, registry):
        agent = Agent(mock_model, registry)
        agent.conversation.add_user("Test message")

        assert len(agent.conversation) == 2

        agent.reset()

        assert len(agent.conversation) == 1
        assert agent.conversation.messages[0].role.value == "system"