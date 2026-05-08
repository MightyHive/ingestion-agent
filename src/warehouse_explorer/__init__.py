"""Warehouse Explorer — multi-agent conversational layer over the client's data warehouse.

This is where the LangGraph multi-agent architecture and PydanticAI agents
genuinely belong: open-ended reasoning over BigQuery datasets that mds has
already populated via ``src/ingestion/``.

Status (2026-05-08): scaffolding only. Implementation deferred until the
ingestion refactor is in production (post Fase 5).

See ``docs/architecture.md`` §8 and ``README.md`` in this package.
"""
