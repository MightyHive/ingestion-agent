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
    eb = final_state.get("event_bus") or []
    requires_human_input = bool(eb and eb[-1].get("status") == "WARN")
    ui_trigger = None
    if requires_human_input:
        ui_trigger = {"component": "ColumnSelector", "message": "Select columns"}
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
