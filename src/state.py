"""
AgentGraphState — Global LangGraph state.

Preserves true parallelism: each agent appends its LOL to `event_bus`
via a custom reducer that supports parallel fan-out and per-turn reset.
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

    # Coordinator LOL result
    coordinator_result: Optional[dict]

    # Parallel dispatch: {target_agent: instruction}
    task_plan: dict[str, str]

    # Agents to run this round
    dispatch_targets: list[str]

    # LOL event bus (reset each turn via reducer)
    event_bus: Annotated[list[dict], _event_bus_reducer]

    # Per-node usage accumulated for turn-level observability
    obs_usages: Annotated[list[dict], add]

    # Turn observability metadata for traces
    round_event_count: int

    # Final user-visible response
    final_response: Optional[str]

    # Lean history: [{role: "user"|"assistant", content: str}, ...]
    conversation_context: list

    # Internal: current turn user_query for injection into conversation_context next turn
    _last_user_query: str
