"""
Catalog: scans the ``connectors-library`` submodule for ``manifest.json``
files, validates each through ``loader.load_manifest``, and exposes both a
frontend-friendly listing summary and a per-id full manifest lookup.

Used by the Phase 1 endpoints in ``src/api.py``:

    GET /api/catalog          -> list of connector summaries (frontend index)
    GET /api/catalog/{id}     -> the full validated manifest for one connector

The default catalog points at ``<repo>/connectors-library``, which is
mounted at runtime via the git submodule introduced in Phase 0. To target
an alternative root (tests, ad-hoc CI runs), construct ``Catalog(root=...)``
explicitly.

The cache is built lazily on first access and persists for the lifetime of
the process. Call ``Catalog.reload()`` to invalidate. We don't poll the
filesystem because the submodule pointer changes only via deploy.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .loader import ManifestValidationError, load_manifest

# Repo root resolves regardless of CWD (uvicorn typically runs from src/).
# parents: [0]=manifest, [1]=ingestion, [2]=src, [3]=repo root.
_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_LIBRARY_ROOT = _REPO_ROOT / "connectors-library"

# Bumped if the /api/catalog response shape changes in a way Mili needs to react to.
CATALOG_API_VERSION = "1.0"


def scan_manifests(root: Path) -> list[tuple[Path, dict[str, Any]]]:
    """Walk ``root`` recursively, validate every ``manifest.json`` found, and
    return ``(path, manifest)`` tuples sorted by path.

    Skips hidden directories (``.git``, ``.github``, ``.venv``, etc.) so the
    submodule's metadata never enters the catalog. Validation errors surface
    immediately — the catalog refuses to half-load.
    """
    if not root.exists():
        return []
    results: list[tuple[Path, dict[str, Any]]] = []
    for p in sorted(root.rglob("manifest.json")):
        rel_parts = p.relative_to(root).parts
        if any(part.startswith(".") for part in rel_parts):
            continue
        manifest = load_manifest(p)
        results.append((p, manifest))
    return results


def summarize_for_listing(manifest: dict[str, Any]) -> dict[str, Any]:
    """Project a full manifest down to the fields the frontend index needs.

    This is the contract shared with Mili for ``GET /api/catalog``. Bump
    ``CATALOG_API_VERSION`` if the keys change shape in a non-additive way.
    """
    params = manifest.get("params") or {}
    fields = manifest.get("available_fields") or []

    summary: dict[str, Any] = {
        "id": manifest["id"],
        "name": manifest["name"],
        "platform": manifest["platform"],
        "connector": manifest["connector"],
        "version": manifest["version"],
        "status": manifest.get("status", "alpha"),
        "available_fields_count": len(fields),
        "params_summary": {
            "required": [p["name"] for p in params.get("required", []) if isinstance(p, dict) and "name" in p],
            "optional": [p["name"] for p in params.get("optional", []) if isinstance(p, dict) and "name" in p],
            "one_of": params.get("one_of", []),
        },
    }
    if "description" in manifest:
        summary["description"] = manifest["description"]
    if "owner" in manifest:
        summary["owner"] = manifest["owner"]
    return summary


@dataclass
class Catalog:
    """In-memory cache of manifests scanned from a library root."""

    root: Path = field(default_factory=lambda: DEFAULT_LIBRARY_ROOT)
    _by_id: Optional[dict[str, dict[str, Any]]] = None
    _paths: Optional[dict[str, Path]] = None

    def _ensure_loaded(self) -> None:
        if self._by_id is not None:
            return
        by_id: dict[str, dict[str, Any]] = {}
        paths: dict[str, Path] = {}
        for path, manifest in scan_manifests(self.root):
            mid = manifest["id"]
            if mid in by_id:
                raise ManifestValidationError(
                    path,
                    [f"duplicate manifest id '{mid}' (also at {paths[mid]})"],
                )
            by_id[mid] = manifest
            paths[mid] = path
        self._by_id = by_id
        self._paths = paths

    def reload(self) -> None:
        """Drop the cache. The next call to ``all()``/``get()`` rescans disk."""
        self._by_id = None
        self._paths = None

    def all(self) -> list[dict[str, Any]]:
        self._ensure_loaded()
        return list((self._by_id or {}).values())

    def get(self, manifest_id: str) -> Optional[dict[str, Any]]:
        self._ensure_loaded()
        return (self._by_id or {}).get(manifest_id)

    def list_summaries(self) -> list[dict[str, Any]]:
        return [summarize_for_listing(m) for m in self.all()]

    def __len__(self) -> int:
        self._ensure_loaded()
        return len(self._by_id or {})


_DEFAULT_CATALOG: Optional[Catalog] = None


def get_default_catalog() -> Catalog:
    """Return the process-wide singleton Catalog rooted at the connectors-library submodule."""
    global _DEFAULT_CATALOG
    if _DEFAULT_CATALOG is None:
        _DEFAULT_CATALOG = Catalog()
    return _DEFAULT_CATALOG
