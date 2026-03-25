"""
Pydantic contracts for structured tool outputs.

Add: ToolOutput subclasses per tool (fields with Field(description=...)).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field


ToolStatus = Literal["OK", "WARN", "ERR"]


# ============================================================
# Shared base for all tools
# ============================================================

class ToolOutput(BaseModel):
    """Base contract for any tool result."""

    status: ToolStatus = Field(
        description=(
            "Execution status: OK (success), WARN (partial result), or ERR (failure)."
        )
    )
    code: Optional[str] = Field(
        default=None,
        description="Optional internal status code to classify the outcome.",
    )
    msg: Optional[str] = Field(
        default=None,
        description="Short message for the consuming agent.",
    )


# ============================================================
# JSON-safe serialization helpers
# ============================================================

def to_json_safe(value: Any) -> Any:
    """Normalize non-JSON-native values for safe transport."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, BaseModel):
        return to_json_safe(value.model_dump())
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, dict):
        return {str(k): to_json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_json_safe(v) for v in value]
    return str(value)


def dump_tool_output(output: ToolOutput) -> Dict[str, Any]:
    """Return a compact JSON-safe dict for the agent."""
    return to_json_safe(output.model_dump(exclude_none=True))
