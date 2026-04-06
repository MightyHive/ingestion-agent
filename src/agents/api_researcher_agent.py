"""APIResearcherAgent — external API documentation investigator for data pipeline building."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from pydantic_ai import Agent, RunContext
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai_skills import SkillsToolset  # pyright: ignore[reportMissingImports]
from config.settings import settings
from models.lol import (
    APIResearcherAuthInfo,
    APIResearcherFieldMapping,
    APIResearcherLOL,
    APIResearcherPayload,
    FreshnessCheck,
)
from models.tool_outputs import dump_tool_output
from observability import extract_usage, run_logged_tool
from tools.api_researcher_tools import (
    _analyze_json_schema,
    _read_documentation_url,
    _search_web,
    apply_save_api_contract,
)


@dataclass
class APIResearcherDeps:
    """Runtime context for the API Researcher agent."""

    project_id: str
    location: str
    #: Mutable dict tools may write into; merged into graph ``artifacts`` (e.g. ``api_spec``).
    artifact_sidecar: dict[str, Any] | None = None

_SKILLS_DIR = Path(__file__).resolve().parents[1] / "skills"
_SRC_DIR = Path(__file__).resolve().parents[1]
_CONNECTOR_LIBRARY_DIR = _SRC_DIR / "connector_library"

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# Known Platforms Registry
# Routing index only — content lives in the reference files.
# ─────────────────────────────────────────────────────────────

KNOWN_PLATFORMS: dict[str, dict[str, Any] | str] = {
    "meta": {
        "platform_id": "meta",
        "display_name": "Meta Marketing API",
        "docs_url": "https://developers.facebook.com/docs/marketing-apis/",
        "reference_file": "src/skills/paid-media-api/references/meta.md",
    },
    "facebook": "meta",
    "instagram": "meta",
    "google ads": {
        "platform_id": "google_ads",
        "display_name": "Google Ads API",
        "docs_url": "https://developers.google.com/google-ads/api/docs/start",
        "reference_file": "src/skills/paid-media-api/references/google-ads.md",
    },
    "google": "google ads",
    "tiktok": {
        "platform_id": "tiktok",
        "display_name": "TikTok Marketing API",
        "docs_url": "https://business-api.tiktok.com/portal/docs",
        "reference_file": "src/skills/paid-media-api/references/tiktok.md",
    },
}
 
# Resolve string aliases to their target dict
for _k, _v in list(KNOWN_PLATFORMS.items()):
    if isinstance(_v, str):
        KNOWN_PLATFORMS[_k] = KNOWN_PLATFORMS[_v]
 
 
def _resolve_platform(api_name: str) -> dict[str, Any] | None:
    """Case-insensitive partial match against KNOWN_PLATFORMS keys."""
    lower = api_name.lower().strip()
    for key, data in KNOWN_PLATFORMS.items():
        if isinstance(data, str):
            continue
        if key in lower or lower in key:
            return data
    return None


def resolve_platform_for_catalog(instruction: str) -> dict[str, Any] | None:
    """Match instruction text to a known platform (keys or display_name)."""
    hit = _resolve_platform(instruction)
    if hit is not None:
        return hit
    low = instruction.lower()
    seen: set[int] = set()
    for pdata in KNOWN_PLATFORMS.values():
        if isinstance(pdata, str):
            continue
        pid = id(pdata)
        if pid in seen:
            continue
        seen.add(pid)
        dn = str(pdata.get("display_name", "")).strip().lower()
        if len(dn) >= 3 and dn in low:
            return pdata
    return None


def api_catalog_json_path(platform_id: str) -> Path:
    """Filesystem path for the persisted API catalog (JSON)."""
    return _CONNECTOR_LIBRARY_DIR / platform_id / "api_catalog.json"


def enrich_instruction_for_known_platform(prompt: str) -> str:
    """Append [KNOWN PLATFORM] block when the prompt matches a registry entry (same as graph node)."""
    platform_data = _resolve_platform(prompt)
    if not platform_data:
        return prompt
    return (
        f"{prompt}\n\n"
        f"[KNOWN PLATFORM]\n"
        f"display_name:   {platform_data['display_name']}\n"
        f"docs_url:       {platform_data['docs_url']}\n"
        f"reference_file: {platform_data['reference_file']}\n\n"
        f"Step 1: call read_documentation_url('{platform_data['reference_file']}') — source of truth.\n"
        f"Step 2: call read_documentation_url('{platform_data['docs_url']}') — freshness check.\n"
        f"Set action='freshness_check'."
    )


def _parse_iso_utc(value: str) -> datetime | None:
    try:
        normalized = value.strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _catalog_is_fresh(last_updated: str, ttl_days: int) -> bool:
    parsed = _parse_iso_utc(last_updated)
    if parsed is None:
        return False
    age = datetime.now(timezone.utc) - parsed
    return age.days < ttl_days


def _spec_has_persistable_data(spec: dict[str, Any]) -> bool:
    if not spec:
        return False
    fields = spec.get("available_fields")
    if isinstance(fields, list) and any(str(x).strip() for x in fields):
        return True
    return bool(str(spec.get("base_url", "")).strip())


async def _read_catalog_file(path: Path) -> dict[str, Any] | None:
    def _read() -> dict[str, Any] | None:
        if not path.is_file():
            return None
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)

    return await asyncio.to_thread(_read)


async def _write_catalog_file(path: Path, payload: dict[str, Any]) -> None:
    def _write() -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)

    await asyncio.to_thread(_write)


def _cached_lol_from_spec(
    spec: dict[str, Any],
    *,
    display_name: str,
) -> APIResearcherLOL:
    raw_fields = spec.get("available_fields")
    names: list[str] = []
    if isinstance(raw_fields, list):
        names = [str(x).strip() for x in raw_fields if str(x).strip()]
    mappings: list[APIResearcherFieldMapping] = [
        APIResearcherFieldMapping(
            api_field=name,
            label=name,
            type="STRING",
            category="other",
        )
        for name in names
    ]
    payload = APIResearcherPayload(
        action="freshness_check",
        platform=display_name,
        auth=APIResearcherAuthInfo(
            method="CACHED",
            required_credentials=[],
            token_type="n/a",
            expiry="n/a",
        ),
        reporting_endpoint=str(spec.get("base_url") or "UNKNOWN"),
        available_fields=mappings,
        total_fields_discovered=len(mappings),
        canonical_fields_found=0,
        discovery_method="docs_only",
        pagination=str(spec.get("pagination") or "UNKNOWN"),
        rate_limit="CACHED",
        freshness_check=FreshnessCheck(checked=False, changes_detected=False, delta=None),
        missing_inputs=["Catalog served from local JSON cache; LLM not invoked."],
        summary=(
            f"Loaded {display_name} API contract from on-disk catalog cache. "
            f"{len(mappings)} fields available for column selection."
        ),
    )
    return APIResearcherLOL(
        status="WARN",
        reason="Loaded from cache. Waiting for user to select columns in the UI",
        usage=None,
        payload=payload,
    )


class _CacheAgentRunResult:
    """Minimal stand-in for pydantic_ai.Agent.run return value (output + usage)."""

    __slots__ = ("output",)

    def __init__(self, output: APIResearcherLOL) -> None:
        self.output = output


async def _try_serve_api_catalog_cache(
    instruction: str,
    deps: APIResearcherDeps,
) -> _CacheAgentRunResult | None:
    if deps.artifact_sidecar is None:
        return None
    pdata = resolve_platform_for_catalog(instruction)
    if pdata is None:
        return None
    platform_id = str(pdata.get("platform_id") or "").strip()
    if not platform_id:
        return None
    path = api_catalog_json_path(platform_id)
    doc = await _read_catalog_file(path)
    if not isinstance(doc, dict):
        return None
    last_updated = doc.get("last_updated")
    spec = doc.get("spec")
    if not isinstance(last_updated, str) or not isinstance(spec, dict):
        return None
    if not _catalog_is_fresh(last_updated, settings.API_CATALOG_TTL_DAYS):
        return None
    deps.artifact_sidecar["api_spec"] = spec
    display_name = str(pdata.get("display_name") or platform_id)
    logger.info(
        "api_researcher: catalog cache HIT for %s (%s) — skipping LLM (no model network)",
        platform_id,
        path,
    )
    return _CacheAgentRunResult(_cached_lol_from_spec(spec, display_name=display_name))


async def _persist_api_catalog_if_applicable(instruction: str, deps: APIResearcherDeps | None) -> None:
    if deps is None or deps.artifact_sidecar is None:
        return
    spec = deps.artifact_sidecar.get("api_spec")
    if not isinstance(spec, dict) or not _spec_has_persistable_data(spec):
        return
    pdata = resolve_platform_for_catalog(instruction)
    if pdata is None:
        return
    platform_id = str(pdata.get("platform_id") or "").strip()
    if not platform_id:
        return
    path = api_catalog_json_path(platform_id)
    payload = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "spec": spec,
    }
    await _write_catalog_file(path, payload)
    logger.info("api_researcher: wrote API catalog cache for %s → %s", platform_id, path)


def _wrap_agent_run_with_catalog_cache(agent: Agent) -> Agent:
    """Intercept Agent.run: TTL JSON cache before LLM; persist spec after a successful run."""

    orig_run = agent.run

    async def run_with_catalog_cache(
        message: str,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        deps = kwargs.get("deps")
        if isinstance(deps, APIResearcherDeps):
            cached = await _try_serve_api_catalog_cache(message, deps)
            if cached is not None:
                return cached
        result = await orig_run(message, *args, **kwargs)
        if isinstance(deps, APIResearcherDeps):
            await _persist_api_catalog_if_applicable(message, deps)
        return result

    agent.run = run_with_catalog_cache  # type: ignore[method-assign]
    return agent
 
 
# ─────────────────────────────────────────────────────────────
# System Prompt
# ─────────────────────────────────────────────────────────────
 
API_RESEARCHER_PROMPT = """
# Role
You are the API Researcher component (Data Sourcer) in a multi-agent ingestion architecture.
 
# Scope
You only handle read-only API investigation tasks:
- load and interpret platform reference files from the skills library
- check live documentation for changes (freshness check)
- search the web for unknown platform documentation
- infer BigQuery field types from JSON response samples
 
**Out of scope:** writing, modifying, or deploying any pipeline code, connectors,
Cloud Functions, or infrastructure. Your output is a structured investigation report
for the Data Architect and for the UI field-selection screen.
 
**Read-only mandate:** never generate code that creates, updates, or deletes
campaigns, ads, or any platform resource.
 
# Goal
Produce an APIResearcherLOL with a COMPLETE field catalog for this platform.
 
"Complete" means ALL fields available from the reporting endpoint(s) — not just the
9 canonical ones. Typical platforms expose 20-50+ fields. Include everything a data
pipeline might reasonably ingest: performance metrics, structural dimensions, video
quartiles, cost sub-types, conversion breakdowns, date segments, etc.
 
The 9 canonical MVP metrics must always be attempted:
  impressions, clicks, spend, ctr, conversions, video_views, reach, campaign_name, date
 
For each canonical metric, find the best matching API field and set canonical_match.
If the platform does not expose it, include it anyway with api_field="NOT_AVAILABLE"
and the correct canonical_match so the catalog is always complete for the UI.
 
 
# Per-field requirements
Every entry in available_fields must set:
 
  api_field        Exact name in the API response (dot notation for nested;
                   "NOT_AVAILABLE" if missing; "DERIVED(formula)" if calculated,
                   e.g. "DERIVED(clicks/impressions)").
 
  label            Name verbatim from the platform docs or JSON response.
                   Do NOT normalize spelling — preserve "link_click_default_uas",
                   "stat_time_day", "cost_micros" exactly as they appear.
 
  type             BigQuery type: FLOAT64 | INTEGER | STRING | DATE | TIMESTAMP | BOOLEAN
 
  category         structural  — ids, names, statuses, hierarchy dimensions
                   performance — impressions, clicks, spend, video metrics, reach
                   conversion  — any conversion event, count, or value metric
                   other       — dates, currencies, platform-specific extras
 
  canonical_match  One of the 9 canonical keys above, or null.
                   Only ONE field per platform may claim each canonical key.
 
  note             Required whenever there is a cast, division, or format gotcha.
                   Examples: "API returns STRING — cast to FLOAT64",
                   "divide by 1,000,000 — never store raw micros",
                   "percentage format: 5.2 means 5.2% — normalize to ratio for
                   cross-platform comparisons".
                   Leave null only for fields with no processing quirks.
 
  semantics        Required for any field with canonical_match="conversions".
                   Also required for CTR (ratio vs percentage), spend (fees included
                   or not), all_conversions vs conversions, and any metric that counts
                   differently across platforms.
                   Describe: what events are counted, the attribution window, and
                   whether view-through is included.
                   Leave null only for unambiguous fields like impressions, campaign_name.
 
 
# Ordering rule for available_fields
1. The 9 canonical fields first, in this fixed order:
   impressions → clicks → spend → ctr → conversions → video_views → reach →
   campaign_name → date
   Include all 9 even if api_field="NOT_AVAILABLE".
2. Remaining fields: structural → performance → conversion → other,
   then alphabetically by label within each group.
 
 
# Required workflow
 
## Known platform (receives a [KNOWN PLATFORM] block)
1. Call read_documentation_url(reference_file) — this is the source of truth.
   Extract: auth, reporting endpoint, ALL field mappings across ALL domains
   (structural + performance + conversions), pagination, rate limits, gotchas.
2. Call read_documentation_url(docs_url) for freshness_check.
   Compare live docs against the reference file.
   - Changes detected → changes_detected=True, describe delta in `delta`.
   - No changes      → changes_detected=False, delta=null.
3. Set action="freshness_check".
 
## Unknown platform
1. search_web("{api_name} official API documentation")
2. read_documentation_url(best result URL)
3. If a JSON sample is found → analyze_json_schema, set action="schema_analysis"
4. Otherwise set action="full_investigation"
5. Set freshness_check.checked=False
 
 
# Payload field: `action`
  "freshness_check"    — known platform, read reference + checked live docs
  "full_investigation" — unknown platform, searched web + read docs
  "schema_analysis"    — also ran analyze_json_schema on a response sample
  "error"              — investigation failed entirely
 
 
# Payload fields: `total_fields_discovered`, `canonical_fields_found`, `discovery_method`
After building available_fields, set:
  total_fields_discovered  = len(available_fields)
  canonical_fields_found   = count of entries where canonical_match is not null
  discovery_method         = "docs_only"        if field types came from docs only
                             "json_schema"       if inferred from a live JSON sample
                             "docs_and_schema"   if both sources were used
 
 
# Payload field: `summary`
3-5 sentence memo for the Data Architect. Include: platform name, action taken,
total fields discovered, canonical coverage (X/9 matched), key DDL gotchas
(micros, string casting, CTR format, conversion semantics), freshness result.
Do not mention tool names.
 
 
# Payload field: `missing_inputs`
List anything that limits accuracy, e.g.:
  "No JSON response sample found — field types inferred from docs only"
  "Live docs behind login wall — freshness could not be verified"
  "Conversion breakdown fields only partially documented — semantics may be incomplete"
 
 
# Output
Must follow the APIResearcherLOL model exactly.
 
 
# Human-in-the-Loop (Yield to UI)
Because the user must select fields from the catalog you just discovered, you **must** set your final LOL
``status`` to **"WARN"** and ``reason`` to **"Waiting for user to select columns in the UI"**.
That signal pauses the orchestrator so FastAPI can emit ``ui_trigger`` (ColumnSelector) with
``available_fields`` from the persisted ``api_spec``. Do not return ``status`` **"OK"** after a successful
catalog discovery in this flow.
 
 
# Artifact handoff (mandatory)
Before you finish your turn, you **must** call ``save_api_contract`` once with the technical
contract for the API you researched: ``base_url``, ``auth_type``, ``pagination`` strategy,
HTTP ``method``, ``headers_required``, and ``available_fields``.
This persists ``api_spec`` into session artifacts so the Software Engineer and UI can consume
a stable contract without relying on volatile chat context.
You **must** populate ``available_fields`` with a comprehensive list of every metric, dimension,
and attribute you discovered (use each field's API name as in ``available_fields`` in your LOL output,
e.g. ``["impressions", "spend", "clicks", "campaign_name", …]``). Order: canonical nine first when
applicable, then the rest as in your field catalog.
Fill scalar parameters from documentation (use empty string or ``[]`` only when truly unknown).
"""
 
 
# ─────────────────────────────────────────────────────────────
# Agent Factory
# ─────────────────────────────────────────────────────────────
 
def build_api_researcher_agent() -> Agent:
    """Build a PydanticAI Agent with API investigation tools.
 
    Returns:
        Configured Agent with output_type=APIResearcherLOL and tools registered.
    """
    provider = GoogleProvider(
        vertexai=True,
        project=settings.PROJECT_ID_LLM,
        location=settings.LOCATION,
    )
    skills_toolset = SkillsToolset(directories=[str(_SKILLS_DIR)])
    agent = Agent(
        GoogleModel(settings.MODEL_NAME, provider=provider),
        system_prompt=API_RESEARCHER_PROMPT,
        output_type=APIResearcherLOL,
        deps_type=APIResearcherDeps,
    )
 
    if hasattr(agent, "instructions") and hasattr(skills_toolset, "get_instructions"):
 
        @agent.instructions
        async def add_skills_instructions(ctx: RunContext[APIResearcherDeps]) -> str | None:
            """Merge dynamic skill instructions (e.g. connector workflow) into the model context."""
            return await skills_toolset.get_instructions(ctx)
 
 
    @agent.tool
    def search_web(ctx: RunContext[APIResearcherDeps], query: str, max_results: int = 3) -> Dict[str, Any]:
        """Search the web for official API documentation.
 
        Args:
            query: Search query (e.g. "Stripe API official documentation").
            max_results: Number of results to return (default 3).
 
        Returns:
            Tool dict with status, query, and results (title, href, body per item).
        """
        return run_logged_tool(
            "api_researcher.search_web",
            lambda: dump_tool_output(_search_web(query=query, max_results=max_results)),
            query=query,
        )
 
    @agent.tool
    def read_documentation_url(ctx: RunContext[APIResearcherDeps], url: str) -> Dict[str, Any]:
        """Fetch and extract clean text from a URL or a local reference file path.
 
        Args:
            url: HTTP/HTTPS URL or local path (e.g. skills/paid-media-api/references/meta.md).
 
        Returns:
            Tool dict with status, url, content (up to 8000 chars), and char_count.
        """
        return run_logged_tool(
            "api_researcher.read_documentation_url",
            lambda: dump_tool_output(_read_documentation_url(url=url)),
            url=url,
        )
 
    @agent.tool
    def analyze_json_schema(ctx: RunContext[APIResearcherDeps], json_str: str) -> Dict[str, Any]:
        """Infer BigQuery field names and types from a JSON API response sample.

        Args:
            json_str: Raw JSON string from an API response (object or array).

        Returns:
            Tool dict with status, fields (api_field, type, sample), and field_count.
        """
        return run_logged_tool(
            "api_researcher.analyze_json_schema",
            lambda: dump_tool_output(_analyze_json_schema(json_str=json_str)),
        )

    @agent.tool
    def save_api_contract(
        ctx: RunContext[APIResearcherDeps],
        base_url: str,
        auth_type: str,
        pagination: str,
        method: str,
        headers_required: List[str],
        available_fields: List[str] | None = None,
    ) -> Dict[str, Any]:
        """Persist a normalized API contract to session artifacts for the Software Engineer and UI.

        Args:
            base_url: Fully qualified base URL or path prefix for reporting requests.
            auth_type: Auth mechanism (e.g. OAuth 2.0 bearer, API key header).
            pagination: How the API pages results (cursor, offset, etc.).
            method: Primary HTTP method for the reporting/read endpoint (GET, POST, ...).
            headers_required: Header names the client must send (besides auth), if any.
            available_fields: All API field names discovered (metrics, dimensions, attributes) for column pickers.

        Returns:
            Serialized ``ToolOutput`` indicating whether ``api_spec`` was written to the sidecar.
        """
        return run_logged_tool(
            "api_researcher.save_api_contract",
            lambda: dump_tool_output(
                apply_save_api_contract(
                    ctx.deps.artifact_sidecar,
                    base_url=base_url,
                    auth_type=auth_type,
                    pagination=pagination,
                    method=method,
                    headers_required=headers_required,
                    available_fields=available_fields,
                )
            ),
            base_url_len=len(base_url or ""),
            method=method,
            fields_count=len(available_fields or []),
        )

    return _wrap_agent_run_with_catalog_cache(agent)


async def run_api_researcher_agent(
    instruction: str, deps: APIResearcherDeps
) -> tuple[dict[str, Any], dict[str, int]]:
    """Run one agent turn: user instruction in, structured APIResearcherLOL dict out.

    ``build_api_researcher_agent().run`` is wrapped with a TTL JSON catalog: on a fresh cache hit,
    ``deps.artifact_sidecar["api_spec"]`` is filled from disk and the LLM is skipped; after a normal
    run, a non-empty ``api_spec`` is written under ``src/connector_library/<platform_id>/``.
    """
    result = await build_api_researcher_agent().run(instruction, deps=deps)
    usage = extract_usage(result)
    return result.output.model_dump(), usage