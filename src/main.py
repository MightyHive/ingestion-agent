"""
Agent platform — LangGraph orchestrator with LOL Protocol.

Flow:
  START -> prepare_new_turn -> Coordinator (PydanticAI)
        -> parallel fan-out to specialist agents
        -> sync_barrier -> synthesizer -> END

Special nodes:
  Coordinator ERR -> coordinator_failure -> END
  out_of_scope / capabilities_help -> END directly

Memory: MemorySaver checkpointer persists state across turns.
        conversation_context holds a lean summary of prior exchanges.

Trace: Each turn writes a .md file under traces/ with the full flow.

Add: PydanticAI agents under `agents/`; register nodes + parallel edges to sync_barrier.
"""

import json
import os
import sys
import time
import asyncio
from datetime import datetime

from typing import Awaitable, Callable

from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.memory import MemorySaver

from agent_registry import ALL_AGENT_NAMES, NORMAL_AGENT_NAMES, SPECIAL_AGENT_NAMES
from agents.coordinator_agent import build_coordinator_agent, CoordinatorDeps
from agents.data_architect_agent import build_data_architect_agent, DataArchitectDeps
from agents.software_engineer_agent import (
    build_software_engineer_agent,
    SoftwareEngineerDeps,
)
from agents.api_researcher_agent import build_api_researcher_agent, APIResearcherDeps
from agents.synthesizer_agent import build_synthesizer_agent
from config.settings import settings
from models.lol import DataArchitectLOL, SoftwareEngineerLOL, APIResearcherLOL
from state import AgentGraphState
from synthesis_enrichment import (
    extract_enrichment_from_events,
    format_mandatory_data_block,
    merge_missing_structured_content,
)
from models.tool_outputs import to_json_safe
from observability import (
    empty_usage,
    extract_usage,
    is_observability_enabled,
    log_agent_end,
    log_agent_start,
    log_console,
    log_retry_end,
    log_retry_start,
    log_turn_summary,
    merge_usage,
    set_observability_enabled,
)

MAX_RETRIES = 2
MAX_CONTEXT_EXCHANGES = 5

# Valid coordinator router destinations (barrier and shortcuts).
COORDINATOR_ROUTE_DESTINATIONS = ALL_AGENT_NAMES + [
    "sync_barrier",
    "coordinator_failure",
    "synthesizer",
]


# ============================================================
# Utilities
# ============================================================

def _write_trace_log(user_query: str, trace_entries: list, conversation_context: list) -> str:
    """Write a .md file with the full turn trace."""
    traces_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "traces")
    os.makedirs(traces_dir, exist_ok=True)

    ts = datetime.now()
    filename = f"trace_{ts.strftime('%Y-%m-%d_%H-%M-%S')}.md"
    filepath = os.path.join(traces_dir, filename)

    lines = [
        f"# Trace — {ts.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## Query",
        "",
        f"> {user_query}",
        "",
    ]

    if conversation_context:
        lines.append("## Conversation context")
        lines.append("")
        for entry in conversation_context:
            role = "User" if entry.get("role") == "user" else "Assistant"
            content = entry.get("content", "")
            lines.append(f"**{role}:** {content}")
            lines.append("")

    lines.append("## Execution flow")
    lines.append("")

    for i, entry in enumerate(trace_entries, 1):
        node = entry["node"]
        timestamp = entry["timestamp"]
        output = entry.get("output", {})

        lines.append(f"### {i}. `{node}` ({timestamp})")
        lines.append("")

        if node == "prepare_new_turn":
            ctx_count = len(output.get("conversation_context", []))
            lines.append(f"- **Context entries:** {ctx_count}")
            lines.append("- Turn execution state reset")

        elif node == "coordinator":
            cr = output.get("coordinator_result", {})
            lines.append(f"- **Status:** `{cr.get('status', '?')}`")
            lines.append(f"- **Reasoning:** {cr.get('reason', 'N/A')}")
            plan = output.get("task_plan", {})
            if plan:
                targets = output.get("dispatch_targets", [])
                lines.append(f"- **Parallel dispatch ({len(targets)} agents):**")
                for agent_name in targets:
                    lines.append(f"  - `{agent_name}`: {plan.get(agent_name, '(no instruction)')}")
            else:
                lines.append("- **Plan:** (empty)")

        elif node == "sync_barrier":
            lines.append(f"- **Round events:** {output.get('round_event_count', '?')}")
            lines.append("- **Lean event bus ready for synthesizer**")

        elif node == "synthesizer":
            resp = output.get("final_response", "")
            lines.append("- **Final response:**")
            lines.append("")
            lines.append("```")
            lines.append(resp[:2000] if resp else "(empty)")
            lines.append("```")

        else:
            results = output.get("event_bus", [])
            result = results[-1] if results else {}
            lines.append(f"- **Agent ID:** `{result.get('id', node)}`")
            lines.append(f"- **Status:** `{result.get('status', '?')}`")
            lines.append(f"- **Reasoning:** {result.get('reason', 'N/A')[:300]}")
            payload = result.get("payload", {})
            lines.append("- **Payload:**")
            lines.append("")
            lines.append("```json")
            try:
                lines.append(json.dumps(to_json_safe(payload), indent=2, ensure_ascii=False))
            except Exception:
                lines.append(str(payload))
            lines.append("```")

        lines.append("")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return filepath


def _make_error_lol(agent_id: str, error: Exception, payload_defaults: dict) -> dict:
    """Build a standard error LOL for any agent."""
    return {
        "status": "ERR",
        "reason": f"Exception in {agent_id}: {str(error)}",
        "id": agent_id,
        "payload": payload_defaults,
    }


def _sanitize_reason(lol: dict) -> dict:
    """
    Trim `reason` tokens on success:
    - OK  -> drop reasoning (empty string)
    - WARN -> short reasoning
    - ERR -> full reasoning
    """
    if not isinstance(lol, dict):
        return lol
    status = lol.get("status")
    text = (lol.get("reason") or "").strip()
    if status == "OK":
        lol["reason"] = ""
    elif status == "WARN":
        lol["reason"] = text[:180]
    else:
        lol["reason"] = text
    return lol


def _safe_min_json(data: dict) -> str:
    """Serialize a dict to minified JSON (one line, no spaces)."""
    return json.dumps(to_json_safe(data), ensure_ascii=False, separators=(",", ":"))


def _to_lean_lol_event(lol: dict, include_warn_reason: bool = False) -> dict:
    """Prune a LOL for low-cost internal transport."""
    lean = {
        "id": lol.get("id"),
        "status": lol.get("status"),
        "payload": lol.get("payload"),
    }
    if lol.get("status") == "ERR":
        lean["reason"] = lol.get("reason", "")
    elif include_warn_reason and lol.get("status") == "WARN" and lol.get("reason"):
        lean["reason"] = lol.get("reason")
    return lean


def get_lean_event_bus(events: list[dict], include_warn_reason: bool = False) -> str:
    """
    Convert LOL events to minified JSON Lines.
    Format: one JSON object per line, no spaces.
    """
    lines = []
    for event in events:
        lines.append(_safe_min_json(_to_lean_lol_event(event, include_warn_reason=include_warn_reason)))
    return "\n".join(lines)


def _round_events(state: AgentGraphState) -> list[dict]:
    """Events for the current turn (event_bus resets each turn)."""
    return state.get("event_bus", [])


def _usage_from_lol(lol: dict | None) -> dict:
    """Read usage attached to LOL, normalized to the standard shape."""
    if not isinstance(lol, dict):
        return empty_usage()
    raw = lol.get("usage")
    if isinstance(raw, dict):
        return merge_usage(empty_usage(), raw)
    return empty_usage()


def _attach_usage(lol: dict, usage: dict) -> dict:
    """Attach usage to LOL for traceability and local debugging."""
    out = dict(lol or {})
    out["usage"] = merge_usage(empty_usage(), usage)
    return out


def _build_agent_event_output(lol: dict, usage: dict | None = None) -> dict:
    """Uniform agent node output for parallel accumulation in event_bus."""
    normalized_usage = merge_usage(empty_usage(), usage)
    return {"event_bus": [to_json_safe(lol)], "obs_usages": [normalized_usage]}


async def _run_with_retries(
    agent_id: str,
    instruction: str,
    invoke_fn: Callable[[str], Awaitable[tuple[dict, dict]]],
    payload_defaults: dict,
    max_retries: int | None = None,
) -> tuple[dict, dict]:
    """
    Retry an agent call when status=ERR.
    Retries run inside the node so graph parallelism stays valid.
    """
    prompt = instruction
    last_lol = _make_error_lol(agent_id, Exception("No output"), payload_defaults)
    total_usage = empty_usage()

    retries = MAX_RETRIES if max_retries is None else max(0, max_retries)
    total_attempts = retries + 1
    for attempt in range(1, total_attempts + 1):
        attempt_started = time.perf_counter()
        log_retry_start(agent_id, attempt, total_attempts)
        attempt_usage = empty_usage()
        try:
            last_lol, attempt_usage = await invoke_fn(prompt)
        except Exception as e:
            last_lol = _make_error_lol(agent_id, e, payload_defaults)
            attempt_usage = empty_usage()

        total_usage = merge_usage(total_usage, attempt_usage)
        last_lol = to_json_safe(last_lol)
        existing_usage = _usage_from_lol(last_lol)
        if attempt_usage.get("total_tokens", 0) > 0 or (
            attempt_usage.get("prompt_tokens", 0) > 0 or attempt_usage.get("completion_tokens", 0) > 0
        ):
            last_lol = _attach_usage(last_lol, attempt_usage)
        else:
            last_lol = _attach_usage(last_lol, existing_usage)
        last_lol = _sanitize_reason(last_lol)
        log_retry_end(
            agent_id,
            attempt,
            time.perf_counter() - attempt_started,
            status=last_lol.get("status"),
            reason=last_lol.get("reason"),
        )
        if last_lol.get("status") != "ERR":
            return last_lol, total_usage

        prompt = (
            f"{instruction}\n\n"
            f"PREVIOUS_ERROR: {last_lol.get('reason', '')}\n"
            "Fix the error and try again."
        )

    return last_lol, total_usage


async def _run_specialist_node(
    state: AgentGraphState,
    agent_id: str,
    display_name: str,
    minimal_trace_message: str,
    invoke_fn: Callable[[str], Awaitable[tuple[dict, dict]]],
    payload_defaults: dict,
    max_retries: int | None = None,
) -> dict:
    """Run a specialist node with start/end observability."""
    instruction = state.get("task_plan", {}).get(agent_id, "")
    if not instruction:
        return {}

    if not is_observability_enabled():
        print(minimal_trace_message)
    log_agent_start(display_name, instruction=instruction)
    started = time.perf_counter()
    lol, usage = await _run_with_retries(
        agent_id,
        instruction,
        invoke_fn,
        payload_defaults,
        max_retries=max_retries,
    )
    log_agent_end(
        display_name,
        time.perf_counter() - started,
        status=lol.get("status"),
        reason=lol.get("reason"),
        prompt_tokens=usage.get("prompt_tokens", 0),
        completion_tokens=usage.get("completion_tokens", 0),
        total_tokens=usage.get("total_tokens", 0),
    )
    return _build_agent_event_output(lol, usage)


# ============================================================
# Graph nodes
# ============================================================

def prepare_new_turn(state: AgentGraphState) -> dict:
    """
    Entry node: reset prior-turn execution state
    and refresh conversation_context with the previous exchange.
    """
    prev_query = state.get("_last_user_query", "")
    prev_response = state.get("final_response")
    context = list(state.get("conversation_context") or [])

    if prev_response and prev_query:
        context.append({"role": "user", "content": prev_query})
        context.append({"role": "assistant", "content": prev_response})
        if len(context) > MAX_CONTEXT_EXCHANGES * 2:
            context = context[-(MAX_CONTEXT_EXCHANGES * 2):]

    return {
        "coordinator_result": None,
        "task_plan": {},
        "dispatch_targets": [],
        "event_bus": [],
        "obs_usages": [],
        "round_event_count": 0,
        "final_response": None,
        "conversation_context": context,
        "_last_user_query": state["user_query"],
    }


async def coordinator_node(state: AgentGraphState) -> dict:
    """Call the Coordinator PydanticAI agent and build dispatch targets."""
    if is_observability_enabled():
        print()
    else:
        print("\n   🧠 [Coordinator planning...]")
    log_agent_start("Coordinator")
    started = time.perf_counter()

    context = state.get("conversation_context", [])
    user_query = state["user_query"]

    if context:
        context_lines = []
        for c in context:
            role = "User" if c.get("role") == "user" else "Assistant"
            context_lines.append(f"{role}: {c.get('content', '')}")
        context_block = "\n".join(context_lines)
        prompt = (
            "PRIOR CONVERSATION CONTEXT:\n"
            + context_block
            + "\n\nNEW USER REQUEST:\n"
            + user_query
        )
    else:
        prompt = user_query

    usage = empty_usage()
    try:
        agent = build_coordinator_agent()
        result = await agent.run(prompt, deps=CoordinatorDeps(session_id="cli_session"))
        lol = result.output.model_dump()
        usage = extract_usage(result)
    except Exception as e:
        lol = _make_error_lol("coordinator", e, {"tasks": []})
        usage = empty_usage()

    tasks = lol.get("payload", {}).get("tasks", []) if isinstance(lol, dict) else []
    task_plan: dict[str, str] = {}
    for step in tasks:
        agent_name = step.get("target_agent")
        instruction = step.get("instruction", "")
        if agent_name in ALL_AGENT_NAMES:
            task_plan[agent_name] = instruction

    dispatch_targets = list(task_plan.keys())

    if any(a in SPECIAL_AGENT_NAMES for a in dispatch_targets) and any(
        a in NORMAL_AGENT_NAMES for a in dispatch_targets
    ):
        dispatch_targets = [a for a in dispatch_targets if a in NORMAL_AGENT_NAMES]
        task_plan = {k: v for k, v in task_plan.items() if k in dispatch_targets}

    lol = _sanitize_reason(_attach_usage(lol, usage))
    log_agent_end(
        "Coordinator",
        time.perf_counter() - started,
        status=lol.get("status"),
        targets=len(dispatch_targets),
        prompt_tokens=usage.get("prompt_tokens", 0),
        completion_tokens=usage.get("completion_tokens", 0),
        total_tokens=usage.get("total_tokens", 0),
    )
    return {
        "coordinator_result": lol,
        "task_plan": task_plan,
        "dispatch_targets": dispatch_targets,
        "obs_usages": [usage],
    }


async def api_researcher_node(state: AgentGraphState) -> dict:
    """Invoke the API Researcher agent and return a LOL event."""
    async def _invoke(prompt: str) -> tuple[dict, dict]:
            # Enrich instruction with known platform context if applicable
            from agents.api_researcher_agent import _resolve_platform
            platform_data = _resolve_platform(prompt)
            if platform_data:
                prompt = (
                    f"{prompt}\n\n"
                    f"[KNOWN PLATFORM]\n"
                    f"display_name:   {platform_data['display_name']}\n"
                    f"docs_url:       {platform_data['docs_url']}\n"
                    f"reference_file: {platform_data['reference_file']}\n\n"
                    f"Step 1: call read_documentation_url('{platform_data['reference_file']}') — source of truth.\n"
                    f"Step 2: call read_documentation_url('{platform_data['docs_url']}') — freshness check.\n"
                    f"Set action='freshness_check'."
                )
            result = await build_api_researcher_agent().run(
                prompt,
                deps=APIResearcherDeps(
                    project_id=settings.PROJECT_ID_LLM or "",
                    location=settings.LOCATION,
                ),
            )
            return result.output.model_dump(), extract_usage(result)

    default_payload = APIResearcherLOL(
        status="ERR",
        reason="API Researcher failure.",
        payload={
            "action": "error",
            "platform": "",
            "auth": {"method": "UNKNOWN", "required_credentials": [], "token_type": "UNKNOWN", "expiry": "UNKNOWN"},
            "reporting_endpoint": "UNKNOWN",
            "available_fields": [],
            "pagination": "UNKNOWN",
            "rate_limit": "UNKNOWN",
            "freshness_check": {"checked": False, "changes_detected": False},
            "missing_inputs": [],
            "summary": "API Researcher failed to process the request.",
        },
    ).payload.model_dump()

    return await _run_specialist_node(
        state,
        "api_researcher",
        "API Researcher",
        "   🔍 [API Researcher investigating...]",
        _invoke,
        default_payload,
    )

async def data_architect_node(state: AgentGraphState) -> dict:
    """Invoke the Data Architect agent and return a LOL event."""

    async def _invoke(prompt: str) -> tuple[dict, dict]:
        result = await build_data_architect_agent().run(
            prompt,
            deps=DataArchitectDeps(project_id=settings.PROJECT_ID_DATA or ""),
        )
        lol = result.output.model_dump()
        return lol, extract_usage(result)

    default_payload = DataArchitectLOL(
        status="ERR",
        reason="Data architect failure.",
        payload={"dataset_target": "", "action_taken": "error"},
    ).payload.model_dump()
    return await _run_specialist_node(
        state,
        "data_architect",
        "Data Architect",
        "   🏗️ [Data Architect working...]",
        _invoke,
        default_payload,
    )


async def software_engineer_node(state: AgentGraphState) -> dict:
    """Invoke the Software Engineer agent and return a LOL event."""

    async def _invoke(prompt: str) -> tuple[dict, dict]:
        result = await build_software_engineer_agent().run(
            prompt,
            deps=SoftwareEngineerDeps(
                project_id=settings.PROJECT_ID_DATA or settings.PROJECT_ID_LLM or "",
                location=settings.LOCATION,
            ),
        )
        lol = result.output.model_dump()
        return lol, extract_usage(result)

    default_payload = SoftwareEngineerLOL(
        status="ERR",
        reason="Software engineer failure.",
        payload={
            "action": "error",
            "connector_name": None,
            "source": None,
            "file_path": None,
            "validation": None,
            "data": None,
            "generated_files": [],
            "env_vars_required": [],
            "required_secrets": [],
            "api_dependencies": [],
            "missing_inputs": [],
            "review_requested": False,
            "review_reason": None,
            "review_notes": None,
            "summary": "Software engineer failed to process the request.",
        },
    ).payload.model_dump()
    return await _run_specialist_node(
        state,
        "software_engineer",
        "Software Engineer",
        "   🧩 [Software Engineer working...]",
        _invoke,
        default_payload,
    )


def out_of_scope_node(state: AgentGraphState) -> dict:
    """Guardrail: request outside scope. Add: copy and rules for your domain."""
    if not is_observability_enabled():
        print("   🚫 [Guardrail: request out of scope]")
    log_console("agent", "start", "Guardrail out_of_scope")
    lol = {
        "status": "OK",
        "reason": "Request outside assistant scope.",
        "id": "out_of_scope",
        "payload": {
            "summary": (
                "This request is outside the assistant's scope. "
                "Define the domain in this node when you add new agents."
            )
        },
    }
    return {"event_bus": [lol], "final_response": lol["payload"]["summary"]}


def capabilities_help_node(state: AgentGraphState) -> dict:
    """Add: help text matching your real agents and tools."""
    if not is_observability_enabled():
        print("   📖 [Help manual activated]")
    log_console("agent", "start", "Help manual")
    help_text = (
        "Help template: when you add agents, describe what each one does "
        "and what the user can ask."
    )
    lol = {
        "status": "OK",
        "reason": "Capabilities overview requested.",
        "id": "capabilities_help",
        "payload": {"summary": help_text},
    }
    return {"event_bus": [lol], "final_response": lol["payload"]["summary"]}


def coordinator_failure_node(state: AgentGraphState) -> dict:
    """User-visible output when the coordinator fails."""
    cr = state.get("coordinator_result") or {}
    msg = cr.get("reason") or "Could not plan the query right now."
    return {"final_response": f"⚠️ Sorry, an error occurred while planning your request.\n\nDetail: {msg}"}


async def synthesizer_node(state: AgentGraphState) -> dict:
    """Produce the final Markdown answer via the Synthesizer PydanticAI agent."""
    if not is_observability_enabled():
        print("   ✍️  [Synthesizer drafting final response...]")
    log_agent_start("Synthesizer")
    started = time.perf_counter()

    user_query = state.get("user_query", "")
    round_events = _round_events(state)
    lean_bus = get_lean_event_bus(round_events, include_warn_reason=True)
    if not lean_bus:
        lean_bus = _safe_min_json({
            "id": "system",
            "status": "WARN",
            "payload": {"summary": "No specialist results"},
        })

    enrichment = extract_enrichment_from_events(round_events)
    mandatory_block = format_mandatory_data_block(enrichment)
    mandatory_section = ""
    if mandatory_block:
        mandatory_section = (
            "\n\n---\n## MANDATORY STRUCTURED DATA (integrate completely in the answer)\n\n"
            f"{mandatory_block}\n"
        )

    prompt_final = (
        f"User request: {user_query}\n\n"
        "Minified LOL event bus (one JSON per line):\n"
        f"{lean_bus}"
        f"{mandatory_section}\n"
        "Produce the final answer from the event bus and mandatory data above."
    )

    log_console("synthesizer", "prompt", "built_prompt", chars=len(prompt_final))
    synth_status = "OK"
    err_reason: str | None = None
    try:
        agent = build_synthesizer_agent()
        result = await agent.run(prompt_final)
        final_text = result.output.payload.summary
        usage = extract_usage(result)
        synth_status = result.output.status
    except Exception as e:
        final_text = "Error generating final synthesis: " + str(e)
        usage = empty_usage()
        synth_status = "ERR"
        err_reason = str(e)

    final_text = merge_missing_structured_content(final_text, enrichment)
    log_agent_end(
        "Synthesizer",
        time.perf_counter() - started,
        status=synth_status,
        reason=err_reason,
        prompt_tokens=usage.get("prompt_tokens", 0),
        completion_tokens=usage.get("completion_tokens", 0),
        total_tokens=usage.get("total_tokens", 0),
    )

    return {"final_response": final_text, "obs_usages": [usage]}


def sync_barrier_node(state: AgentGraphState) -> dict:
    """Barrier after fan-out: sync parallel agents before the synthesizer."""
    event_count = len(_round_events(state))
    log_console("system", "info", "Sync Barrier", events=event_count)
    return {"round_event_count": event_count}


# ============================================================
# Deterministic routers (pure Python, no LLM)
# ============================================================

def route_from_coordinator(state: AgentGraphState):
    """After coordinator: route to parallel agents or special nodes."""
    coordinator = state["coordinator_result"]
    if coordinator["status"] == "ERR":
        return "coordinator_failure"

    targets = state.get("dispatch_targets", [])
    if not targets:
        return "synthesizer"

    if len(targets) == 1 and targets[0] in SPECIAL_AGENT_NAMES:
        return targets[0]

    normal_targets = [t for t in targets if t in NORMAL_AGENT_NAMES]
    if not normal_targets:
        return "synthesizer"
    return normal_targets


# ============================================================
# Graph build
# Add: builder.add_node("my_agent", my_agent_node) and NORMAL_AGENT_NAMES.
# ============================================================

builder = StateGraph(AgentGraphState)

builder.add_node("prepare_new_turn", prepare_new_turn)
builder.add_node("coordinator", coordinator_node)
builder.add_node("api_researcher", api_researcher_node)
builder.add_node("data_architect", data_architect_node)
builder.add_node("software_engineer", software_engineer_node)
builder.add_node("out_of_scope", out_of_scope_node)
builder.add_node("capabilities_help", capabilities_help_node)
builder.add_node("coordinator_failure", coordinator_failure_node)
builder.add_node("sync_barrier", sync_barrier_node)
builder.add_node("synthesizer", synthesizer_node)

builder.add_edge(START, "prepare_new_turn")
builder.add_edge("prepare_new_turn", "coordinator")

builder.add_conditional_edges(
    "coordinator",
    route_from_coordinator,
    COORDINATOR_ROUTE_DESTINATIONS,
)

for agent_name in NORMAL_AGENT_NAMES:
    builder.add_edge(agent_name, "sync_barrier")

builder.add_edge("sync_barrier", "synthesizer")

builder.add_edge("synthesizer", END)
builder.add_edge("coordinator_failure", END)
builder.add_edge("out_of_scope", END)
builder.add_edge("capabilities_help", END)

memory = MemorySaver()
# Exposed for FastAPI (`api.py`). Safe to import: the CLI runs only under `if __name__ == "__main__"`.
compiled_graph = builder.compile(checkpointer=memory)


# ============================================================
# CLI
# ============================================================

async def _cli_loop() -> None:
    obs_enabled = any(arg in {"-obs", "--obs"} for arg in sys.argv[1:])
    set_observability_enabled(obs_enabled)

    print("\n" + "=" * 50)
    print("🚀 Starting agent platform (LOL Protocol)...")
    print("💡 Type 'exit' or 'quit' to leave.")
    if obs_enabled:
        print("🔍 Local observability: ON (-obs)")
    print("=" * 50 + "\n")

    config = {"configurable": {"thread_id": "1"}}
    is_first_turn = True

    while True:
        print("\n👤 User (paste your text and press Ctrl+D to send):")
        try:
            user_input = sys.stdin.read().strip()
        except EOFError:
            break

        print("\n" + "-" * 40)

        if user_input.lower() in ["exit", "quit"]:
            print("👋 Leaving the platform...")
            break

        if not user_input.strip():
            continue

        if is_first_turn:
            input_state = {
                "user_query": user_input,
                "coordinator_result": None,
                "task_plan": {},
                "dispatch_targets": [],
                "event_bus": [],
                "obs_usages": [],
                "round_event_count": 0,
                "final_response": None,
                "conversation_context": [],
                "_last_user_query": "",
            }
            is_first_turn = False
        else:
            input_state = {"user_query": user_input}

        trace_entries = []
        turn_context = []
        turn_started = time.perf_counter()
        turn_usage = empty_usage()
        turn_error: Exception | None = None

        try:
            async for event in compiled_graph.astream(input_state, config, stream_mode="updates"):
                for node_name, values in event.items():
                    trace_entries.append({
                        "node": node_name,
                        "timestamp": datetime.now().strftime("%H:%M:%S"),
                        "output": values,
                    })

                    if node_name == "prepare_new_turn":
                        turn_context = values.get("conversation_context", [])

                    if isinstance(values, dict):
                        if "obs_usages" in values and isinstance(values["obs_usages"], list):
                            for usage_item in values["obs_usages"]:
                                turn_usage = merge_usage(turn_usage, usage_item)
                        elif "obs_usage" in values:
                            turn_usage = merge_usage(turn_usage, values.get("obs_usage"))

                    if node_name in [
                        "synthesizer",
                        "out_of_scope",
                        "capabilities_help",
                        "coordinator_failure",
                    ] and values.get("final_response"):
                        print(f"\n🤖 ASSISTANT:\n{values['final_response']}\n")
                        print("-" * 60)
        except Exception as e:
            turn_error = e
            print(f"\n❌ Error during turn execution: {str(e)}")
        finally:
            _write_trace_log(user_input, trace_entries, turn_context)
            if obs_enabled:
                log_turn_summary(
                    elapsed_s=time.perf_counter() - turn_started,
                    usage=turn_usage,
                    turns_events=len(trace_entries),
                )

        if turn_error is not None:
            continue


if __name__ == "__main__":
    asyncio.run(_cli_loop())
