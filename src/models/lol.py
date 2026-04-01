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


CanonicalMetric = Literal[
    "impressions",
    "clicks",
    "spend",
    "ctr",
    "conversions",
    "video_views",
    "reach",
    "campaign_name",
    "date",
]
 
# Grouping aligned with the UI tabs in the field-selection mockup.
FieldCategory = Literal["structural", "performance", "conversion", "other"]

class APIResearcherFieldMapping(BaseModel):
    "Full desriptor for a single API field. Used to populate the field-selection catalog exposed to users and consumed by the Software Engineer."
    api_field: str = Field(
        description= ("Exact field name in the API response."
        "Use dot notation for nested fields (e.g. metrics.cost_micros)."
        "Set to 'NOT_AVAILABLE' if the platform does not expose this metric"
        "Set to 'DERIVED' if the field must be calculated, e.g. clicks/impressions"
    ))
    label: str = Field(description="Human-readable name exactly as it appears in the platform UI or API documentation.")
    type: str = Field(
        description="BigQuery column type: FLOAT64, INTEGER, STRING, DATE, TIMESTAMP, BOOLEAN"
    )
    note: Optional[str] = Field(
        default=None,
        description=(
            "Type gotchas, cast requirements, or normalization instructions. "
            "Examples: 'API returns STRING — cast to numeric', "
            "'DIVIDE BY 1,000,000 — never store raw micros', "
            "'PERCENTAGE format (5.2 = 5.2%) — normalize before cross-platform comparisons'."
        ),
    )
    category: FieldCategory = Field(
        description=(
            "Field grouping for the UI selector tabs: "
            "'structural' (ids, names, statuses), "
            "'performance' (impressions, clicks, spend, video metrics), "
            "'conversion' (any conversion event or value metric), "
            "'other' (timestamps, currencies, platform-specific extras)."
        )
    )
    canonical_match: Optional[CanonicalMetric] = Field(
        default=None,
        description=(
            "Which of the 9 canonical MVP metrics this field best maps to. "
            "Null if the field has no canonical equivalent. "
            "Only one field per platform should claim each canonical key; "
            "flag any ambiguity in `semantics`."
        ),
    )
    semantics: Optional[str] = Field(
        default=None,
        description=(
            "Short free-text clarification of what this field actually counts — "
            "required when the field is polysemous or platform-specific. "
            "Examples: "
            "'click-through conversions only, using account-default attribution window', "
            "'total spend including fees — not net media cost', "
            "'view-through 1-day window, not included in default conversions total'. "
            "Always populate for any field whose canonical_match is conversions."
        ),
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
 
    # ── Endpoints ─────────────────────────────────────────────────────────────
    reporting_endpoint: str = Field(
        description=(
            "Primary read-only reporting endpoint: full URL or SDK method. "
            "For Google Ads: describe the SDK method, not a REST URL. "
            "When multiple endpoints exist, this is the main performance/insights endpoint")
    )
 
    # ── Field catalog ─────────────────────────────────────────────────────────
    available_fields: List[APIResearcherFieldMapping] = Field(
        description=(
            "Complete catalog of fields available from this platform's reporting endpoints. "
            "Include ALL relevant fields — not just the 9 canonical metrics. "
            "Typical platforms expose 20-50+ fields; include everything that a data pipeline "
            "might reasonably ingest (performance metrics, structural dimensions, video quartiles, "
            "conversion breakdowns, cost sub-types, etc.). "
            "The 9 canonical metrics (impressions, clicks, spend, ctr, conversions, video_views, "
            "reach, campaign_name, date) MUST be present if the platform exposes them, and their "
            "entries must set `canonical_match` appropriately. "
            "Non-canonical fields must still set `category` and `label`. "
            "fields grouped by category."
        )
    )
    total_fields_discovered: int = Field(
        description="Total de campos en available_fields."
    )
    canonical_fields_found: int = Field(
        description="Cuántos de los 9 canónicos tienen canonical_match no nulo."
    )
    discovery_method: Literal["docs_only", "json_schema", "docs_and_schema"] = Field(
        description=(
            "'docs_only' — field types inferred from documentation only; "
            "'json_schema' — field types inferred from a live JSON response sample; "
            "'docs_and_schema' — both sources used and cross-validated."
        )
    )
     # ── Infra ──────────────────────────────────────────────────────────────────
    pagination: str = Field(
        description=(
            "Pagination strategy, e.g. 'cursor-based (paging.after)' or "
            "'page-based (page >= total_page)'"
        )
    )
    rate_limit: str = Field(
        description="Key rate limit constraints relevant to a daily ingestion job"
    )
    freshness_check: FreshnessCheck = Field(
        description="Whether live docs were checked and if anything changed vs stored reference"
    )
 
    # ── Quality signals ────────────────────────────────────────────────────────
    missing_inputs: List[str] = Field(
        default_factory=list,
        description=(
            "Inputs that were unavailable during investigation and may affect downstream accuracy. "
            "Examples: 'No JSON response sample available — field types inferred from docs only', "
            "'Documentation behind login wall — could not verify freshness', "
            "'Conversion fields only partially documented — semantic notes incomplete'."
        ),
    )
    summary: str = Field(
        description=(
            "Concise narrative (3-5 sentences) for the next agent (Data Architect). "
            "Include: platform investigated, action taken, total fields discovered, "
            "canonical coverage (X/9 matched), any cross-platform gotchas the DDL must account for, "
            "and whether the freshness check found changes. "
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

class BQSchemaField(BaseModel):
    """
    Single field in the BigQuery schema preview.
    Mirrors the table shown in the UI mockup.
    """
    field_name: str = Field(
        description=(
            "Snake_case column name in BigQuery. "
            "Derived from the platform's api_field: strip dots, normalize separators. "
            "Example: 'metrics.cost_micros' → 'cost_micros'."
        )
    )
    type: str = Field(
        description="BigQuery column type: STRING, FLOAT64, INT64, TIMESTAMP, DATE, BOOLEAN."
    )
    mode: Literal["REQUIRED", "NULLABLE"] = Field(
        description=(
            "REQUIRED only for columns guaranteed non-null by the API contract "
            "(e.g. ingest_ts, platform, date). Default to NULLABLE for all metric fields."
        )
    )
    description: str = Field(
        description=(
            "Human-readable column description shown in the schema preview. "
            "Incorporate the platform label, any cast/normalization note, and semantics "
            "when available. Keep it under 120 characters."
        )
    )

class DataArchitectPayload(BaseModel):
    proposed_ddl: Optional[str] = Field(
        default=None,
        description=(
            "Full CREATE TABLE / CREATE SCHEMA DDL proposed for the Raw/Bronze layer."
            "Must be consistent with schema_preview."
            "using BigQuery SQL. Omit or null if the turn only listed datasets or validated inputs without drafting DDL."
            "Null if the turn only listed datasets or no field were selected."
        ),
    )
    dataset_target: str = Field(
        default="",
        description=(
            "Target BigQuery dataset for raw ingestion (e.g. raw_social, raw_youtube). "
            "Must align with Medallion naming: raw/bronze landing zone, not curated silver/gold."
        ),
    )
    table_name: Optional[str] = Field(
        default=None,
        description=("Target table name in snake_case (e.g. 'meta_perfomance_raw', 'tiktok_ads_raw')."
        "Null until schema is proposed and user approves the table name.")
    )
    selected_fields: List[str] = Field(
        default_factory=list,
        description=("List of api_field values the user chose from the full catalog."
        "Populated from the user instruction. Used to filter available_fields for the schema preview."
        "From the API Researcher LOL before generating DDL.")
    )
    schema_preview: List[BQSchemaField] = Field(
        default_factory=list,
        description=("Ordered list of BigQuery columns for the proposed table."
        "This is the data shown in the UI schema preview table.")
    )
    action_taken: str = Field(
        description=(
            "Short machine-readable label for what this agent did in this turn, e.g. "
            "'listed_raw_datasets', 'proposed_schema', 'awaiting_approval', "
            "'executed_ddl', 'rejected_unsafe_ddl', 'clarification_needed', 'error'."
        ),
    )
    sql_preview: Optional[str] = Field(
        default=None,
        description=(
            "Short illustrative SELECT query using the proposed table, "
            "showing canonical aggregations (SUM(spend), COUNT(*), GROUP BY date, etc.). "
            "Shown in the UI SQL preview panel. Null until schema is proposed."
        ),
    )
    ddl_approved: bool = Field(
        default=False,
        description=(
            "True ONLY when the user has explicitly confirmed execution in this turn "
            "(e.g. 'yes, execute', 'apply the DDL'). "
            "The agent must NEVER set this to True on its own initiative. "
            "execute_ddl must not be called when this is False."
        ),
    )

    missing_inputs: List[str] = Field(
        default_factory=list,
        description=(
            "Inputs missing to proceed. Examples: "
            "'No fields selected — ask user which fields to include', "
            "'dataset_target not confirmed — listing available datasets', "
            "'DDL not yet approved by user'."
        ),
    )
    summary: str = Field(
        default="",
        description=(
            "Concise narrative for the Synthesizer. Include: platform, table proposed, "
            "field count, any typing gotchas applied, and whether DDL is pending approval "
            "or was executed. Do not mention internal tool names."
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


