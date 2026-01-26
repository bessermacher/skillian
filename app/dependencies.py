"""FastAPI dependency injection."""

from collections.abc import AsyncGenerator
from functools import lru_cache

from langchain_core.language_models import BaseChatModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.sessions import SessionStore
from app.config import get_settings
from app.connectors import Connector, create_business_connector, create_connector
from app.core import Agent, SkillRegistry
from app.db.connection import get_db_session
from app.llm import LLMProvider, create_llm_provider
from app.rag import RAGManager, VectorStore, create_embeddings
from app.skills import BusinessSkill, FinancialSkill


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
def get_connector() -> Connector:
    """Get cached data connector instance."""
    settings = get_settings()
    return create_connector(settings)


@lru_cache
def get_skill_registry() -> SkillRegistry:
    """Get cached skill registry with all skills registered."""
    registry = SkillRegistry()
    settings = get_settings()

    # Financial skill uses mock connector (for development)
    mock_connector = create_connector(settings)
    registry.register(FinancialSkill(mock_connector))

    # Business skill uses PostgreSQL connector
    business_connector = create_business_connector(settings)
    registry.register(BusinessSkill(business_connector))

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


async def get_session_store() -> AsyncGenerator[SessionStore, None]:
    """Get session store with database session."""
    async for db_session in get_db_session():
        yield SessionStore(db_session, get_agent)