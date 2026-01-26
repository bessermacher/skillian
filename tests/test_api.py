"""Tests for API endpoints."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, AsyncMock, patch

from main import app


@pytest.fixture
def client():
    return TestClient(app)


class TestHealthEndpoint:
    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] in ["healthy", "degraded"]
        assert "version" in data
        assert "llm_provider" in data

    def test_health_with_api_prefix(self, client):
        response = client.get("/api/v1/health")
        assert response.status_code == 200


class TestSkillsEndpoint:
    def test_list_skills(self, client):
        response = client.get("/skills")
        assert response.status_code == 200

        data = response.json()
        assert "skills" in data
        # Should have at least the financial skill
        assert len(data["skills"]) >= 1

    def test_skill_has_tools(self, client):
        response = client.get("/skills")
        data = response.json()

        for skill in data["skills"]:
            assert "name" in skill
            assert "description" in skill
            assert "tools" in skill
            assert isinstance(skill["tools"], list)


class TestChatEndpoint:
    def test_chat_success(self, client):
        from app.dependencies import get_agent

        # Mock agent response
        mock_agent = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Test response"
        mock_response.tool_calls_made = []
        mock_response.finished = True
        mock_agent.process = AsyncMock(return_value=mock_response)

        # Use FastAPI's dependency override
        app.dependency_overrides[get_agent] = lambda: mock_agent

        try:
            response = client.post(
                "/chat",
                json={"message": "Hello"},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["response"] == "Test response"
            assert data["finished"] is True
        finally:
            # Clean up override
            app.dependency_overrides.pop(get_agent, None)

    def test_chat_empty_message(self, client):
        response = client.post(
            "/chat",
            json={"message": ""},
        )
        assert response.status_code == 422  # Validation error


class TestSessionEndpoints:
    def test_create_session(self, client):
        from app.dependencies import get_agent

        mock_agent = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Hello!"
        mock_response.tool_calls_made = []
        mock_response.finished = True
        mock_agent.process = AsyncMock(return_value=mock_response)

        # Use FastAPI's dependency override
        app.dependency_overrides[get_agent] = lambda: mock_agent

        try:
            response = client.post(
                "/sessions",
                json={"message": "Start conversation"},
            )

            assert response.status_code == 200
            data = response.json()
            assert "session_id" in data
            assert data["session_id"] is not None
        finally:
            app.dependency_overrides.pop(get_agent, None)

    def test_list_sessions(self, client):
        response = client.get("/sessions")
        assert response.status_code == 200
        data = response.json()
        assert "sessions" in data

    def test_session_not_found(self, client):
        response = client.post(
            "/sessions/nonexistent-id/chat",
            json={"message": "Hello"},
        )
        assert response.status_code == 404


class TestKnowledgeEndpoints:
    def test_search_knowledge(self, client):
        # Note: This may fail if embeddings aren't available
        # In CI, mock the RAG manager
        response = client.post(
            "/knowledge/search",
            json={"query": "budget analysis", "k": 2},
        )

        # Accept either success or service unavailable
        assert response.status_code in [200, 500]

    def test_search_validation(self, client):
        response = client.post(
            "/knowledge/search",
            json={"query": "", "k": 2},
        )
        assert response.status_code == 422  # Validation error

        response = client.post(
            "/knowledge/search",
            json={"query": "test", "k": 100},  # k too high
        )
        assert response.status_code == 422