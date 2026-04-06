import os

from dotenv import load_dotenv
from pydantic import Field

# Load environment variables from .env
load_dotenv()


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or str(raw).strip() == "":
        return default
    return int(raw)


class Settings:
    """Application configuration from environment variables."""

    RUN_MODE = os.getenv("RUN_MODE", "cli").strip().lower()

    PROJECT_ID_LLM = os.getenv("PROJECT_ID_LLM")
    PROJECT_ID_DATA = os.getenv("PROJECT_ID_DATA")
    LOCATION = os.getenv("LOCATION", "us-central1")

    MODEL_NAME = os.getenv("MODEL_NAME", "gemini-2.5-flash")
    TEMPERATURE = float(os.getenv("TEMPERATURE", "0.0"))

    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

    API_CATALOG_TTL_DAYS: int = _env_int("API_CATALOG_TTL_DAYS", Field(default=7).default)


settings = Settings()
