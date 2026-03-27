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

    # Coordinator planning output for current turn
    coordinator_result: Optional[dict]
    task_plan: dict[str, str]
    dispatch_targets: list[str]

    # LOL event bus (reset each turn via reducer for new turns)
    event_bus: Annotated[list[dict], _event_bus_reducer]

    # Per-node usage for turn-level observability
    obs_usages: Annotated[list[dict], add]

    # Sync point telemetry between fan-out and synthesizer
    round_event_count: int

    # Final response produced by the active component
    final_response: Optional[str]

    # Lean history: [{role: "user"|"assistant", content: str}, ...]
    conversation_context: list

    # Internal: previous turn user query
    _last_user_query: str
