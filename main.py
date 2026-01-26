"""Skillian - SAP BW AI Assistant."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import router
from app.config import get_settings
from app.db import init_db
from app.dependencies import (
    get_connector,
    get_llm_provider,
    get_rag_manager,
    get_skill_registry,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    settings = get_settings()
    provider = get_llm_provider()
    registry = get_skill_registry()
    connector = get_connector()

    print(f"Starting {settings.app_name} v{settings.app_version}")

    # Initialize database
    await init_db()
    print("Database initialized")
    print(f"Environment: {settings.env}")
    print(f"LLM Provider: {provider.provider_name} ({provider.model_name})")
    print(f"Connector: {connector.name}")
    print(f"Skills registered: {registry.skill_count}")
    print(f"Tools available: {registry.tool_count}")

    # Ingest knowledge on startup
    try:
        rag_manager = get_rag_manager()
        results = rag_manager.ingest_all_skills()
        total = sum(results.values())
        print(f"Knowledge ingested: {total} chunks from {len(results)} skills")
    except Exception as e:
        print(f"Warning: RAG initialization failed: {e}")

    yield
    print("Shutting down...")


settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description="SAP BW AI Assistant with domain-specific skills for data diagnostics",
    version=settings.app_version,
    debug=settings.debug,
    lifespan=lifespan,
)

# CORS middleware for frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(router, prefix="/api/v1")

# Also mount at root for backwards compatibility
app.include_router(router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.is_development,
    )