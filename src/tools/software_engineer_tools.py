"""Connector-library helpers for listing, validating, saving, and executing local connectors.

All public-facing behavior is exposed via ``_*`` functions that return serialized tool payloads
(``dict``) suitable for the Software Engineer agent and logging. Paths are constrained under
``src/connector_library``; connector names follow ``[source]_[type]`` with a ``fetch(params, context)``
entrypoint that honors ``params["fields"]``.
"""

from __future__ import annotations

import ast
import importlib.util
import re
from difflib import get_close_matches
from pathlib import Path
from typing import Any, Dict, List, Tuple

import uuid

from models.tool_outputs import (
    CloudFunctionCodeToolOutput,
    ConnectorExecuteToolOutput,
    ConnectorListToolOutput,
    ConnectorReadToolOutput,
    ConnectorRef,
    ConnectorRunResult,
    ConnectorSaveToolOutput,
    ConnectorSearchToolOutput,
    ConnectorValidateToolOutput,
    ConnectorValidationOutput,
    EnvironmentVariablesToolOutput,
    GoldStandardCodeToolOutput,
    StageConnectorToolOutput,
    dump_tool_output,
)

STAGING_ROOT = Path(__file__).resolve().parents[1] / "pending_deploy"


CONNECTOR_ROOT = Path(__file__).resolve().parents[1] / "connector_library"


def _sanitize_segment(value: str) -> str:
    """Normalize a string to lowercase snake_case safe for folder and file names."""
    normalized = re.sub(r"[^a-zA-Z0-9_]+", "_", value.strip().lower())
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized or "unnamed"


def _normalize_source(raw_source: str) -> str:
    """Normalize a data source label to a single path segment (alias of sanitization)."""
    return _sanitize_segment(raw_source)


def _normalize_connector_name(raw_name: str) -> str:
    """Normalize connector stem; strip long numeric date-like suffixes for stable reuse."""
    candidate = _sanitize_segment(raw_name)
    # Keep names reusable: collapse very numeric tails like "..._20260325".
    candidate = re.sub(r"(_\d{4,})+$", "", candidate).strip("_")
    return candidate or "fetch_data"


def _matches_connector_pattern(source: str, connector_name: str) -> bool:
    """Return True if ``connector_name`` matches ``[source]_[type]`` (with optional extra segments)."""
    # Required naming convention: [source]_[type] (optionally with extra suffixes).
    pattern = rf"^{re.escape(source)}_[a-z0-9]+(?:_[a-z0-9]+)*$"
    return re.fullmatch(pattern, connector_name) is not None


def _all_connector_files(root: Path = CONNECTOR_ROOT) -> List[Path]:
    """Return sorted paths to every ``*.py`` file under ``root`` (empty if missing)."""
    if not root.exists():
        return []
    return sorted(root.glob("**/*.py"))


def _connector_ref_from_path(path: Path) -> ConnectorRef:
    """Build a ``ConnectorRef`` from a library path (parent folder = source, stem = name)."""
    source = path.parent.name
    return ConnectorRef(
        connector_name=path.stem,
        source=source,
        file_path=str(path),
    )


def _extract_def_names(code: str) -> List[str]:
    """List top-level function names in Python source (raises ``SyntaxError`` if parse fails)."""
    tree = ast.parse(code)
    return [node.name for node in tree.body if isinstance(node, ast.FunctionDef)]


def _validate_connector_code_struct(code: str) -> ConnectorValidationOutput:
    """Static validation: syntax, ``fetch`` presence, ``fetch(params, context)``, and ``fields`` reference."""
    try:
        defs = _extract_def_names(code)
    except SyntaxError as exc:
        return ConnectorValidationOutput(
            valid=False,
            function_defs=[],
            has_fetch_entrypoint=False,
            has_required_signature=False,
            uses_fields_parameter=False,
            error=f"{exc.msg} (line {exc.lineno})",
        )

    has_fetch = "fetch" in defs
    if not defs:
        return ConnectorValidationOutput(
            valid=False,
            function_defs=[],
            has_fetch_entrypoint=False,
            has_required_signature=False,
            uses_fields_parameter=False,
            error="No function definitions found.",
        )
    if not has_fetch:
        return ConnectorValidationOutput(
            valid=False,
            function_defs=defs,
            has_fetch_entrypoint=False,
            has_required_signature=False,
            uses_fields_parameter=False,
            error="Connector must define a top-level callable named `fetch`.",
        )

    tree = ast.parse(code)
    fetch_node = next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "fetch"
        ),
        None,
    )
    has_required_signature = False
    uses_fields_parameter = False
    if fetch_node is not None:
        arg_names = [arg.arg for arg in fetch_node.args.args]
        has_required_signature = arg_names[:2] == ["params", "context"]

        for node in ast.walk(fetch_node):
            if isinstance(node, ast.Constant) and node.value == "fields":
                uses_fields_parameter = True
                break
            if isinstance(node, ast.Name) and node.id == "fields":
                uses_fields_parameter = True
                break

    if not has_required_signature:
        return ConnectorValidationOutput(
            valid=False,
            function_defs=defs,
            has_fetch_entrypoint=True,
            has_required_signature=False,
            uses_fields_parameter=uses_fields_parameter,
            error="`fetch` must use signature `fetch(params, context)`.",
        )
    if not uses_fields_parameter:
        return ConnectorValidationOutput(
            valid=False,
            function_defs=defs,
            has_fetch_entrypoint=True,
            has_required_signature=True,
            uses_fields_parameter=False,
            error="Connector must reference `fields` from input params.",
        )

    return ConnectorValidationOutput(
        valid=True,
        function_defs=defs,
        has_fetch_entrypoint=True,
        has_required_signature=True,
        uses_fields_parameter=True,
        error=None,
    )


def _resolve_within_connector_root(file_path: str) -> Tuple[bool, Path]:
    """Return (allowed, resolved_path) where allowed means ``resolved_path`` is under ``CONNECTOR_ROOT``."""
    resolved = Path(file_path).resolve()
    try:
        resolved.relative_to(CONNECTOR_ROOT.resolve())
        return True, resolved
    except Exception:
        return False, resolved


def _normalize_connector_result(raw: Any) -> ConnectorRunResult:
    """Coerce arbitrary ``fetch`` return value into a structured ``ConnectorRunResult``."""
    if isinstance(raw, dict):
        status = raw.get("status") or raw.get("st") or "OK"
        code = raw.get("code")
        records = raw.get("records")
        if not isinstance(records, list):
            data_rows = raw.get("data")
            records = data_rows if isinstance(data_rows, list) else []
        next_cursor = raw.get("next_cursor")
        meta = raw.get("meta")
        if not isinstance(meta, dict):
            meta = {}
        errors = raw.get("errors")
        if isinstance(errors, str):
            errors_list = [errors]
        elif isinstance(errors, list):
            errors_list = [str(item) for item in errors]
        else:
            errors_list = []
        return ConnectorRunResult(
            status=status if status in {"OK", "WARN", "ERR"} else "WARN",
            code=str(code) if code is not None else None,
            records=records if isinstance(records, list) else [],
            next_cursor=str(next_cursor) if next_cursor is not None else None,
            meta=meta,
            errors=errors_list,
        )
    if isinstance(raw, list):
        dict_rows = [item for item in raw if isinstance(item, dict)]
        return ConnectorRunResult(status="OK", records=dict_rows, meta={})
    return ConnectorRunResult(
        status="WARN",
        code="NON_STANDARD_CONNECTOR_RESULT",
        records=[],
        meta={"raw_result": str(raw)},
        errors=["Connector returned non-dict payload; output normalized."],
    )


def _list_connectors(source: str | None = None) -> Dict[str, Any]:
    """List connector modules; if ``source`` is set, only that subdirectory is scanned."""
    normalized_source = _normalize_source(source) if source else None
    root = CONNECTOR_ROOT / normalized_source if normalized_source else CONNECTOR_ROOT
    connectors = [_connector_ref_from_path(path) for path in _all_connector_files(root)]
    return dump_tool_output(
        ConnectorListToolOutput(
            status="OK",
            code="CONNECTORS_LISTED",
            msg="Connector inventory collected.",
            connector_root=str(CONNECTOR_ROOT),
            connectors=connectors,
        )
    )


def _find_connector(name: str) -> Dict[str, Any]:
    """Find connector by normalized stem; exact match or fuzzy suggestions in ``close_matches``."""
    needle = _normalize_connector_name(name)
    files = _all_connector_files()
    by_name = {path.stem: path for path in files}
    exact = by_name.get(needle)
    if exact:
        return dump_tool_output(
            ConnectorSearchToolOutput(
                status="OK",
                code="CONNECTOR_FOUND_EXACT",
                connector_name=needle,
                connector=_connector_ref_from_path(exact),
                close_matches=[],
            )
        )

    candidates = sorted(by_name.keys())
    close = get_close_matches(needle, candidates, n=5, cutoff=0.55)
    return dump_tool_output(
        ConnectorSearchToolOutput(
            status="WARN",
            code="CONNECTOR_NOT_FOUND",
            msg="Connector not found in local library.",
            connector_name=needle,
            connector=None,
            close_matches=close,
        )
    )


def _read_connector(path: str) -> Dict[str, Any]:
    """Read file text if path is inside the connector library; otherwise return path error."""
    is_allowed, resolved_path = _resolve_within_connector_root(path)
    if not is_allowed:
        return dump_tool_output(
            ConnectorReadToolOutput(
                status="ERR",
                code="PATH_OUTSIDE_CONNECTOR_LIBRARY",
                msg="Requested path is outside connector library root.",
                connector=ConnectorRef(
                    connector_name=resolved_path.stem or "unknown",
                    source=resolved_path.parent.name or "unknown",
                    file_path=str(resolved_path),
                ),
                code_text="",
            )
        )
    if not resolved_path.exists():
        return dump_tool_output(
            ConnectorReadToolOutput(
                status="ERR",
                code="CONNECTOR_FILE_NOT_FOUND",
                msg="Connector file does not exist.",
                connector=ConnectorRef(
                    connector_name=resolved_path.stem or "unknown",
                    source=resolved_path.parent.name or "unknown",
                    file_path=str(resolved_path),
                ),
                code_text="",
            )
        )
    return dump_tool_output(
        ConnectorReadToolOutput(
            status="OK",
            code="CONNECTOR_READ",
            connector=_connector_ref_from_path(resolved_path),
            code_text=resolved_path.read_text(encoding="utf-8"),
        )
    )


def _normalize_connector_source_code(code: str) -> str:
    """Normalize LLM-produced Python before parse/write (newlines, BOM, smart quotes, over-escaping)."""
    text = (code or "").replace("\r\n", "\n").replace("\r", "\n")
    if text.startswith("\ufeff"):
        text = text[1:]
    text = (
        text.replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2018", "'")
        .replace("\u2019", "'")
    )
    # Fix escaped single quotes from LLM over-escaping when passing code as string argument
    text = text.replace("\\'", "'")
    return text


def _validate_connector_code(code: str) -> Dict[str, Any]:
    """Run structural validation and return a serialized ``ConnectorValidateToolOutput``."""
    code = _normalize_connector_source_code(code)
    validation = _validate_connector_code_struct(code)
    status = "OK" if validation.valid else "ERR"
    status_code = "CONNECTOR_CODE_VALID" if validation.valid else "CONNECTOR_CODE_INVALID"
    return dump_tool_output(
        ConnectorValidateToolOutput(
            status=status,
            code=status_code,
            validation=validation,
        )
    )


def _save_connector(
    source: str,
    name: str,
    code: str,
    overwrite: bool = False,
    skip_validation: bool = True,
) -> Dict[str, Any]:
    """Write ``connector_library/<source>/<name>.py``; enforce naming convention.

    Validation is skipped by default (``skip_validation=True``) because a downstream
    QA Agent is responsible for syntax checks and security scans. Set ``skip_validation=False``
    to gate on structural validation before persisting.
    """
    code = _normalize_connector_source_code(code)
    source_name = _normalize_source(source)
    connector_name = _normalize_connector_name(name)
    if not _matches_connector_pattern(source_name, connector_name):
        return dump_tool_output(
            ConnectorSaveToolOutput(
                status="ERR",
                code="INVALID_CONNECTOR_NAME_PATTERN",
                msg=(
                    "Connector name must follow [source]_[type] naming convention, "
                    f"e.g. `{source_name}_analytics`."
                ),
                connector=ConnectorRef(
                    connector_name=connector_name,
                    source=source_name,
                    file_path=str(CONNECTOR_ROOT / source_name / f"{connector_name}.py"),
                ),
                validation=ConnectorValidationOutput(
                    valid=False,
                    function_defs=[],
                    has_fetch_entrypoint=False,
                    has_required_signature=False,
                    uses_fields_parameter=False,
                    error="Connector name does not follow required naming pattern.",
                ),
            )
        )

    if skip_validation:
        validation = ConnectorValidationOutput(
            valid=True,
            function_defs=[],
            has_fetch_entrypoint=True,
            has_required_signature=True,
            uses_fields_parameter=True,
            error=None,
        )
    else:
        validation = _validate_connector_code_struct(code)
        if not validation.valid:
            return dump_tool_output(
                ConnectorSaveToolOutput(
                    status="ERR",
                    code="CONNECTOR_VALIDATION_FAILED",
                    msg="Connector code is invalid and was not saved.",
                    connector=ConnectorRef(
                        connector_name=connector_name,
                        source=source_name,
                        file_path=str(CONNECTOR_ROOT / source_name / f"{connector_name}.py"),
                    ),
                    validation=validation,
                )
            )

    target_dir = CONNECTOR_ROOT / source_name
    target_path = target_dir / f"{connector_name}.py"
    if target_path.exists() and not overwrite:
        return dump_tool_output(
            ConnectorSaveToolOutput(
                status="WARN",
                code="CONNECTOR_ALREADY_EXISTS",
                msg="Connector already exists. Use overwrite=True to update.",
                connector=_connector_ref_from_path(target_path),
                validation=validation,
            )
        )

    target_dir.mkdir(parents=True, exist_ok=True)
    try:
        target_path.write_text(code, encoding="utf-8")
    except OSError as exc:
        return dump_tool_output(
            ConnectorSaveToolOutput(
                status="ERR",
                code="CONNECTOR_WRITE_FAILED",
                msg=f"Could not write connector file: {exc}",
                connector=_connector_ref_from_path(target_path),
                validation=validation,
            )
        )
    return dump_tool_output(
        ConnectorSaveToolOutput(
            status="OK",
            code="CONNECTOR_SAVED",
            msg="Connector saved in local library.",
            connector=_connector_ref_from_path(target_path),
            validation=validation,
        )
    )


def _get_gold_standard_code(channel_name: str) -> Dict[str, Any]:
    """Resolve a connector by name and return its full source as the approved gold-standard template."""
    lookup = _find_connector(channel_name)
    if lookup.get("status") != "OK":
        return dump_tool_output(
            GoldStandardCodeToolOutput(
                status="WARN",
                code="GOLD_STANDARD_NOT_FOUND",
                msg="No approved template found for requested channel.",
                connector=None,
                code_text=None,
                close_matches=lookup.get("close_matches", []),
            )
        )

    connector_info = lookup.get("connector") or {}
    file_path = str(connector_info.get("file_path", ""))
    read = _read_connector(file_path)
    if read.get("status") != "OK":
        return dump_tool_output(
            GoldStandardCodeToolOutput(
                status="ERR",
                code="GOLD_STANDARD_READ_ERROR",
                msg=read.get("msg") or "Could not read approved template.",
                connector=connector_info if isinstance(connector_info, dict) else None,
                code_text=None,
                close_matches=[],
            )
        )

    return dump_tool_output(
        GoldStandardCodeToolOutput(
            status="OK",
            code="GOLD_STANDARD_LOADED",
            msg="Approved template code loaded.",
            connector=read.get("connector"),
            code_text=read.get("code_text"),
            close_matches=[],
        )
    )


def _stage_connector_instance(
    source: str,
    connector_name: str,
    fields: List[str],
    endpoint_id: str | None = None,
    target_table: str | None = None,
) -> Dict[str, Any]:
    """Stage a connector instance with hardcoded fields for deployment.

    Reads the generic connector from the library, injects the user-selected fields,
    and writes a temporary file to ``pending_deploy/`` for the DevOps agent to deploy.
    The staged file is deleted after deployment.

    Args:
        source: Data source slug (e.g. ``meta``, ``tiktok``).
        connector_name: Name of the connector in the library (e.g. ``meta_marketing_performance``).
        fields: Fields from Data Architect DDL to hardcode into the staged instance.
        endpoint_id: Identifier for this endpoint (e.g. "insights", "campaigns"). Defaults to connector_name.
        target_table: BigQuery table this connector writes to (e.g. "raw_meta.insights_raw").

    Returns:
        Tool dict with ``library_connector``, ``staged_path``, ``fields_configured``, ``endpoint_id``, ``target_table``.
    """
    effective_endpoint_id = endpoint_id or connector_name
    normalized_fields = [str(f).strip() for f in fields if str(f).strip()]
    if not normalized_fields:
        return dump_tool_output(
            StageConnectorToolOutput(
                status="ERR",
                code="EMPTY_FIELDS_SELECTION",
                msg="At least one field must be provided.",
                library_connector="",
                staged_path="",
                fields_configured=[],
                staged_connector_name="",
            )
        )

    search_result = _find_connector(connector_name)
    if search_result.get("status") != "OK":
        close = search_result.get("close_matches", [])
        return dump_tool_output(
            StageConnectorToolOutput(
                status="ERR",
                code="CONNECTOR_NOT_FOUND",
                msg=f"Connector '{connector_name}' not found in library. Close matches: {close}",
                library_connector="",
                staged_path="",
                fields_configured=[],
                staged_connector_name="",
            )
        )

    library_path = search_result.get("connector", {}).get("file_path", "")
    if not library_path:
        return dump_tool_output(
            StageConnectorToolOutput(
                status="ERR",
                code="CONNECTOR_PATH_MISSING",
                msg="Connector found but file_path is missing.",
                library_connector="",
                staged_path="",
                fields_configured=[],
                staged_connector_name="",
            )
        )

    read_result = _read_connector(library_path)
    if read_result.get("status") != "OK":
        return dump_tool_output(
            StageConnectorToolOutput(
                status="ERR",
                code="CONNECTOR_READ_FAILED",
                msg=f"Failed to read connector: {read_result.get('msg', 'unknown error')}",
                library_connector=library_path,
                staged_path="",
                fields_configured=[],
                staged_connector_name="",
            )
        )

    template_code = read_result.get("code_text", "")
    if not template_code.strip():
        return dump_tool_output(
            StageConnectorToolOutput(
                status="ERR",
                code="CONNECTOR_EMPTY",
                msg="Connector file is empty.",
                library_connector=library_path,
                staged_path="",
                fields_configured=[],
                staged_connector_name="",
            )
        )

    updated_code = template_code
    fields_literal = repr(normalized_fields)

    if re.search(r"DEFAULT_FIELDS\s*=\s*\[.*?\]", updated_code, flags=re.DOTALL):
        updated_code = re.sub(
            r"DEFAULT_FIELDS\s*=\s*\[.*?\]",
            f"DEFAULT_FIELDS = {fields_literal}",
            updated_code,
            flags=re.DOTALL,
        )

    STAGING_ROOT.mkdir(parents=True, exist_ok=True)

    instance_id = uuid.uuid4().hex[:8]
    staged_name = f"{_normalize_connector_name(connector_name)}_{instance_id}.py"
    staged_path = STAGING_ROOT / staged_name

    staged_path.write_text(updated_code, encoding="utf-8")

    return dump_tool_output(
        StageConnectorToolOutput(
            status="OK",
            code="STAGED_FOR_DEPLOY",
            msg=f"Connector staged for deployment with {len(normalized_fields)} fields.",
            library_connector=library_path,
            staged_path=str(staged_path),
            fields_configured=normalized_fields,
            staged_connector_name=staged_name,
            endpoint_id=effective_endpoint_id,
            target_table=target_table,
        )
    )


def _parse_api_research(api_research: Dict[str, Any] | None, source_name: str) -> Dict[str, Any]:
    """Extract scaffold hints from an ``APIResearcherPayload``-shaped dict."""
    ctx = api_research or {}

    # ── Endpoint ──────────────────────────────────────────────────────────────
    reporting_endpoint = str(ctx.get("reporting_endpoint", "")).strip()
    http_method = "GET"
    base_url = ""

    relative_endpoint_path = ""
    if reporting_endpoint:
        parts = reporting_endpoint.split(None, 1)
        if len(parts) == 2 and parts[0].upper() in {"GET", "POST", "PUT", "DELETE", "PATCH"}:
            http_method = parts[0].upper()
            endpoint_part = parts[1].strip()
        else:
            endpoint_part = reporting_endpoint
        el = endpoint_part.lower()
        if el.startswith("http://") or el.startswith("https://"):
            base_url = endpoint_part
        elif endpoint_part:
            relative_endpoint_path = endpoint_part
            base_url = ""

    # ── Auth ──────────────────────────────────────────────────────────────────
    auth_obj = ctx.get("auth") or {}
    auth_method = str(auth_obj.get("method", "")).strip() if isinstance(auth_obj, dict) else ""
    required_credentials = [
        str(c).strip()
        for c in (auth_obj.get("required_credentials") or [] if isinstance(auth_obj, dict) else [])
        if str(c).strip()
    ]

    env_vars: List[str] = [
        f"{source_name.upper()}_{_sanitize_segment(cred).upper()}"
        for cred in required_credentials
    ]
    if not env_vars:
        env_vars = [f"{source_name.upper()}_ACCESS_TOKEN"]

    is_oauth = "oauth" in auth_method.lower()

    # ── Fields ────────────────────────────────────────────────────────────────
    canonical_api_fields: List[str] = []
    for field in ctx.get("available_fields") or []:
        if not isinstance(field, dict) or not field.get("canonical_match"):
            continue
        api_field = str(field.get("api_field", "")).strip()
        if api_field and api_field != "NOT_AVAILABLE" and not api_field.startswith("DERIVED"):
            canonical_api_fields.append(api_field)

    default_fields = canonical_api_fields or ["id"]

    # ── Scalar hints ──────────────────────────────────────────────────────────
    pagination_hint = str(ctx.get("pagination", "")).strip()
    platform = str(ctx.get("platform", "")).strip()
    rate_limit = str(ctx.get("rate_limit", "")).strip()

    return {
        "base_url": base_url,
        "relative_endpoint_path": relative_endpoint_path,
        "http_method": http_method,
        "auth_method": auth_method,
        "is_oauth": is_oauth,
        "env_vars": env_vars,
        "default_fields": default_fields,
        "pagination_hint": pagination_hint,
        "platform": platform,
        "rate_limit": rate_limit,
    }


def _format_api_spec_block(api_spec: Dict[str, Any] | None) -> str:
    """Human-readable block for generated module header (paired with Bronze DDL)."""
    if not api_spec or not isinstance(api_spec, dict):
        return ""
    lines = [
        "API SPECIFICATIONS (persisted contract):",
        f"  Base URL: {api_spec.get('base_url', '')}",
        f"  Auth type: {api_spec.get('auth_type', '')}",
        f"  Pagination: {api_spec.get('pagination', '')}",
        f"  HTTP method: {api_spec.get('method', '')}",
    ]
    hrs = api_spec.get("headers_required")
    if isinstance(hrs, list) and hrs:
        lines.append(f"  Headers required: {', '.join(str(h) for h in hrs)}")
    else:
        lines.append("  Headers required: (none beyond auth)")
    return "\n".join(lines)


def _apply_api_spec_overrides(
    parsed: Dict[str, Any],
    api_spec: Dict[str, Any] | None,
) -> None:
    """Prefer explicit ``api_spec`` fields over inferred ``api_research`` hints when present."""
    if not api_spec or not isinstance(api_spec, dict):
        return
    bu = str(api_spec.get("base_url") or "").strip()
    if bu:
        parsed["base_url"] = bu
    m = str(api_spec.get("method") or "").strip().upper()
    if m in {"GET", "POST", "PUT", "DELETE", "PATCH"}:
        parsed["http_method"] = m
    pag = str(api_spec.get("pagination") or "").strip()
    if pag:
        parsed["pagination_hint"] = pag
    at = str(api_spec.get("auth_type") or "").strip()
    if at:
        parsed["auth_method"] = at


def _write_cf_code(
    source: str,
    connector_type: str,
    api_research: Dict[str, Any] | None = None,
    table_ddl: str | None = None,
    api_spec: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Generate ``main_py`` + ``requirements_txt`` scaffold from API research context.

    Expects the ``APIResearcherPayload`` shape: ``reporting_endpoint``,
    ``auth`` object, ``available_fields``, ``pagination``, ``platform``, ``rate_limit``.

    ``table_ddl`` is optional persisted Bronze DDL from LangGraph ``artifacts`` when the
    current turn's ``event_bus`` no longer carries the Data Architect payload.

    ``api_spec`` is the persisted contract from the API Researcher (``artifacts['api_spec']``);
    when set, it overrides endpoint/method/pagination/auth hints and is embedded in the header.

    If ``reporting_endpoint`` is a **relative** path template (e.g.
    ``GET /{account_id}/insights``) and ``api_spec.base_url`` supplies the API root, the
    scaffold joins root + path and replaces ``{placeholder}`` tokens from ``params`` and
    ``context`` (longest keys first). Absolute ``https://…`` endpoints are used as-is.
    """
    source_name = _normalize_source(source)
    type_name = _sanitize_segment(connector_type)
    connector_name = _normalize_connector_name(f"{source_name}_{type_name}")
    if not _matches_connector_pattern(source_name, connector_name):
        return dump_tool_output(
            CloudFunctionCodeToolOutput(
                status="ERR",
                code="INVALID_CONNECTOR_NAME_PATTERN",
                msg="Generated connector name does not follow [source]_[type].",
                connector_name=connector_name,
                source=source_name,
                main_py="",
                requirements_txt="",
                suggested_env_vars=[],
            )
        )

    r = _parse_api_research(api_research, source_name)
    _apply_api_spec_overrides(r, api_spec)
    base_url: str = r["base_url"]
    http_method: str = r["http_method"]
    env_vars: List[str] = r["env_vars"]
    default_fields: List[str] = r["default_fields"]
    pagination_hint: str = r["pagination_hint"]
    platform: str = r["platform"]
    rate_limit: str = r["rate_limit"]
    auth_method: str = r["auth_method"]
    relative_endpoint_path: str = str(r.get("relative_endpoint_path") or "").strip()

    fields_repr = repr(default_fields)

    # ── Build header block ────────────────────────────────────────────────────
    header_comment = f'"""{source_name}_{type_name} connector'
    if platform:
        header_comment += f" — {platform}"
    header_comment += '.\n\nAuto-scaffolded from API research.'
    if pagination_hint:
        header_comment += f"\nPagination: {pagination_hint}"
    if rate_limit:
        header_comment += f"\nRate limit: {rate_limit}"
    if auth_method:
        header_comment += f"\nAuth: {auth_method}"
    if table_ddl and str(table_ddl).strip():
        ddl_text = str(table_ddl).strip().replace('"""', "'''")
        if len(ddl_text) > 6000:
            ddl_text = ddl_text[:6000] + "\n... [truncated]"
        header_comment += f"\n\nBronze DDL (persisted from Data Architect):\n{ddl_text}"
    spec_block = _format_api_spec_block(api_spec)
    if spec_block:
        header_comment += f"\n\n{spec_block}"
    header_comment += '\n"""'

    # ── Build auth block ──────────────────────────────────────────────────────
    token_load_lines = "\n".join(
        f'    {_sanitize_segment(v).lower()} = os.getenv("{v}")'
        for v in env_vars
    )
    missing_check_cond = " or ".join(
        f"not {_sanitize_segment(v).lower()}" for v in env_vars
    )
    missing_names = ", ".join(env_vars)

    auth_header_line = f'        "Authorization": f"Bearer {{{_sanitize_segment(env_vars[0]).lower()}}}",'

    # ── Pagination cursor block ───────────────────────────────────────────────
    pagination_lower = pagination_hint.lower()
    if "cursor" in pagination_lower or "after" in pagination_lower or "paging" in pagination_lower:
        cursor_extract = '    next_cursor = None\n'
        cursor_extract += '    if isinstance(body, dict):\n'
        cursor_extract += '        paging = body.get("paging", {})\n'
        cursor_extract += '        cursors = paging.get("cursors", {}) if isinstance(paging, dict) else {}\n'
        cursor_extract += '        next_cursor = cursors.get("after") or body.get("next_cursor")'
    elif "page" in pagination_lower:
        cursor_extract = '    next_cursor = None\n'
        cursor_extract += '    if isinstance(body, dict):\n'
        cursor_extract += '        page_info = body.get("page_info", body.get("paging", {}))\n'
        cursor_extract += '        if isinstance(page_info, dict) and page_info.get("has_more", False):\n'
        cursor_extract += '            next_cursor = str(int(params.get("cursor", "1")) + 1)'
    else:
        cursor_extract = '    next_cursor = body.get("next_cursor") if isinstance(body, dict) else None'

    if relative_endpoint_path:
        path_lit = repr(relative_endpoint_path)
        if base_url.strip():
            root_assign = f"    root = {repr(base_url)}\n"
        else:
            root_assign = '    root = str(context.get("base_url") or "").strip()\n'
        url_build_block = (
            f"{root_assign}"
            f"    path_tpl = {path_lit}\n"
            "    subs: dict[str, Any] = {**context, **params}\n"
            "    path = path_tpl\n"
            "    for key in sorted(subs.keys(), key=lambda k: len(str(k)), reverse=True):\n"
            "        if isinstance(key, str):\n"
            '            token = "{" + key + "}"\n'
            "            if token in path:\n"
            "                val = subs.get(key)\n"
            '                path = path.replace(token, "" if val is None else str(val))\n'
            "    if not root:\n"
            "        return {\n"
            '            "status": "ERR",\n'
            '            "code": "MISSING_BASE_URL",\n'
            '            "records": [],\n'
            '            "errors": [\n'
            '                "Set api_spec.base_url (persisted) or context.base_url; "\n'
            '                "reporting_endpoint was a relative path template."\n'
            '            ],\n'
            "        }\n"
            "    url = f\"{root.rstrip('/')}/{path.lstrip('/')}\" if path else root\n"
        )
    elif base_url:
        url_build_block = f"    url = {repr(base_url)}\n"
    else:
        url_build_block = '    url = str(context.get("base_url") or "").strip()\n'

    if http_method == "POST":
        request_line = "    response = requests.post(url, headers=headers, json=query, timeout=60)"
    else:
        request_line = "    response = requests.get(url, headers=headers, params=query, timeout=60)"

    main_py = (
        f"{header_comment}\n\n"
        "from __future__ import annotations\n\n"
        "import os\n"
        "from typing import Any\n\n"
        "import requests\n\n\n"
        f"DEFAULT_FIELDS = {fields_repr}\n\n\n"
        "def fetch(params: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:\n"
        '    requested_fields = params.get("fields", DEFAULT_FIELDS)\n'
        "    if not isinstance(requested_fields, list) or not requested_fields:\n"
        "        return {\n"
        '            "status": "ERR",\n'
        '            "code": "FIELDS_REQUIRED",\n'
        '            "records": [],\n'
        '            "errors": ["params.fields must be a non-empty list"],\n'
        "        }\n\n"
        f"{token_load_lines}\n"
        f"    if {missing_check_cond}:\n"
        "        return {\n"
        '            "status": "ERR",\n'
        '            "code": "MISSING_CREDENTIALS",\n'
        '            "records": [],\n'
        f'            "errors": ["Missing required env vars: {missing_names}"],\n'
        "        }\n\n"
        "    headers = {\n"
        f"{auth_header_line}\n"
        "    }\n"
        "    query = {\n"
        '        "fields": ",".join(requested_fields),\n'
        "    }\n"
        '    cursor = params.get("cursor")\n'
        "    if cursor is not None and str(cursor).strip() != \"\":\n"
        '        if "after" in '
        + repr(pagination_lower)
        + ":\n"
        '            query["after"] = str(cursor)\n'
        "        else:\n"
        '            query["cursor"] = str(cursor)\n\n'
        f"{url_build_block}\n"
        "    if not url:\n"
        "        return {\n"
        '            "status": "ERR",\n'
        '            "code": "MISSING_URL",\n'
        '            "records": [],\n'
        '            "errors": ["No request URL: set reporting_endpoint or context.base_url."],\n'
        "        }\n\n"
        f"{request_line}\n"
        "    if response.status_code >= 400:\n"
        "        return {\n"
        '            "status": "ERR",\n'
        '            "code": "UPSTREAM_HTTP_ERROR",\n'
        '            "records": [],\n'
        '            "errors": [f"HTTP {response.status_code}: {response.text[:300]}"],\n'
        "        }\n\n"
        "    body = response.json()\n"
        '    records = body.get("data", []) if isinstance(body, dict) else []\n'
        f"{cursor_extract}\n"
        "    return {\n"
        '        "status": "OK",\n'
        '        "code": "FETCH_OK",\n'
        '        "records": records if isinstance(records, list) else [],\n'
        '        "next_cursor": next_cursor,\n'
        '        "meta": {"requested_fields": requested_fields},\n'
        '        "errors": [],\n'
        "    }\n"
    )

    requirements_txt = "requests>=2.31.0\n"
    return dump_tool_output(
        CloudFunctionCodeToolOutput(
            status="OK",
            code="CF_CODE_GENERATED",
            msg="Generated Cloud Function artifacts.",
            connector_name=connector_name,
            source=source_name,
            main_py=main_py,
            requirements_txt=requirements_txt,
            suggested_env_vars=env_vars,
        )
    )


def _identify_environment_variables(code_text: str) -> Dict[str, Any]:
    """Heuristic scan: ``os.getenv('X')``, ``${X}`` patterns; flag names that look like secrets."""
    env_vars = sorted(
        set(re.findall(r"os\.getenv\(\s*[\"']([A-Z0-9_]+)[\"']", code_text))
    )
    env_vars.extend(
        var for var in re.findall(r"\$\{([A-Z0-9_]+)\}", code_text) if var not in env_vars
    )
    env_vars = sorted(set(env_vars))

    likely_secrets = [
        name
        for name in env_vars
        if any(token in name for token in ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL"))
    ]

    return dump_tool_output(
        EnvironmentVariablesToolOutput(
            status="OK",
            code="ENV_VARS_IDENTIFIED",
            msg="Environment variable analysis completed.",
            env_vars=env_vars,
            likely_secrets=sorted(set(likely_secrets)),
        )
    )

def _execute_connector(
    name: str,
    params: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Dynamically import a library connector and call ``fetch``; requires ``params["fields"]`` as a list."""
    lookup = _find_connector(name)
    if lookup.get("status") != "OK":
        return dump_tool_output(
            ConnectorExecuteToolOutput(
                status="WARN",
                code="CONNECTOR_NOT_FOUND_FOR_EXECUTION",
                msg="Connector does not exist in local library.",
                connector=ConnectorRef(
                    connector_name=lookup.get("connector_name", _normalize_connector_name(name)),
                    source="unknown",
                    file_path="",
                ),
                params=params or {},
                context=context or {},
                result=ConnectorRunResult(
                    status="WARN",
                    code="CONNECTOR_NOT_FOUND",
                    records=[],
                    errors=["Connector missing."],
                ),
            )
        )

    connector_info = lookup.get("connector") or {}
    file_path = str(connector_info.get("file_path", ""))
    connector_name = str(connector_info.get("connector_name", _normalize_connector_name(name)))
    source = str(connector_info.get("source", "unknown"))
    module_name = f"connector_{source}_{connector_name}"

    try:
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            return dump_tool_output(
                ConnectorExecuteToolOutput(
                    status="ERR",
                    code="CONNECTOR_MODULE_LOAD_ERROR",
                    msg="Could not load connector module.",
                    connector=ConnectorRef(
                        connector_name=connector_name,
                        source=source,
                        file_path=file_path,
                    ),
                    params=params or {},
                    context=context or {},
                    result=ConnectorRunResult(
                        status="ERR",
                        code="MODULE_LOAD_ERROR",
                        records=[],
                        errors=["Unable to load connector module."],
                    ),
                )
            )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        fetch_callable = getattr(module, "fetch", None)
        if not callable(fetch_callable):
            return dump_tool_output(
                ConnectorExecuteToolOutput(
                    status="ERR",
                    code="CONNECTOR_FETCH_NOT_CALLABLE",
                    msg="Connector missing callable `fetch(params, context)`.",
                    connector=ConnectorRef(
                        connector_name=connector_name,
                        source=source,
                        file_path=file_path,
                    ),
                    params=params or {},
                    context=context or {},
                    result=ConnectorRunResult(
                        status="ERR",
                        code="FETCH_NOT_CALLABLE",
                        records=[],
                        errors=["Top-level fetch function not found."],
                    ),
                )
            )

        call_params = params or {}
        call_context = context or {}
        fields = call_params.get("fields")
        if not isinstance(fields, list) or not fields:
            return dump_tool_output(
                ConnectorExecuteToolOutput(
                    status="ERR",
                    code="MISSING_REQUIRED_FIELDS_PARAM",
                    msg="Execution requires params.fields as a non-empty list.",
                    connector=ConnectorRef(
                        connector_name=connector_name,
                        source=source,
                        file_path=file_path,
                    ),
                    params=call_params,
                    context=call_context,
                    result=ConnectorRunResult(
                        status="ERR",
                        code="FIELDS_REQUIRED",
                        records=[],
                        errors=["Provide params.fields with at least one requested field."],
                    ),
                )
            )
        raw_result = fetch_callable(call_params, call_context)
        normalized = _normalize_connector_result(raw_result)
        status = normalized.status if normalized.status in {"OK", "WARN"} else "ERR"
        code = "CONNECTOR_EXECUTED" if status == "OK" else "CONNECTOR_EXECUTION_WARN"
        return dump_tool_output(
            ConnectorExecuteToolOutput(
                status=status,
                code=code,
                connector=ConnectorRef(
                    connector_name=connector_name,
                    source=source,
                    file_path=file_path,
                ),
                params=call_params,
                context=call_context,
                result=normalized,
            )
        )
    except Exception as exc:
        return dump_tool_output(
            ConnectorExecuteToolOutput(
                status="ERR",
                code="CONNECTOR_EXECUTION_ERROR",
                msg=str(exc),
                connector=ConnectorRef(
                    connector_name=connector_name,
                    source=source,
                    file_path=file_path,
                ),
                params=params or {},
                context=context or {},
                result=ConnectorRunResult(
                    status="ERR",
                    code="RUNTIME_EXCEPTION",
                    records=[],
                    errors=[str(exc)],
                ),
            )
        )

