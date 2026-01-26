"""Tool definition for skills."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel


@dataclass(frozen=True)
class Tool:
    """Represents a callable tool within a skill.

    Attributes:
        name: Unique identifier for the tool.
        description: Human-readable description shown to LLM.
        function: The callable that executes the tool.
        input_schema: Pydantic model defining input parameters.
    """

    name: str
    description: str
    function: Callable[..., Any]
    input_schema: type[BaseModel]

    def execute(self, **kwargs: Any) -> Any:
        """Execute the tool with validated inputs.

        Args:
            **kwargs: Tool parameters matching input_schema.

        Returns:
            Tool execution result.
        """
        # Validate inputs using Pydantic
        validated = self.input_schema(**kwargs)
        return self.function(**validated.model_dump())

    async def aexecute(self, **kwargs: Any) -> Any:
        """Execute the tool asynchronously with validated inputs.

        For async functions, awaits the result.
        For sync functions, calls directly.
        """
        import asyncio

        validated = self.input_schema(**kwargs)
        result = self.function(**validated.model_dump())

        if asyncio.iscoroutine(result):
            return await result
        return result

    def to_langchain_tool(self) -> dict:
        """Convert to LangChain tool format for binding to models."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.input_schema.model_json_schema(),
        }