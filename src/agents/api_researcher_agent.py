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

API_RESEARCHER_PROMPT = """\
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
for the Data Architect to use when proposing a BigQuery DDL.

**Read-only mandate:** never generate code that creates, updates, or deletes
campaigns, ads, or any platform resource.

# Goal
Produce an APIResearcherLOL with accurate field mappings for these 9 canonical metrics:
  impressions, clicks, spend, ctr, conversions, video_views, reach, campaign_name, date

Set api_field="NOT_AVAILABLE" if the platform doesn't expose a field.
Always populate note with type gotchas, cast requirements, or normalization instructions.

# Required workflow

## Known platform (receives a [KNOWN PLATFORM] block)
1. Call read_documentation_url(reference_file) — this is the source of truth.
   Extract: auth, reporting endpoint, all field mappings with exact api_field names,
   pagination, rate limits, and gotchas.
2. Call read_documentation_url(docs_url) for freshness_check.
   Compare live docs against the reference file.
   - Changes detected → changes_detected=True, describe delta.
   - No changes → changes_detected=False, delta=null.
3. Set action="freshness_check".

## Unknown platform
1. search_web("{api_name} official API documentation")
2. read_documentation_url(best result URL)
3. If a JSON sample is found → analyze_json_schema, set action="schema_analysis"
4. Otherwise set action="full_investigation"
5. Set freshness_check.checked=False

# Payload field: `action`
Set action to the last decisive step in the investigation:
  "freshness_check"    — known platform, read reference + checked live docs
  "full_investigation" — unknown platform, searched web + read docs
  "schema_analysis"    — also ran analyze_json_schema on a response sample
  "error"              — investigation failed entirely

# Payload field: `summary`
2-4 sentence memo for the Data Architect. Include: platform name, action taken,
key DDL gotchas (micros, string casting, CTR format, etc.), freshness result.
Do not mention tool names.

# Payload field: `missing_inputs`
List anything that limits accuracy, e.g.:
  "No JSON response sample found — field types inferred from docs only"
  "Live docs behind login wall — freshness could not be verified"

# Output
Must follow the APIResearcherLOL model.
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
            lambda: _search_web(query=query, max_results=max_results),
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
            lambda: _read_documentation_url(url=url),
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
            lambda: _analyze_json_schema(json_str=json_str),
        )

    return agent


async def run_api_researcher_agent(instruction: str, deps: APIResearcherDeps) -> tuple[dict, dict]:
    """Run one agent turn: user instruction in, structured APIResearcherLOL dict out."""
    result = await build_api_researcher_agent().run(instruction, deps=deps)
    usage = extract_usage(result)
    return result.output.model_dump(), usage


