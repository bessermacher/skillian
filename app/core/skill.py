"""Skill protocol definition."""

from typing import Protocol, runtime_checkable

from app.core.tool import Tool


@runtime_checkable
class Skill(Protocol):
    """Protocol defining the interface for domain skills.

    A skill represents a domain-specific capability composed of:
    - Tools: Callable functions the LLM can invoke
    - Knowledge: RAG documents for context (optional)
    - System Prompt: Domain-specific instructions

    Example:
        class FinancialSkill:
            @property
            def name(self) -> str:
                return "financial"

            @property
            def description(self) -> str:
                return "Analyze financial data in SAP BW"

            @property
            def tools(self) -> list[Tool]:
                return [self.analyze_cost_center, ...]

            @property
            def system_prompt(self) -> str:
                return "You are a financial analyst..."

            @property
            def knowledge_paths(self) -> list[str]:
                return ["app/skills/financial/knowledge/"]
    """

    @property
    def name(self) -> str:
        """Unique identifier for the skill (e.g., 'financial', 'sales')."""
        ...

    @property
    def description(self) -> str:
        """Human-readable description of what the skill does."""
        ...

    @property
    def tools(self) -> list[Tool]:
        """List of tools available in this skill."""
        ...

    @property
    def system_prompt(self) -> str:
        """System prompt providing domain context to the LLM."""
        ...

    @property
    def knowledge_paths(self) -> list[str]:
        """Paths to knowledge documents for RAG (can be empty)."""
        ...

    def get_tool(self, name: str) -> Tool | None:
        """Get a specific tool by name.

        Args:
            name: The tool name to look up.

        Returns:
            The tool if found, None otherwise.
        """
        ...
