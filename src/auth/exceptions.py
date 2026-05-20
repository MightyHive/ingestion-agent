"""Domain errors for tenant authorization in API requests."""

from __future__ import annotations


class AuthError(Exception):
    """Base class for tenant authorization errors."""


class MissingUserError(AuthError):
    """Raised when the request does not provide a user identity."""


class InvalidApiKeyError(AuthError):
    """Raised when an Authorization Bearer API key is unknown."""


class UnknownUserError(AuthError):
    """Raised when a resolved user is not present in the registry."""


class TenantAccessDeniedError(AuthError):
    """Raised when a user tries to act on an unauthorized tenant."""

