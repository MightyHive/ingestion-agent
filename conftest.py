"""Global pytest bootstrap for repository tests."""

from __future__ import annotations

import os

from mds_env import load_mds_env

load_mds_env()

# Test runs should not depend on a local Postgres driver.
os.environ.pop("DATABASE_URL", None)

