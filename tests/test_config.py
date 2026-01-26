"""Tests for configuration module."""

import os

import pytest

from app.config import Settings, get_settings


class TestSettings:
    def test_default_values(self):
        settings = Settings()
        assert settings.env == "development"
        assert settings.debug is True
        assert settings.llm_provider == "ollama"

    def test_is_development(self):
        settings = Settings(env="development")
        assert settings.is_development is True
        assert settings.is_production is False

    def test_is_production(self):
        settings = Settings(env="production")
        assert settings.is_production is True
        assert settings.is_development is False

    def test_from_environment(self, monkeypatch):
        monkeypatch.setenv("ENV", "staging")
        monkeypatch.setenv("DEBUG", "false")
        monkeypatch.setenv("LLM_PROVIDER", "anthropic")

        # Clear cached settings
        get_settings.cache_clear()

        settings = Settings()
        assert settings.env == "staging"
        assert settings.debug is False
        assert settings.llm_provider == "anthropic"

        # Restore cache
        get_settings.cache_clear()


class TestGetSettings:
    def test_returns_settings_instance(self):
        settings = get_settings()
        assert isinstance(settings, Settings)

    def test_caches_result(self):
        settings1 = get_settings()
        settings2 = get_settings()
        assert settings1 is settings2