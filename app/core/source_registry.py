"""Source registry - loads and manages data source definitions from YAML."""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class DimensionDef(BaseModel):
    """Definition of a dimension in a source."""

    column: str
    type: str = "string"
    format: str | None = None
    values: list[str] | None = None


class MeasureDef(BaseModel):
    """Definition of a measure in a source."""

    column: str
    aggregation: str = "sum"


class SourceDef(BaseModel):
    """Definition of a data source."""

    name: str
    description: str
    table: str
    dimensions: dict[str, DimensionDef]
    measures: dict[str, MeasureDef]
    defaults: dict[str, Any] = Field(default_factory=dict)


class ComparisonThreshold(BaseModel):
    """Threshold for comparison matching."""

    absolute: float
    percentage: float


class ComparisonConfig(BaseModel):
    """Configuration for comparisons."""

    default_align_on: list[str]
    thresholds: dict[str, ComparisonThreshold]
    cache_ttl_seconds: int


class SourceNotFoundError(Exception):
    """Raised when a source is not found."""


class SourceRegistry:
    """Registry of available data sources loaded from YAML config."""

    def __init__(self, config_path: Path | str = "config/sources.yaml"):
        self._sources: dict[str, SourceDef] = {}
        self._comparison_config: ComparisonConfig | None = None
        self._load_config(Path(config_path))

    def _load_config(self, config_path: Path) -> None:
        """Load source definitions from YAML file."""
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(config_path) as f:
            config = yaml.safe_load(f)

        # Load sources
        for name, source_data in config.get("sources", {}).items():
            dimensions = {
                k: DimensionDef(**v) if isinstance(v, dict) else DimensionDef(column=v)
                for k, v in source_data.get("dimensions", {}).items()
            }
            measures = {
                k: MeasureDef(**v) if isinstance(v, dict) else MeasureDef(column=v)
                for k, v in source_data.get("measures", {}).items()
            }
            self._sources[name] = SourceDef(
                name=name,
                description=source_data.get("description", ""),
                table=source_data.get("table", name),
                dimensions=dimensions,
                measures=measures,
                defaults=source_data.get("defaults", {}),
            )

        # Load comparison config
        comp_config = config.get("comparison", {})
        if comp_config:
            thresholds = {
                k: ComparisonThreshold(**v)
                for k, v in comp_config.get("thresholds", {}).items()
            }
            self._comparison_config = ComparisonConfig(
                default_align_on=comp_config.get("default_align_on", ["company", "period"]),
                thresholds=thresholds,
                cache_ttl_seconds=comp_config.get("cache_ttl_seconds", 3600),
            )

    def get(self, name: str) -> SourceDef:
        """Get source by name.

        Raises:
            SourceNotFoundError: If source doesn't exist.
        """
        if name not in self._sources:
            raise SourceNotFoundError(f"Source '{name}' not found")
        return self._sources[name]

    def list_sources(self) -> list[str]:
        """List all source names."""
        return list(self._sources.keys())

    def get_source_info(self) -> list[dict[str, Any]]:
        """Get info about all sources for LLM context."""
        return [
            {
                "name": s.name,
                "description": s.description,
                "dimensions": list(s.dimensions.keys()),
                "measures": list(s.measures.keys()),
            }
            for s in self._sources.values()
        ]

    def get_common_dimensions(self, source1: str, source2: str) -> list[str]:
        """Get dimensions that exist in both sources."""
        s1 = self.get(source1)
        s2 = self.get(source2)
        return list(set(s1.dimensions.keys()) & set(s2.dimensions.keys()))

    @property
    def comparison_config(self) -> ComparisonConfig | None:
        """Get comparison configuration."""
        return self._comparison_config
