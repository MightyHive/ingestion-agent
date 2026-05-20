"""OAuth-specific domain errors for authorization code flows."""

from __future__ import annotations


class OAuthError(Exception):
    """Base OAuth error."""


class InvalidOAuthStateError(OAuthError):
    """Raised when callback state cannot be validated."""


class OAuthProviderError(OAuthError):
    """Raised when provider authorize/token exchange fails."""

