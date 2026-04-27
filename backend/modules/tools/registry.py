"""
JARVIS — Tool Registry.

Tools are async functions decorated with @tool.  The registry exposes them
to the LLM orchestrator as a callable catalog.  Each tool has a name,
description (in Spanish for the LLM), and a parameter schema.
"""
from __future__ import annotations

import functools
import inspect
from typing import Any, Callable, Dict, List, Optional


class ToolDefinition:
    def __init__(self, fn: Callable, name: str, description: str, params: Dict[str, str]) -> None:
        self.fn          = fn
        self.name        = name
        self.description = description
        self.params      = params  # {param_name: description}

    def to_prompt_block(self) -> str:
        """Format for injection into the LLM system prompt."""
        lines = [f"- **{self.name}**: {self.description}"]
        if self.params:
            for p, d in self.params.items():
                lines.append(f"    • {p}: {d}")
        return "\n".join(lines)


class ToolRegistry:
    """Global tool catalog."""

    def __init__(self) -> None:
        self._tools: Dict[str, ToolDefinition] = {}

    def register(self, fn: Callable, name: str, description: str, params: Dict[str, str]) -> None:
        self._tools[name] = ToolDefinition(fn=fn, name=name, description=description, params=params)

    def get(self, name: str) -> Optional[ToolDefinition]:
        return self._tools.get(name)

    def all(self) -> List[ToolDefinition]:
        return list(self._tools.values())

    def names(self) -> List[str]:
        return list(self._tools.keys())

    def catalog_prompt(self) -> str:
        """Return all tools formatted for the LLM system prompt."""
        if not self._tools:
            return ""
        lines = ["HERRAMIENTAS DISPONIBLES (úsalas cuando el usuario lo necesite):"]
        for t in self._tools.values():
            lines.append(t.to_prompt_block())
        return "\n".join(lines)


# ── Singleton ────────────────────────────────────────────────────────────────

_REGISTRY = ToolRegistry()


def tool(name: str, description: str, params: Optional[Dict[str, str]] = None):
    """Decorator to register a function as a JARVIS tool.

    Usage::

        @tool("buscar_web", "Busca información en internet", {"query": "texto a buscar"})
        async def web_search(query: str) -> ToolResult:
            ...
    """
    def decorator(fn: Callable) -> Callable:
        _REGISTRY.register(fn, name=name, description=description, params=params or {})
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            return await fn(*args, **kwargs)
        wrapper._tool_name = name
        return wrapper
    return decorator


def get_registry() -> ToolRegistry:
    return _REGISTRY
