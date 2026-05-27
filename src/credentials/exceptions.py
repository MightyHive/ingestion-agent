"""Custom exceptions for the credentials repository layer."""

from __future__ import annotations


class CredentialsRepositoryError(Exception):
    """Base repository error for credentials persistence."""


class ConnectionNotFoundError(CredentialsRepositoryError):
    """Raised when a tenant-scoped connection cannot be found."""


class ConnectionAlreadyExistsError(CredentialsRepositoryError):
    """Raised when creating a connection with an existing identifier."""


class SecretManagerError(CredentialsRepositoryError):
    """Raised when a secret backend operation fails."""


class SecretPayloadError(CredentialsRepositoryError):
    """Raised when a secret payload cannot be normalized to bytes."""


class ConnectionInactiveError(CredentialsRepositoryError):
    """Raised when trying to run ingestion with non-active connection."""


class ConnectionProviderMismatchError(CredentialsRepositoryError):
    """Raised when connection provider does not match manifest platform."""


class InvalidStatusTransitionError(CredentialsRepositoryError):
    """Raised when a lifecycle status change is not allowed."""
