"""Base skill implementation with common functionality."""

from abc import ABC, abstractmethod

from app.core.skill import Skill
from app.core.tool import Tool


class BaseSkill(ABC):
    """Abstract base class providing common skill functionality.

    Subclasses must implement:
    - name
    - description
    - tools
    - system_prompt

    Optional override:
    - knowledge_paths (defaults to empty list)
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for the skill."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description."""
        ...

    @property
    @abstractmethod
    def tools(self) -> list[Tool]:
        """List of available tools."""
        ...

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """System prompt for the LLM."""
        ...

    @property
    def knowledge_paths(self) -> list[str]:
        """Paths to knowledge documents (override if needed)."""
        return []

    def get_tool(self, name: str) -> Tool | None:
        """Get a tool by name."""
        for tool in self.tools:
            if tool.name == name:
                return tool
        return None

    def get_tool_names(self) -> list[str]:
        """Get list of all tool names."""
        return [tool.name for tool in self.tools]

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r}, tools={self.get_tool_names()})"