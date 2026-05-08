"""Manifest loading, validation and DDL generation.

Each connector in the ``connectors-library`` submodule exports a
``manifest.json`` describing its parameters, available fields, auth
requirements and Cloud Function endpoint. That manifest is the single
source of truth consumed by:
- the frontend catalog (``GET /api/catalog`` / ``GET /api/catalog/{id}``)
- the deterministic data-architect (``Manifest.to_ddl``, Phase 2)
- the dispatcher (Phase 2 / Phase 5)
- CI validation

Schema: ``schema.json`` in this package (Draft 2020-12).
"""

from .catalog import (
    CATALOG_API_VERSION,
    Catalog,
    DEFAULT_LIBRARY_ROOT,
    get_default_catalog,
    scan_manifests,
    summarize_for_listing,
)
from .loader import ManifestValidationError, load_manifest, load_schema, validate_manifest

__all__ = [
    "CATALOG_API_VERSION",
    "Catalog",
    "DEFAULT_LIBRARY_ROOT",
    "ManifestValidationError",
    "get_default_catalog",
    "load_manifest",
    "load_schema",
    "scan_manifests",
    "summarize_for_listing",
    "validate_manifest",
]
