"""Tests for source registry."""

import tempfile
from pathlib import Path

import pytest
import yaml

from app.core.source_registry import (
    ComparisonConfig,
    DimensionDef,
    MeasureDef,
    SourceDef,
    SourceNotFoundError,
    SourceRegistry,
)


@pytest.fixture
def sample_config():
    """Sample YAML config for testing."""
    return {
        "sources": {
            "source_a": {
                "description": "Test source A",
                "table": "table_a",
                "dimensions": {
                    "company": {"column": "comp_code"},
                    "period": {"column": "fiscal_period"},
                },
                "measures": {
                    "amount": {"column": "amount_lc", "aggregation": "sum"},
                },
                "defaults": {"dimensions": ["company", "period"]},
            },
            "source_b": {
                "description": "Test source B",
                "table": "table_b",
                "dimensions": {
                    "company": {"column": "company_id"},
                    "period": {"column": "period_id"},
                    "version": {"column": "version"},
                },
                "measures": {
                    "amount": {"column": "value", "aggregation": "sum"},
                },
            },
        },
        "comparison": {
            "default_align_on": ["company", "period"],
            "thresholds": {
                "match": {"absolute": 100, "percentage": 1.0},
                "minor_diff": {"absolute": 500, "percentage": 5.0},
            },
            "cache_ttl_seconds": 1800,
        },
    }


@pytest.fixture
def config_file(sample_config, tmp_path):
    """Create a temporary config file."""
    config_path = tmp_path / "sources.yaml"
    with open(config_path, "w") as f:
        yaml.dump(sample_config, f)
    return config_path


@pytest.fixture
def registry(config_file):
    """Create a registry with sample config."""
    return SourceRegistry(config_file)


class TestSourceRegistry:
    def test_load_sources(self, registry):
        """Test that sources are loaded correctly."""
        sources = registry.list_sources()
        assert "source_a" in sources
        assert "source_b" in sources
        assert len(sources) == 2

    def test_get_source(self, registry):
        """Test getting a source by name."""
        source = registry.get("source_a")
        assert source.name == "source_a"
        assert source.description == "Test source A"
        assert source.table == "table_a"

    def test_get_source_not_found(self, registry):
        """Test getting a non-existent source raises error."""
        with pytest.raises(SourceNotFoundError) as exc:
            registry.get("nonexistent")
        assert "nonexistent" in str(exc.value)

    def test_source_dimensions(self, registry):
        """Test source dimensions are loaded correctly."""
        source = registry.get("source_a")
        assert "company" in source.dimensions
        assert "period" in source.dimensions
        assert source.dimensions["company"].column == "comp_code"

    def test_source_measures(self, registry):
        """Test source measures are loaded correctly."""
        source = registry.get("source_a")
        assert "amount" in source.measures
        assert source.measures["amount"].column == "amount_lc"
        assert source.measures["amount"].aggregation == "sum"

    def test_source_defaults(self, registry):
        """Test source defaults are loaded."""
        source = registry.get("source_a")
        assert source.defaults.get("dimensions") == ["company", "period"]

    def test_get_source_info(self, registry):
        """Test getting source info for LLM context."""
        info = registry.get_source_info()
        assert len(info) == 2

        source_a_info = next(i for i in info if i["name"] == "source_a")
        assert source_a_info["description"] == "Test source A"
        assert "company" in source_a_info["dimensions"]
        assert "amount" in source_a_info["measures"]

    def test_get_common_dimensions(self, registry):
        """Test finding common dimensions between sources."""
        common = registry.get_common_dimensions("source_a", "source_b")
        assert "company" in common
        assert "period" in common
        assert "version" not in common  # Only in source_b

    def test_comparison_config(self, registry):
        """Test comparison config is loaded."""
        config = registry.comparison_config
        assert config is not None
        assert config.default_align_on == ["company", "period"]
        assert config.cache_ttl_seconds == 1800
        assert "match" in config.thresholds
        assert config.thresholds["match"].absolute == 100

    def test_file_not_found(self, tmp_path):
        """Test error when config file doesn't exist."""
        with pytest.raises(FileNotFoundError):
            SourceRegistry(tmp_path / "nonexistent.yaml")


class TestSourceRegistryWithRealConfig:
    """Test with the actual project config file."""

    def test_load_real_config(self):
        """Test loading the real sources.yaml."""
        registry = SourceRegistry("config/sources.yaml")

        sources = registry.list_sources()
        assert "fi_reporting" in sources
        assert "consolidation_mart" in sources
        assert "bpc_reporting" in sources

    def test_real_config_dimensions(self):
        """Test real config has expected dimensions."""
        registry = SourceRegistry("config/sources.yaml")

        fi = registry.get("fi_reporting")
        assert "company" in fi.dimensions
        assert "period" in fi.dimensions
        assert "account" in fi.dimensions

    def test_real_config_common_dimensions(self):
        """Test common dimensions between real sources."""
        registry = SourceRegistry("config/sources.yaml")

        common = registry.get_common_dimensions("fi_reporting", "consolidation_mart")
        assert "company" in common
        assert "period" in common
