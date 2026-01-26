"""Application configuration using pydantic-settings."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Application
    env: Literal["development", "staging", "production"] = "development"
    debug: bool = True
    app_name: str = "Skillian"
    app_version: str = "0.1.0"

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # LLM Provider
    llm_provider: Literal["ollama", "anthropic", "openai"] = "ollama"

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"

    # Anthropic (for production)
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-4-20250514"

    # OpenAI (optional)
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o"

    # Vector Store (uses database_url for pgvector)
    vector_collection_name: str = "skillian_knowledge"

    # Database
    database_url: str = "postgresql+asyncpg://skillian:skillian@localhost:5432/skillian"

    # Business Database (SAP BW data)
    business_database_url: str = "postgresql://business:business@localhost:5433/business_db"

    @property
    def is_development(self) -> bool:
        return self.env == "development"

    @property
    def is_production(self) -> bool:
        return self.env == "production"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
