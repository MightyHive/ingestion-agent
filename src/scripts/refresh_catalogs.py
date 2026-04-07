#!/usr/bin/env python3
"""Cron-friendly refresh: delete on-disk API catalogs and rebuild via API Researcher (LLM)."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import Any

# Repo root = two levels above this file (src/scripts → project root)
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.agents.api_researcher_agent import (  # noqa: E402
    APIResearcherDeps,
    KNOWN_PLATFORMS,
    api_catalog_json_path,
    enrich_instruction_for_known_platform,
    run_api_researcher_agent,
)
from src.config.settings import settings  # noqa: E402

logger = logging.getLogger(__name__)


def _unique_platform_dicts() -> list[dict[str, Any]]:
    seen: set[int] = set()
    out: list[dict[str, Any]] = []
    for pdata in KNOWN_PLATFORMS.values():
        if not isinstance(pdata, dict):
            continue
        pid = id(pdata)
        if pid in seen:
            continue
        seen.add(pid)
        out.append(pdata)
    return sorted(out, key=lambda d: str(d.get("platform_id", "")))


async def _refresh_one(platform: dict[str, Any]) -> None:
    platform_id = str(platform.get("platform_id") or "").strip()
    display_name = str(platform.get("display_name") or platform_id)
    if not platform_id:
        logger.warning("Skipping platform entry without platform_id: %s", platform)
        return

    path = api_catalog_json_path(platform_id)
    if path.is_file():
        path.unlink()
        logger.info("Removed stale catalog: %s", path)

    base_prompt = (
        f"User wants to connect and ingest reporting data from {display_name}. "
        "Run the full API researcher workflow and persist the contract via save_api_contract."
    )
    instruction = enrich_instruction_for_known_platform(base_prompt)
    sidecar: dict[str, Any] = {}
    deps = APIResearcherDeps(
        project_id=settings.PROJECT_ID_LLM or "",
        location=settings.LOCATION,
        artifact_sidecar=sidecar,
    )
    lol, usage = await run_api_researcher_agent(instruction, deps=deps)
    status = lol.get("status")
    spec = sidecar.get("api_spec")
    n_fields = (
        len(spec.get("available_fields", []))
        if isinstance(spec, dict) and isinstance(spec.get("available_fields"), list)
        else 0
    )
    logger.info(
        "Finished %s — status=%s usage=%s catalog_fields=%s",
        platform_id,
        status,
        usage,
        n_fields,
    )


async def main_async() -> None:
    platforms = _unique_platform_dicts()
    if not platforms:
        logger.warning("No platforms registered in KNOWN_PLATFORMS.")
        return
    for p in platforms:
        await _refresh_one(p)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
