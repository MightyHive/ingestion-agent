"""
Manifest loader: reads connector manifests from disk and validates them
against the JSON Schema in ``schema.json`` (Draft 2020-12).

Pure functions; no I/O beyond what is explicitly requested. The schema is
cached after first read.

Public surface (Phase 1):
    - ManifestValidationError
    - load_schema()
    - validate_manifest(data, source=None)
    - load_manifest(path)

The loader knows nothing about HTTP, FastAPI, or where manifests live in
the filesystem — that's the catalog's job. This separation keeps validation
trivially testable and reusable from CI scripts.
"""
from __future__ import annotations

import functools
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

_SCHEMA_PATH = Path(__file__).resolve().parent / "schema.json"


class ManifestValidationError(ValueError):
    """Raised when a manifest fails JSON Schema validation or cannot be parsed."""

    def __init__(self, source: Path | str, errors: list[str]):
        self.source = str(source)
        self.errors = list(errors)
        joined = "\n  - ".join(self.errors) if self.errors else "(no error detail)"
        super().__init__(f"Invalid manifest at {self.source}:\n  - {joined}")


@functools.lru_cache(maxsize=1)
def load_schema() -> dict[str, Any]:
    """Return the cached connector manifest JSON Schema (Draft 2020-12)."""
    with _SCHEMA_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def _format_errors(errors) -> list[str]:
    out: list[str] = []
    for e in errors:
        loc = "/" + "/".join(str(p) for p in e.absolute_path) if e.absolute_path else "(root)"
        out.append(f"{loc}: {e.message}")
    return out


def validate_manifest(data: dict[str, Any], source: Path | str | None = None) -> None:
    """Validate ``data`` against the manifest schema. Raise ManifestValidationError on failure."""
    validator = Draft202012Validator(load_schema())
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))
    if errors:
        raise ManifestValidationError(source if source is not None else "<in-memory>", _format_errors(errors))


def load_manifest(path: Path | str) -> dict[str, Any]:
    """Load and validate a manifest from disk. Returns the parsed manifest dict."""
    p = Path(path)
    try:
        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError as e:
        raise ManifestValidationError(p, [f"file not found: {e}"]) from e
    except json.JSONDecodeError as e:
        raise ManifestValidationError(p, [f"invalid JSON: {e}"]) from e
    if not isinstance(data, dict):
        raise ManifestValidationError(p, ["root of manifest must be a JSON object"])
    validate_manifest(data, source=p)
    return data
