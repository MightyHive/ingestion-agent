"""Pytest bootstrap for testpaths rooted under ``src/``."""

from __future__ import annotations

import os

from mds_env import load_mds_env

load_mds_env()

# Avoid importing a postgres dialect driver in local test runs.
os.environ.pop("DATABASE_URL", None)

