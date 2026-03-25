# ingestion-agent

Python agent platform skeleton: LangGraph orchestrator, LOL protocol (Pydantic), local traces, optional observability (`-obs`).

## Scripts

- `src/scripts/list_models.py` — list Gemini embedding models (requires `GOOGLE_API_KEY`).
- `src/scripts/ingest_docs.py` — chunk `.txt` under `docs/` into Chroma (`./chroma_db`).
