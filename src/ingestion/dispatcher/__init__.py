"""Connector dispatcher.

Selects between two backends at runtime:
- ``LocalBackend`` (dev): imports the connector module via ``importlib``
  from the ``connectors-library/`` git submodule.
- ``HTTPBackend`` (prod): POSTs to the deployed Cloud Function URL using
  signed id_tokens via impersonated service-account credentials.

Selection driven by env var ``MDS_RUNTIME=local|http``.

See ``docs/architecture.md`` §4.
"""
