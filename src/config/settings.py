import os
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()


class Settings:
    PROJECT_ID_LLM = os.getenv("PROJECT_ID_LLM")
    PROJECT_ID_DATA = os.getenv("PROJECT_ID_DATA")
    LOCATION = os.getenv("LOCATION", "us-central1")

    MODEL_NAME = os.getenv("MODEL_NAME", "gemini-2.5-flash")
    TEMPERATURE = float(os.getenv("TEMPERATURE", "0.0"))

    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")


settings = Settings()
