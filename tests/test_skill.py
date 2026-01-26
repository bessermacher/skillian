"""Tests for Skill protocol and BaseSkill."""

from app.core import BaseSkill, Skill, Tool
from pydantic import BaseModel


class DummyInput(BaseModel):
    param: str


def dummy_func(param: str) -> str:
    return param


class TestSkill(BaseSkill):
    """Test implementation of BaseSkill."""

    @property
    def name(self) -> str:
        return "test_skill"

    @property
    def description(self) -> str:
        return "A test skill"

    @property
    def tools(self) -> list[Tool]:
        return [
            Tool(
                name="dummy_tool",
                description="A dummy tool",
                function=dummy_func,
                input_schema=DummyInput,
            )
        ]

    @property
    def system_prompt(self) -> str:
        return "You are a test assistant."


class TestBaseSkill:
    def test_implements_protocol(self):
        skill = TestSkill()
        assert isinstance(skill, Skill)

    def test_get_tool_found(self):
        skill = TestSkill()
        tool = skill.get_tool("dummy_tool")
        assert tool is not None
        assert tool.name == "dummy_tool"

    def test_get_tool_not_found(self):
        skill = TestSkill()
        tool = skill.get_tool("nonexistent")
        assert tool is None

    def test_get_tool_names(self):
        skill = TestSkill()
        names = skill.get_tool_names()
        assert names == ["dummy_tool"]

    def test_knowledge_paths_default_empty(self):
        skill = TestSkill()
        assert skill.knowledge_paths == []

    def test_repr(self):
        skill = TestSkill()
        repr_str = repr(skill)
        assert "TestSkill" in repr_str
        assert "test_skill" in repr_str