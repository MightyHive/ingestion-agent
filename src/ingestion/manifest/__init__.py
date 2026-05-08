"""Manifest loading, validation and DDL generation.

Each connector in the ``connectors-library`` submodule exports a
``manifest.json`` describing its parameters, available fields, auth
requirements and Cloud Function endpoint. That manifest is the single
source of truth consumed by:
- the frontend catalog (``GET /api/catalog``)
- the deterministic data-architect (``Manifest.to_ddl``)
- the dispatcher
- CI validation

Schema: ``schema.json`` in this package.
"""
