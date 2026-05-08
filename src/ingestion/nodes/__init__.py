"""Deterministic graph nodes for the ingestion pipeline.

Each node is a pure function (or class with a single entrypoint) that
takes a typed input, returns a typed output, and never calls an LLM.

Planned nodes (Fase 2 of migration-plan.md):
- request_validator
- data_architect (Manifest.to_ddl)
- connector_runner (uses ConnectorDispatcher)
- format_response
"""
