"""Backends for storing credential payloads outside the metadata database.

This module currently provides the GCP backend used by the credentials API.
Payloads are written to Secret Manager in the configured project.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from google.api_core.exceptions import AlreadyExists, GoogleAPICallError
from google.cloud import secretmanager

from credentials.exceptions import SecretManagerError


class SecretsBackend(ABC):
    """Abstract backend for secret creation and rotation."""

    @abstractmethod
    def ensure_secret(self, secret_id: str) -> None:
        """Create backing storage for a secret if it does not exist."""

    @abstractmethod
    def add_secret_version(self, secret_id: str, payload: bytes) -> str:
        """Persist a new payload version and return a version identifier."""


class GcpSecretsBackend(SecretsBackend):
    """Google Secret Manager backend for real credential storage."""

    def __init__(
        self,
        project_id: str,
        client: secretmanager.SecretManagerServiceClient | None = None,
    ):
        self._project_id = project_id
        self._client = client or secretmanager.SecretManagerServiceClient()

    def ensure_secret(self, secret_id: str) -> None:
        """Create a Secret Manager secret with automatic replication."""

        parent = f"projects/{self._project_id}"
        secret = secretmanager.Secret(
            replication=secretmanager.Replication(
                automatic=secretmanager.Replication.Automatic()
            )
        )
        try:
            self._client.create_secret(
                request={"parent": parent, "secret_id": secret_id, "secret": secret}
            )
        except AlreadyExists:
            return
        except GoogleAPICallError as exc:
            raise SecretManagerError(
                f"failed to create secret '{secret_id}' in project '{self._project_id}'"
            ) from exc

    def add_secret_version(self, secret_id: str, payload: bytes) -> str:
        """Add a Secret Manager payload version and return version name."""

        parent = f"projects/{self._project_id}/secrets/{secret_id}"
        try:
            response = self._client.add_secret_version(
                request={"parent": parent, "payload": {"data": payload}}
            )
        except GoogleAPICallError as exc:
            raise SecretManagerError(
                f"failed to add version for secret '{secret_id}'"
            ) from exc
        return response.name
