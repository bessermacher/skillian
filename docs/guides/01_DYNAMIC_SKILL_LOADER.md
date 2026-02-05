# Guide 1: Dynamic Skill Loader

This guide walks you through implementing the dynamic skill loader that auto-discovers and loads skills from the directory structure.

## Overview

The skill loader replaces manual skill registration with automatic discovery. Instead of editing `dependencies.py` for each new skill, skills are automatically loaded from `app/skills/`.

**Before (manual):**
```python
registry.register(DataAnalystSkill(connector))
registry.register(FinancialSkill(connector))  # Must add each manually
```

**After (automatic):**
```python
loader = SkillLoader(Path("app/skills"))
for skill_name in loader.discover_skills():
    skill = loader.load_skill(skill_name)
    registry.register(skill)
```

## Step 1: Create the Base Exception Classes

Create `app/core/exceptions.py`:

```python
"""Skill system exceptions."""


class SkillError(Exception):
    """Base exception for skill-related errors."""
    pass


class SkillLoadError(SkillError):
    """Failed to load a skill."""
    pass


class SkillValidationError(SkillError):
    """Skill definition is invalid."""
    pass


class ToolLoadError(SkillError):
    """Failed to load a tool."""
    pass
```

## Step 2: Create the ConfiguredSkill Class

This class represents skills loaded from configuration files (SKILL.md + tools.yaml).

Create `app/core/configured_skill.py`:

```python
"""Skill implementation loaded from configuration files."""

from dataclasses import dataclass, field
from typing import Any

from app.core.tool import Tool


@dataclass
class ConfiguredSkill:
    """A skill loaded from SKILL.md and tools.yaml configuration.

    This class provides the same interface as Python-based skills
    but is populated from configuration files instead of code.
    """

    name: str
    description: str
    system_prompt: str
    tools: list[Tool] = field(default_factory=list)
    knowledge_paths: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    # Optional fields from SKILL.md
    version: str = "1.0.0"
    author: str = ""
    domain: str = ""
    tags: list[str] = field(default_factory=list)
    connector_type: str | None = None  # Required connector

    def get_tool(self, name: str) -> Tool | None:
        """Get a tool by name."""
        for tool in self.tools:
            if tool.name == name:
                return tool
        return None

    def get_tool_names(self) -> list[str]:
        """Get list of all tool names."""
        return [tool.name for tool in self.tools]

    @property
    def is_enabled(self) -> bool:
        """Check if skill is enabled."""
        return self.metadata.get("enabled", True)

    def __repr__(self) -> str:
        return (
            f"ConfiguredSkill(name={self.name!r}, "
            f"tools={len(self.tools)}, version={self.version!r})"
        )
```

## Step 3: Create the Skill Loader

Create `app/core/skill_loader.py`:

```python
"""Dynamic skill loader with hot-reload support."""

from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.core.configured_skill import ConfiguredSkill
from app.core.exceptions import SkillLoadError, ToolLoadError
from app.core.skill_parser import parse_skill_md
from app.core.yaml_tools import load_tools_from_yaml

if TYPE_CHECKING:
    from app.core.skill import Skill


class SkillLoader:
    """Load skills dynamically from directory structure.

    Supports two skill formats:
    1. Config-based: SKILL.md + tools.yaml + tools.py
    2. Python-based: skill.py (traditional format)

    Directory structure:
        app/skills/
        ├── financial/           # Config-based skill
        │   ├── SKILL.md
        │   ├── tools.yaml
        │   ├── tools.py
        │   └── knowledge/
        └── data_analyst/        # Python-based skill
            ├── skill.py
            ├── tools.py
            └── knowledge/
    """

    def __init__(
        self,
        skills_dir: Path,
        connector_factory: dict[str, Any] | None = None,
    ):
        """Initialize the skill loader.

        Args:
            skills_dir: Path to the skills directory
            connector_factory: Dict mapping connector names to instances
        """
        self.skills_dir = Path(skills_dir)
        self.connector_factory = connector_factory or {}
        self._loaded_skills: dict[str, Skill] = {}
        self._skill_mtimes: dict[str, float] = {}  # For hot-reload detection

    def discover_skills(self) -> list[str]:
        """Discover all valid skill directories.

        Returns:
            List of skill names (directory names)
        """
        if not self.skills_dir.exists():
            return []

        skills = []
        for path in self.skills_dir.iterdir():
            if not path.is_dir():
                continue
            if path.name.startswith("_"):  # Skip _templates, __pycache__
                continue

            # Check for valid skill markers
            has_skill_md = (path / "SKILL.md").exists()
            has_skill_py = (path / "skill.py").exists()

            if has_skill_md or has_skill_py:
                skills.append(path.name)

        return sorted(skills)

    def load_skill(self, skill_name: str) -> Skill:
        """Load a skill by name.

        Determines the skill type (config vs Python) and loads accordingly.

        Args:
            skill_name: Name of the skill (directory name)

        Returns:
            Loaded Skill instance

        Raises:
            SkillLoadError: If skill cannot be loaded
        """
        skill_path = self.skills_dir / skill_name

        if not skill_path.exists():
            raise SkillLoadError(f"Skill directory not found: {skill_path}")

        # Check for config-based skill first (preferred)
        skill_md = skill_path / "SKILL.md"
        if skill_md.exists():
            skill = self._load_config_skill(skill_name, skill_path)
        else:
            # Fall back to Python-based skill
            skill_py = skill_path / "skill.py"
            if skill_py.exists():
                skill = self._load_python_skill(skill_name, skill_path)
            else:
                raise SkillLoadError(
                    f"No skill definition found in {skill_path}. "
                    "Expected SKILL.md or skill.py"
                )

        self._loaded_skills[skill_name] = skill
        self._skill_mtimes[skill_name] = self._get_skill_mtime(skill_path)

        return skill

    def load_all_skills(self) -> list[Skill]:
        """Load all discovered skills.

        Returns:
            List of loaded Skill instances
        """
        skills = []
        for skill_name in self.discover_skills():
            try:
                skill = self.load_skill(skill_name)
                skills.append(skill)
            except SkillLoadError as e:
                # Log error but continue loading other skills
                print(f"Warning: Failed to load skill '{skill_name}': {e}")
        return skills

    def _load_config_skill(self, skill_name: str, skill_path: Path) -> ConfiguredSkill:
        """Load a config-based skill from SKILL.md and tools.yaml.

        Args:
            skill_name: Name of the skill
            skill_path: Path to skill directory

        Returns:
            ConfiguredSkill instance
        """
        skill_md = skill_path / "SKILL.md"

        # Parse SKILL.md
        try:
            config = parse_skill_md(skill_md)
        except Exception as e:
            raise SkillLoadError(f"Failed to parse SKILL.md: {e}") from e

        # Load tools from tools.yaml if present
        tools = []
        tools_yaml = skill_path / "tools.yaml"
        if tools_yaml.exists():
            try:
                tools = load_tools_from_yaml(
                    tools_yaml,
                    skill_name=skill_name,
                    connector=self._get_connector(config.get("connector")),
                )
            except ToolLoadError as e:
                raise SkillLoadError(f"Failed to load tools: {e}") from e

        # Build knowledge paths
        knowledge_dir = skill_path / "knowledge"
        knowledge_paths = [str(knowledge_dir)] if knowledge_dir.exists() else []

        return ConfiguredSkill(
            name=config.get("name", skill_name),
            description=config.get("description", ""),
            system_prompt=config.get("instructions", ""),
            tools=tools,
            knowledge_paths=knowledge_paths,
            metadata=config.get("metadata", {}),
            version=config.get("version", "1.0.0"),
            author=config.get("author", ""),
            domain=config.get("domain", ""),
            tags=config.get("tags", []),
            connector_type=config.get("connector"),
        )

    def _load_python_skill(self, skill_name: str, skill_path: Path) -> Skill:
        """Load a Python-based skill from skill.py.

        Args:
            skill_name: Name of the skill
            skill_path: Path to skill directory

        Returns:
            Skill instance
        """
        skill_py = skill_path / "skill.py"
        module_name = f"app.skills.{skill_name}.skill"

        try:
            # Load or reload the module
            if module_name in sys.modules:
                module = importlib.reload(sys.modules[module_name])
            else:
                spec = importlib.util.spec_from_file_location(module_name, skill_py)
                if spec is None or spec.loader is None:
                    raise SkillLoadError(f"Cannot load module spec for {skill_py}")

                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)

            # Find the skill class
            skill_class = self._find_skill_class(module, skill_name)
            if skill_class is None:
                raise SkillLoadError(
                    f"No skill class found in {skill_py}. "
                    "Expected a class ending with 'Skill'."
                )

            # Instantiate with connector if needed
            connector = self._get_connector_for_python_skill(skill_class)
            if connector:
                return skill_class(connector)
            return skill_class()

        except Exception as e:
            raise SkillLoadError(f"Failed to load Python skill: {e}") from e

    def _find_skill_class(self, module: Any, skill_name: str) -> type | None:
        """Find the skill class in a module.

        Looks for classes ending with 'Skill' or matching the skill name.
        """
        # Convert skill_name to expected class name (e.g., data_analyst -> DataAnalystSkill)
        expected_name = "".join(word.capitalize() for word in skill_name.split("_")) + "Skill"

        for name in dir(module):
            obj = getattr(module, name)
            if not isinstance(obj, type):
                continue
            if name == expected_name:
                return obj
            if name.endswith("Skill") and name != "Skill":
                return obj

        return None

    def _get_connector(self, connector_type: str | None) -> Any | None:
        """Get a connector instance by type."""
        if not connector_type:
            return None
        return self.connector_factory.get(connector_type)

    def _get_connector_for_python_skill(self, skill_class: type) -> Any | None:
        """Determine if a Python skill class needs a connector."""
        import inspect

        sig = inspect.signature(skill_class.__init__)
        params = list(sig.parameters.keys())

        # Skip 'self'
        if params and params[0] == "self":
            params = params[1:]

        if not params:
            return None

        # Try to match first parameter name to connector
        first_param = params[0]
        for name, connector in self.connector_factory.items():
            if name in first_param.lower() or first_param.lower() in name:
                return connector

        # Return first available connector as fallback
        if self.connector_factory:
            return next(iter(self.connector_factory.values()))

        return None

    def _get_skill_mtime(self, skill_path: Path) -> float:
        """Get the latest modification time for skill files."""
        mtimes = []
        for pattern in ["SKILL.md", "tools.yaml", "tools.py", "skill.py"]:
            path = skill_path / pattern
            if path.exists():
                mtimes.append(path.stat().st_mtime)
        return max(mtimes) if mtimes else 0

    def needs_reload(self, skill_name: str) -> bool:
        """Check if a skill has been modified and needs reloading."""
        skill_path = self.skills_dir / skill_name
        current_mtime = self._get_skill_mtime(skill_path)
        cached_mtime = self._skill_mtimes.get(skill_name, 0)
        return current_mtime > cached_mtime

    def reload_skill(self, skill_name: str) -> Skill:
        """Reload a skill (hot-reload).

        Args:
            skill_name: Name of the skill to reload

        Returns:
            Reloaded Skill instance
        """
        # Clear from cache
        if skill_name in self._loaded_skills:
            del self._loaded_skills[skill_name]

        # Clear Python module cache for Python-based skills
        module_prefix = f"app.skills.{skill_name}"
        modules_to_remove = [
            name for name in sys.modules if name.startswith(module_prefix)
        ]
        for name in modules_to_remove:
            del sys.modules[name]

        return self.load_skill(skill_name)

    def get_loaded_skill(self, skill_name: str) -> Skill | None:
        """Get a previously loaded skill from cache."""
        return self._loaded_skills.get(skill_name)

    def is_loaded(self, skill_name: str) -> bool:
        """Check if a skill is currently loaded."""
        return skill_name in self._loaded_skills
```

## Step 4: Update Dependencies

Update `app/dependencies.py` to use the skill loader:

```python
"""Dependency injection for FastAPI."""

from functools import lru_cache
from pathlib import Path

from app.config import get_settings
from app.core.skill_loader import SkillLoader
from app.core.registry import SkillRegistry
# ... other imports ...


@lru_cache
def get_skill_loader() -> SkillLoader:
    """Get cached skill loader with connector factory."""
    settings = get_settings()

    # Build connector factory
    connector_factory = {}

    # Add business connector
    connector_factory["postgres"] = get_business_connector()
    connector_factory["business"] = get_business_connector()

    # Add Datasphere connector if configured
    datasphere = get_datasphere_connector()
    if datasphere:
        connector_factory["datasphere"] = datasphere

    return SkillLoader(
        skills_dir=Path("app/skills"),
        connector_factory=connector_factory,
    )


@lru_cache
def get_skill_registry() -> SkillRegistry:
    """Get cached skill registry with auto-discovered skills."""
    registry = SkillRegistry()
    loader = get_skill_loader()

    # Auto-discover and load all skills
    for skill in loader.load_all_skills():
        registry.register(skill)

    return registry
```

## Step 5: Add Hot-Reload Endpoint (Optional)

Add an API endpoint for hot-reloading skills during development:

```python
# app/api/routes.py

from fastapi import APIRouter, HTTPException
from app.dependencies import get_skill_loader, get_skill_registry

router = APIRouter()


@router.post("/admin/skills/{skill_name}/reload")
async def reload_skill(skill_name: str):
    """Hot-reload a skill (development only)."""
    settings = get_settings()
    if not settings.debug:
        raise HTTPException(403, "Hot-reload only available in debug mode")

    loader = get_skill_loader()
    registry = get_skill_registry()

    try:
        # Check if skill exists
        if skill_name not in loader.discover_skills():
            raise HTTPException(404, f"Skill '{skill_name}' not found")

        # Reload the skill
        skill = loader.reload_skill(skill_name)

        # Update registry (need to implement registry update method)
        registry.unregister(skill_name)
        registry.register(skill)

        return {
            "status": "reloaded",
            "skill": skill_name,
            "tools": [t.name for t in skill.tools],
        }
    except Exception as e:
        raise HTTPException(500, f"Failed to reload: {e}")
```

## Step 6: Add Registry Update Methods

Update `app/core/registry.py` to support unregistration:

```python
# Add to SkillRegistry class

def unregister(self, skill_name: str) -> bool:
    """Remove a skill from the registry.

    Args:
        skill_name: Name of skill to remove

    Returns:
        True if skill was removed, False if not found
    """
    if skill_name not in self._skills:
        return False

    skill = self._skills[skill_name]

    # Remove tool index entries
    for tool in skill.tools:
        if tool.name in self._tool_index:
            del self._tool_index[tool.name]

    # Remove skill
    del self._skills[skill_name]
    return True

def update(self, skill: Skill) -> None:
    """Update or add a skill in the registry.

    If skill exists, it will be replaced.
    """
    self.unregister(skill.name)
    self.register(skill)
```

## Testing

Create `tests/test_skill_loader.py`:

```python
"""Tests for the skill loader."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock

from app.core.skill_loader import SkillLoader
from app.core.exceptions import SkillLoadError


@pytest.fixture
def temp_skills_dir(tmp_path):
    """Create a temporary skills directory with test skills."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    # Create a config-based skill
    config_skill = skills_dir / "test_config"
    config_skill.mkdir()
    (config_skill / "SKILL.md").write_text("""---
name: test-config
description: A test skill
version: "1.0.0"
---

# Test Config Skill

## Instructions

This is a test skill.
""")

    # Create a Python-based skill
    python_skill = skills_dir / "test_python"
    python_skill.mkdir()
    (python_skill / "skill.py").write_text("""
class TestPythonSkill:
    @property
    def name(self):
        return "test_python"

    @property
    def description(self):
        return "A Python test skill"

    @property
    def tools(self):
        return []

    @property
    def system_prompt(self):
        return "Test prompt"

    @property
    def knowledge_paths(self):
        return []

    def get_tool(self, name):
        return None
""")

    return skills_dir


class TestSkillLoader:
    def test_discover_skills(self, temp_skills_dir):
        loader = SkillLoader(temp_skills_dir)
        skills = loader.discover_skills()

        assert "test_config" in skills
        assert "test_python" in skills

    def test_discover_ignores_underscore_dirs(self, temp_skills_dir):
        (temp_skills_dir / "_templates").mkdir()
        (temp_skills_dir / "_templates" / "SKILL.md").write_text("test")

        loader = SkillLoader(temp_skills_dir)
        skills = loader.discover_skills()

        assert "_templates" not in skills

    def test_load_config_skill(self, temp_skills_dir):
        loader = SkillLoader(temp_skills_dir)
        skill = loader.load_skill("test_config")

        assert skill.name == "test-config"
        assert skill.description == "A test skill"
        assert skill.version == "1.0.0"

    def test_load_python_skill(self, temp_skills_dir):
        loader = SkillLoader(temp_skills_dir)
        skill = loader.load_skill("test_python")

        assert skill.name == "test_python"
        assert skill.description == "A Python test skill"

    def test_load_nonexistent_skill(self, temp_skills_dir):
        loader = SkillLoader(temp_skills_dir)

        with pytest.raises(SkillLoadError):
            loader.load_skill("nonexistent")

    def test_load_all_skills(self, temp_skills_dir):
        loader = SkillLoader(temp_skills_dir)
        skills = loader.load_all_skills()

        assert len(skills) == 2

    def test_needs_reload(self, temp_skills_dir):
        loader = SkillLoader(temp_skills_dir)
        loader.load_skill("test_config")

        # Initially no reload needed
        assert not loader.needs_reload("test_config")

        # Modify the file
        import time
        time.sleep(0.1)
        skill_md = temp_skills_dir / "test_config" / "SKILL.md"
        skill_md.write_text(skill_md.read_text() + "\n# Updated")

        # Now reload is needed
        assert loader.needs_reload("test_config")
```

## Summary

You've implemented:

1. **SkillLoader** - Core class for discovering and loading skills
2. **ConfiguredSkill** - Dataclass for config-based skills
3. **Hot-reload support** - Detect changes and reload without restart
4. **Connector injection** - Pass connectors to skills that need them
5. **Hybrid loading** - Support both SKILL.md and Python-based skills

## Next Steps

- Implement the [SKILL.md Parser](02_SKILL_MD_PARSER.md) for parsing skill definitions
- Implement the [YAML Tool Loader](03_YAML_TOOL_DEFINITIONS.md) for loading tools from YAML
