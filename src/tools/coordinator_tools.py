"""
Coordinator agent tools (project manager / router).

Dual-layer pattern:
  - Top: pure Python returning ToolOutput (testable).
  - Bottom: PydanticAI tools; call register_coordinator_tools(agent).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pydantic_ai import RunContext

from models.tool_outputs import ToolOutput, dump_tool_output

if TYPE_CHECKING:
    from pydantic_ai import Agent


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------


@dataclass
class CoordinatorDeps:
    """Runtime dependencies for coordinator tools."""

    session_id: str


# ---------------------------------------------------------------------------
# Pure Python (mock implementations)
# ---------------------------------------------------------------------------


def _check_template_catalog(channel_name: str, session_id: str = "") -> ToolOutput:
    """
    Mock template catalog lookup for a data source channel.
    YouTube and Facebook return a fixed template version; anything else does not.
    """
    channel = (channel_name or "").strip().lower()
    if channel in ("youtube", "facebook"):
        body = {
            "session_id": session_id,
            "channel": channel,
            "result": "Template V1.2 found",
            "template_id": "ingestion_v1_2",
            "track": "fast_track",
        }
        return ToolOutput(
            status="OK",
            code="TEMPLATE_FOUND",
            msg=json.dumps(body),
        )
    body = {
        "session_id": session_id,
        "channel": channel or "(empty)",
        "result": "No template found",
        "track": "ai_factory",
    }
    return ToolOutput(
        status="OK",
        code="NO_TEMPLATE",
        msg=json.dumps(body),
    )

def _request_human_input(prompt_message: str, session_id: str = "") -> ToolOutput:
    """Simulate pausing the flow until the UI collects user input via terminal."""
    # EL INPUT DETIENE LA CONSOLA Y TE DEJA ESCRIBIR A TI
    print(f"\n⏸️  [SISTEMA PAUSADO - ESPERANDO AL HUMANO]")
    respuesta = input(f"👤 {prompt_message}\n> ")
    
    return ToolOutput(
        status="WARN", # WARN porque el flujo se interrumpió
        msg=f"El usuario respondió: {respuesta}"
    )


def _update_ui_status(status_message: str, session_id: str = "") -> ToolOutput:
    """Simulate pushing a real-time loading/status line to the frontend via terminal."""
    # ESTE PRINT ES PARA QUE TÚ LO VEAS EN LA CONSOLA MIENTRAS PRUEBAS
    print(f"\n🖥️  [UI MOCK - Cargando...]: {status_message}") 
    
    return ToolOutput(status="OK", msg="UI updated successfully")

'''
def _request_human_input(prompt_message: str, session_id: str = "") -> ToolOutput:
    """Simulate pausing the flow until the UI collects user input."""
    text = (prompt_message or "").strip() or "Additional input required."
    body = {
        "session_id": session_id,
        "paused": True,
        "ui_prompt": text,
        "session_note": "Coordinator requested human input via UI (mock).",
    }
    return ToolOutput(
        status="WARN",
        code="HUMAN_INPUT_REQUIRED",
        msg=json.dumps(body),
    )


def _update_ui_status(status_message: str, session_id: str = "") -> ToolOutput:
    """Simulate pushing a real-time loading/status line to the frontend."""
    text = (status_message or "").strip() or "Working…"
    body = {
        "session_id": session_id,
        "ui_status": text,
        "delivered": True,
        "mock": True,
    }
    return ToolOutput(
        status="OK",
        code="UI_STATUS_UPDATED",
        msg=json.dumps(body),
    )
'''

# ---------------------------------------------------------------------------
# PydanticAI registration
# ---------------------------------------------------------------------------


def register_coordinator_tools(agent: Agent[Any, Any]) -> None:
    """Attach coordinator tools to a PydanticAI Agent."""

    @agent.tool
    async def check_template_catalog(
        ctx: RunContext[CoordinatorDeps],
        channel_name: str,
    ) -> dict[str, Any]:
        """
        Look up whether a pre-built ingestion template exists for the given channel
        (e.g. youtube, facebook). Call this FIRST before routing.
        """
        out = _check_template_catalog(channel_name, session_id=ctx.deps.session_id)
        return dump_tool_output(out)

    @agent.tool
    async def request_human_input(
        ctx: RunContext[CoordinatorDeps],
        prompt_message: str,
    ) -> dict[str, Any]:
        """
        Signal that the workflow should pause and ask the user (via UI) for input,
        e.g. API token, OAuth consent, or column selection.
        """
        out = _request_human_input(prompt_message, session_id=ctx.deps.session_id)
        return dump_tool_output(out)

    @agent.tool
    async def update_ui_status(
        ctx: RunContext[CoordinatorDeps],
        status_message: str,
    ) -> dict[str, Any]:
        """Send a short status line to the frontend loading indicator (mock)."""
        out = _update_ui_status(status_message, session_id=ctx.deps.session_id)
        return dump_tool_output(out)
