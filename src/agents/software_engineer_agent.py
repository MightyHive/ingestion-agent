"""SoftwareEngineerAgent — connector-library manager for external data sources."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict

from pydantic_ai import Agent, RunContext
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai_skills import SkillsToolset  # pyright: ignore[reportMissingImports]

from config.settings import settings
from models.lol import SoftwareEngineerLOL
from observability import extract_usage, run_logged_tool
from tools.software_engineer_tools import (
    _find_connector,
    _get_gold_standard_code,
    _identify_environment_variables,
    _list_connectors,
    _modify_payload_and_columns,
    _read_connector,
    _save_connector,
    _validate_connector_code,
    _write_cf_code,
)


@dataclass
class SoftwareEngineerDeps:
    """Runtime context for the Software Engineer agent (GCP project and region)."""

    project_id: str
    location: str
    #: Cross-turn artifact snapshot from LangGraph (e.g. ``table_ddl`` from Data Architect).
    artifacts: dict[str, Any] = field(default_factory=dict)


_SKILLS_DIR = Path(__file__).resolve().parents[1] / "skills"

SOFTWARE_ENGINEER_PROMPT = """\
# Role
You are the Software Engineer component in a multi-agent ingestion architecture.

# Scope
You only handle connector code engineering tasks:
- reuse existing connector templates
- modify payload/column selection in templates
- scaffold connector source (e.g. strings shaped like a `main.py` + `requirements.txt` via `write_cf_code`)
- identify **names** of environment variables / likely secrets from code (not their values)
- validate connector code

**Out of scope (other agents / teams):** deploying or running connectors as **Google Cloud Functions** (or any
cloud runtime), **importing saved modules to call `fetch` locally**, wiring IAM, Secret Manager injection in GCP,
scheduling, or production execution. Your output is the **connector library on disk** plus structured LOL metadata
for downstream handoff.

**Secrets and API keys:** you never obtain, generate, or embed credential values. Connectors should read secrets
via `os.getenv("VAR_NAME")` (or similar) and you report those names via `identify_environment_variables` and
`payload.env_vars_required` / `required_secrets`. Actual values are provided at **runtime** by DevOps, the
coordinator handoff, Secret Manager, or CI—not by this agent.

You do not perform deployment, cloud infra configuration, or final QA approval.

# Goal
Your primary deliverable is **connector modules in the local connector library** (on-disk `.py` files).
Strings returned by `write_cf_code` alone are never sufficient: the library is the source of truth.


# Consuming upstream context

Your instruction may be enriched with structured context blocks produced by other agents.
Look for the labelled sections described below and use them as indicated.

## Persistent ``deps.artifacts['api_spec']`` (canonical API contract)
When present, this is the **authoritative** technical contract for connector generation:
base URL, auth type, pagination, HTTP method, and required headers. **Rely on it** for
endpoint and request semantics—do not infer URLs, methods, or pagination from chat prose
or stale conversation context. Still pass ``API_RESEARCH_CONTEXT`` into ``write_cf_code``
as ``api_research`` when you have it (field catalog, platform metadata); ``write_cf_code``
merges ``api_spec`` overrides with that payload.

## API_RESEARCH_CONTEXT (`APIResearcherPayload`)
Structured field catalog and platform metadata from the API Researcher. Forward as the
`api_research` dict to `write_cf_code` when available. Endpoint/method/pagination should
match ``artifacts['api_spec']`` when both exist; treat discrepancies as a warning in
``missing_inputs``.

## DATA_ARCHITECT_CONTEXT (`DataArchitectPayload`)
Contains the Data Architect's BigQuery schema decision: `dataset_target` (e.g.
`raw_social`), `proposed_ddl` (CREATE TABLE SQL), and `action_taken`. Use this to:
- Set the connector's target dataset/table so the generated code writes to the correct
  BigQuery destination (dataset and table name from the DDL).
- Align the connector's output columns with the columns declared in the DDL.
- If `proposed_ddl` is null or `action_taken` indicates no schema was finalized yet,
  note this gap in `missing_inputs` and proceed with a best-effort scaffold.

## Runtime ``deps.artifacts`` (same session, prior turns)
The graph may inject ``deps.artifacts["table_ddl"]`` when the turn-local ``event_bus`` no longer
contains the Data Architect LOL (e.g. Software Engineer runs alone on a follow-up turn).
It may also inject ``deps.artifacts["api_spec"]`` from the API Researcher. The
``write_cf_code`` tool reads both automatically—ensure upstream agents have persisted them
before you claim a complete connector.

**When both contexts are absent:** do NOT fabricate endpoints, auth flows, field names,
or BigQuery destinations. Set `status: WARN` or `ERR`, explain what is missing in
`missing_inputs`, and let the pipeline route work to the appropriate upstream agent first.


# Required workflow
1. Search and reuse connectors before creating new ones.
2. If missing, define source and create a reusable connector.
3. Validate connector code, then **always persist** valid code to the library (see below).
4. If needed, request explicit human approval and explain why.

# Mandatory library persistence (non-negotiable)
- `write_cf_code` and `modify_payload_and_columns` only return text; they **never** write files.
- Whenever you **author or finalize** connector Python for this component (`write_cf_code`, `modify_payload_and_columns`,
  or edited gold-standard code), you **must** call `validate_connector_code` on the final module source, then
  **`save_connector`** with that exact source before returning `status` **OK** or **WARN** for that work.
- Do **not** return OK/WARN with new connector code living only inside `payload.data` or the model narrative—
  a successful authoring turn **ends with `save_connector`** and real paths from its tool output.
- **Exceptions (no save required):** read-only turns (`list_connectors`, `find_connector`, `read_connector` without
  producing new code); or **`status: ERR`** when validation fails, naming is invalid, or critical upstream research
  is missing—in those cases explain in `reason` / `missing_inputs` and do not claim a file was saved.
- Set `payload.file_path`, `payload.connector_name`, and `payload.validation` from **actual tool results**
  (`validate_connector_code`, `save_connector`), not invented shapes.

# Constraints
- Always execute at least one real tool per request.
- Never invent tool results.
- Never save invalid code.
- Never hardcode secrets or tokens in generated code.

# Skills
- Skills are available via `load_skill` and resources via `read_skill_resource`.
- For connector naming conventions and runtime input contract details, follow `software-engineer-connector-manager`.

# Output
Must follow the `SoftwareEngineerLOL` model.

# Payload field: `action`
Set `payload.action` to the **last decisive tool** in this turn—the step that best represents what
was ultimately delivered (e.g. persisting code → `save_connector`; only validating → `validate_connector_code`).
Earlier tool calls in the same turn should still be reflected in `summary`, `validation`, `data`,
`generated_files`, `env_vars_required`, and related fields—not in `action`, which stays a single literal.
"""


def build_software_engineer_agent() -> Agent:
    """Build a PydanticAI Agent with connector-library tools and the skills toolset.

    Returns:
        Configured ``Agent`` with ``output_type=SoftwareEngineerLOL`` and tools registered.
    """
    provider = GoogleProvider(
        vertexai=True,
        project=settings.PROJECT_ID_LLM,
        location=settings.LOCATION,
    )
    skills_toolset = SkillsToolset(directories=[str(_SKILLS_DIR)])
    agent = Agent(
        GoogleModel(settings.MODEL_NAME, provider=provider),
        system_prompt=SOFTWARE_ENGINEER_PROMPT,
        output_type=SoftwareEngineerLOL,
        deps_type=SoftwareEngineerDeps,
        toolsets=[skills_toolset],
    )

    if hasattr(agent, "instructions") and hasattr(skills_toolset, "get_instructions"):

        @agent.instructions
        async def add_skills_instructions(ctx: RunContext[SoftwareEngineerDeps]) -> str | None:
            """Merge dynamic skill instructions (e.g. connector workflow) into the model context."""
            return await skills_toolset.get_instructions(ctx)

    @agent.tool
    def get_gold_standard_code(ctx: RunContext[SoftwareEngineerDeps], channel_name: str) -> Dict[str, Any]:
        """Load pre-approved connector template source from the local library.

        Args:
            channel_name: Normalized connector name (e.g. ``youtube_analytics``) to resolve as gold-standard.

        Returns:
            Tool dict with ``status``, ``code``, ``connector``, ``code_text``, and optional ``close_matches``.
        """
        return run_logged_tool(
            "software_engineer.get_gold_standard_code",
            lambda: _get_gold_standard_code(channel_name=channel_name),
            channel_name=channel_name,
        )

    @agent.tool
    def modify_payload_and_columns(
        ctx: RunContext[SoftwareEngineerDeps],
        template_code: str,
        fields: list[str],
    ) -> Dict[str, Any]:
        """Inject user-selected source fields into template code (placeholders / DEFAULT_FIELDS / fetch).

        Args:
            template_code: Full Python source of an existing connector template.
            fields: Field or metric names to request from the upstream API (non-empty).

        Returns:
            Tool dict with ``updated_code``, ``fields``, and ``modifications_applied``.
        """
        return run_logged_tool(
            "software_engineer.modify_payload_and_columns",
            lambda: _modify_payload_and_columns(template_code=template_code, fields=fields),
            fields_count=len(fields),
        )

    @agent.tool
    def write_cf_code(
        ctx: RunContext[SoftwareEngineerDeps],
        source: str,
        connector_type: str,
        api_research: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Generate scaffold strings: a ``main.py``-shaped module body plus ``requirements.txt`` (library handoff only; no cloud deploy).

        Args:
            source: Data source slug (e.g. ``meta``, ``tiktok``); used in naming and env var hints.
            connector_type: Type segment for ``[source]_[type]`` naming (e.g. ``ads``, ``analytics``).
            api_research: ``APIResearcherPayload`` fields forwarded from the API Researcher:
                ``reporting_endpoint`` — ``"GET https://…/insights"``.
                ``auth`` — ``{"method": "OAuth 2.0", "required_credentials": ["access_token", …], …}``.
                ``available_fields`` — list of ``{"api_field": "…", "canonical_match": "…", …}``.
                ``pagination`` — ``"cursor-based (paging.after)"``.
                ``platform`` — ``"Meta Marketing API"``.
                ``rate_limit`` — constraint description.
            Persisted ``deps.artifacts["api_spec"]`` (if any) is merged automatically for URL,
            method, pagination, and auth hints, and embedded in the generated module header.

        Returns:
            Tool dict with ``main_py``, ``requirements_txt``, ``connector_name``, ``suggested_env_vars``.
        """
        arts = ctx.deps.artifacts or {}
        table_ddl = arts.get("table_ddl")
        table_ddl_str = table_ddl.strip() if isinstance(table_ddl, str) else None
        raw_spec = arts.get("api_spec")
        api_spec = raw_spec if isinstance(raw_spec, dict) else None
        return run_logged_tool(
            "software_engineer.write_cf_code",
            lambda: _write_cf_code(
                source=source,
                connector_type=connector_type,
                api_research=api_research,
                table_ddl=table_ddl_str,
                api_spec=api_spec,
            ),
            source=source,
            connector_type=connector_type,
        )

    @agent.tool
    def identify_environment_variables(ctx: RunContext[SoftwareEngineerDeps], code_text: str) -> Dict[str, Any]:
        """Scan Python source for ``os.getenv`` / ``${VAR}`` usage and flag likely secrets.

        Args:
            code_text: Full connector or generated module source to analyze.

        Returns:
            Tool dict with ``env_vars`` and ``likely_secrets`` lists.
        """
        return run_logged_tool(
            "software_engineer.identify_environment_variables",
            lambda: _identify_environment_variables(code_text=code_text),
        )

    @agent.tool
    def list_connectors(ctx: RunContext[SoftwareEngineerDeps], source: str | None = None) -> Dict[str, Any]:
        """List all ``.py`` connectors under ``connector_library``, optionally under one source folder.

        Args:
            source: If set, restrict listing to ``connector_library/<source>/``.

        Returns:
            Tool dict with ``connector_root`` and ``connectors`` (name, source, path per file).
        """
        return run_logged_tool(
            "software_engineer.list_connectors",
            lambda: _list_connectors(source=source),
            source=source,
        )

    @agent.tool
    def find_connector(ctx: RunContext[SoftwareEngineerDeps], name: str) -> Dict[str, Any]:
        """Resolve a connector by normalized stem name; exact match or fuzzy ``close_matches``.

        Args:
            name: Connector name to search (normalized to snake_case).

        Returns:
            Tool dict with ``connector`` ref on hit, or ``close_matches`` on miss.
        """
        return run_logged_tool(
            "software_engineer.find_connector",
            lambda: _find_connector(name=name),
            name=name,
        )

    @agent.tool
    def read_connector(ctx: RunContext[SoftwareEngineerDeps], path: str) -> Dict[str, Any]:
        """Read connector file contents; path must stay inside ``connector_library``.

        Args:
            path: Absolute path to a ``.py`` file under the connector root.

        Returns:
            Tool dict with ``connector`` metadata and ``code_text``.
        """
        return run_logged_tool(
            "software_engineer.read_connector",
            lambda: _read_connector(path=path),
            path=path,
        )

    @agent.tool
    def validate_connector_code(ctx: RunContext[SoftwareEngineerDeps], code: str) -> Dict[str, Any]:
        """Validate syntax and required connector contract: ``fetch(params, context)`` and ``fields`` usage.

        Args:
            code: Full Python source of the connector module.

        Returns:
            Tool dict with nested ``validation`` (flags and error message if invalid).
        """
        return run_logged_tool(
            "software_engineer.validate_connector_code",
            lambda: _validate_connector_code(code=code),
        )

    @agent.tool
    def save_connector(
        ctx: RunContext[SoftwareEngineerDeps],
        source: str,
        name: str,
        code: str,
        overwrite: bool = False,
    ) -> Dict[str, Any]:
        """Persist connector module to ``connector_library/<source>/<name>.py`` after validation.

        Args:
            source: Source folder name (normalized).
            name: Connector stem; must match ``[source]_[type]`` pattern.
            code: Full Python source to write.
            overwrite: If True, replace an existing file; otherwise warn on conflict.

        Returns:
            Tool dict with ``connector`` path and ``validation`` details.
        """
        return run_logged_tool(
            "software_engineer.save_connector",
            lambda: _save_connector(source=source, name=name, code=code, overwrite=overwrite),
            source=source,
            name=name,
            overwrite=overwrite,
        )

    return agent


async def run_software_engineer_agent(instruction: str, deps: SoftwareEngineerDeps) -> tuple[dict, dict]:
    """Run one agent turn: user instruction in, structured ``SoftwareEngineerLOL`` dict out.

    Args:
        instruction: Natural-language task for the model (may include tool use).
        deps: Project and region for future integrations; tools currently use minimal deps.

    Returns:
        Tuple of ``(lol_dict, usage_dict)`` where ``lol_dict`` matches ``SoftwareEngineerLOL`` shape.
    """
    result = await build_software_engineer_agent().run(instruction, deps=deps)
    usage = extract_usage(result)
    return result.output.model_dump(), usage
