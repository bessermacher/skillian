"""FastAPI dependency injection."""

from collections.abc import AsyncGenerator
from functools import lru_cache

from langchain_core.language_models import BaseChatModel

from app.api.sessions import SessionStore
from app.config import get_settings
from app.connectors.datasphere import DatasphereConnector
from app.connectors.postgres import PostgresConnector
from app.core import Agent, SkillRegistry
from app.core.comparison_engine import ComparisonCache, ComparisonEngine
from app.core.query_engine import QueryEngine
from app.core.source_registry import SourceRegistry
from app.db.connection import get_db_session
from app.llm import LLMProvider, create_llm_provider
from app.rag import RAGManager, VectorStore, create_embeddings
from app.skills.data_analyst import DataAnalystSkill
from app.skills.datasphere import DatasphereSkill


@lru_cache
def get_llm_provider() -> LLMProvider:
    """Get cached LLM provider instance."""
    settings = get_settings()
    return create_llm_provider(settings)


def get_chat_model() -> BaseChatModel:
    """Get LangChain chat model for dependency injection."""
    provider = get_llm_provider()
    return provider.get_chat_model()


@lru_cache
def get_source_registry() -> SourceRegistry:
    """Get cached source registry."""
    return SourceRegistry("config/sources.yaml")


@lru_cache
def get_business_connector() -> PostgresConnector:
    """Get cached PostgreSQL connector for business data."""
    settings = get_settings()
    return PostgresConnector(settings.business_database_url)


@lru_cache
def get_query_engine() -> QueryEngine:
    """Get cached query engine."""
    connector = get_business_connector()
    return QueryEngine(connector)


@lru_cache
def get_comparison_cache() -> ComparisonCache:
    """Get cached comparison cache."""
    registry = get_source_registry()
    ttl = (
        registry.comparison_config.cache_ttl_seconds
        if registry.comparison_config
        else 3600
    )
    return ComparisonCache(ttl_seconds=ttl)


@lru_cache
def get_comparison_engine() -> ComparisonEngine:
    """Get cached comparison engine."""
    registry = get_source_registry()
    query_engine = get_query_engine()
    cache = get_comparison_cache()
    return ComparisonEngine(registry, query_engine, cache)


@lru_cache
def get_data_analyst_skill() -> DataAnalystSkill:
    """Get cached data analyst skill."""
    registry = get_source_registry()
    query_engine = get_query_engine()
    comparison_engine = get_comparison_engine()
    return DataAnalystSkill(registry, query_engine, comparison_engine)


@lru_cache
def get_datasphere_connector() -> DatasphereConnector | None:
    """Get cached Datasphere connector if configured."""
    settings = get_settings()

    if not settings.datasphere_host:
        return None

    return DatasphereConnector(
        host=settings.datasphere_host,
        space=settings.datasphere_space,
        client_id=settings.datasphere_client_id,
        client_secret=settings.datasphere_client_secret,
        token_url=settings.datasphere_token_url,
        port=settings.datasphere_port,
        timeout=settings.datasphere_timeout,
        max_connections=settings.datasphere_max_connections,
    )


@lru_cache
def get_datasphere_skill() -> DatasphereSkill | None:
    """Get cached Datasphere skill if connector is configured."""
    connector = get_datasphere_connector()
    if connector is None:
        return None
    return DatasphereSkill(connector)


@lru_cache
def get_skill_registry() -> SkillRegistry:
    """Get cached skill registry with all skills registered."""
    registry = SkillRegistry()

    # Register data analyst skill (always available)
    data_analyst = get_data_analyst_skill()
    registry.register(data_analyst)

    # Register Datasphere skill if configured
    datasphere = get_datasphere_skill()
    if datasphere:
        registry.register(datasphere)

    return registry


@lru_cache
def get_vector_store() -> VectorStore:
    """Get cached vector store instance."""
    settings = get_settings()
    embeddings = create_embeddings(settings)
    return VectorStore(
        embeddings=embeddings,
        connection_string=settings.database_url,
        collection_name=settings.vector_collection_name,
    )


@lru_cache
def get_rag_manager() -> RAGManager:
    """Get cached RAG manager instance."""
    store = get_vector_store()
    registry = get_skill_registry()
    return RAGManager(store=store, registry=registry)


def get_agent() -> Agent:
    """Get a configured agent instance."""
    chat_model = get_chat_model()
    registry = get_skill_registry()
    return Agent(chat_model, registry)


async def get_session_store() -> AsyncGenerator[SessionStore]:
    """Get session store with database session."""
    async for db_session in get_db_session():
        yield SessionStore(db_session, get_agent)
