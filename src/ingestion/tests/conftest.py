"""Pytest configuration for ingestion tests.

* Adds the repo's ``src/`` directory to ``sys.path`` so test modules
  can ``import ingestion``.
* Adds the fixture connectors directory to ``MDS_LOCAL_BACKEND_PATHS``
  so :class:`LocalBackend` can import ``mock_connector.fetcher``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
_FIXTURES_DIR = _TESTS_DIR / "fixtures"
_SRC_DIR = _TESTS_DIR.parents[1]  # repo/src

# Ensure ``import ingestion`` works regardless of cwd.
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

# Register fixture connectors with LocalBackend.
existing = os.environ.get("MDS_LOCAL_BACKEND_PATHS", "")
parts = [p for p in existing.split(":") if p]
if str(_FIXTURES_DIR) not in parts:
    parts.append(str(_FIXTURES_DIR))
os.environ["MDS_LOCAL_BACKEND_PATHS"] = ":".join(parts)
