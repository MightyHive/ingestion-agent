"""
AgentGraphState — Global LangGraph state.

Minimal shared state shape for component execution.
Kept intentionally small for single-component PoC mode, while preserving
event bus and context fields useful for future multi-agent integration.
"""

from operator import add
from typing import Annotated, Optional, TypedDict


def _event_bus_reducer(current: list[dict], update: list[dict]) -> list[dict]:
    """
    Custom reducer for event_bus.
    - Empty update list = reset (prepare_new_turn at each turn start).
    - Non-empty update = append (agent nodes in parallel fan-out).
    """
    if not update:
        return []
    return current + update


class AgentGraphState(TypedDict):
    user_query: str

    # LOL event bus (reset each turn via reducer for new turns)
    event_bus: Annotated[list[dict], _event_bus_reducer]

    # Per-node usage for turn-level observability
    obs_usages: Annotated[list[dict], add]

    # Final response produced by the active component
    final_response: Optional[str]

    # Lean history: [{role: "user"|"assistant", content: str}, ...]
    conversation_context: list

    # Internal: previous turn user query
    _last_user_query: str
