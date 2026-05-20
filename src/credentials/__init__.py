"""Credentials package — tenant-scoped connection metadata.

This package stores connection metadata in a relational DB.
Secret payloads must be handled by Secret Manager, not in this database.
"""

from credentials.db import get_session, init_db
from credentials.repository import ConnectionRepository
from credentials.resolver import resolve_for_run
from credentials.schemas import ConnectionCreate, ConnectionRecord, ConnectionStatus
from credentials.secrets import (
    build_secret_id,
    get_connection_secret,
    revoke_connection_secret,
    rotate_connection_secret,
    secret_resource_name,
    store_connection_secret,
)
from credentials.service import (
    get_connection,
    list_connections,
    update_connection_status,
    upsert_connection,
)

__all__ = [
    "build_secret_id",
    "ConnectionCreate",
    "ConnectionRecord",
    "ConnectionRepository",
    "ConnectionStatus",
    "get_connection_secret",
    "get_connection",
    "get_session",
    "init_db",
    "list_connections",
    "revoke_connection_secret",
    "rotate_connection_secret",
    "secret_resource_name",
    "store_connection_secret",
    "update_connection_status",
    "upsert_connection",
    "resolve_for_run",
]
