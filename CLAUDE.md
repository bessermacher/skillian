# Skillian - SAP BW AI Assistant

## Overview
Skillian is an AI-powered assistant for SAP BW data diagnostics. It uses a skill-based architecture where each skill (data_analyst, datasphere, ownership_check) provides domain-specific tools for querying and comparing SAP financial data.

## Tech Stack
- **Language**: Python 3.13
- **Framework**: FastAPI (backend API) + Streamlit (chat UI)
- **LLM**: LangChain with multiple providers (Ollama, Anthropic, OpenAI, custom OpenAI-compatible)
- **Database**: PostgreSQL with pgvector (vector store), async via SQLAlchemy + asyncpg
- **Business DB**: PostgreSQL (SAP BW data), optional SAP Datasphere via hdbcli
- **Package manager**: uv
- **Linter**: ruff
- **Testing**: pytest with pytest-asyncio

## Project Structure
```
main.py              # FastAPI app entrypoint
app/
  api/               # REST routes and schemas
  cli/               # Typer CLI (skillian command)
  config.py          # pydantic-settings configuration
  connectors/        # Database connectors (postgres, datasphere)
  core/              # Agent, skill registry, tool system, skill loading/parsing
  db/                # DB connection and models
  dependencies.py    # Dependency injection
  llm/               # LLM provider factory (ollama, anthropic, openai, custom_openai)
  rag/               # RAG pipeline (embeddings, vector store, manager)
  skills/            # Domain skills (data_analyst, datasphere, ownership_check)
config/sources.yaml  # Data source definitions (tables, dimensions, measures)
database/            # SQL init and seed scripts
ui/chat.py           # Streamlit chat frontend
tests/               # pytest test suite
```

## Common Commands
```bash
# Run the API server
uv run uvicorn main:app --reload

# Run the Streamlit UI
uv run streamlit run ui/chat.py

# Run tests (unit only, skips integration)
uv run pytest

# Run tests with coverage
uv run pytest --cov=app --cov-report=term-missing

# Run integration tests (requires running databases)
uv run pytest -m integration

# Lint
uv run ruff check .
uv run ruff format .

# Docker (full stack)
docker compose up --build

# CLI
uv run skillian --help
```

## Configuration
All settings are in `app/config.py` via pydantic-settings, loaded from environment variables or `.env` file. Key settings:
- `LLM_PROVIDER`: ollama | anthropic | openai | custom_openai
- `DATABASE_URL`: PostgreSQL connection for vector store
- `BUSINESS_DATABASE_URL`: PostgreSQL connection for SAP BW data
- `DATASPHERE_*`: Optional SAP Datasphere connection settings

## Skills Architecture
Skills live in `app/skills/<name>/` and contain:
- `SKILL.md` — skill description and knowledge (ingested into RAG)
- `tools.yaml` — tool definitions (name, description, parameters)
- `tools.py` — tool implementations
- `knowledge/` — additional markdown docs for RAG ingestion

Skills are discovered and registered automatically by `app/core/registry.py` and `app/core/skill_loader.py`.

## Time Tracking

Every request is instrumented with timing data (`app/core/agent.py`). `AgentResponse.timing` contains:

- `total_seconds` — end-to-end request duration
- `llm_calls` — list of `{iteration, duration_seconds}` per LLM invocation
- `tool_calls` — list of `{tool, duration_seconds}` per tool execution

Streaming emits `llm_response` and augmented `tool_result` events with `duration_seconds`. The `done` event includes the full `timing` summary. The non-streaming `ChatResponse` also includes `timing` and per-tool `duration_seconds` in `ToolCall`.

## Testing Conventions
- Unit tests run by default (`pytest`), integration tests are marked with `@pytest.mark.integration`
- Async tests use `pytest-asyncio` with `asyncio_mode = "auto"`
- Test files follow `test_<module>.py` naming
