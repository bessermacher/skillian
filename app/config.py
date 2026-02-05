"""Application configuration using pydantic-settings."""

from functools import lru_cache
from typing import Literal, Self

from pydantic import model_validator
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
    llm_provider: Literal["ollama", "anthropic", "openai", "custom_openai"] = "ollama"

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"

    # Anthropic (for production)
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-4-20250514"

    # OpenAI (optional)
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o"

    # Custom OpenAI-compatible provider
    custom_openai_api_key: str | None = None
    custom_openai_base_url: str = "https://your-api-endpoint.com/v1"
    custom_openai_model: str = "your-model"
    custom_openai_timeout: int = 60
    custom_openai_max_retries: int = 3

    # Vector Store (uses database_url for pgvector)
    vector_collection_name: str = "skillian_knowledge"

    # Database
    database_url: str = "postgresql+asyncpg://skillian:skillian@localhost:5432/skillian"

    # Business Database (SAP BW data)
    business_database_url: str = "postgresql://business:business@localhost:5433/business_db"

    # SAP Datasphere
    datasphere_host: str | None = None
    datasphere_port: int = 443
    datasphere_space: str | None = None
    datasphere_client_id: str | None = None
    datasphere_client_secret: str | None = None
    datasphere_token_url: str | None = None
    datasphere_timeout: int = 60
    datasphere_max_connections: int = 10

    @property
    def is_development(self) -> bool:
        return self.env == "development"

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    @model_validator(mode="after")
    def validate_provider_config(self) -> Self:
        """Validate that required API keys are present for the selected provider."""
        if self.llm_provider == "anthropic" and not self.anthropic_api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic"
            )
        if self.llm_provider == "openai" and not self.openai_api_key:
            raise ValueError(
                "OPENAI_API_KEY is required when LLM_PROVIDER=openai"
            )
        if self.llm_provider == "custom_openai" and not self.custom_openai_api_key:
            raise ValueError(
                "CUSTOM_OPENAI_API_KEY is required when LLM_PROVIDER=custom_openai"
            )
        return self

    @model_validator(mode="after")
    def validate_datasphere_config(self) -> Self:
        """Validate Datasphere config when connector is needed."""
        if self.datasphere_host and not all([
            self.datasphere_client_id,
            self.datasphere_client_secret,
            self.datasphere_token_url,
        ]):
            raise ValueError(
                "DATASPHERE_CLIENT_ID, DATASPHERE_CLIENT_SECRET, and "
                "DATASPHERE_TOKEN_URL are required when DATASPHERE_HOST is set"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
