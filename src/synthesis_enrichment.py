"""
Deterministic extraction of structured data from the LOL event bus for the synthesizer.

Helps ensure lists (datasets, tables, etc.) are not dropped when the LLM over-summarizes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


def _try_json_loads(s: str) -> Optional[Any]:
    s = (s or "").strip()
    if not s or not (s.startswith("{") or s.startswith("[")):
        return None
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError):
        return None


def _walk_for_dicts(obj: Any, out: List[dict]) -> None:
    if isinstance(obj, dict):
        out.append(obj)
        for v in obj.values():
            _walk_for_dicts(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _walk_for_dicts(v, out)
    elif isinstance(obj, str):
        parsed = _try_json_loads(obj)
        if isinstance(parsed, (dict, list)):
            _walk_for_dicts(parsed, out)


def _unique_preserve(seq: List[str]) -> List[str]:
    seen: Set[str] = set()
    out: List[str] = []
    for x in seq:
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


@dataclass
class SynthesisEnrichment:
    """Lists extracted from the bus for mandatory prompt blocks and post-synthesis checks."""

    project_id: Optional[str] = None
    datasets: List[str] = field(default_factory=list)
    tables: List[str] = field(default_factory=list)  # "dataset.table" or table_id
    column_hits: List[str] = field(default_factory=list)  # "dataset.table.column"
    service_names: List[str] = field(default_factory=list)
    workflow_names: List[str] = field(default_factory=list)
    log_snippets: List[str] = field(default_factory=list)
    doc_titles: List[str] = field(default_factory=list)

    def has_any_list(self) -> bool:
        return any(
            [
                self.datasets,
                self.tables,
                self.column_hits,
                self.service_names,
                self.workflow_names,
                self.log_snippets,
                self.doc_titles,
            ]
        )


def extract_enrichment_from_events(events: List[Dict[str, Any]]) -> SynthesisEnrichment:
    e = SynthesisEnrichment()
    for ev in events:
        if not isinstance(ev, dict):
            continue
        payload = ev.get("payload") if isinstance(ev.get("payload"), dict) else {}
        data = payload.get("data")

        dicts: List[dict] = []
        _walk_for_dicts(data, dicts)

        for d in dicts:
            if isinstance(d.get("project_id"), str) and not e.project_id:
                e.project_id = d["project_id"]
            if isinstance(d.get("datasets"), list):
                for item in d["datasets"]:
                    if isinstance(item, dict) and item.get("dataset_id"):
                        e.datasets.append(str(item["dataset_id"]))
            if isinstance(d.get("tables"), list):
                ds = d.get("dataset_id") or payload.get("action")
                for item in d["tables"]:
                    if not isinstance(item, dict):
                        continue
                    tid = item.get("table_id")
                    if not tid:
                        continue
                    did = item.get("dataset_id") or d.get("dataset_id")
                    if did:
                        e.tables.append(f"{did}.{tid}")
                    else:
                        e.tables.append(str(tid))
            if isinstance(d.get("matches"), list):
                for item in d["matches"]:
                    if isinstance(item, dict):
                        ds, tb, col = (
                            item.get("dataset_id"),
                            item.get("table_id"),
                            item.get("column_name"),
                        )
                        if ds and tb and col:
                            e.column_hits.append(f"{ds}.{tb}.{col}")

        # Add: extract lists from `payload` by ev["id"] and each agent's payload shape (e.g. services).

    e.datasets = _unique_preserve(e.datasets)
    e.tables = _unique_preserve(e.tables)
    e.column_hits = _unique_preserve(e.column_hits)
    e.service_names = _unique_preserve(e.service_names)
    e.workflow_names = _unique_preserve(e.workflow_names)
    e.log_snippets = _unique_preserve(e.log_snippets)
    e.doc_titles = _unique_preserve(e.doc_titles)
    return e


def format_mandatory_data_block(enrichment: SynthesisEnrichment) -> str:
    """Markdown block for the prompt: data the synthesizer must integrate."""
    parts: List[str] = []
    if enrichment.project_id:
        parts.append(f"**GCP project:** `{enrichment.project_id}`")

    if enrichment.datasets:
        parts.append("### Datasets (full list — do not omit any)")
        parts.extend(f"- `{d}`" for d in enrichment.datasets)

    if enrichment.tables:
        parts.append("### Tables / objects")
        parts.extend(f"- `{t}`" for t in enrichment.tables)

    if enrichment.column_hits:
        parts.append("### Column matches")
        parts.extend(f"- `{c}`" for c in enrichment.column_hits[:80])
        if len(enrichment.column_hits) > 80:
            parts.append(f"- _(and {len(enrichment.column_hits) - 80} more)_")

    if enrichment.service_names:
        parts.append("### Ingestion microservices / functions")
        parts.extend(f"- `{s}`" for s in enrichment.service_names)

    if enrichment.workflow_names:
        parts.append("### Workflows / executions mentioned")
        parts.extend(f"- `{w}`" for w in enrichment.workflow_names[:50])

    if enrichment.log_snippets:
        parts.append("### Error messages (logs)")
        for i, msg in enumerate(enrichment.log_snippets[:15], 1):
            parts.append(f"{i}. {msg}")

    if enrichment.doc_titles:
        parts.append("### Documentation sources")
        parts.extend(f"- {t}" for t in enrichment.doc_titles)

    return "\n".join(parts) if parts else ""


def _coverage_ratio(items: List[str], text: str) -> float:
    if not items:
        return 1.0
    tl = text.lower()
    found = sum(1 for x in items if x.lower() in tl)
    return found / len(items)


def _append_section(title: str, bullets: List[str]) -> str:
    lines = [f"\n\n### {title}\n"]
    lines.extend(f"- `{b}`" if "`" not in b else f"- {b}" for b in bullets)
    return "\n".join(lines)


def merge_missing_structured_content(
    synthesizer_text: str,
    enrichment: SynthesisEnrichment,
    *,
    coverage_threshold: float = 0.82,
) -> str:
    """
    If the synthesizer text does not reflect most extracted items,
    append sections with full detail (without duplicating when already covered).
    """
    if not enrichment.has_any_list():
        return synthesizer_text

    text = (synthesizer_text or "").strip()
    append_parts: List[str] = []

    if enrichment.datasets and _coverage_ratio(enrichment.datasets, text) < coverage_threshold:
        append_parts.append(_append_section("Full dataset list", enrichment.datasets))

    if enrichment.tables and _coverage_ratio(enrichment.tables, text) < coverage_threshold:
        append_parts.append(_append_section("Table list", enrichment.tables[:200]))
        if len(enrichment.tables) > 200:
            append_parts.append(f"\n_(Total: {len(enrichment.tables)} tables; showing first 200.)_")

    if enrichment.column_hits and _coverage_ratio(enrichment.column_hits, text) < 0.7:
        append_parts.append(
            _append_section("Column matches", enrichment.column_hits[:100])
        )

    if enrichment.service_names and _coverage_ratio(enrichment.service_names, text) < 0.75:
        append_parts.append(_append_section("Ingestion services", enrichment.service_names))

    if enrichment.workflow_names and _coverage_ratio(enrichment.workflow_names, text) < 0.75:
        append_parts.append(_append_section("Workflows", enrichment.workflow_names))

    if not append_parts:
        return text

    sep = "\n\n---\n*Verified detail from specialist-returned data:*"
    return text + sep + "".join(append_parts)
