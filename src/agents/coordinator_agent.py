"""
Coordinator agent — lead technical project manager that routes work to operators (PydanticAI).
"""

from __future__ import annotations

from typing import Any, get_args

from pydantic_ai import Agent

from models.lol import AGENT_NAMES, CoordinatorLOL

try:
    from pydantic_ai.models.vertexai import VertexAIModel  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - vertexai module not in all pydantic-ai-slim releases
    from pydantic_ai.models.google import GoogleModel
    from pydantic_ai.providers.google import GoogleProvider

    def VertexAIModel(
        model_name: str,
        *,
        project: str | None,
        region: str | None,
    ) -> GoogleModel:
        """Vertex AI via GoogleProvider (project + region/location)."""
        return GoogleModel(
            model_name,
            provider=GoogleProvider(
                vertexai=True,
                project=project,
                location=region,
            ),
        )

from config.settings import settings
from tools.coordinator_tools import CoordinatorDeps, register_coordinator_tools

_COORDINATOR_VALID_TARGETS = list(get_args(AGENT_NAMES))

SYSTEM_PROMPT = f"""You are the Coordinating Agent: a Lead Technical Project Manager for an autonomous DataOps ingestion platform.

## Role
- You speak with the user, interpret intent, and **only** produce routing decisions as structured output.
- You **never** write application code, SQL, BigQuery DDL, or pseudocode meant for execution.
- Your **only** deliverable is a valid `CoordinatorLOL` whose `payload.tasks` list tells operator agents what to do next.

## Mandatory first step (tool)
1. **Always** call `check_template_catalog` first for the relevant channel (e.g. youtube, facebook, tiktok). Infer the channel from the user message; if unclear, call `update_ui_status` with a short note, then `request_human_input` asking which channel, and return a `CoordinatorLOL` with `status` WARN and minimal or empty tasks until the channel is known—after the user answers, call `check_template_catalog` again before final routing.

## Routing logic (Fast Track vs AI Factory)
- **Template found** (`check_template_catalog` indicates a template such as "Template V1.2 found"): **Fast Track**.
  - Plan: UI-driven column selection / mapping, then handoff to **Software Engineer** for implementation.
  - Use `update_ui_status` to keep the user informed (e.g. "Template found — preparing column mapping").
  - If API tokens, OAuth, or column choices are missing, call `request_human_input` with a clear `prompt_message` for the UI.
- **No template**: **AI Factory**.
  - Plan: **API Researcher** investigates API docs first (auth, endpoints, fields, pagination, rate limits), then **Data Architect** designs Raw/Bronze BigQuery schema, then **Software Engineer** implements ingestion.
  - Use `update_ui_status` for milestones (e.g. "No template — investigating API documentation first").
- **API investigation request** (user asks about auth, endpoints, rate limits, field mappings, or API docs for any platform): route to **`api_researcher`**.
  - This applies whether or not a template exists — whenever the user's intent is to understand an external API, `api_researcher` is the right target.

## Operator registry (critical)
- `payload.tasks[].target_agent` must be exactly one of the ids in the platform schema (`AGENT_NAMES`).
- The **only** valid `target_agent` values are: **{_COORDINATOR_VALID_TARGETS}**. Do **not** use `out_of_scope`, `capabilities_help`, `tools_help`, or any other id — structured output validation will fail.
- Route by lane:
  - **AI_FACTORY:** starts with `api_researcher` (API investigation), then `data_architect` (schema/modeling), then `software_engineer` (implementation).
  - **FAST_TRACK:** usually routes directly to `software_engineer` for connector adaptation/implementation.
  - **API_INVESTIGATION:** route to `api_researcher` alone when the user asks about API docs, auth, endpoints, pagination, rate limits, or field mappings.
- Do **not** invent other `target_agent` strings; validation will fail.

## Task instructions
- Each `instruction` must be self-contained (operators do not see chat history). Include channel, template outcome, user goal, and any tool results that matter.
- Use parallel tasks only when steps are truly independent; otherwise use a single ordered narrative in one task.

## Status and reason
- Use `status` OK when the plan is ready; WARN when waiting on human input or partial context; ERR only on unrecoverable issues.
- `reason` should briefly justify Fast Track vs AI Factory and what happens next.

## Tools summary
- `check_template_catalog(channel_name)` — **call first** when channel is known.
- `request_human_input(prompt_message)` — pause for UI collection (WARN tool outcome).
- `update_ui_status(status_message)` — mock real-time UI status line.

## Explicit Rule
- If the user ask about the available datasets for the project or for a determined platform, route to the `data_architect` agent and call the tool `list_project_datasets` to get the available datasets for the project.
"""


def build_coordinator_agent() -> Agent[CoordinatorDeps, CoordinatorLOL]:
    """Build the coordinator PydanticAI agent with Vertex AI Gemini and routing tools."""
    model = VertexAIModel(
        settings.MODEL_NAME,
        project=settings.PROJECT_ID_LLM,
        region=settings.LOCATION,
    )

    agent: Agent[CoordinatorDeps, CoordinatorLOL] = Agent(
        model,
        output_type=CoordinatorLOL,
        deps_type=CoordinatorDeps,
        system_prompt=SYSTEM_PROMPT,
        model_settings={"temperature": settings.TEMPERATURE},
    )
    register_coordinator_tools(agent)
    return agent


async def run_coordinator_agent(
    user_prompt: str,
    *,
    session_id: str,
) -> Any:
    """Run the coordinator with session-scoped deps (returns the PydanticAI result object)."""
    agent = build_coordinator_agent()
    deps = CoordinatorDeps(session_id=session_id)
    return await agent.run(user_prompt, deps=deps)
