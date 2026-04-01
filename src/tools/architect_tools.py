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
    #: Optional mutable dict filled by ``propose_bq_schema`` so LangGraph can persist ``table_ddl``.
    artifact_sidecar: dict[str, Any] | None = None


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
        "naming_convention": "raw_{platform} - snake_case, no hyphens.",
        "note": "Mock response: replace with BigQuery API listing when wired.",
    }
    return ToolOutput(
        status="OK",
        code="RAW_DATASETS_LISTED",
        msg=json.dumps(payload),
    )

# Map from APIResearcherFieldMapping.type → BigQuery DDL type
_BQ_TYPE_MAP: dict[str, str] = {
    "FLOAT64":   "FLOAT64",
    "INTEGER":   "INT64",
    "INT64":     "INT64",
    "STRING":    "STRING",
    "TIMESTAMP": "TIMESTAMP",
    "DATE":      "DATE",
    "BOOLEAN":   "BOOL",
    "BOOL":      "BOOL",
}

# System columns always added to every Bronze table
_SYSTEM_COLUMNS: list[dict] = [
    {
        "field_name": "ingest_ts",
        "type": "TIMESTAMP",
        "mode": "REQUIRED",
        "description": "UTC timestamp when this row was loaded into BigQuery.",
    },
    # {
    #     "field_name": "raw_json",
    #     "type": "STRING",
    #     "mode": "NULLABLE",
    #     "description": "Full raw API response row as JSON string — immutable source record.",
    # }, a pensar si va en un futuro!!
]

def _api_field_to_column_name(api_field: str) -> str:
    """Convert an api_field to a safe BigQuery column name.
 
    Examples:
      'metrics.cost_micros'            → 'cost_micros'
      'link_click_default_uas'         → 'link_click_default_uas'
      'DERIVED(clicks/impressions)'    → 'ctr'
      'offsite_conversion.fb_pixel_purchase' → 'offsite_conversion_fb_pixel_purchase'
    """
    if api_field == "NOT_AVAILABLE":
        return "not_available"
    # Strip dot notation prefix (take last segment for simple nested paths)
    name = api_field.split(".")[-1]
    # Replace any non-alphanumeric with underscore
    name = re.sub(r"[^a-zA-Z0-9]", "_", name).lower().strip("_")
    return name


def _propose_bq_schema(selected_fields_json:str, platform:str, project_id:str = "", dataset:str ="",) -> ToolOutput:
    """
    Generate BigQuery DDL and schema preview from user-selected fields.
 
    Args:
        selected_fields_json: JSON array of APIResearcherFieldMapping dicts (only the fields the user selected).
        platform: Platform display name (e.g. 'For Meta Marketing API: Facebook Ads').
        project_id: GCP project id.
        dataset: Target BigQuery dataset name (e.g. 'raw_facebook_ads').
    """
    try:
        selected: list[dict] = json.loads(selected_fields_json)
        if not isinstance(selected, list):
            raise ValueError("Expected a JSON array of field objects.")
    except (json.JSONDecodeError, ValueError) as exc:
        return ToolOutput(
            status="ERR",
            code="INVALID_JSON",
            msg=f"selected_fields_json is not a valid JSON array: {exc}",
        )
 
    project = project_id or "your-gcp-project"
    ds = dataset or f"raw_{platform.lower().split()[0]}"
    platform_slug = platform.lower().split()[0]  # 'meta', 'tiktok', etc.
    table_name = f"{platform_slug}_performance_raw"
    full_table = f"`{project}.{ds}.{table_name}`"

    schema_preview: list[dict] = []
 
    for field in selected:
        api_field = field.get("api_field", "")
        if api_field in ("NOT_AVAILABLE", ""):
            continue
        col_name = _api_field_to_column_name(api_field)
        bq_type = _BQ_TYPE_MAP.get(field.get("type", "STRING"), "STRING")
        mode = "NULLABLE"
        description = field.get("note", "")
        schema_preview.append({
            "field_name": col_name,
            "type": bq_type,
            "mode": mode,
            "description": description,
        })
 
    # Always append system columns at the end
    schema_preview.extend(_SYSTEM_COLUMNS)
 
    # ── Build DDL ─────────────────────────────────────────────
    col_lines = []
    for col in schema_preview:
        col_lines.append(
            f"  {col['field_name']} {col['type']} {col['mode']}"
            f" OPTIONS(description='{col['description']}')"
        )
 
    ddl = (
        f"CREATE TABLE IF NOT EXISTS {full_table}\n"
        f"(\n"
        + ",\n".join(col_lines)
        + "\n)\n"
        "PARTITION BY DATE(ingest_ts)\n"
        f"OPTIONS(\n"
        f"  description='Bronze landing table for {platform} — immutable raw capture.',\n"
        f"  labels=[('layer', 'raw'), ('platform', '{platform_slug}')]\n"
        f");"
    )
 

    select_cols = []
    agg_cols = []
    for col in schema_preview:
        if col["field_name"] in ("campaign_name", "date_start", "stat_time_day",
                                  "segments_date", "record_date", "ingest_ts",
                                  "platform"):
            select_cols.append(col["field_name"])
        elif col["type"] in ("FLOAT64", "INT64") and col["field_name"] not in (
            "ingest_ts", "platform", "raw_json"
        ):
            agg_cols.append(f"SUM({col['field_name']}) AS {col['field_name']}")
 
    if not select_cols:
        select_cols = ["platform", "ingest_ts"]
    select_parts = select_cols + agg_cols[:4]  # cap aggs at 4 for readability
    sql_preview = (
        f"SELECT\n  "
        + ",\n  ".join(select_parts)
        + f"\nFROM\n  {full_table}\n"
        "WHERE\n  DATE(ingest_ts) = CURRENT_DATE()\n"
        f"GROUP BY\n  {', '.join(str(i + 1) for i in range(len(select_cols)))}"
    )
 
    result = {
        "table_name": table_name,
        "dataset_target": ds,
        "full_table": full_table,
        "schema_preview": schema_preview,
        "proposed_ddl": ddl,
        "sql_preview": sql_preview,
        "total_columns": len(schema_preview),
        "user_columns": len(schema_preview) - len(_SYSTEM_COLUMNS),
        "system_columns": len(_SYSTEM_COLUMNS),
        "note": (
            "DDL is a proposal — not yet executed. "
            "Set ddl_approved=True in the LOL only after explicit user confirmation."
        ),
    }
 
    return ToolOutput(
        status="OK",
        code="SCHEMA_PROPOSED",
        msg=json.dumps(result),
    )


_UNSAFE_DDL_PATTERN = re.compile(
    r"\b(DROP\s+(TABLE|SCHEMA|VIEW|FUNCTION|PROCEDURE)|TRUNCATE\s+TABLE|DELETE\s+FROM)\b",
    re.IGNORECASE | re.DOTALL,
)


def _execute_ddl(project_id: str, ddl_statement: str, ddl_approved: bool) -> ToolOutput:
    """
    Execute approved DDL against the configured project (mock).
 
    Args:
        project_id: GCP project id.
        ddl_statement: The DDL to execute.
        ddl_approved: Must be True (explicit user confirmation) or the tool refuses.
    """
    if not ddl_approved:
        return ToolOutput(
            status="ERR",
            code="APPROVAL_REQUIRED",
            msg=(
                "DDL execution requires explicit user approval. "
                "Show the proposed DDL and schema preview to the user and ask: "
                "'Do you want to apply this DDL?' — only proceed after confirmation."
            ),
        )
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
    async def propose_bq_schema(ctx: RunContext[DataArchitectDeps], selected_fields_json: str, platform:str, dataset:str = "") -> dict[str, Any]:
        """
        Propose BigQuery DDL for a Bronze table from a JSON description of the API response shape.
        Pass the sample or schema JSON as a string.
        """
        out = _propose_bq_schema(selected_fields_json, platform, project_id=ctx.deps.project_id, dataset=dataset)
        sidecar = ctx.deps.artifact_sidecar
        if sidecar is not None and out.status == "OK" and out.msg:
            try:
                parsed = json.loads(out.msg)
                if isinstance(parsed, dict):
                    ddl = parsed.get("proposed_ddl")
                    if isinstance(ddl, str) and ddl.strip():
                        sidecar["table_ddl"] = ddl.strip()
            except (json.JSONDecodeError, TypeError):
                pass
        return dump_tool_output(out)

    @agent.tool
    async def execute_ddl(ctx: RunContext[DataArchitectDeps], ddl_statement: str, ddl_approved: bool = False) -> dict[str, Any]:
        """
        Execute approved DDL against the configured project (mock).
        Will reject destructive statements (DROP, TRUNCATE, DELETE FROM).
        """
        out = _execute_ddl(ctx.deps.project_id, ddl_statement, ddl_approved=ddl_approved)
        return dump_tool_output(out)
