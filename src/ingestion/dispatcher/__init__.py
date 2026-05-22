"""Connector dispatcher.

Selects between two backends at runtime:

- :class:`LocalBackend` (dev): imports the connector module via
  :mod:`importlib` from the ``connectors-library/`` git submodule.
- :class:`HTTPBackend` (prod, Phase 5): POSTs to the deployed Cloud
  Function URL using signed id_tokens via ADC.
- :class:`AutoBackend` (mixed Phase 5): picks Local or HTTP per-manifest
  based on whether ``endpoint.cloud_function_name`` is declared.

Selection driven by env var ``MDS_RUNTIME=local|http|auto``. Default:
local.

See ``docs/architecture.md`` §4.
"""

from ingestion.dispatcher.base import (
    AutoBackend,
    BackendBase,
    BackendError,
    ConnectorDispatcher,
    ConnectorResponse,
)
from ingestion.dispatcher.http import HTTPBackend
from ingestion.dispatcher.local import LocalBackend

__all__ = [
    "AutoBackend",
    "BackendBase",
    "BackendError",
    "ConnectorDispatcher",
    "ConnectorResponse",
    "HTTPBackend",
    "LocalBackend",
]
