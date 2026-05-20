"""Environment bootstrap for local development.

Loads ``<repo>/.env`` when present so local runs and tests can reuse the same
configuration without shell ``source`` boilerplate.
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parents[1]
_ENV_PATH = _REPO_ROOT / ".env"


def load_mds_env() -> None:
    """Load the repo-level .env file if it exists.

    Existing exported environment variables are preserved and take precedence.
    """

    load_dotenv(_ENV_PATH, override=False)
