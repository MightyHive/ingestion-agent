"""APIResearcherAgent — external API documentation investigator for data pipeline building."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai_skills import SkillsToolset  # pyright: ignore[reportMissingImports]
from config.settings import settings
from models.lol import APIResearcherLOL
from models.tool_outputs import dump_tool_output
from observability import extract_usage, run_logged_tool
from tools.api_researcher_tools import (
    _analyze_json_schema,
    _read_documentation_url,
    _search_web,
)


@dataclass
class APIResearcherDeps:
    """Runtime context for the API Researcher agent."""

    project_id: str
    location: str

_SKILLS_DIR = Path(__file__).resolve().parents[1] / "skills"

# ─────────────────────────────────────────────────────────────
# Known Platforms Registry
# Routing index only — content lives in the reference files.
# ─────────────────────────────────────────────────────────────

KNOWN_PLATFORMS: dict[str, dict] = {
    "meta": {
        "display_name":   "Meta Marketing API",
        "docs_url":       "https://developers.facebook.com/docs/marketing-apis/",
        "reference_file": "src/skills/paid-media-api/references/meta.md",
    },
    "facebook": "meta",
    "instagram": "meta",
    "google ads": {
        "display_name":   "Google Ads API",
        "docs_url":       "https://developers.google.com/google-ads/api/docs/start",
        "reference_file": "src/skills/paid-media-api/references/google-ads.md",
    },
    "google": "google ads",
    "tiktok": {
        "display_name":   "TikTok Marketing API",
        "docs_url":       "https://business-api.tiktok.com/portal/docs",
        "reference_file": "src/skills/paid-media-api/references/tiktok.md",
    },
}
 
# Resolve string aliases to their target dict
for _k, _v in list(KNOWN_PLATFORMS.items()):
    if isinstance(_v, str):
        KNOWN_PLATFORMS[_k] = KNOWN_PLATFORMS[_v]
 
 
def _resolve_platform(api_name: str) -> dict | None:
    """Case-insensitive partial match against KNOWN_PLATFORMS keys."""
    lower = api_name.lower().strip()
    for key, data in KNOWN_PLATFORMS.items():
        if key in lower or lower in key:
            return data
    return None
 
 
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
 
    return agent
 
 
async def run_api_researcher_agent(instruction: str, deps: APIResearcherDeps) -> tuple[dict, dict]:
    """Run one agent turn: user instruction in, structured APIResearcherLOL dict out."""
    result = await build_api_researcher_agent().run(instruction, deps=deps)
    usage = extract_usage(result)
    return result.output.model_dump(), usage