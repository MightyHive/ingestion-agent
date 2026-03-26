"""
Data Architect agent tools.

Dual-layer pattern:
  - Top: pure Python functions returning ToolOutput (testable, no framework).
  - Bottom: PydanticAI tool wrappers (RunContext + deps); call register_architect_tools(agent).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pydantic_ai import RunContext

from models.tool_outputs import ToolOutput, dump_tool_output

if TYPE_CHECKING:
    from pydantic_ai import Agent


# ---------------------------------------------------------------------------
# Dependencies (injected via RunContext.deps)
# ---------------------------------------------------------------------------


@dataclass
class DataArchitectDeps:
    """Runtime dependencies for Data Architect tools."""

    project_id: str


# ---------------------------------------------------------------------------
# Pure Python (mock implementations)
# ---------------------------------------------------------------------------

_MOCK_RAW_DATASETS = (
    "raw_youtube",
    "raw_tiktok",
    "raw_meta_ads",
    "raw_shopify",
)


def _list_raw_datasets(project_id: str) -> ToolOutput:
    """Return a mock inventory of Raw/Bronze-layer datasets for the project."""
    payload = {
        "project_id": project_id,
        "datasets": list(_MOCK_RAW_DATASETS),
        "layer": "raw_bronze",
        "note": "Mock response: replace with BigQuery API listing when wired.",
    }
    return ToolOutput(
        status="OK",
        code="RAW_DATASETS_LISTED",
        msg=json.dumps(payload),
    )


def _propose_bq_schema(api_structure_json: str, project_id: str = "") -> ToolOutput:
    """
    Simulate designing a BigQuery schema from an API payload shape (JSON string).
    Does not call BigQuery; returns illustrative DDL in the message body.
    """
    try:
        parsed = json.loads(api_structure_json) if api_structure_json.strip() else {}
    except json.JSONDecodeError as exc:
        return ToolOutput(
            status="ERR",
            code="INVALID_JSON",
            msg=f"api_structure_json is not valid JSON: {exc}",
        )

    project = project_id or "your-gcp-project"
    # Mock DDL: defensive typing — timestamps as TIMESTAMP, opaque blobs as STRING JSON
    mock_ddl = (
        "-- Mock Bronze table: land API payload with ingestion metadata\n"
        f"CREATE TABLE IF NOT EXISTS `{project}.raw_example.api_events` (\n"
        "  ingest_id STRING NOT NULL OPTIONS(description='UUID assigned at ingest'),\n"
        "  ingest_ts TIMESTAMP NOT NULL OPTIONS(description='Load time in UTC'),\n"
        "  source_system STRING NOT NULL,\n"
        "  payload_json STRING NOT NULL OPTIONS(description='Raw API body as JSON string'),\n"
        "  api_timestamp TIMESTAMP OPTIONS(description='Event time from API when parseable')\n"
        ")\n"
        "PARTITION BY DATE(ingest_ts)\n"
        "OPTIONS(description='Bronze landing — immutable raw capture');"
    )
    meta = {
        "input_keys": list(parsed.keys()) if isinstance(parsed, dict) else [],
        "proposed_ddl": mock_ddl,
        "typing_notes": (
            "Use TIMESTAMP for true datetimes; use STRING for unstable or multi-format dates until parsed. "
            "Never infer NUMERIC from free-text fields."
        ),
    }
    return ToolOutput(
        status="OK",
        code="SCHEMA_PROPOSED",
        msg=json.dumps(meta),
    )


_UNSAFE_DDL_PATTERN = re.compile(
    r"\b(DROP\s+(TABLE|SCHEMA|VIEW|FUNCTION|PROCEDURE)|TRUNCATE\s+TABLE|DELETE\s+FROM)\b",
    re.IGNORECASE | re.DOTALL,
)


def _execute_ddl(project_id: str, ddl_statement: str) -> ToolOutput:
    """
    Simulate executing DDL in BigQuery. Refuses obviously destructive statements.
    """
    text = (ddl_statement or "").strip()
    if not text:
        return ToolOutput(
            status="ERR",
            code="EMPTY_DDL",
            msg="ddl_statement is empty.",
        )
    if _UNSAFE_DDL_PATTERN.search(text):
        return ToolOutput(
            status="ERR",
            code="UNSAFE_DDL_REJECTED",
            msg=(
                "Refused: destructive or data-mutating patterns (DROP, TRUNCATE, DELETE FROM) "
                "are not allowed from this agent in mock or production guard mode."
            ),
        )
    return ToolOutput(
        status="OK",
        code="DDL_EXECUTED_MOCK",
        msg=json.dumps(
            {
                "project_id": project_id,
                "executed": False,
                "simulation": True,
                "statement_preview": text[:500] + ("..." if len(text) > 500 else ""),
            }
        ),
    )


# ---------------------------------------------------------------------------
# PydanticAI tools (register on the Agent instance)
# ---------------------------------------------------------------------------


def register_architect_tools(agent: Agent[Any, Any]) -> None:
    """Attach Data Architect tools to a PydanticAI Agent (mutates agent in place)."""

    @agent.tool
    async def list_raw_datasets(ctx: RunContext[DataArchitectDeps]) -> dict[str, Any]:
        """List Raw/Bronze datasets available (mock) for deps.project_id."""
        out = _list_raw_datasets(ctx.deps.project_id)
        return dump_tool_output(out)

    @agent.tool
    async def propose_bq_schema(ctx: RunContext[DataArchitectDeps], api_structure_json: str) -> dict[str, Any]:
        """
        Propose BigQuery DDL for a Bronze table from a JSON description of the API response shape.
        Pass the sample or schema JSON as a string.
        """
        out = _propose_bq_schema(api_structure_json, project_id=ctx.deps.project_id)
        return dump_tool_output(out)

    @agent.tool
    async def execute_ddl(ctx: RunContext[DataArchitectDeps], ddl_statement: str) -> dict[str, Any]:
        """
        Execute approved DDL against the configured project (mock).
        Will reject destructive statements (DROP, TRUNCATE, DELETE FROM).
        """
        out = _execute_ddl(ctx.deps.project_id, ddl_statement)
        return dump_tool_output(out)
