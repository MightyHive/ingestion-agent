"""
Pydantic contracts for structured tool outputs.

Add: ToolOutput subclasses per tool (fields with Field(description=...)).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


ToolStatus = Literal["OK", "WARN", "ERR"]


# ============================================================
# Shared base for all tools
# ============================================================



class ToolOutput(BaseModel):
    """Base contract for any tool result."""

    status: ToolStatus = Field(
        description=(
            "Execution status: OK (success), WARN (partial result), or ERR (failure)."
        )
    )
    code: Optional[str] = Field(
        default=None,
        description="Optional internal status code to classify the outcome.",
    )
    msg: Optional[str] = Field(
        default=None,
        description="Short message for the consuming agent.",
    )

# ============================================================
# API Researcher Tools
# ============================================================

class SearchResult(BaseModel):
    """Single result from search_web."""
    title: str
    href: str
    body: str
 
 
class SearchWebOutput(ToolOutput):
    """Output of the search_web tool."""
    results: List[SearchResult] = Field(
        default_factory=list,
        description="Ordered list of search results (title, URL, snippet). Empty on ERR.",
    )
    query: str = Field(
        description="The search query that was executed."
    )
 
 
class ReadDocumentationOutput(ToolOutput):
    """Output of the read_documentation_url tool."""
    url: str = Field(
        description="The URL that was fetched."
    )
    content: Optional[str] = Field(
        default=None,
        description="Extracted plain text from the documentation page. Null on ERR.",
    )
    char_count: int = Field(
        default=0,
        description="Number of characters in the extracted content.",
    )
 
 
class SchemaField(BaseModel):
    """Single inferred field from analyze_json_schema."""
    api_field: str = Field(description="Dot-notation path in the JSON response")
    type: str       = Field(description="Inferred BigQuery type")
    sample: str     = Field(description="Sample value (truncated to 60 chars)")
 
 
class AnalyzeJsonSchemaOutput(ToolOutput):
    """Output of the analyze_json_schema tool."""
    fields: List[SchemaField] = Field(
        default_factory=list,
        description="All inferred fields with their BigQuery types and sample values.",
    )
    field_count: int = Field(
        default=0,
        description="Total number of fields detected.",
    )

# ============================================================
# Software Engineer Tools
# ============================================================


class ConnectorRef(BaseModel):
    """Reference to a connector function file."""

    connector_name: str = Field(description="Normalized connector function name.")
    source: str = Field(description="Data source group (youtube, ga4, etc.).")
    file_path: str = Field(description="Connector absolute path.")


class ConnectorValidationOutput(BaseModel):
    """Validation details for connector code."""

    valid: bool = Field(description="Whether code passes structural checks.")
    function_defs: List[str] = Field(
        default_factory=list,
        description="Function names defined in the module.",
    )
    has_fetch_entrypoint: bool = Field(
        description="True when a top-level callable named `fetch` exists."
    )
    has_required_signature: bool = Field(
        description="True when `fetch` uses signature `fetch(params, context)`."
    )
    uses_fields_parameter: bool = Field(
        description=(
            "True when `fetch` reads the requested columns/metrics via `params['fields']` or "
            "`params.get('fields', ...)` (not a bare variable named `fields`)."
        )
    )
    error: Optional[str] = Field(
        default=None,
        description="Validation error details when invalid.",
    )


class ConnectorListToolOutput(ToolOutput):
    """Response for listing connectors in the local library."""

    connector_root: str = Field(description="Connector library root path.")
    connectors: List[ConnectorRef] = Field(
        default_factory=list,
        description="Connectors discovered in the local connector library.",
    )


class ConnectorSearchToolOutput(ToolOutput):
    """Response for connector exact/fuzzy search."""

    connector_name: str = Field(description="Normalized connector name searched.")
    connector: Optional[ConnectorRef] = Field(
        default=None,
        description="Matched connector reference when found.",
    )
    close_matches: List[str] = Field(
        default_factory=list,
        description="Approximate connector name matches.",
    )


class ConnectorReadToolOutput(ToolOutput):
    """Response for reading connector source code."""

    connector: ConnectorRef = Field(description="Connector reference.")
    code_text: str = Field(description="Connector source code content.")


class ConnectorValidateToolOutput(ToolOutput):
    """Response for validating connector code structure."""

    validation: ConnectorValidationOutput = Field(
        description="Detailed validation results for connector code."
    )


class ConnectorSaveToolOutput(ToolOutput):
    """Response for saving a connector file."""

    connector: ConnectorRef = Field(description="Connector reference saved/updated.")
    validation: ConnectorValidationOutput = Field(
        description="Validation details used before persisting code."
    )


class GoldStandardCodeToolOutput(ToolOutput):
    """Response for fetching approved template code from connector library."""

    connector: Optional[ConnectorRef] = Field(
        default=None,
        description="Template connector reference when found.",
    )
    code_text: Optional[str] = Field(
        default=None,
        description="Template source code when available.",
    )
    close_matches: List[str] = Field(
        default_factory=list,
        description="Approximate template matches when exact one is missing.",
    )


class StageConnectorToolOutput(ToolOutput):
    """Response for staging a connector instance with user-selected fields for deployment."""

    library_connector: str = Field(
        description="Path to the generic connector in the permanent library.",
    )
    staged_path: str = Field(
        description="Path to the staged instance in pending_deploy/ (temporary, deleted after deploy).",
    )
    fields_configured: List[str] = Field(
        default_factory=list,
        description="Fields hardcoded into the staged instance from Data Architect DDL.",
    )
    staged_connector_name: str = Field(
        description="Name of the staged connector file (without path).",
    )


class CloudFunctionCodeToolOutput(ToolOutput):
    """Response for generated Cloud Function artifacts."""

    connector_name: str = Field(description="Generated connector/function name.")
    source: str = Field(description="Source namespace used in generated code.")
    main_py: str = Field(description="Generated Cloud Function `main.py` content.")
    requirements_txt: str = Field(description="Generated `requirements.txt` content.")
    suggested_env_vars: List[str] = Field(
        default_factory=list,
        description="Environment variables suggested by generated code.",
    )


class EnvironmentVariablesToolOutput(ToolOutput):
    """Response for environment variable detection from source code."""

    env_vars: List[str] = Field(
        default_factory=list,
        description="Environment variables found or inferred from code.",
    )
    likely_secrets: List[str] = Field(
        default_factory=list,
        description="Subset of env vars likely containing secrets/tokens.",
    )


class ConnectorRunResult(BaseModel):
    """Normalized runtime output returned by connector ``fetch``."""

    status: ToolStatus = Field(description="Connector execution status.")
    code: Optional[str] = Field(
        default=None,
        description="Optional connector-level status code.",
    )
    records: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Normalized records emitted by the connector.",
    )
    next_cursor: Optional[str] = Field(
        default=None,
        description="Pagination cursor for subsequent calls, when available.",
    )
    meta: Dict[str, Any] = Field(
        default_factory=dict,
        description="Connector execution metadata.",
    )
    errors: List[str] = Field(
        default_factory=list,
        description="Non-fatal warnings or runtime error details.",
    )


class ConnectorExecuteToolOutput(ToolOutput):
    """Response for dynamic connector execution via ``fetch(params, context)``."""

    connector: ConnectorRef = Field(description="Connector reference executed.")
    params: Dict[str, Any] = Field(
        default_factory=dict,
        description="Input params passed to ``fetch``.",
    )
    context: Dict[str, Any] = Field(
        default_factory=dict,
        description="Execution context passed to ``fetch``.",
    )
    result: ConnectorRunResult = Field(
        description="Normalized runtime result from connector execution.",
    )



# ============================================================
# JSON-safe serialization helpers
# ============================================================

def to_json_safe(value: Any) -> Any:
    """Normalize non-JSON-native values for safe transport."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, BaseModel):
        return to_json_safe(value.model_dump())
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, dict):
        return {str(k): to_json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_json_safe(v) for v in value]
    return str(value)


def dump_tool_output(output: ToolOutput) -> Dict[str, Any]:
    """Return a compact JSON-safe dict for the agent."""
    return to_json_safe(output.model_dump(exclude_none=True))
