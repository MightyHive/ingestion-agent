"""API Researcher tool implementations — called via run_logged_tool in the agent."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import parse_qs, quote_plus, urlparse

import requests
from bs4 import BeautifulSoup

from models.tool_outputs import (
    AnalyzeJsonSchemaOutput,
    ReadDocumentationOutput,
    SchemaField,
    SearchResult,
    SearchWebOutput,
)


# ─────────────────────────────────────────────────────────────
# _search_web
# ─────────────────────────────────────────────────────────────

_SEARCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def _normalize_ddg_link(href: str) -> str:
    """Convert DuckDuckGo redirect links to direct URLs."""
    if not href:
        return ""
    parsed = urlparse(href)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        uddg = parse_qs(parsed.query).get("uddg", [])
        if uddg:
            return uddg[0]
    if href.startswith("//"):
        return f"https:{href}"
    return href


_THIRD_PARTY_DOMAINS = (
    "stackoverflow.com",
    "github.com/issues",
    "medium.com",
    "towardsdatascience.com",
    "data365.co",
    "blog.",
    "quora.com",
    "reddit.com/r/",
    "youtube.com/watch",
    "w3schools.com",
)

_OFFICIAL_DOMAIN_TOKENS = (
    "ads-api.",
    "marketing-api.",
    "marketingapi.",
    "business-api.",
    "developers.",
    "developer.",
    "api.",
    "learn.microsoft.com",
)


def _result_score(url: str, title: str) -> int:
    """Rank results: official paid-media API docs first, third-party blogs last."""
    haystack = f"{url} {title}".lower()
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    score = 0

    for token in _OFFICIAL_DOMAIN_TOKENS:
        if domain.startswith(token) or f".{token}" in domain:
            score += 5
            break

    for token in ("docs", "documentation", "api", "reference"):
        if token in parsed.path.lower():
            score += 3

    for token in ("official", "api documentation"):
        if token in haystack:
            score += 2

    for blocked in _THIRD_PARTY_DOMAINS:
        if blocked in haystack:
            score -= 6
            break

    return score


def _dedupe_and_rank(results: list[SearchResult], max_results: int) -> list[SearchResult]:
    seen: set[str] = set()
    cleaned: list[SearchResult] = []
    for r in results:
        href = _normalize_ddg_link((r.href or "").strip())
        if not href or href in seen:
            continue
        seen.add(href)
        cleaned.append(SearchResult(title=(r.title or "").strip(), href=href, body=(r.body or "").strip()))
    cleaned.sort(key=lambda r: _result_score(r.href, r.title), reverse=True)
    return cleaned[:max_results]


def _search_with_ddgs(query: str, max_results: int) -> list[SearchResult]:
    from ddgs import DDGS

    # Try multiple backends since some regions/providers are flaky.
    backends = ["api", "html", "lite", "auto"]
    last_error = None
    for backend in backends:
        try:
            with DDGS() as ddgs:
                raw = list(ddgs.text(query, max_results=max_results * 3, backend=backend))
            return [
                SearchResult(
                    title=item.get("title", ""),
                    href=item.get("href", ""),
                    body=item.get("body", ""),
                )
                for item in raw
            ]
        except Exception as e:  # pragma: no cover - network/provider dependent
            last_error = e
    if last_error:
        raise last_error
    return []


def _search_duckduckgo_html(query: str, max_results: int) -> list[SearchResult]:
    """Fallback parser for DuckDuckGo HTML page."""
    url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
    response = requests.get(url, headers=_SEARCH_HEADERS, timeout=20)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    results: list[SearchResult] = []
    for item in soup.select(".result"):
        link = item.select_one(".result__a")
        if not link:
            continue
        snippet_node = item.select_one(".result__snippet")
        results.append(
            SearchResult(
                title=link.get_text(" ", strip=True),
                href=link.get("href", ""),
                body=snippet_node.get_text(" ", strip=True) if snippet_node else "",
            )
        )
    return results[: max_results * 3]


def _extract_brand_hints(query: str) -> list[str]:
    q = (query or "").lower()
    hints: list[str] = []
    known = [
        "meta",
        "facebook",
        "instagram",
        "google ads",
        "google",
        "youtube",
        "tiktok",
        "reddit",
        "linkedin",
        "snapchat",
        "pinterest",
        "x ads",
        "twitter",
    ]
    for item in known:
        if item in q:
            hints.append(item)
    return hints


def _candidate_docs_urls(query: str) -> list[str]:
    hints = _extract_brand_hints(query)
    candidates: list[str] = []
    curated = {
        "reddit": [
            "https://www.reddit.com/dev/api/",
            "https://developers.reddit.com/docs/api/",
        ],
        "linkedin": [
            "https://learn.microsoft.com/en-us/linkedin/marketing/",
            "https://learn.microsoft.com/en-us/linkedin/marketing/getting-started",
            "https://learn.microsoft.com/en-us/linkedin/marketing/integrations/ads-reporting/ads-reporting",
            "https://developer.linkedin.com/",
        ],
        "snapchat": [
            "https://marketingapi.snapchat.com/docs/",
        ],
        "pinterest": [
            "https://developers.pinterest.com/docs/api/v5/",
        ],
        "twitter": [
            "https://developer.x.com/en/docs/x-api",
            "https://developer.x.com/en/docs/twitter-ads-api",
        ],
        "x ads": [
            "https://developer.x.com/en/docs/twitter-ads-api",
        ],
    }
    for hint in hints:
        candidates.extend(curated.get(hint, []))
    return list(dict.fromkeys(candidates))


def _probe_known_docs(query: str, max_results: int) -> list[SearchResult]:
    """Last-resort fallback when search engines are blocked."""
    results: list[SearchResult] = []
    for url in _candidate_docs_urls(query):
        try:
            response = requests.get(url, headers=_SEARCH_HEADERS, timeout=12, allow_redirects=True)
            if response.status_code < 500:
                results.append(
                    SearchResult(
                        title=f"Potential official docs ({response.status_code})",
                        href=response.url or url,
                        body=f"Discovered via paid-media fallback probe for query: {query}",
                    )
                )
        except Exception:
            continue
        if len(results) >= max_results:
            break
    return results


def _candidate_docs_unverified(query: str, max_results: int) -> list[SearchResult]:
    """Return unverified official-doc candidates when outbound search is blocked."""
    results: list[SearchResult] = []
    for url in _candidate_docs_urls(query)[:max_results]:
        results.append(
            SearchResult(
                title="Potential official docs (unverified)",
                href=url,
                body=f"Generated fallback URL for query: {query}",
            )
        )
    return results


def _search_web(query: str, max_results: int = 3) -> SearchWebOutput:
    """Search web docs with robust fallback strategy.

    Args:
        query: Search query string.
        max_results: Number of results to return.

    Returns:
        SearchWebOutput with title, href, and body per result.
    """
    try:
        errors: list[str] = []
        raw_results: list[SearchResult] = []

        try:
            raw_results = _search_with_ddgs(query, max_results=max_results)
        except Exception as e:
            errors.append(f"ddgs failed: {e}")

        if not raw_results:
            try:
                raw_results = _search_duckduckgo_html(query, max_results=max_results)
            except Exception as e:
                errors.append(f"duckduckgo html failed: {e}")

        # Always mix in curated official URLs so the ranker can prioritize them
        # over random blog posts returned by search engines.
        curated = _candidate_docs_unverified(query, max_results=max_results)
        raw_results.extend(curated)

        if not raw_results:
            raw_results = _probe_known_docs(query, max_results=max_results)
            if raw_results:
                errors.append("search engines unavailable, using fallback docs probe")

        results = _dedupe_and_rank(raw_results, max_results=max_results)
        if not results:
            raise RuntimeError("; ".join(errors) if errors else "No search results found")

        return SearchWebOutput(
            status="OK",
            msg=f"Found {len(results)} results for: {query}",
            query=query,
            results=results,
        )
    except Exception as e:
        return SearchWebOutput(
            status="ERR",
            msg=str(e),
            query=query,
            results=[],
        )


# ─────────────────────────────────────────────────────────────
# _read_documentation_url
# ─────────────────────────────────────────────────────────────

def _read_documentation_url(url: str, max_chars: int = 8000) -> ReadDocumentationOutput:
    """Fetch text from a URL or a local file path.

    Local paths (not starting with 'http') are read directly from disk —
    used for reference files (e.g. skills/paid-media-api/references/meta.md).

    Args:
        url: HTTP/HTTPS URL or local file path.
        max_chars: Maximum characters to return (default 8000).

    Returns:
        ReadDocumentationOutput with content and char_count.
    """
    # ── Local file ──────────────────────────────────────────
    if not url.startswith("http"):
        try:
            with open(url, "r", encoding="utf-8") as f:
                content = f.read()[:max_chars]
            return ReadDocumentationOutput(
                status="OK",
                msg=f"Read local file: {url} ({len(content)} chars)",
                url=url,
                content=content,
                char_count=len(content),
            )
        except FileNotFoundError:
            return ReadDocumentationOutput(
                status="ERR",
                msg=f"Local file not found: {url}",
                url=url,
                content=None,
                char_count=0,
            )
        except Exception as e:
            return ReadDocumentationOutput(
                status="ERR",
                msg=str(e),
                url=url,
                content=None,
                char_count=0,
            )

    # ── HTTP fetch ───────────────────────────────────────────
    headers = _SEARCH_HEADERS

    def _extract_text(raw_html: str) -> str:
        soup = BeautifulSoup(raw_html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer",
                          "header", "aside", "form", "iframe", "noscript"]):
            tag.decompose()
        lines = [
            line.strip()
            for line in soup.get_text(separator="\n").splitlines()
            if line.strip()
        ]
        return "\n".join(lines)[:max_chars]

    def _ok(content: str, source: str) -> ReadDocumentationOutput:
        return ReadDocumentationOutput(
            status="OK",
            msg=f"Fetched {source} ({len(content)} chars)",
            url=url,
            content=content,
            char_count=len(content),
        )

    # Attempt 1: normal fetch with SSL verification.
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        content = _extract_text(response.text)
        if content.strip():
            return _ok(content, url)
    except requests.exceptions.SSLError:
        # Attempt 2: retry without SSL verification (self-signed certs).
        try:
            response = requests.get(url, headers=headers, timeout=15, verify=False)
            response.raise_for_status()
            content = _extract_text(response.text)
            if content.strip():
                return _ok(content, f"{url} (ssl-skip)")
        except Exception:
            pass
    except Exception:
        pass

    # Attempt 3: text mirror for JS-heavy or bot-blocked sites.
    try:
        mirror_url = f"https://r.jina.ai/{url}"
        mirror_response = requests.get(mirror_url, headers=headers, timeout=20)
        mirror_response.raise_for_status()
        mirror_content = (mirror_response.text or "")[:max_chars]
        if mirror_content.strip():
            return _ok(mirror_content, f"mirror:{url}")
    except Exception:
        pass

    return ReadDocumentationOutput(
        status="ERR",
        msg=f"All fetch strategies failed for {url}",
        url=url,
        content=None,
        char_count=0,
    )


# ─────────────────────────────────────────────────────────────
# _analyze_json_schema
# ─────────────────────────────────────────────────────────────

_BQ_TYPE_MAP: dict[type, str] = {
    int:        "INTEGER",
    float:      "FLOAT",
    str:        "STRING",
    bool:       "BOOLEAN",
    list:       "REPEATED",
    dict:       "RECORD",
    type(None): "STRING",
}


def _infer_fields(obj: Any, prefix: str = "") -> list[SchemaField]:
    """Recursively walk a JSON object and infer field names + BigQuery types."""
    if not isinstance(obj, dict):
        return []

    fields = []
    for key, value in obj.items():
        full_key = f"{prefix}.{key}" if prefix else key
        bq_type = _BQ_TYPE_MAP.get(type(value), "STRING")

        
        if isinstance(value, str):
            try:
                float(value)
                bq_type = "FLOAT"
            except ValueError:
                pass

        
        if isinstance(value, str) and len(value) == 10 and value[4] == "-":
            bq_type = "DATE"

        fields.append(SchemaField(
            api_field=full_key,
            type=bq_type,
            sample=str(value)[:60],
        ))

        if isinstance(value, dict):
            fields.extend(_infer_fields(value, full_key))
        elif isinstance(value, list) and value and isinstance(value[0], dict):
            fields.extend(_infer_fields(value[0], f"{full_key}[]"))

    return fields


def _analyze_json_schema(json_str: str) -> AnalyzeJsonSchemaOutput:
    """Infer field names, BigQuery types and sample values from a raw JSON string.

    Args:
        json_str: Raw JSON string from an API response (object or array).

    Returns:
        AnalyzeJsonSchemaOutput with fields and field_count.
    """
    try:
        data = json.loads(json_str)
        if isinstance(data, list):
            data = data[0] if data else {}
        fields = _infer_fields(data)
        return AnalyzeJsonSchemaOutput(
            status="OK",
            msg=f"Inferred {len(fields)} fields",
            fields=fields,
            field_count=len(fields),
        )
    except json.JSONDecodeError as e:
        return AnalyzeJsonSchemaOutput(
            status="ERR",
            msg=f"JSON parse error: {e}",
            fields=[],
            field_count=0,
        )