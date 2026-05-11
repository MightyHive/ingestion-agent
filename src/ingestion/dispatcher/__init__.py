"""Connector dispatcher.

Selects between two backends at runtime:

- :class:`LocalBackend` (dev): imports the connector module via
  :mod:`importlib` from the ``connectors-library/`` git submodule.
- ``HTTPBackend`` (prod, Phase 5): POSTs to the deployed Cloud Function
  URL using signed id_tokens via impersonated service-account
  credentials.

Selection driven by env var ``MDS_RUNTIME=local|http``. Default: local.

See ``docs/architecture.md`` §4.
"""

from ingestion.dispatcher.base import (
    BackendBase,
    BackendError,
    ConnectorDispatcher,
    ConnectorResponse,
)
from ingestion.dispatcher.local import LocalBackend

__all__ = [
    "BackendBase",
    "BackendError",
    "ConnectorDispatcher",
    "ConnectorResponse",
    "LocalBackend",
]
