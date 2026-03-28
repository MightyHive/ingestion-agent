from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


# Extend with coordinator / synthesizer / other specialists as they are added.
AGENT_NAMES = Literal["data_architect", "software_engineer", "api_researcher"]


# ============================================================
# BASE LOL — Universal inter-agent contract
# ============================================================

class BaseLOL(BaseModel):
    status: Literal["OK", "WARN", "ERR"] = Field(
        description="Operation status: OK (success), WARN (partial success), ERR (failure)"
    )
    reason: str = Field(
        description=(
            "Agent rationale. If status is OK/WARN, explain the logic; if ERR, state the failure cause."
        )
    )
    usage: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Token usage metrics (prompt_tokens, completion_tokens, total_tokens)",
    )


# ============================================================
# COORDINATOR — Plans parallel dispatch
# ============================================================

class TaskStep(BaseModel):
    target_agent: AGENT_NAMES = Field(
        description="Exact name of the agent that will run this task"
    )
    instruction: str = Field(
        description=(
            "Self-contained instruction for the target agent. "
            "Must include all required context because specialists do not read full chat history."
        )
    )


class CoordinatorPayload(BaseModel):
    tasks: List[TaskStep] = Field(
        description=(
            "Independent tasks for the current round. "
            "All tasks should be runnable in parallel unless explicitly serialized in one instruction."
        )
    )


class CoordinatorLOL(BaseLOL):
    id: Literal["coordinator"] = Field(
        default="coordinator",
        description="Fixed identifier for the coordinator agent.",
    )
    payload: CoordinatorPayload = Field(
        description="Parallel dispatch plan with specialist tasks."
    )


# ============================================================
# SYNTHESIZER — Final user-facing answer
# ============================================================

class SynthesizerPayload(BaseModel):
    file_path: Optional[str] = Field(
        default=None,
        description="Path of generated Markdown file when user requested export/save.",
    )
    summary: str = Field(
        description=(
            "Unified final answer from specialist LOL reports on the event bus. "
            "Never mention internal tools."
        )
    )


class SynthesizerLOL(BaseLOL):
    id: Literal["synthesizer"] = Field(
        default="synthesizer",
        description="Fixed identifier for the synthesizer agent.",
    )
    payload: SynthesizerPayload = Field(
        description="Synthesis result: final answer and optional generated file path."
    )


class GeneratedFile(BaseModel):
    path: str = Field(description="Generated or updated file path.")
    description: Optional[str] = Field(
        default=None,
        description="Why this file was generated/changed.",
    )

# ============================================================
# SOFTWARE ENGINEER — Connector code engineering
# ============================================================

class SoftwareEngineerPayload(BaseModel):
    action: Literal[
        "list_connectors",
        "find_connector",
        "read_connector",
        "validate_connector_code",
        "save_connector",
        "overwrite_connector",
        "get_gold_standard_code",
        "modify_payload_and_columns",
        "write_cf_code",
        "identify_environment_variables",
        "error",
    ] = Field(
        description=(
            "Which tool outcome this turn should be filed under: use the **last** registered tool "
            "that was decisive for the user-facing result. When authoring connector code, the turn "
            "should normally end with `save_connector` (new file) or `overwrite_connector` (replace after user consent)—"
            "not `write_cf_code`. Matches `@agent.tool` names; use `error` only when no successful tool path applies."
        )
    )
    connector_name: Optional[str] = Field(
        default=None, description="Target connector normalized name.")
    source: Optional[str] = Field(
        default=None, description="Connector source namespace.")
    file_path: Optional[str] = Field(
        default=None,
        description=(
            "Absolute path under the connector library after a successful `save_connector` or `overwrite_connector` result. "
            "When status is OK/WARN and this turn authored or finalized connector Python, must be set from that tool output."
        ),
    )
    validation: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Structured output from `validate_connector_code` (mirror tool JSON; do not invent fields).",
    )
    data: Optional[Dict[str, Any]] = Field(
        default=None, description="Auxiliary structured operation data.")
    generated_files: List[GeneratedFile] = Field(
        default_factory=list,
        description=(
            "Only paths confirmed by tools or present on disk (e.g. save_connector / overwrite_connector output). "
            "Do not list files that were not written."
        ),
    )
    env_vars_required: List[str] = Field(
        default_factory=list,
        description=(
            "Names of environment variables the connector reads (e.g. via os.getenv). "
            "Values are configured by DevOps / runtime / another agent—never embedded here."
        ),
    )
    required_secrets: List[str] = Field(
        default_factory=list,
        description=(
            "Names of secrets or high-sensitivity env vars (subset or alias of env_vars_required). "
            "This agent only lists names for downstream Secret Manager or coordinator handoff."
        ),
    )
    api_dependencies: List[str] = Field(
        default_factory=list,
        description="External APIs/services consumed by the connector.",
    )
    missing_inputs: List[str] = Field(
        default_factory=list,
        description=(
            "Inputs missing from user context to proceed safely. If a connector file already exists and the user "
            "has not authorized replace, include an explicit item such as confirmation to overwrite that path."
        ),
    )
    review_requested: bool = Field(
        default=False,
        description=(
            "True when this turn successfully validated connector `fetch` code intended for use (new or updated). "
            "Read-only turns without validated new code: false. Downstream review is always part of the pipeline; "
            "this flag marks that this turn produced reviewable connector work."
        ),
    )
    review_reason: Optional[str] = Field(
        default=None,
        description="One line on why review matters for this change (e.g. validated new connector).",
    )
    review_notes: Optional[str] = Field(
        default=None,
        description=(
            "Assumptions and facts for the next agent: API behavior, auth/env var names, pagination, limitations."
        ),
    )
    summary: str = Field(
        description=(
            "Concise narrative for the next agent (e.g. synthesizer). Do not mention internal tool names or call syntax; "
            "put machine-readable detail in structured fields (`review_notes`, `env_vars_required`, paths, etc.)."
        )
    )


class SoftwareEngineerLOL(BaseLOL):
    id: Literal["software_engineer"] = Field(
        default="software_engineer",
        description="Fixed identifier for software engineer component (must match graph node and target_agent).",
    )
    payload: SoftwareEngineerPayload = Field(
        description="Software engineer connector-library operation result."
    )

# ============================================================
# API RESEARCHER — Technical discovery and documentation research
# ============================================================
class APIResearcherFieldMapping(BaseModel):
    """Maps a canonical metric name to its exact API field and BigQuery type."""
    name: str = Field(
        description="Canonical field name used across all platforms (e.g. 'impressions', 'spend')"
    )
    type: str = Field(
        description="BigQuery column type: FLOAT64, INTEGER, STRING, DATE, TIMESTAMP, BOOLEAN"
    )
    api_field: str = Field(
        description=(
            "Exact field name in the API response. "
            "Use dot notation for nested fields (e.g. 'metrics.cost_micros'). "
            "Set to 'NOT_AVAILABLE' if the platform does not expose this metric. "
            "Set to 'DERIVED(formula)' if the field must be calculated (e.g. 'DERIVED(clicks/impressions)')."
        )
    )
    note: Optional[str] = Field(
        default=None,
        description=(
            "Type gotchas, cast requirements, or normalization instructions for this field. "
            "Examples: 'API returns STRING — cast to numeric', "
            "'DIVIDE BY 1,000,000 — never store raw micros', "
            "'PERCENTAGE format (5.2 = 5.2%) — normalize before cross-platform comparisons'."
        )
    )
 
 
class APIResearcherAuthInfo(BaseModel):
    method: str = Field(
        description="Authentication method, e.g. 'OAuth 2.0', 'Service Account via google-ads.yaml'"
    )
    required_credentials: List[str] = Field(
        description="Credential names the pipeline will need (e.g. ['access_token', 'advertiser_id'])"
    )
    token_type: str = Field(
        description="Token type and lifecycle, e.g. 'System User Token (non-expiring)'"
    )
    expiry: str = Field(
        description="Token expiry, e.g. 'non-expiring', '1 hour (refresh_token long-lived)'"
    )
 
 
class FreshnessCheck(BaseModel):
    checked: bool = Field(
        description="True if live documentation was fetched and compared against stored data"
    )
    changes_detected: bool = Field(
        description="True if the live docs differ meaningfully from stored reference data"
    )
    delta: Optional[str] = Field(
        default=None,
        description="Short description of what changed (new API version, deprecated fields, auth changes). Null if no changes."
    )
 
 
class APIResearcherPayload(BaseModel):
    action: Literal[
        "freshness_check",       # known platform — checked live docs vs stored
        "full_investigation",    # unknown platform — searched web + read docs
        "schema_analysis",       # analyzed JSON sample to infer field types
        "error",                 # investigation failed, see BaseLOL.reason
    ] = Field(
        description=(
            "Which investigation path was taken this turn. "
            "Use 'freshness_check' for known platforms even if no changes were found. "
            "Use 'error' only when no successful investigation path completed."
        )
    )
    platform: str = Field(
        description="Full display name of the investigated platform (e.g. 'Meta Marketing API')"
    )
    auth: APIResearcherAuthInfo = Field(
        description="Authentication requirements for the reporting endpoint"
    )
    reporting_endpoint: str = Field(
        description=(
            "Full URL or SDK method of the main read-only reporting/analytics endpoint. "
            "For Google Ads: describe the SDK method, not a REST URL."
        )
    )
    available_fields: List[APIResearcherFieldMapping] = Field(
        description=(
            "Exactly 9 field mappings for the MVP metrics: "
            "impressions, clicks, spend, ctr, conversions, video_views, reach, campaign_name, date. "
            "Always include all 9. Set api_field='NOT_AVAILABLE' if the platform doesn't expose it."
        )
    )
    pagination: str = Field(
        description="Pagination strategy, e.g. 'cursor-based (paging.after)' or 'page-based (page >= total_page)'"
    )
    rate_limit: str = Field(
        description="Key rate limit constraints relevant to a daily ingestion job"
    )
    freshness_check: FreshnessCheck = Field(
        description="Whether live docs were checked and if anything changed vs stored reference"
    )
    missing_inputs: List[str] = Field(
        default_factory=list,
        description=(
            "Inputs that were unavailable during investigation and may affect downstream accuracy. "
            "Examples: 'No JSON response sample available — field types inferred from docs only', "
            "'Documentation behind login wall — could not verify freshness'."
        )
    )
    summary: str = Field(
        description=(
            "Concise narrative for the next agent (Data Architect). "
            "Include: platform investigated, action taken, any gotchas the DDL must account for, "
            "and whether freshness check found changes. "
            "Do not mention internal tool names."
        )
    )
 

class APIResearcherLOL(BaseLOL):
    id: Literal["api_researcher"] = Field(
        default="api_researcher",
        description="Fixed identifier for the API Researcher agent",
    )
    payload: APIResearcherPayload = Field(
        description=(
            "Investigation result: auth info, reporting endpoint, field mappings (with notes), "
            "pagination, rate limits, and freshness check. "
            "Handed off to the Data Architect agent to generate BigQuery DDL."
        )
    )


# ============================================================
# DATA ARCHITECT — BigQuery Raw/Bronze modeling and DDL
# ============================================================

class DataArchitectPayload(BaseModel):
    proposed_ddl: Optional[str] = Field(
        default=None,
        description=(
            "Full CREATE TABLE / CREATE SCHEMA DDL proposed for the Raw/Bronze layer, "
            "using BigQuery SQL. Omit or null if the turn only listed datasets or validated inputs without drafting DDL."
        ),
    )
    dataset_target: str = Field(
        description=(
            "Target BigQuery dataset for raw ingestion (e.g. raw_social, raw_youtube). "
            "Must align with Medallion naming: raw/bronze landing zone, not curated silver/gold."
        ),
    )
    action_taken: str = Field(
        description=(
            "Short machine-readable label for what this agent did in this turn, e.g. "
            "'listed_raw_datasets', 'proposed_schema', 'executed_ddl', 'rejected_unsafe_ddl', 'clarification_needed'."
        ),
    )


class DataArchitectLOL(BaseLOL):
    id: Literal["data_architect"] = Field(
        default="data_architect",
        description="Fixed identifier for the Data Architect (data modeler) agent",
    )
    payload: DataArchitectPayload = Field(
        description=(
            "Structured outcome: which dataset was targeted, what action was taken, "
            "and optional DDL text for the event bus / synthesizer."
        ),
    )


