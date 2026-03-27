"""
Software Engineer component runtime (PoC mode).

This entrypoint runs the Software Engineer agent directly (no coordinator/synthesizer).
The LOL dict is the contract for downstream agents; the CLI prints ``payload.summary`` for convenience.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from datetime import datetime

<<<<<<< Updated upstream
from typing import Awaitable, Callable

from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.memory import MemorySaver

from agents.coordinator_agent import build_coordinator_agent, CoordinatorDeps
from agents.data_architect_agent import build_data_architect_agent, DataArchitectDeps
from agents.synthesizer_agent import build_synthesizer_agent
from config.settings import settings
from models.lol import DataArchitectLOL
from state import AgentGraphState
from synthesis_enrichment import (
    extract_enrichment_from_events,
    format_mandatory_data_block,
    merge_missing_structured_content,
)
=======
from agents.software_engineer_agent import SoftwareEngineerDeps, run_software_engineer_agent
from config.settings import settings
>>>>>>> Stashed changes
from models.tool_outputs import to_json_safe
from observability import (
    empty_usage,
    extract_usage,
    is_observability_enabled,
    log_agent_end,
    log_agent_start,
    log_retry_end,
    log_retry_start,
    log_turn_summary,
    merge_usage,
    set_observability_enabled,
)

MAX_RETRIES = 2
MAX_CONTEXT_EXCHANGES = 5

<<<<<<< Updated upstream
# Add: each id must match the graph node name and TaskStep.target_agent.
SPECIAL_AGENT_NAMES = ["out_of_scope", "capabilities_help"]
NORMAL_AGENT_NAMES: list[str] = ["data_architect"]
ALL_AGENT_NAMES = SPECIAL_AGENT_NAMES + NORMAL_AGENT_NAMES
=======
>>>>>>> Stashed changes

def _write_trace_log(user_query: str, lol: dict, elapsed_s: float, usage: dict, conversation_context: list) -> str:
    traces_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "traces")
    os.makedirs(traces_dir, exist_ok=True)

    ts = datetime.now()
    filename = f"trace_{ts.strftime('%Y-%m-%d_%H-%M-%S')}.md"
    filepath = os.path.join(traces_dir, filename)

    lines = [
        f"# Software Engineer Trace — {ts.strftime('%Y-%m-%d %H:%M:%S')}",
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
            lines.append(f"**{role}:** {entry.get('content', '')}")
            lines.append("")

    lines.extend(
        [
            "## Result (LOL)",
            "",
            "```json",
            json.dumps(to_json_safe(lol), ensure_ascii=False, indent=2),
            "```",
            "",
            "## Telemetry",
            "",
            f"- Elapsed: `{elapsed_s:.2f}s`",
            f"- Prompt tokens: `{usage.get('prompt_tokens', 0)}`",
            f"- Completion tokens: `{usage.get('completion_tokens', 0)}`",
            f"- Total tokens: `{usage.get('total_tokens', 0)}`",
            "",
        ]
    )

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return filepath


def _sanitize_reason(lol: dict) -> dict:
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


def _extract_final_text(lol: dict) -> str:
    """Prefer ``payload.summary``; otherwise dump the LOL for CLI/debug."""
    payload = lol.get("payload", {}) if isinstance(lol, dict) else {}
    summary = payload.get("summary") if isinstance(payload, dict) else None
    if isinstance(summary, str) and summary.strip():
        return summary
    return json.dumps(to_json_safe(lol), ensure_ascii=False, indent=2)


async def _run_with_retries(prompt: str, deps: SoftwareEngineerDeps) -> tuple[dict, dict]:
    retries = max(0, MAX_RETRIES)
    total_attempts = retries + 1
    total_usage = empty_usage()
    last_lol = {
        "status": "ERR",
        "reason": "No output",
        "id": "software_engineer_agent",
        "payload": {
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
            "summary": "The software engineer component could not complete the request.",
        },
    }
    working_prompt = prompt

    for attempt in range(1, total_attempts + 1):
        log_retry_start("software_engineer_agent", attempt, total_attempts)
        started = time.perf_counter()
        try:
            lol, usage = await run_software_engineer_agent(working_prompt, deps=deps)
            total_usage = merge_usage(total_usage, usage)
            last_lol = _sanitize_reason(to_json_safe(lol))
            log_retry_end(
                "software_engineer_agent",
                attempt,
                time.perf_counter() - started,
                status=last_lol.get("status"),
                reason=last_lol.get("reason"),
            )
            if last_lol.get("status") != "ERR":
                return last_lol, total_usage
        except Exception as exc:
            log_retry_end(
                "software_engineer_agent",
                attempt,
                time.perf_counter() - started,
                status="ERR",
                reason=str(exc),
            )
            last_lol = {
                "status": "ERR",
                "reason": f"Exception in software_engineer_agent: {str(exc)}",
                "id": "software_engineer_agent",
                "payload": last_lol.get("payload", {}),
            }

        working_prompt = (
            f"{prompt}\n\nPREVIOUS_ERROR: {last_lol.get('reason', '')}\n"
            "Fix the error and try again."
        )

    return last_lol, total_usage


<<<<<<< Updated upstream
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
builder.add_node("data_architect", data_architect_node)
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
compiled_graph = builder.compile(checkpointer=memory)


# ============================================================
# CLI
# ============================================================
=======
def _append_library_persistence_rule(prompt: str) -> str:
    """Reinforce non-optional persistence for this agent (SE CLI entrypoint)."""
    return (
        prompt
        + "\n\n[Library rule] If you author or finalize connector Python (`write_cf_code`, "
        "`modify_payload_and_columns`, or edited template), you MUST call `validate_connector_code` "
        "then `save_connector` (new file) or `overwrite_connector` (replace only after user explicitly authorizes). "
        "`save_connector` never overwrites—on conflict ask the user before `overwrite_connector`. "
        "If the turn is read-only (list/find/read), persistence does not apply. "
        "Set payload.file_path from the save tool output when authoring succeeds."
    )


def _build_prompt(user_query: str, conversation_context: list[dict]) -> str:
    if not conversation_context:
        return user_query
    context_lines: list[str] = []
    for c in conversation_context:
        role = "User" if c.get("role") == "user" else "Assistant"
        context_lines.append(f"{role}: {c.get('content', '')}")
    return (
        "PRIOR CONVERSATION CONTEXT:\n"
        + "\n".join(context_lines)
        + "\n\nNEW USER REQUEST:\n"
        + user_query
    )

>>>>>>> Stashed changes

async def _cli_loop() -> None:
    obs_enabled = any(arg in {"-obs", "--obs"} for arg in sys.argv[1:])
    set_observability_enabled(obs_enabled)

    print("\n" + "=" * 50)
    print("🚀 Starting Software Engineer component (PoC)...")
    print("💡 Type 'exit' or 'quit' to leave.")
    if obs_enabled:
        print("🔍 Local observability: ON (-obs)")
    print("=" * 50 + "\n")

    conversation_context: list[dict] = []
    while True:
        print("\n👤 User (paste your text and press Ctrl+D to send):")
        try:
            user_input = sys.stdin.read().strip()
        except EOFError:
            break

        print("\n" + "-" * 40)
        if user_input.lower() in {"exit", "quit"}:
            print("👋 Leaving the platform...")
            break
        if not user_input:
            continue

        prompt = _append_library_persistence_rule(_build_prompt(user_input, conversation_context))
        deps = SoftwareEngineerDeps(
            project_id=settings.PROJECT_ID_DATA or settings.PROJECT_ID_LLM or "",
            location=settings.LOCATION,
        )

        log_agent_start("Software Engineer", instruction=prompt)
        started = time.perf_counter()
        lol, usage = await _run_with_retries(prompt, deps)
        elapsed = time.perf_counter() - started
        log_agent_end(
            "Software Engineer",
            elapsed,
            status=lol.get("status"),
            reason=lol.get("reason"),
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
        )

        answer = _extract_final_text(lol)
        print(f"\n🤖 ASSISTANT:\n{answer}\n")
        print("-" * 60)

        _write_trace_log(user_input, lol, elapsed, usage, conversation_context)
        if obs_enabled:
            log_turn_summary(elapsed_s=elapsed, usage=usage, turns_events=1)

        conversation_context.append({"role": "user", "content": user_input})
        conversation_context.append({"role": "assistant", "content": answer})
        if len(conversation_context) > MAX_CONTEXT_EXCHANGES * 2:
            conversation_context = conversation_context[-(MAX_CONTEXT_EXCHANGES * 2):]


if __name__ == "__main__":
    asyncio.run(_cli_loop())
