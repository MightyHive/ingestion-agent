"""Public API for storing credential payloads in Secret Manager.

The credentials repository persists metadata only (secret references). This
module persists sensitive payloads in GCP Secret Manager.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any

from credentials.exceptions import SecretManagerError, SecretPayloadError
from credentials.secrets_backends import GcpSecretsBackend, SecretsBackend

_DEFAULT_PROJECT = "monks-mds-dev"
_MAX_SECRET_ID_LEN = 255
_INVALID_CHARS = re.compile(r"[^A-Za-z0-9_-]+")


def build_secret_id(tenant_id: str, provider: str, connection_id: str) -> str:
    """Build a stable, GCP-compatible secret id.

    The format is ``{tenant}-{provider}-{connection_id}`` after sanitization.
    """

    tenant = _sanitize_segment(tenant_id)
    platform = _sanitize_segment(provider)
    connection = _sanitize_segment(connection_id)
    raw = f"{tenant}-{platform}-{connection}"
    return _trim_secret_id(raw)


def secret_resource_name(project_id: str, secret_id: str) -> str:
    """Return full Secret Manager resource name for one secret id."""

    return f"projects/{project_id}/secrets/{secret_id}"


def get_secrets_backend() -> SecretsBackend:
    """Create the GCP backend from environment configuration."""

    project = os.getenv("MDS_GCP_PROJECT", _DEFAULT_PROJECT).strip()
    if not project:
        raise SecretManagerError("MDS_GCP_PROJECT cannot be empty")
    return GcpSecretsBackend(project_id=project)


def store_connection_secret(
    tenant_id: str,
    provider: str,
    connection_id: str,
    payload: str | bytes | dict[str, Any],
) -> str:
    """Create (if needed) and write the first/latest payload version."""

    backend = get_secrets_backend()
    secret_id = build_secret_id(tenant_id=tenant_id, provider=provider, connection_id=connection_id)
    payload_bytes = _normalize_payload(payload)
    backend.ensure_secret(secret_id)
    backend.add_secret_version(secret_id, payload_bytes)
    return secret_id


def rotate_connection_secret(
    tenant_id: str,
    provider: str,
    connection_id: str,
    payload: str | bytes | dict[str, Any],
) -> str:
    """Write a new payload version for an existing connection secret."""

    backend = get_secrets_backend()
    secret_id = build_secret_id(tenant_id=tenant_id, provider=provider, connection_id=connection_id)
    payload_bytes = _normalize_payload(payload)
    return backend.add_secret_version(secret_id, payload_bytes)


def _normalize_payload(payload: str | bytes | dict[str, Any]) -> bytes:
    """Normalize payload to UTF-8 bytes without logging sensitive values."""

    if isinstance(payload, bytes):
        return payload
    if isinstance(payload, str):
        return payload.encode("utf-8")
    if isinstance(payload, dict):
        try:
            encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        except (TypeError, ValueError) as exc:
            raise SecretPayloadError("payload dict must be JSON-serializable") from exc
        return encoded.encode("utf-8")
    raise SecretPayloadError("payload must be bytes, str, or dict")


def _sanitize_segment(value: str) -> str:
    clean = _INVALID_CHARS.sub("-", value.strip())
    clean = clean.strip("-_")
    if not clean:
        return "x"
    return clean.lower()


def _trim_secret_id(secret_id: str) -> str:
    """Trim ids to provider limits while preserving uniqueness."""

    if len(secret_id) <= _MAX_SECRET_ID_LEN:
        return secret_id
    digest = hashlib.sha1(secret_id.encode("utf-8")).hexdigest()[:10]
    keep = _MAX_SECRET_ID_LEN - len(digest) - 1
    return f"{secret_id[:keep]}-{digest}"
