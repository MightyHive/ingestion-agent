"""Public API for storing credential payloads in Secret Manager.

The credentials repository persists metadata only (secret references). This
module persists sensitive payloads in GCP Secret Manager.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from enum import Enum
from typing import Any

from google.cloud import secretmanager
from google.oauth2 import service_account

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


class SecretManagerRole(str, Enum):
    """Which service account to use for Secret Manager API calls."""

    WRITER = "writer"
    READER = "reader"


def _credentials_path_for_role(role: SecretManagerRole) -> str | None:
    """Resolve SA key file for writer/reader; fall back to ADC when unset."""

    if role is SecretManagerRole.WRITER:
        explicit = os.getenv("MDS_SA_CONNECTION_KEY", "").strip()
    else:
        explicit = os.getenv("MDS_SA_INGESTION_KEY", "").strip()
    if explicit and "$" not in explicit:
        return explicit
    fallback = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    if fallback and "$" not in fallback:
        return fallback
    return None


def _secret_manager_client_for_role(role: SecretManagerRole) -> secretmanager.SecretManagerServiceClient:
    """Build a Secret Manager client using the SA mapped to the operation."""

    path = _credentials_path_for_role(role)
    if path is None:
        return secretmanager.SecretManagerServiceClient()
    if not os.path.isfile(path):
        env_name = (
            "MDS_SA_CONNECTION_KEY"
            if role is SecretManagerRole.WRITER
            else "MDS_SA_INGESTION_KEY"
        )
        raise SecretManagerError(f"{env_name} or GOOGLE_APPLICATION_CREDENTIALS file not found: {path}")
    credentials = service_account.Credentials.from_service_account_file(path)
    return secretmanager.SecretManagerServiceClient(credentials=credentials)


def get_secrets_backend(*, role: SecretManagerRole) -> SecretsBackend:
    """Create the GCP backend for one role (writer vs reader service account)."""

    project = os.getenv("MDS_GCP_PROJECT", _DEFAULT_PROJECT).strip()
    if not project:
        raise SecretManagerError("MDS_GCP_PROJECT cannot be empty")
    client = _secret_manager_client_for_role(role)
    return GcpSecretsBackend(project_id=project, client=client)


def get_writer_secrets_backend() -> SecretsBackend:
    """Backend for create/rotate/revoke (MDS_SA_CONNECTION_KEY or ADC fallback)."""

    return get_secrets_backend(role=SecretManagerRole.WRITER)


def _reader_backend_for_project(secret_project_id: str) -> SecretsBackend:
    """Reader backend for one explicit Secret Manager project."""

    project = secret_project_id.strip()
    if not project:
        raise SecretManagerError("secret_project_id cannot be empty")
    client = _secret_manager_client_for_role(SecretManagerRole.READER)
    return GcpSecretsBackend(project_id=project, client=client)


def get_reader_secrets_backend() -> SecretsBackend:
    """Backend for read at ingestion time (MDS_SA_INGESTION_KEY or ADC fallback)."""

    return _reader_backend_for_project(default_secret_project_id())


def default_secret_project_id() -> str:
    """Return the configured Secret Manager project for connection payloads."""

    project = os.getenv("MDS_GCP_PROJECT", _DEFAULT_PROJECT).strip()
    if not project:
        raise SecretManagerError("MDS_GCP_PROJECT cannot be empty")
    return project


def store_connection_secret(
    tenant_id: str,
    provider: str,
    connection_id: str,
    payload: str | bytes | dict[str, Any],
) -> str:
    """Create (if needed) and write the first/latest payload version."""

    backend = get_writer_secrets_backend()
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

    backend = get_writer_secrets_backend()
    secret_id = build_secret_id(tenant_id=tenant_id, provider=provider, connection_id=connection_id)
    payload_bytes = _normalize_payload(payload)
    return backend.add_secret_version(secret_id, payload_bytes)


def revoke_connection_secret(
    tenant_id: str,
    provider: str,
    connection_id: str,
) -> int:
    """Disable all Secret Manager versions for one connection (revocation policy)."""

    backend = get_writer_secrets_backend()
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
    """Read one connection payload from Secret Manager and decode JSON object."""

    secret_id = build_secret_id(
        tenant_id=tenant_id,
        provider=provider,
        connection_id=connection_id,
    )
    return access_secret_payload(
        secret_project_id=default_secret_project_id(),
        secret_id=secret_id,
        version=version,
    )


def access_secret_payload(
    *,
    secret_project_id: str,
    secret_id: str,
    version: str = "latest",
) -> dict[str, Any]:
    """Read one payload by explicit Secret Manager project + secret id."""

    project = secret_project_id.strip()
    if not project:
        raise SecretManagerError("secret_project_id cannot be empty")
    sid = secret_id.strip()
    if not sid:
        raise SecretManagerError("secret_id cannot be empty")
    backend = _reader_backend_for_project(project)
    payload_bytes = backend.access_secret_version(sid, version=version)
    return _decode_payload_to_dict(payload_bytes)


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


def _decode_payload_to_dict(payload: bytes) -> dict[str, Any]:
    """Decode a stored payload and require a JSON object for connector context."""

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
    """Trim ids to provider limits while preserving uniqueness."""

    if len(secret_id) <= _MAX_SECRET_ID_LEN:
        return secret_id
    digest = hashlib.sha1(secret_id.encode("utf-8")).hexdigest()[:10]
    keep = _MAX_SECRET_ID_LEN - len(digest) - 1
    return f"{secret_id[:keep]}-{digest}"
