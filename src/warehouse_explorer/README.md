# Warehouse Explorer

> Multi-agent conversational layer over the client's data warehouse.

## Status

**Scaffolding only.** Implementation deferred until the deterministic ingestion pipeline is live in production (post Fase 5 of `docs/migration-plan.md`).

## Why this lives here

`src/ingestion/` is intentionally LLM-free: it consumes prebuilt connectors from `connectors-library/` and emits records to BigQuery. That's a deterministic pipeline and the LLM was the wrong tool for the job.

`src/warehouse_explorer/` is the *opposite* — open-ended reasoning over already-ingested data. Questions like:
- "Which campaigns delivered the highest CPM last month vs the same period last year?"
- "Show me anomalies in spend across the Meta-attribution dataset for client X."
- "Generate a chart of conversion rate by ad set for last week."

These problems require:
- Schema understanding from BigQuery `INFORMATION_SCHEMA`
- SQL generation under tenant-specific constraints (project, dataset, row policies)
- Multi-step reasoning (decompose → query → reflect → re-query)
- Conversational state across turns

That's where the LLM, PydanticAI agents, LangGraph multi-agent topology and the LOL Protocol earn their keep.

## Shared infra

This package will reuse:
- `src/shared/lol/` — LOL Protocol for typed agent-to-agent messages
- `src/shared/state.py` — LangGraph state typing
- `src/shared/observability.py` — logging utilities
- BigQuery client + the `TenantContext` from `src/ingestion/auth/`

## Out of scope (for the ingestion refactor)

- No agents are implemented in this package yet. PRs that touch `src/warehouse_explorer/` should land *after* Fase 5 of the migration plan.
- The mds API does not expose any `/api/explore/*` endpoint yet.
