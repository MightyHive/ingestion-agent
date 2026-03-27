"""
FastAPI HTTP surface for the LangGraph / PydanticAI platform.

Run from the `src/` directory (so `main` and sibling packages resolve):

  cd src && RUN_MODE=api uvicorn api:app --reload --host 0.0.0.0 --port 8000

After `cd src`, use `api:app` only — not `src.api:app` (that needs the repo root on PYTHONPATH with `src` as a package).

`RUN_MODE=api` ensures coordinator tools emit structured payloads instead of blocking on stdin.
Importing this module loads `main.compiled_graph` but does not start the CLI.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from main import compiled_graph

app = FastAPI(title="Ingestion Agent API", version="1.0.0")

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


class ChatResponse(BaseModel):
    session_id: str
    response_text: str
    requires_human_input: bool


def _initial_turn_state(user_query: str) -> dict:
    """Match CLI first-turn keys so MemorySaver threads start with a valid AgentGraphState."""
    return {
        "user_query": user_query,
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


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    config = {"configurable": {"thread_id": request.session_id}}
    try:
        snapshot = await compiled_graph.aget_state(config)
        values = getattr(snapshot, "values", None) or {}
    except Exception:
        # New or unknown thread: some checkpointer versions error on first read; treat as empty.
        values = {}
    input_state = _initial_turn_state(request.message) if not values else {"user_query": request.message}

    try:
        result_state = await compiled_graph.ainvoke(input_state, config)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    if not isinstance(result_state, dict):
        raise HTTPException(status_code=500, detail="Unexpected graph result type")

    coordinator = result_state.get("coordinator_result") or {}
    requires_human_input = coordinator.get("status") == "WARN"
    response_text = result_state.get("final_response") or ""

    return ChatResponse(
        session_id=request.session_id,
        response_text=response_text,
        requires_human_input=requires_human_input,
    )
