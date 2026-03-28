"""Shared registry of operator IDs used by coordinator prompts and graph routing."""

from __future__ import annotations

SPECIAL_AGENT_NAMES = ["out_of_scope", "capabilities_help"]
NORMAL_AGENT_NAMES = ["data_architect", "software_engineer", "api_researcher"]
ALL_AGENT_NAMES = SPECIAL_AGENT_NAMES + NORMAL_AGENT_NAMES

