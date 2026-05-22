"""Test-only shim that fakes out functions-framework and the GCP SDKs.

The Cloud Function runtime supplies these at deploy time; pulling them
into the developer's machine just to run unit tests would slow CI and
make first-touch contribution annoying. Instead, the tests rely on
``conftest.py`` (which pytest auto-imports BEFORE collecting any
test modules) to plant minimal stubs in ``sys.modules`` so the import
of ``main`` succeeds.

The actual SM / BQ logic is replaced via ``monkeypatch`` inside each
test, so the stubs only need to expose the symbols that ``main``
references at import time.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from typing import Any


# --- functions_framework --------------------------------------------------
# ``main`` only uses ``@functions_framework.http`` as a no-op decorator
# at import time. The stub returns the function unchanged.

def _ff_http(func):
    return func


_ff_module = types.ModuleType("functions_framework")
_ff_module.http = _ff_http
sys.modules.setdefault("functions_framework", _ff_module)


# --- google.cloud.secretmanager + google.cloud.bigquery -------------------
# ``main`` lazy-imports these inside the helper functions, so we do NOT
# strictly need to stub them at the package level — every test replaces
# ``_resolve_secret`` / ``_write_records_to_bq`` via monkeypatch instead.
# We still register skeleton modules so that an accidental real call
# fails with a clear error rather than crashing on ``ImportError``.

def _register_pkg(dotted_name: str, attrs: dict[str, Any] | None = None) -> None:
    parts = dotted_name.split(".")
    accumulated = ""
    for i, part in enumerate(parts):
        accumulated = part if not accumulated else f"{accumulated}.{part}"
        if accumulated in sys.modules:
            continue
        mod = types.ModuleType(accumulated)
        sys.modules[accumulated] = mod
        if i > 0:
            parent_name = ".".join(parts[:i])
            setattr(sys.modules[parent_name], part, mod)
    if attrs:
        for key, value in attrs.items():
            setattr(sys.modules[dotted_name], key, value)


def _explosive_client(*_a, **_kw):  # noqa: D401
    raise RuntimeError(
        "tests must monkeypatch main._resolve_secret / main._write_records_to_bq "
        "rather than letting the real google-cloud-* client fire."
    )


_register_pkg("google")
_register_pkg("google.cloud")
_register_pkg(
    "google.cloud.secretmanager",
    attrs={"SecretManagerServiceClient": _explosive_client},
)
_register_pkg(
    "google.cloud.bigquery",
    attrs={
        "Client": _explosive_client,
        "Table": _explosive_client,
        "SchemaField": _explosive_client,
        "LoadJobConfig": _explosive_client,
        "WriteDisposition": types.SimpleNamespace(WRITE_APPEND="WRITE_APPEND"),
        "SchemaUpdateOption": types.SimpleNamespace(ALLOW_FIELD_ADDITION="ALLOW_FIELD_ADDITION"),
        "SourceFormat": types.SimpleNamespace(NEWLINE_DELIMITED_JSON="NEWLINE_DELIMITED_JSON"),
    },
)


# --- Bundled manifest -----------------------------------------------------
# In production, deploy.sh copies connectors-library/meta/facebook/manifest.json
# into the deploy dir. For tests we don't want that copy to exist (it
# would pollute the source tree), so conftest writes a transient copy
# into the same directory before any test runs and removes it after.
#
# Pytest evaluates conftest module-level code at collection time, which
# happens BEFORE main is imported — perfect for setting this up. We
# avoid pytest fixtures here because main._MANIFEST_CACHE is populated
# lazily on first call, and we want the manifest available from the
# very first test.

_HERE = Path(__file__).resolve().parent
_MANIFEST_DEST = _HERE / "manifest.json"
_MANIFEST_SRC = (
    _HERE.parent.parent / "connectors-library" / "meta" / "facebook" / "manifest.json"
)
_MANIFEST_PLACED_BY_CONFTEST = False

if not _MANIFEST_DEST.exists():
    if _MANIFEST_SRC.exists():
        _MANIFEST_DEST.write_text(_MANIFEST_SRC.read_text(encoding="utf-8"), encoding="utf-8")
        _MANIFEST_PLACED_BY_CONFTEST = True
    else:
        # Fall back to a minimal manifest so tests can still run.
        _MANIFEST_DEST.write_text(
            json.dumps(
                {
                    "id": "meta_facebook_ad_insights",
                    "version": "0.0.0-test",
                    "endpoint": {"cloud_function_name": "meta-facebook-insights"},
                    "metadata": {"response_subkey": "ads"},
                    "available_fields": [
                        {"name": "ad_id", "type": "STRING"},
                        {"name": "impressions", "type": "NUMERIC"},
                        {"name": "spend", "type": "NUMERIC"},
                        {"name": "date_start", "type": "DATE"},
                    ],
                }
            ),
            encoding="utf-8",
        )
        _MANIFEST_PLACED_BY_CONFTEST = True


def pytest_sessionfinish(session, exitstatus):  # noqa: D401
    """Remove the test-only manifest copy so the source tree stays clean."""
    if _MANIFEST_PLACED_BY_CONFTEST and _MANIFEST_DEST.exists():
        try:
            _MANIFEST_DEST.unlink()
        except OSError:
            pass
