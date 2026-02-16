"""Dynamic skill loader for config-based skills."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.core.configured_skill import ConfiguredSkill
from app.core.exception import SkillLoadError, ToolLoadError
from app.core.skill_parser import parse_skill_md
from app.core.yaml_tools import load_tools_from_yaml

if TYPE_CHECKING:
    pass


class SkillLoader:
    """Load skills dynamically from directory structure.

    Skills are defined using configuration files:
        - SKILL.md: Skill metadata and system prompt
        - tools.yaml: Tool definitions
        - tools.py: Tool implementations

    Directory structure:
        app/skills/
        ├── financial/
        │   ├── SKILL.md
        │   ├── tools.yaml
        │   ├── tools.py
        │   └── knowledge/
        └── sales/
            ├── SKILL.md
            ├── tools.yaml
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
        self._loaded_skills: dict[str, ConfiguredSkill] = {}
        self._skill_mtimes: dict[str, float] = {}

    def discover_skills(self) -> list[str]:
        """Discover all valid skill directories.

        A valid skill directory contains a SKILL.md file.

        Returns:
            List of skill names (directory names)
        """
        if not self.skills_dir.exists():
            return []

        skills = []
        for path in self.skills_dir.iterdir():
            if not path.is_dir():
                continue
            if path.name.startswith("_"):
                continue

            if (path / "SKILL.md").exists():
                skills.append(path.name)

        return sorted(skills)

    def load_skill(self, skill_name: str) -> ConfiguredSkill:
        """Load a skill by name.

        Args:
            skill_name: Name of the skill (directory name)

        Returns:
            ConfiguredSkill instance

        Raises:
            SkillLoadError: If skill cannot be loaded
        """
        skill_path = self.skills_dir / skill_name

        if not skill_path.exists():
            raise SkillLoadError(f"Skill directory not found: {skill_path}")

        skill_md = skill_path / "SKILL.md"
        if not skill_md.exists():
            raise SkillLoadError(f"Missing SKILL.md in {skill_path}")

        skill = self._load_skill(skill_name, skill_path)
        self._loaded_skills[skill_name] = skill
        self._skill_mtimes[skill_name] = self._get_skill_mtime(skill_path)

        return skill

    def load_all_skills(self) -> list[ConfiguredSkill]:
        """Load all discovered skills.

        Returns:
            List of loaded ConfiguredSkill instances
        """
        skills = []
        for skill_name in self.discover_skills():
            try:
                skill = self.load_skill(skill_name)
                skills.append(skill)
            except SkillLoadError as e:
                print(f"Warning: Failed to load skill '{skill_name}': {e}")
        return skills

    def load_skill_metadata(
        self, skill_name: str, *, include_tools: bool = False
    ) -> ConfiguredSkill:
        """Load skill metadata without requiring tools/connector.

        Useful for CLI operations that need to display skill info
        without actually loading functional tools.

        Args:
            skill_name: Name of the skill (directory name)
            include_tools: If True, attempt to load tools (may fail without connector)

        Returns:
            ConfiguredSkill with metadata (tools may be empty)
        """
        skill_path = self.skills_dir / skill_name

        if not skill_path.exists():
            raise SkillLoadError(f"Skill directory not found: {skill_path}")

        skill_md = skill_path / "SKILL.md"
        if not skill_md.exists():
            raise SkillLoadError(f"Missing SKILL.md in {skill_path}")

        try:
            config = parse_skill_md(skill_md)
        except Exception as e:
            raise SkillLoadError(f"Failed to parse SKILL.md: {e}") from e

        tools = []
        tool_error = None
        tools_yaml = skill_path / "tools.yaml"

        if include_tools and tools_yaml.exists():
            try:
                tools = load_tools_from_yaml(
                    tools_yaml,
                    skill_name=skill_name,
                    connector=self._get_connector(config.get("connector")),
                )
            except ToolLoadError as e:
                tool_error = str(e)

        knowledge_dir = skill_path / "knowledge"
        knowledge_paths = [str(knowledge_dir)] if knowledge_dir.exists() else []

        # Count tools from YAML even if we can't load them
        tool_count = 0
        if tools_yaml.exists() and not tools:
            try:
                import yaml

                content = yaml.safe_load(tools_yaml.read_text())
                tool_count = len(content.get("tools", []))
            except Exception:
                pass

        return ConfiguredSkill(
            name=config.get("name", skill_name),
            description=config.get("description", ""),
            system_prompt=config.get("instructions", ""),
            tools=tools,
            knowledge_paths=knowledge_paths,
            metadata={
                **config.get("metadata", {}),
                "tool_count": tool_count if not tools else len(tools),
                "tool_error": tool_error,
            },
            version=config.get("version", "1.0.0"),
            author=config.get("author", ""),
            domain=config.get("domain", ""),
            tags=config.get("tags", []),
            connector_type=config.get("connector"),
        )

    def _load_skill(self, skill_name: str, skill_path: Path) -> ConfiguredSkill:
        """Load a skill from SKILL.md and tools.yaml.

        Args:
            skill_name: Name of the skill
            skill_path: Path to skill directory

        Returns:
            ConfiguredSkill instance
        """
        skill_md = skill_path / "SKILL.md"

        try:
            config = parse_skill_md(skill_md)
        except Exception as e:
            raise SkillLoadError(f"Failed to parse SKILL.md: {e}") from e

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

    def _get_connector(self, connector_type: str | None) -> Any | None:
        """Get a connector instance by type."""
        if not connector_type:
            return None
        return self.connector_factory.get(connector_type)

    def _get_skill_mtime(self, skill_path: Path) -> float:
        """Get the latest modification time for skill files."""
        mtimes = []
        for pattern in ["SKILL.md", "tools.yaml", "tools.py"]:
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

    def reload_skill(self, skill_name: str) -> ConfiguredSkill:
        """Reload a skill (hot-reload).

        Args:
            skill_name: Name of the skill to reload

        Returns:
            Reloaded ConfiguredSkill instance
        """
        if skill_name in self._loaded_skills:
            del self._loaded_skills[skill_name]

        return self.load_skill(skill_name)

    def get_loaded_skill(self, skill_name: str) -> ConfiguredSkill | None:
        """Get a previously loaded skill from cache."""
        return self._loaded_skills.get(skill_name)

    def is_loaded(self, skill_name: str) -> bool:
        """Check if a skill is currently loaded."""
        return skill_name in self._loaded_skills
