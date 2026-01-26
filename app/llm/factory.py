"""LLM provider factory."""

from typing import Literal

from app.config import Settings
from app.llm.anthropic import AnthropicProvider
from app.llm.ollama import OllamaProvider
from app.llm.openai import OpenAIProvider
from app.llm.protocol import LLMProvider

ProviderType = Literal["ollama", "anthropic", "openai"]


class LLMFactoryError(Exception):
    """Raised when LLM factory cannot create a provider."""


def create_llm_provider(settings: Settings) -> LLMProvider:
    """Create an LLM provider based on settings.

    Args:
        settings: Application settings containing provider configuration.

    Returns:
        Configured LLM provider instance.

    Raises:
        LLMFactoryError: If provider cannot be created due to missing config.
    """
    match settings.llm_provider:
        case "ollama":
            return OllamaProvider(
                base_url=settings.ollama_base_url,
                model=settings.ollama_model,
            )

        case "anthropic":
            if not settings.anthropic_api_key:
                raise LLMFactoryError(
                    "ANTHROPIC_API_KEY is required for Anthropic provider"
                )
            return AnthropicProvider(
                api_key=settings.anthropic_api_key,
                model=settings.anthropic_model,
            )

        case "openai":
            if not settings.openai_api_key:
                raise LLMFactoryError(
                    "OPENAI_API_KEY is required for OpenAI provider"
                )
            return OpenAIProvider(
                api_key=settings.openai_api_key,
                model=settings.openai_model,
            )

        case _:
            raise LLMFactoryError(f"Unknown LLM provider: {settings.llm_provider}")