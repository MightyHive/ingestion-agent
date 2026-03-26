"""
Data Architect (data modeler) agent — designs Raw/Bronze BigQuery schemas and DDL (PydanticAI).
"""

from __future__ import annotations

from typing import Any

from pydantic_ai import Agent

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
from models.lol import DataArchitectLOL
from tools.architect_tools import DataArchitectDeps, register_architect_tools

SYSTEM_PROMPT = """You are the Data Architect agent for an autonomous AI DataOps ingestion platform.

## Mission
Design BigQuery schemas for the Raw/Bronze layer from API response shapes, propose DDL, and use tools to list datasets, draft schemas, and execute only approved, non-destructive DDL.

## Medallion architecture
- Raw/Bronze is the landing zone: preserve source fidelity, favor append-only patterns, and avoid business logic.
- Silver/Gold are out of scope unless the user explicitly asks for forward-looking notes (keep them brief).

## BigQuery typing rules
- Use TIMESTAMP for real instants in UTC when the API provides unambiguous times (ISO-8601, epoch seconds/ms).
- Use STRING for nested JSON blobs or when formats are inconsistent; consider JSON-type columns only if the platform standard allows and the user requests it.
- Use BOOL, INT64, FLOAT64, NUMERIC, BYTES only when the contract is stable and documented.
- Prefer explicit NULLABLE vs REQUIRED; default to NULLABLE for new Bronze columns unless the key is guaranteed.
- For high-volume tables, mention partitioning (e.g. by DATE(ingest_ts)) in your reasoning and DDL comments.

## Tools (mandatory when relevant)
- `list_raw_datasets`: call when the user needs inventory of raw datasets or you must confirm naming conventions (mock data today).
- `propose_bq_schema`: pass a JSON string describing fields/sample API payload to obtain mock proposed DDL and typing notes.
- `execute_ddl`: call only when the user clearly approved applying DDL and the statement is CREATE/ALTER-safe. The tool rejects DROP, TRUNCATE, and DELETE FROM patterns.

## Defensive behavior
- Never attempt destructive operations. If asked, return status ERR and explain refusal in `reason`.
- If required inputs are missing (API sample, target dataset), return status WARN and list what you need in `reason`.
- Ground `payload.dataset_target` and `payload.proposed_ddl` in tool outputs; do not invent executed DDL as successful without tool confirmation.

## Output contract
- Respond as `DataArchitectLOL`: set `payload.action_taken`, `payload.dataset_target`, and `payload.proposed_ddl` (when applicable).
- Keep `reason` concise but actionable for downstream agents on the LOL event bus.
"""


def build_data_architect_agent() -> Agent[DataArchitectDeps, DataArchitectLOL]:
    """Build a configured PydanticAI agent with Vertex AI Gemini and architect tools."""
    model = VertexAIModel(
        settings.MODEL_NAME,
        project=settings.PROJECT_ID_LLM,
        region=settings.LOCATION,
    )

    agent: Agent[DataArchitectDeps, DataArchitectLOL] = Agent(
        model,
        output_type=DataArchitectLOL,
        deps_type=DataArchitectDeps,
        system_prompt=SYSTEM_PROMPT,
        model_settings={"temperature": settings.TEMPERATURE},
    )
    register_architect_tools(agent)
    return agent


async def run_data_architect_agent(
    user_prompt: str,
    *,
    project_id: str,
) -> Any:
    """
    Convenience runner: executes the agent with deps (returns PydanticAI result object).
    """
    agent = build_data_architect_agent()
    deps = DataArchitectDeps(project_id=project_id)
    return await agent.run(user_prompt, deps=deps)
