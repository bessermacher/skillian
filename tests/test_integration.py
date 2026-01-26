"""Integration tests for the complete application flow."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestFullChatFlow:
    """Test complete chat flows from API to response."""

    @pytest.fixture
    def mock_agent_response(self):
        """Standard mock agent response."""
        response = MagicMock()
        response.content = "The budget for CC-1001 is $500,000"
        response.tool_calls_made = [
            {
                "tool": "get_cost_center",
                "args": {"cost_center_id": "CC-1001"},
                "result": '{"budget": 500000}',
            }
        ]
        response.finished = True
        return response

    @patch("app.dependencies.get_agent")
    def test_chat_with_tool_execution(self, mock_get_agent, client, mock_agent_response):
        """Test chat that triggers tool execution."""
        mock_agent = MagicMock()
        mock_agent.process = AsyncMock(return_value=mock_agent_response)
        mock_get_agent.return_value = mock_agent

        response = client.post(
            "/chat",
            json={"message": "What is the budget for CC-1001?"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "budget" in data["response"].lower() or "500" in data["response"]
        assert len(data["tool_calls"]) == 1
        assert data["tool_calls"][0]["tool"] == "get_cost_center"

    @patch("app.dependencies.get_agent")
    def test_session_conversation_flow(self, mock_get_agent, client):
        """Test multi-turn conversation in a session."""
        # First message response
        first_response = MagicMock()
        first_response.content = "I found 3 cost centers."
        first_response.tool_calls_made = []
        first_response.finished = True

        # Second message response
        second_response = MagicMock()
        second_response.content = "CC-1001 has a budget of $500,000."
        second_response.tool_calls_made = []
        second_response.finished = True

        mock_agent = MagicMock()
        mock_agent.process = AsyncMock(side_effect=[first_response, second_response])
        mock_get_agent.return_value = mock_agent

        # Create session with first message
        response1 = client.post(
            "/sessions",
            json={"message": "List all cost centers"},
        )
        assert response1.status_code == 200
        session_id = response1.json()["session_id"]
        assert session_id is not None

        # Continue with second message
        response2 = client.post(
            f"/sessions/{session_id}/chat",
            json={"message": "Tell me about the first one"},
        )
        assert response2.status_code == 200
        assert response2.json()["session_id"] == session_id


class TestSkillIntegration:
    """Test skill registration and tool execution."""

    def test_financial_skill_registered(self, client):
        """Verify financial skill is properly registered."""
        response = client.get("/skills")
        assert response.status_code == 200

        data = response.json()
        skill_names = [s["name"] for s in data["skills"]]
        assert "financial" in skill_names

    def test_financial_skill_has_expected_tools(self, client):
        """Verify financial skill has all expected tools."""
        response = client.get("/skills")
        data = response.json()

        financial_skill = next(
            s for s in data["skills"] if s["name"] == "financial"
        )

        tool_names = [t["name"] for t in financial_skill["tools"]]
        expected_tools = [
            "get_cost_center",
            "list_cost_centers",
            "get_profit_center",
            "search_transactions",
            "compare_budget",
        ]

        for tool in expected_tools:
            assert tool in tool_names, f"Missing tool: {tool}"


class TestErrorHandling:
    """Test error handling throughout the application."""

    def test_invalid_session_id(self, client):
        """Test error response for invalid session."""
        response = client.post(
            "/sessions/invalid-session-id/chat",
            json={"message": "Hello"},
        )
        assert response.status_code == 404

    def test_empty_message_validation(self, client):
        """Test validation error for empty message."""
        response = client.post(
            "/chat",
            json={"message": ""},
        )
        assert response.status_code == 422

    def test_missing_message_field(self, client):
        """Test validation error for missing message."""
        response = client.post("/chat", json={})
        assert response.status_code == 422


class TestHealthAndDiagnostics:
    """Test health and diagnostic endpoints."""

    def test_health_returns_all_fields(self, client):
        """Verify health check returns all expected fields."""
        response = client.get("/health")
        assert response.status_code == 200

        data = response.json()
        required_fields = [
            "status",
            "version",
            "environment",
            "llm_provider",
            "llm_model",
            "connector",
            "skills_count",
            "tools_count",
        ]

        for field in required_fields:
            assert field in data, f"Missing field: {field}"

    def test_skills_endpoint_structure(self, client):
        """Verify skills endpoint returns proper structure."""
        response = client.get("/skills")
        assert response.status_code == 200

        data = response.json()
        assert "skills" in data
        assert isinstance(data["skills"], list)

        if data["skills"]:
            skill = data["skills"][0]
            assert "name" in skill
            assert "description" in skill
            assert "tools" in skill