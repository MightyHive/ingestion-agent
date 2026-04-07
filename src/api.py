"""
FastAPI HTTP surface for the LangGraph / PydanticAI platform.

Run from the `src/` directory (so `main` and sibling packages resolve):

  cd src && RUN_MODE=api uvicorn api:app --reload --host 0.0.0.0 --port 8000

After `cd src`, use `api:app` only — not `src.api:app` (that needs the repo root on PYTHONPATH with `src` as a package).

`RUN_MODE=api` ensures coordinator tools emit structured payloads instead of blocking on stdin.
Startup runs `init_graph_async()` to attach an AsyncSqliteSaver checkpointer (`checkpoints.db` at repo root).

Streaming POST endpoints use Server-Sent Events (`text/event-stream`): each event is `data: <json>\\n\\n`.
GET `/api/templates` and `/api/sessions/{session_id}/history` support the frontend without running the graph.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Union

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from main import get_compiled_graph, init_graph_async


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await init_graph_async()
    yield


app = FastAPI(title="Ingestion Agent API", version="1.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    session_id: str = Field(..., min_length=1, description="LangGraph thread_id / conversation key")
    message: str = Field(..., min_length=1, description="User message for the current turn")


class SubmitRequest(BaseModel):
    session_id: str = Field(..., min_length=1, description="Same thread_id as /api/chat")
    user_input: Union[str, dict[str, Any]] = Field(
        ...,
        description="Human follow-up as plain text or structured dict (keys: message, text, user_message)",
    )


def _initial_turn_state(user_query: str) -> dict:
    """Match CLI first-turn keys so checkpointer threads start with a valid AgentGraphState."""
    return {
        "user_query": user_query,
        "coordinator_result": None,
        "task_plan": {},
        "dispatch_targets": [],
        "event_bus": [],
        "artifacts": {},
        "obs_usages": [],
        "round_event_count": 0,
        "final_response": None,
        "conversation_context": [],
        "_last_user_query": "",
    }


def _normalize_submit_user_input(user_input: Union[str, dict[str, Any]]) -> str:
    if isinstance(user_input, str):
        return user_input.strip()
    if isinstance(user_input, dict):
        for key in ("message", "text", "user_message"):
            val = user_input.get(key)
            if val is not None and str(val).strip():
                return str(val).strip()
        return json.dumps(user_input, ensure_ascii=False)
    return str(user_input).strip()


def _sse_headers() -> dict[str, str]:
    return {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }


def _field_strs_from_api_spec(artifacts: dict[str, Any]) -> list[str]:
    spec = artifacts.get("api_spec")
    if not isinstance(spec, dict):
        return []
    raw = spec.get("available_fields")
    if not isinstance(raw, list) or not raw:
        return []
    return [str(x).strip() for x in raw if str(x).strip()]


def _field_strs_from_researcher_events(event_bus: list[dict]) -> list[str]:
    """Build API field names from the latest successful api_researcher LOL payload."""
    for ev in reversed(event_bus):
        if ev.get("id") != "api_researcher" or ev.get("status") == "ERR":
            continue
        payload = ev.get("payload")
        if not isinstance(payload, dict):
            continue
        fields = payload.get("available_fields")
        if not isinstance(fields, list):
            continue
        names: list[str] = []
        for item in fields:
            if isinstance(item, dict):
                af = item.get("api_field")
                if af is None:
                    continue
                s = str(af).strip()
                if s and s != "NOT_AVAILABLE" and not s.startswith("DERIVED("):
                    names.append(s)
            elif isinstance(item, str) and item.strip():
                names.append(item.strip())
        if names:
            return names
    return []


def _column_selector_field_strs(artifacts: dict[str, Any], event_bus: list[dict]) -> list[str]:
    from_spec = _field_strs_from_api_spec(artifacts)
    if from_spec:
        return from_spec
    return _field_strs_from_researcher_events(event_bus)


def _parse_last_msg_content(final_state: dict[str, Any], event_bus: list[dict]) -> dict[str, Any]:
    """
    Prefer structured JSON from LangGraph ``messages[-1].content`` when present;
    otherwise use the last event_bus entry payload (current graph stores LOL payloads there).
    """
    last_msg_content: dict[str, Any] = {}
    msgs = final_state.get("messages")
    if isinstance(msgs, list) and msgs:
        raw_last = msgs[-1]
        content: Any = None
        if isinstance(raw_last, dict):
            content = raw_last.get("content")
        else:
            content = getattr(raw_last, "content", None)
        if isinstance(content, str) and content.strip():
            try:
                parsed = json.loads(content.strip())
                if isinstance(parsed, dict):
                    last_msg_content = parsed
            except Exception:
                pass
    if not last_msg_content and event_bus:
        last_e = event_bus[-1]
        pl = last_e.get("payload")
        if isinstance(pl, dict):
            last_msg_content = pl
    return last_msg_content


def _schema_preview_rows_for_ui(raw: list[Any]) -> list[dict[str, Any]]:
    """Ensure each schema_preview row includes a string ``description`` for the frontend."""
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        desc = row.get("description")
        row["description"] = desc.strip() if isinstance(desc, str) else ""
        out.append(row)
    return out


def _schema_approval_table_name(
    last_msg_content: dict[str, Any], artifacts: dict[str, Any]
) -> str:
    """Resolve display table name for SchemaApproval from architect payload or artifacts."""
    for candidate in (last_msg_content.get("table_name"), artifacts.get("table_name")):
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return "Pending Schema"


def _should_offer_schema_approval(last_event: dict[str, Any] | None, payload: dict[str, Any]) -> bool:
    """True when Data Architect just produced a schema/DDL worth reviewing (not stale artifacts alone)."""
    if not last_event or last_event.get("id") != "data_architect":
        return False
    if last_event.get("status") == "ERR":
        return False
    if "schema_preview" in payload:
        sp = payload.get("schema_preview")
        if isinstance(sp, list) and len(sp) > 0:
            return True
    if "proposed_ddl" in payload:
        pd = payload.get("proposed_ddl")
        if isinstance(pd, str) and pd.strip():
            return True
    return False


async def _sse_graph_stream(*, session_id: str, input_state: dict) -> AsyncIterator[str]:
    graph = get_compiled_graph()
    config = {"configurable": {"thread_id": session_id}}
    yield f"data: {json.dumps({'type': 'connection', 'status': 'connected'})}\n\n"
    try:
        async for output in graph.astream(input_state, config, stream_mode="updates"):
            if not isinstance(output, dict):
                continue
            for node_name in output.keys():
                yield f"data: {json.dumps({'type': 'progress', 'node': node_name})}\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'type': 'error', 'detail': str(e)})}\n\n"
        return

    snap = await graph.aget_state(config)
    final_state = getattr(snap, "values", None) or {}
    if not isinstance(final_state, dict):
        final_state = {}
    eb = final_state.get("event_bus") or []
    if not isinstance(eb, list):
        eb = []
    eb = [e for e in eb if isinstance(e, dict)]

    artifacts = final_state.get("artifacts") or {}
    if not isinstance(artifacts, dict):
        artifacts = {}

    last_msg_content = _parse_last_msg_content(final_state, eb)
    last_ev: dict[str, Any] | None = eb[-1] if eb else None
    last_warn = bool(last_ev.get("status") == "WARN") if last_ev else False

    schema_ui = _should_offer_schema_approval(last_ev, last_msg_content)
    field_strs = _column_selector_field_strs(artifacts, eb)
    # Column picker when we have a field list and this turn is not the Data Architect schema step.
    column_ui = bool(field_strs) and not schema_ui

    requires_human_input = last_warn or schema_ui or column_ui

    ui_trigger: dict[str, Any] | None = None
    if requires_human_input:
        if schema_ui:
            raw_cols = last_msg_content.get("schema_preview", [])
            columns = (
                _schema_preview_rows_for_ui(raw_cols)
                if isinstance(raw_cols, list)
                else []
            )
            ddl_val = artifacts.get("table_ddl", "")
            ddl_str = ddl_val.strip() if isinstance(ddl_val, str) else ""
            table_name = _schema_approval_table_name(last_msg_content, artifacts)
            ui_trigger = {
                "component": "SchemaApproval",
                "message": "Review and approve the proposed schema",
                "data": {
                    "ddl": ddl_str,
                    "columns": columns,
                    "tableName": table_name,
                },
            }
        elif "api_spec" in artifacts:
            api_spec = artifacts["api_spec"]
            if isinstance(api_spec, dict):
                raw_fields = api_spec.get("available_fields", [])
                fields = raw_fields if isinstance(raw_fields, list) else []
                ui_trigger = {
                    "component": "ColumnSelector",
                    "message": "Select columns for ingestion",
                    "data": {"available_fields": fields},
                }
        elif field_strs:
            ui_trigger = {
                "component": "ColumnSelector",
                "message": "Select columns for ingestion",
                "data": {"available_fields": field_strs},
            }
        else:
            ui_trigger = {
                "component": "ColumnSelector",
                "message": "Select columns for ingestion",
                "data": {"available_fields": []},
            }
    final_payload = {
        "type": "final",
        "response_text": final_state.get("final_response") or "",
        "requires_human_input": requires_human_input,
        "ui_trigger": ui_trigger,
        "session_id": session_id,
    }
    yield f"data: {json.dumps(final_payload)}\n\n"


@app.post("/api/chat")
async def chat(request: ChatRequest) -> StreamingResponse:
    graph = get_compiled_graph()
    config = {"configurable": {"thread_id": request.session_id}}
    try:
        snapshot = await graph.aget_state(config)
        values = getattr(snapshot, "values", None) or {}
    except Exception:
        values = {}
    input_state = _initial_turn_state(request.message) if not values else {"user_query": request.message}

    return StreamingResponse(
        _sse_graph_stream(session_id=request.session_id, input_state=input_state),
        media_type="text/event-stream",
        headers=_sse_headers(),
    )


@app.post("/api/submit_input")
async def submit_input(request: SubmitRequest) -> StreamingResponse:
    text = _normalize_submit_user_input(request.user_input)
    if not text:
        raise HTTPException(status_code=400, detail="user_input is empty after normalization")
    input_state = {"user_query": text}
    return StreamingResponse(
        _sse_graph_stream(session_id=request.session_id, input_state=input_state),
        media_type="text/event-stream",
        headers=_sse_headers(),
    )


@app.get("/api/templates")
async def get_templates() -> dict[str, Any]:
    """MVP catalog of connector templates aligned with paid-media skills (frontend picker)."""
    return {
        "templates": [
            {"id": "tiktok", "name": "TikTok Ads", "category": "Paid Media", "status": "active"},
            {"id": "meta", "name": "Meta Ads", "category": "Paid Media", "status": "active"},
            {"id": "google-ads", "name": "Google Ads", "category": "Paid Media", "status": "active"},
        ]
    }


@app.get("/api/sessions/{session_id}/history")
async def get_session_history(session_id: str) -> dict[str, Any]:
    """Return checkpointed state for a thread without running the graph."""
    graph = get_compiled_graph()
    config = {"configurable": {"thread_id": session_id}}
    snapshot = None
    try:
        snapshot = await graph.aget_state(config)
        values = getattr(snapshot, "values", None) or {}
    except Exception:
        values = {}

    if not values:
        raise HTTPException(status_code=404, detail="Session not found or empty")

    next_nodes = getattr(snapshot, "next", None) if snapshot is not None else None
    is_paused = bool(next_nodes) if next_nodes is not None else False

    return {
        "session_id": session_id,
        "conversation_context": values.get("conversation_context", []),
        "event_bus": values.get("event_bus", []),
        "artifacts": values.get("artifacts", {}),
        "is_paused": is_paused,
    }
