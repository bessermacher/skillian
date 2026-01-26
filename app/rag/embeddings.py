"""Embeddings factory for different providers."""

from typing import Literal

from langchain_core.embeddings import Embeddings

from app.config import Settings


EmbeddingsType = Literal["ollama", "openai"]


class EmbeddingsFactoryError(Exception):
    """Raised when embeddings cannot be created."""


def create_embeddings(settings: Settings) -> Embeddings:
    """Create embeddings based on settings.

    Uses the same provider as the LLM for consistency.
    Falls back to Ollama embeddings for local development.

    Args:
        settings: Application settings.

    Returns:
        Configured embeddings instance.
    """
    match settings.llm_provider:
        case "ollama":
            from langchain_ollama import OllamaEmbeddings

            return OllamaEmbeddings(
                base_url=settings.ollama_base_url,
                model="nomic-embed-text",  # Good embedding model for Ollama
            )

        case "openai":
            if not settings.openai_api_key:
                raise EmbeddingsFactoryError(
                    "OPENAI_API_KEY required for OpenAI embeddings"
                )
            from langchain_openai import OpenAIEmbeddings

            return OpenAIEmbeddings(
                api_key=settings.openai_api_key,
                model="text-embedding-3-small",
            )

        case "anthropic":
            # Anthropic doesn't have embeddings, use Ollama as fallback
            from langchain_ollama import OllamaEmbeddings

            return OllamaEmbeddings(
                base_url=settings.ollama_base_url,
                model="nomic-embed-text",
            )

        case _:
            raise EmbeddingsFactoryError(
                f"Unknown provider for embeddings: {settings.llm_provider}"
            )