"""Load tools from YAML definitions."""

from __future__ import annotations

import asyncio
import functools
import importlib
import inspect
from pathlib import Path
from typing import Any, Callable

import yaml
from pydantic import BaseModel, Field, create_model

from app.core.exception import ToolLoadError
from app.core.tool import Tool


def load_tools_from_yaml(
    yaml_path: Path | str,
    skill_name: str | None = None,
    connector: Any | None = None,
) -> list[Tool]:
    """Load tools from a tools.yaml file.

    Args:
        yaml_path: Path to tools.yaml file
        skill_name: Name of the skill (for module paths)
        connector: Optional connector to pass to tool implementations

    Returns:
        List of Tool instances

    Raises:
        ToolLoadError: If loading fails
    """
    yaml_path = Path(yaml_path)

    if not yaml_path.exists():
        raise ToolLoadError(f"tools.yaml not found: {yaml_path}")

    try:
        content = yaml.safe_load(yaml_path.read_text())
    except yaml.YAMLError as e:
        raise ToolLoadError(f"Invalid YAML in {yaml_path}: {e}") from e

    if not isinstance(content, dict):
        raise ToolLoadError("tools.yaml must be a dictionary with 'tools' key")

    tools_config = content.get("tools", [])
    if not isinstance(tools_config, list):
        raise ToolLoadError("'tools' must be a list")

    tools = []
    for tool_config in tools_config:
        try:
            tool = _build_tool(tool_config, skill_name, connector)
            tools.append(tool)
        except Exception as e:
            name = tool_config.get("name", "unknown")
            raise ToolLoadError(f"Failed to load tool '{name}': {e}") from e

    return tools


def _build_tool(
    config: dict[str, Any],
    skill_name: str | None,
    connector: Any | None,
) -> Tool:
    """Build a Tool instance from YAML configuration.

    Args:
        config: Tool configuration dictionary
        skill_name: Parent skill name
        connector: Optional connector

    Returns:
        Tool instance
    """
    # Validate required fields
    if "name" not in config:
        raise ToolLoadError("Tool missing required 'name' field")

    name = config["name"]
    description = config.get("description", f"Tool: {name}")

    parameters = config.get("parameters", [])

    # Build Pydantic input schema
    input_schema = _build_input_schema(name, parameters)

    # Get the implementation function
    if "implementation" in config:
        func = _load_implementation(config["implementation"], connector)
    elif "query_template" in config:
        func = _build_query_function(config["query_template"], connector)
    else:
        raise ToolLoadError(f"Tool '{name}' needs 'implementation' or 'query_template'")

    return Tool(
        name=name,
        description=description,
        function=func,
        input_schema=input_schema,
    )


def _build_input_schema(
    tool_name: str,
    parameters: list[dict[str, Any]],
) -> type[BaseModel]:
    """Build a Pydantic model from parameter definitions.

    Args:
        tool_name: Name of the tool (for model naming)
        parameters: List of parameter configs

    Returns:
        Pydantic BaseModel class
    """
    # Build field definitions
    fields: dict[str, tuple[type, Any]] = {}

    for param in parameters:
        param_name = param["name"]
        param_type = _get_python_type(param.get("type", "string"))
        required = param.get("required", False)
        description = param.get("description", "")
        default = param.get("default")

        # Handle nested objects
        if param.get("type") == "object" and "properties" in param:
            nested_schema = _build_nested_schema(
                f"{tool_name}_{param_name}",
                param["properties"],
            )
            if required:
                fields[param_name] = (nested_schema, Field(description=description))
            else:
                fields[param_name] = (
                    nested_schema | None,
                    Field(default=None, description=description),
                )
            continue

        # Build field
        if required:
            fields[param_name] = (param_type, Field(description=description))
        elif default is not None:
            fields[param_name] = (param_type, Field(default=default, description=description))
        else:
            fields[param_name] = (
                param_type | None,
                Field(default=None, description=description),
            )

    # Create dynamic model
    model_name = "".join(word.capitalize() for word in tool_name.split("_")) + "Input"
    return create_model(model_name, **fields)


def _build_nested_schema(
    name: str,
    properties: dict[str, Any],
) -> type[BaseModel]:
    """Build a nested Pydantic model from properties.

    Args:
        name: Model name
        properties: Property definitions

    Returns:
        Pydantic BaseModel class
    """
    fields: dict[str, tuple[type, Any]] = {}

    for prop_name, prop_config in properties.items():
        prop_type = _get_python_type(prop_config.get("type", "string"))
        description = prop_config.get("description", "")
        default = prop_config.get("default")

        if default is not None:
            fields[prop_name] = (prop_type, Field(default=default, description=description))
        else:
            fields[prop_name] = (
                prop_type | None,
                Field(default=None, description=description),
            )

    return create_model(name, **fields)


def _get_python_type(type_str: str) -> type:
    """Convert YAML type string to Python type.

    Args:
        type_str: Type string from YAML (string, integer, number, boolean, array, object)

    Returns:
        Python type
    """
    type_map = {
        "string": str,
        "integer": int,
        "int": int,
        "number": float,
        "float": float,
        "boolean": bool,
        "bool": bool,
        "array": list,
        "list": list,
        "object": dict,
        "dict": dict,
    }

    return type_map.get(type_str.lower(), str)


def _load_implementation(
    implementation_path: str,
    connector: Any | None,
) -> Callable[..., Any]:
    """Load implementation function from module path.

    Args:
        implementation_path: Path like "app.skills.financial.tools:check_gl_balance"
        connector: Optional connector to inject

    Returns:
        Callable function

    Raises:
        ToolLoadError: If function cannot be loaded
    """
    if ":" not in implementation_path:
        raise ToolLoadError(
            f"Invalid implementation path '{implementation_path}'. "
            "Expected format: 'module.path:function_name'"
        )

    module_path, func_name = implementation_path.rsplit(":", 1)

    try:
        module = importlib.import_module(module_path)
    except ImportError as e:
        raise ToolLoadError(f"Cannot import module '{module_path}': {e}") from e

    if not hasattr(module, func_name):
        raise ToolLoadError(f"Function '{func_name}' not found in module '{module_path}'")

    func = getattr(module, func_name)

    if not callable(func):
        raise ToolLoadError(f"'{func_name}' is not callable")

    # If it's a class, instantiate with connector
    if isinstance(func, type):
        if connector:
            instance = func(connector)
        else:
            instance = func()
        # Assume it has a __call__ method
        if hasattr(instance, "__call__"):
            return instance
        raise ToolLoadError(f"Class '{func_name}' is not callable")

    # If function expects connector, create wrapper
    if connector and _function_wants_connector(func):
        return _wrap_with_connector(func, connector)

    return func


def _function_wants_connector(func: Callable) -> bool:
    """Check if a function has a 'connector' parameter."""
    sig = inspect.signature(func)
    return "connector" in sig.parameters


def _wrap_with_connector(func: Callable, connector: Any) -> Callable:
    """Wrap a function to inject connector."""

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, connector=connector, **kwargs)

    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs):
        return await func(*args, connector=connector, **kwargs)

    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    return wrapper


def _build_query_function(
    query_template: str,
    connector: Any | None,
) -> Callable[..., Any]:
    """Build a function that executes a query template.

    This enables zero-code tools that just run SQL/OData queries.

    Args:
        query_template: SQL/OData query with {placeholders}
        connector: Connector to execute queries

    Returns:
        Async function that executes the query
    """
    if connector is None:
        raise ToolLoadError("Query template tools require a connector")

    async def execute_query(**kwargs: Any) -> dict[str, Any]:
        """Execute the query template with provided parameters."""
        # Simple string formatting (for basic templates)
        try:
            query = query_template.format(**kwargs)
        except KeyError as e:
            return {"error": f"Missing parameter: {e}"}

        try:
            # Try SQL execution first
            if hasattr(connector, "execute_sql"):
                results = await connector.execute_sql(query)
            elif hasattr(connector, "execute"):
                results = await connector.execute(query)
            else:
                return {"error": "Connector does not support query execution"}

            return {
                "query": query,
                "row_count": len(results),
                "rows": results[:100],  # Limit results
                "truncated": len(results) > 100,
            }
        except Exception as e:
            return {"error": str(e), "query": query}

    return execute_query


# Utility function for validation
def validate_tools_yaml(yaml_path: Path | str) -> dict[str, Any]:
    """Validate a tools.yaml file without loading implementations.

    Args:
        yaml_path: Path to tools.yaml

    Returns:
        Dict with 'valid', 'errors', 'warnings' keys
    """
    yaml_path = Path(yaml_path)
    errors = []
    warnings = []

    if not yaml_path.exists():
        return {
            "valid": False,
            "errors": [f"File not found: {yaml_path}"],
            "warnings": [],
        }

    try:
        content = yaml.safe_load(yaml_path.read_text())
    except yaml.YAMLError as e:
        return {
            "valid": False,
            "errors": [f"Invalid YAML: {e}"],
            "warnings": [],
        }

    if not isinstance(content, dict):
        errors.append("Root must be a dictionary")
        return {"valid": False, "errors": errors, "warnings": warnings}

    if "tools" not in content:
        errors.append("Missing 'tools' key")
        return {"valid": False, "errors": errors, "warnings": warnings}

    tools = content["tools"]
    if not isinstance(tools, list):
        errors.append("'tools' must be a list")
        return {"valid": False, "errors": errors, "warnings": warnings}

    seen_names = set()
    for i, tool in enumerate(tools):
        # Check name
        if "name" not in tool:
            errors.append(f"Tool at index {i} missing 'name'")
            continue

        name = tool["name"]
        if name in seen_names:
            errors.append(f"Duplicate tool name: '{name}'")
        seen_names.add(name)

        # Check description
        if "description" not in tool:
            warnings.append(f"Tool '{name}' missing description")

        # Check implementation or query_template
        has_impl = "implementation" in tool
        has_query = "query_template" in tool

        if not has_impl and not has_query:
            errors.append(
                f"Tool '{name}' needs 'implementation' or 'query_template'"
            )

        if has_impl and has_query:
            warnings.append(f"Tool '{name}' has both implementation and query_template")

        # Validate parameters
        params = tool.get("parameters", [])
        if not isinstance(params, list):
            errors.append(f"Tool '{name}' parameters must be a list")
            continue

        param_names = set()
        for param in params:
            if "name" not in param:
                errors.append(f"Tool '{name}' has parameter without name")
                continue

            pname = param["name"]
            if pname in param_names:
                errors.append(f"Tool '{name}' has duplicate parameter: '{pname}'")
            param_names.add(pname)

            # Check type
            ptype = param.get("type", "string")
            valid_types = {
                "string",
                "integer",
                "int",
                "number",
                "float",
                "boolean",
                "bool",
                "array",
                "list",
                "object",
                "dict",
            }
            if ptype.lower() not in valid_types:
                warnings.append(f"Tool '{name}' parameter '{pname}' has unusual type: '{ptype}'")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }
