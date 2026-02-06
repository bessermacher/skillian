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
