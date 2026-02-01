# Skillian Code Review & Refactoring Guide

**Date:** 2026-02-01
**Reviewer:** Claude Code
**Project Version:** 0.1.0 (MVP)

This document provides a comprehensive analysis of the Skillian codebase and serves as the starting point for refactoring and optimization efforts.

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Project Overview](#project-overview)
3. [Critical Issues](#critical-issues)
4. [Architecture Analysis](#architecture-analysis)
5. [Code Quality Issues](#code-quality-issues)
6. [Performance Optimizations](#performance-optimizations)
7. [Testing Gaps](#testing-gaps)
8. [Best Practices Alignment](#best-practices-alignment)
9. [Refactoring Roadmap](#refactoring-roadmap)
10. [Appendix: File Reference](#appendix-file-reference)

---

## Executive Summary

### Overall Assessment

| Category | Score | Notes |
|----------|-------|-------|
| Architecture | 8/10 | Clean, well-structured, minor DI issues |
| Security | 6/10 | CORS, rate limiting, error exposure |
| Performance | 7/10 | Missing pagination, pool limits |
| Code Quality | 8/10 | Good patterns, needs logging |
| Testing | 7/10 | Good coverage, mock quality issues |
| Best Practices | 8/10 | Modern Python, minor gaps |

**Verdict:** Well-architected MVP with production-readiness gaps that should be addressed before deployment.

### Key Strengths

- Protocol-based design for extensibility
- Modern Python 3.13+ syntax throughout
- Clean separation of concerns
- Comprehensive async implementation
- Good test structure with fixtures

### Key Weaknesses

- Security configuration not production-ready
- No proper logging infrastructure
- Resource cleanup gaps
- Scalability limitations (in-memory cache)

---

## Project Overview

### Tech Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.13 |
| Framework | FastAPI + LangChain |
| Database | PostgreSQL + pgvector |
| LLM | Ollama (dev) / Claude (prod) |
| Package Manager | uv |

### Architecture

```
User Request
    ↓
FastAPI Route (/chat)
    ↓
Agent.process()
    ├── Converts conversation to LangChain messages
    ├── Calls LLM with bound tools
    ├── Executes tool calls (query_source, compare_sources)
    └── Returns response
```

### Codebase Statistics

- **Source files:** ~25 Python modules
- **Test files:** 14 test modules (~2000 lines)
- **Total lines:** ~5,755 lines
- **Skills implemented:** 1 (data_analyst)

---

## Critical Issues

### 1. Security Vulnerabilities

#### 1.1 CORS Configuration (HIGH)

**Location:** `main.py:59-65`

```python
# CURRENT - INSECURE
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows any origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Problem:** Open CORS allows any website to make authenticated requests to the API.

**Fix:**
```python
# RECOMMENDED
from app.config import get_settings

settings = get_settings()
allowed_origins = (
    ["*"] if settings.is_development
    else ["https://your-production-domain.com"]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)
```

#### 1.2 No Rate Limiting (MEDIUM)

**Location:** `app/api/routes.py`

**Problem:** API endpoints have no throttling, allowing abuse.

**Fix:** Add `slowapi` or custom middleware:
```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@router.post("/chat")
@limiter.limit("10/minute")
async def chat(request: Request, ...):
    ...
```

#### 1.3 Error Message Exposure (MEDIUM)

**Location:** `app/api/routes.py:126`

```python
# CURRENT - EXPOSES INTERNALS
except Exception as e:
    raise HTTPException(status_code=400, detail=str(e))
```

**Problem:** Exception details may leak sensitive information.

**Fix:**
```python
# RECOMMENDED
import logging
logger = logging.getLogger(__name__)

except Exception as e:
    logger.exception("Chat processing failed")
    raise HTTPException(
        status_code=500,
        detail="An internal error occurred. Please try again."
    )
```

### 2. Python Version Mismatch

| File | States |
|------|--------|
| `CLAUDE.md` | Python 3.14+ |
| `pyproject.toml:5` | `>=3.13,<3.14` |
| `pyproject.toml:43` | `target-version = "py313"` |

**Fix:** Update `CLAUDE.md` to reflect actual version:
```markdown
- Python 3.13+
```

---

## Architecture Analysis

### What's Good

1. **Protocol-based Design**
   - `Skill` protocol in `app/core/skill.py` enables duck typing
   - `LLMProvider` protocol allows easy provider switching
   - Clean interface contracts

2. **Factory Pattern**
   - `create_llm_provider()` cleanly abstracts provider creation
   - `match` statement for provider selection

3. **Separation of Concerns**
   - Clear module boundaries (core, api, llm, rag, skills)
   - Single responsibility per module

4. **Async Throughout**
   - Consistent use of async/await
   - asyncpg for database operations

### Issues to Address

#### 3.1 Dependency Injection Limitations

**Location:** `app/dependencies.py`

**Problem:** Heavy `@lru_cache` usage creates global singletons that are difficult to reset in tests.

```python
# CURRENT
@lru_cache
def get_skill_registry() -> SkillRegistry:
    registry = SkillRegistry()
    skill = get_data_analyst_skill()
    registry.register(skill)
    return registry
```

**Impact:**
- Tests may share state unintentionally
- Cannot easily swap implementations
- Memory not released until process ends

**Fix Options:**
1. Use FastAPI's `Depends()` with request-scoped lifetimes
2. Implement a proper DI container (e.g., `dependency-injector`)
3. Add cache clearing utility for tests

#### 3.2 Resource Cleanup Missing

**Location:** `main.py` lifespan handler

**Problem:** Database connections are not closed on shutdown.

```python
# CURRENT
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ... startup ...
    yield
    print("Shutting down...")  # No cleanup!
```

**Fix:**
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    # ... rest of startup ...

    yield

    # Cleanup
    from app.dependencies import get_business_connector
    from app.db.connection import close_db

    connector = get_business_connector()
    await connector.close()
    await close_db()
    print("Shutdown complete")
```

#### 3.3 In-Memory Cache Scalability

**Location:** `app/core/comparison_engine.py:59-93`

**Problem:** `ComparisonCache` uses in-memory dict, won't work with multiple instances.

```python
class ComparisonCache:
    def __init__(self, ttl_seconds: int = 3600):
        self._cache: dict[str, ComparisonResult] = {}  # In-memory only
```

**Fix:** Abstract cache interface, implement Redis backend:
```python
from abc import ABC, abstractmethod

class CacheBackend(ABC):
    @abstractmethod
    async def get(self, key: str) -> ComparisonResult | None: ...

    @abstractmethod
    async def set(self, key: str, value: ComparisonResult, ttl: int) -> None: ...

class RedisCache(CacheBackend):
    def __init__(self, redis_url: str):
        self._redis = aioredis.from_url(redis_url)
    # ... implementation
```

#### 3.4 Inefficient Session Listing

**Location:** `app/api/sessions.py:179-197`

**Problem:** `list_all()` creates a full Agent for every session, even for metadata-only listing.

```python
async def list_all(self) -> list[Session]:
    # ...
    for db_session in db_sessions:
        agent = self._agent_factory()  # Unnecessary!
        sessions.append(Session(..., agent=agent, ...))
```

**Fix:** Create lightweight metadata-only response:
```python
@dataclass
class SessionMetadata:
    session_id: str
    created_at: datetime
    last_accessed: datetime
    message_count: int

async def list_all(self) -> list[SessionMetadata]:
    result = await self._db.execute(select(SessionModel))
    return [
        SessionMetadata(
            session_id=str(s.id),
            created_at=s.created_at,
            last_accessed=s.last_accessed,
            message_count=s.message_count,
        )
        for s in result.scalars().all()
    ]
```

---

## Code Quality Issues

### 4.1 Logging Infrastructure

**Problem:** Uses `print()` instead of proper logging.

**Locations:**
- `main.py:25-42`
- `app/rag/store.py:118`

**Current:**
```python
print(f"Starting {settings.app_name} v{settings.app_version}")
print(f"Warning: RAG initialization failed: {e}")
```

**Fix:** Implement structured logging:

```python
# app/logging.py
import logging
import structlog

def setup_logging(debug: bool = False):
    level = logging.DEBUG if debug else logging.INFO

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
    )

    logging.basicConfig(level=level)

# Usage
logger = structlog.get_logger(__name__)
logger.info("starting_app", name=settings.app_name, version=settings.app_version)
```

### 4.2 Type Hint Issues

| Issue | Location | Fix |
|-------|----------|-----|
| `callable` should be `Callable` | `app/api/sessions.py:68` | `from collections.abc import Callable` |
| Empty class uses `pass` | `app/skills/data_analyst/tools.py:20` | Use `...` instead |

**Before:**
```python
class ListSourcesInput(BaseModel):
    pass
```

**After:**
```python
class ListSourcesInput(BaseModel):
    """Input for list_sources tool - no parameters needed."""
    ...
```

### 4.3 Exception Handling

**Problem:** Generic exception handling swallows errors silently.

**Locations:**
- `app/api/routes.py:52` - health check
- `app/connectors/postgres.py:69` - health check
- `main.py:41` - RAG initialization

**Current:**
```python
except Exception:
    doc_count = 0  # Silently fails
```

**Fix:** Log errors, use specific exceptions:
```python
except (DatabaseError, ConnectionError) as e:
    logger.warning("health_check_failed", error=str(e))
    doc_count = 0
```

### 4.4 Missing Docstrings

Several public methods lack docstrings:
- `ComparisonCache.size()`
- `QueryEngine._build_query()` (has minimal docstring)
- Various `__init__` methods

---

## Performance Optimizations

### 5.1 Database Connection Pool

**Location:** `app/connectors/postgres.py:23`

**Problem:** No pool size limits or timeouts.

**Current:**
```python
self._pool = await asyncpg.create_pool(self._url)
```

**Fix:**
```python
self._pool = await asyncpg.create_pool(
    self._url,
    min_size=2,
    max_size=10,
    max_inactive_connection_lifetime=300,
    command_timeout=60,
)
```

### 5.2 VectorStore Engine Creation

**Location:** `app/rag/store.py:192-210`

**Problem:** Creates new SQLAlchemy engine on every `count()` call.

**Current:**
```python
@property
def count(self) -> int:
    # Creates engine every time!
    engine = create_engine(connection)
    with engine.connect() as conn:
        ...
```

**Fix:** Reuse engine from initialization or cache it:
```python
def __post_init__(self):
    # ... existing code ...
    self._sync_engine = create_engine(connection)

@property
def count(self) -> int:
    with self._sync_engine.connect() as conn:
        ...
```

### 5.3 Missing Pagination

**Location:** `app/api/routes.py:195-209`

**Problem:** `list_sessions()` returns all sessions without pagination.

**Fix:**
```python
@router.get("/sessions")
async def list_sessions(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    session_store: SessionStore = Depends(get_session_store),
) -> SessionListResponse:
    sessions = await session_store.list_paginated(skip=skip, limit=limit)
    total = await session_store.count()
    return SessionListResponse(
        sessions=[...],
        total=total,
        skip=skip,
        limit=limit,
    )
```

### 5.4 Query Result Limits

**Location:** `app/skills/data_analyst/tools.py:227`

**Current:** Hard-coded 100 row limit.

**Improvement:** Make configurable and add proper pagination:
```python
class QuerySourceInput(BaseModel):
    # ... existing fields ...
    limit: int = Field(default=100, le=1000, description="Max rows to return")
    offset: int = Field(default=0, ge=0, description="Rows to skip")
```

---

## Testing Gaps

### 6.1 Mock Embeddings Quality

**Location:** `tests/conftest.py:181-193`

**Problem:** Mock embeddings return identical vectors for all inputs.

```python
def embed_documents(self, texts: list[str]) -> list[list[float]]:
    return [[0.1] * self.dimension for _ in texts]  # All same!
```

**Impact:** All documents have identical similarity scores in tests.

**Fix:**
```python
import hashlib

def embed_documents(self, texts: list[str]) -> list[list[float]]:
    embeddings = []
    for text in texts:
        # Generate deterministic but unique embedding per text
        hash_val = hashlib.md5(text.encode()).digest()
        embedding = [b / 255.0 for b in hash_val[:self.dimension]]
        # Pad or truncate to dimension
        embedding = (embedding * (self.dimension // len(embedding) + 1))[:self.dimension]
        embeddings.append(embedding)
    return embeddings
```

### 6.2 Missing Test Categories

| Category | Status | Notes |
|----------|--------|-------|
| Unit tests | ✓ Good | Core modules well covered |
| Integration tests | Partial | Marked, skipped by default |
| Error path tests | Missing | Need negative test cases |
| Security tests | Missing | SQL injection, XSS, auth |
| Performance tests | Missing | Load testing, benchmarks |

### 6.3 Test Configuration

**Location:** `pyproject.toml:52`

Integration tests skipped by default:
```toml
addopts = "-v --tb=short -m 'not integration'"
```

**Recommendation:** Add CI job that runs integration tests separately.

---

## Best Practices Alignment

### What's Already Good

| Practice | Implementation |
|----------|----------------|
| Modern type hints | `list[str]`, `str \| None` |
| Match statements | LLM factory, message conversion |
| Protocols over ABC | Skill, LLMProvider |
| Frozen dataclasses | Tool definition |
| Pydantic validation | Input schemas, Settings |
| Async/await | Throughout codebase |

### What Needs Improvement

| Area | Current | Recommended |
|------|---------|-------------|
| Logging | `print()` | `structlog` or `logging` |
| Config validation | Basic | Add `@field_validator` for conditional requirements |
| Database migrations | None | Alembic |
| API versioning | `/api/v1` prefix | Proper versioning strategy |
| Error responses | Generic | Structured error schema |
| Health checks | Partial | Include all dependencies |

### Recommended Config Validation

```python
from pydantic import field_validator

class Settings(BaseSettings):
    # ... existing fields ...

    @field_validator('anthropic_api_key')
    @classmethod
    def validate_anthropic_key(cls, v, info):
        if info.data.get('llm_provider') == 'anthropic' and not v:
            raise ValueError('ANTHROPIC_API_KEY required when using Anthropic provider')
        return v
```

---

## Refactoring Roadmap

### Phase 1: Critical Security (Priority: Immediate)

| Task | File | Effort |
|------|------|--------|
| Fix CORS configuration | `main.py` | 30 min |
| Add rate limiting | `main.py`, new middleware | 2 hours |
| Sanitize error responses | `app/api/routes.py` | 1 hour |
| Add request validation | API routes | 2 hours |

### Phase 2: Infrastructure (Priority: High)

| Task | File | Effort |
|------|------|--------|
| Implement logging | New `app/logging.py`, all modules | 4 hours |
| Add resource cleanup | `main.py` lifespan | 1 hour |
| Fix connection pool config | `app/connectors/postgres.py` | 30 min |
| Fix VectorStore engine reuse | `app/rag/store.py` | 1 hour |

### Phase 3: Performance (Priority: Medium)

| Task | File | Effort |
|------|------|--------|
| Add pagination to list endpoints | `app/api/routes.py`, schemas | 2 hours |
| Optimize session listing | `app/api/sessions.py` | 1 hour |
| Abstract cache backend | `app/core/comparison_engine.py` | 4 hours |
| Add database indexes | New migration | 1 hour |

### Phase 4: Code Quality (Priority: Medium)

| Task | File | Effort |
|------|------|--------|
| Fix type hints | `app/api/sessions.py`, others | 1 hour |
| Add missing docstrings | Various | 2 hours |
| Improve exception handling | Various | 3 hours |
| Update Python version in docs | `CLAUDE.md` | 10 min |

### Phase 5: Testing (Priority: Medium)

| Task | File | Effort |
|------|------|--------|
| Fix mock embeddings | `tests/conftest.py` | 1 hour |
| Add error path tests | New test files | 4 hours |
| Add security tests | New test file | 4 hours |
| Set up integration test CI | CI config | 2 hours |

### Phase 6: Production Readiness (Priority: Lower)

| Task | File | Effort |
|------|------|--------|
| Add Alembic migrations | New `alembic/` directory | 4 hours |
| Implement Redis cache | New module | 4 hours |
| Add OpenTelemetry tracing | New middleware | 4 hours |
| Create Kubernetes manifests | New `k8s/` directory | 8 hours |

---

## Appendix: File Reference

### Core Files

| File | Purpose | Lines |
|------|---------|-------|
| `main.py` | FastAPI entry point | 82 |
| `app/config.py` | Pydantic settings | 65 |
| `app/dependencies.py` | DI container | 127 |
| `app/core/agent.py` | Agent orchestration | 212 |
| `app/core/skill.py` | Skill protocol | 75 |
| `app/core/tool.py` | Tool dataclass | 60 |
| `app/core/registry.py` | Skill registry | ~150 |
| `app/core/query_engine.py` | SQL builder | 141 |
| `app/core/comparison_engine.py` | Data comparison | 339 |

### API Files

| File | Purpose | Lines |
|------|---------|-------|
| `app/api/routes.py` | REST endpoints | 275 |
| `app/api/schemas.py` | Pydantic models | ~200 |
| `app/api/sessions.py` | Session management | 203 |

### LLM Files

| File | Purpose | Lines |
|------|---------|-------|
| `app/llm/factory.py` | Provider factory | 58 |
| `app/llm/protocol.py` | LLMProvider protocol | ~50 |
| `app/llm/ollama.py` | Ollama implementation | ~50 |
| `app/llm/anthropic.py` | Claude implementation | ~50 |
| `app/llm/openai.py` | OpenAI implementation | ~50 |

### RAG Files

| File | Purpose | Lines |
|------|---------|-------|
| `app/rag/store.py` | Vector store wrapper | 211 |
| `app/rag/manager.py` | Knowledge ingestion | ~100 |
| `app/rag/embeddings.py` | Embeddings factory | ~50 |

### Skill Files

| File | Purpose | Lines |
|------|---------|-------|
| `app/skills/data_analyst/skill.py` | Skill implementation | ~100 |
| `app/skills/data_analyst/tools.py` | Tool implementations | 265 |

---

## Document History

| Date | Author | Changes |
|------|--------|---------|
| 2026-02-01 | Claude Code | Initial review |

---

*This document should be updated as refactoring progresses. Mark completed items and add new findings as they emerge.*
