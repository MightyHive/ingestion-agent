"""Public API for storing credential payloads in a secrets backend.

Backend selection is controlled by ``MDS_SECRETS_BACKEND``:
- ``local`` (default): stores payloads in a local JSON file (dev).
- ``gcp``: stores payloads in GCP Secret Manager (production).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any

from credentials.exceptions import SecretManagerError, SecretPayloadError
from credentials.secrets_backends import GcpCliSecretsBackend, GcpSecretsBackend, LocalSecretsBackend, SecretsBackend

_DEFAULT_PROJECT = "monks-mds-dev"
_MAX_SECRET_ID_LEN = 255
_INVALID_CHARS = re.compile(r"[^A-Za-z0-9_-]+")


def build_secret_id(tenant_id: str, provider: str, connection_id: str) -> str:
    tenant = _sanitize_segment(tenant_id)
    platform = _sanitize_segment(provider)
    connection = _sanitize_segment(connection_id)
    raw = f"{tenant}-{platform}-{connection}"
    return _trim_secret_id(raw)


def _get_secrets_backend() -> SecretsBackend:
    backend_type = os.getenv("MDS_SECRETS_BACKEND", "local").strip().lower()
    if backend_type == "gcp":
        project = os.getenv("MDS_GCP_PROJECT", _DEFAULT_PROJECT).strip()
        if not project:
            raise SecretManagerError("MDS_GCP_PROJECT cannot be empty when using GCP backend")
        return GcpCliSecretsBackend(project_id=project)
    return LocalSecretsBackend()


def store_connection_secret(
    tenant_id: str,
    provider: str,
    connection_id: str,
    payload: str | bytes | dict[str, Any],
) -> str:
    backend = _get_secrets_backend()
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
    backend = _get_secrets_backend()
    secret_id = build_secret_id(tenant_id=tenant_id, provider=provider, connection_id=connection_id)
    payload_bytes = _normalize_payload(payload)
    return backend.add_secret_version(secret_id, payload_bytes)


def revoke_connection_secret(
    tenant_id: str,
    provider: str,
    connection_id: str,
) -> int:
    backend = _get_secrets_backend()
    secret_id = build_secret_id(
        tenant_id=tenant_id,
        provider=provider,
        connection_id=connection_id,
    )
    return backend.disable_all_secret_versions(secret_id)


def get_connection_secret(
    tenant_id: str,
    provider: str,
    connection_id: str,
    *,
    version: str = "latest",
) -> dict[str, Any]:
    secret_id = build_secret_id(
        tenant_id=tenant_id,
        provider=provider,
        connection_id=connection_id,
    )
    backend = _get_secrets_backend()
    payload_bytes = backend.access_secret_version(secret_id, version=version)
    return _decode_payload_to_dict(payload_bytes)


def list_sm_secrets_for_tenant(tenant_id: str) -> list[str]:
    """Return all secret IDs in SM whose name starts with the sanitized tenant prefix."""
    prefix = _sanitize_segment(tenant_id) + "-"
    backend = _get_secrets_backend()
    return backend.list_secret_ids(prefix)


def check_secret_exists(tenant_id: str, provider: str, connection_id: str) -> bool:
    secret_id = build_secret_id(tenant_id=tenant_id, provider=provider, connection_id=connection_id)
    backend = _get_secrets_backend()
    return backend.secret_exists(secret_id)


def default_secret_project_id() -> str:
    project = os.getenv("MDS_GCP_PROJECT", _DEFAULT_PROJECT).strip()
    if not project:
        raise SecretManagerError("MDS_GCP_PROJECT cannot be empty")
    return project


def _normalize_payload(payload: str | bytes | dict[str, Any]) -> bytes:
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


def _decode_payload_to_dict(payload: bytes) -> dict[str, Any]:
    try:
        raw = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SecretPayloadError("secret payload is not valid UTF-8") from exc
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SecretPayloadError("secret payload must be a JSON object") from exc
    if not isinstance(parsed, dict):
        raise SecretPayloadError("secret payload must decode to a JSON object")
    return parsed


def _sanitize_segment(value: str) -> str:
    clean = _INVALID_CHARS.sub("-", value.strip())
    clean = clean.strip("-_")
    if not clean:
        return "x"
    return clean.lower()


def _trim_secret_id(secret_id: str) -> str:
    if len(secret_id) <= _MAX_SECRET_ID_LEN:
        return secret_id
    digest = hashlib.sha1(secret_id.encode("utf-8")).hexdigest()[:10]
    keep = _MAX_SECRET_ID_LEN - len(digest) - 1
    return f"{secret_id[:keep]}-{digest}"
