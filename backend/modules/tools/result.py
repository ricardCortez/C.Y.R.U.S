"""Tool execution result."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolResult:
    ok:      bool
    output:  str        # human-readable result for LLM context
    data:    Any = None # structured data (optional)
    error:   str = ""

    @classmethod
    def success(cls, output: str, data: Any = None) -> "ToolResult":
        return cls(ok=True, output=output, data=data)

    @classmethod
    def failure(cls, error: str) -> "ToolResult":
        return cls(ok=False, output=f"Error: {error}", error=error)
