"""MDS deterministic ingestion pipeline.

This package replaces the multi-agent LLM ingestion graph (src/agents/*)
with a deterministic pipeline that consumes manifests from the
``connectors-library`` git submodule.

See ``docs/architecture.md`` for the design.
"""
