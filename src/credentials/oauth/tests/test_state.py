"""Unit tests for signed OAuth state tokens."""

from __future__ import annotations

import pytest

from credentials.oauth.exceptions import InvalidOAuthStateError
from credentials.oauth.state import build_state_token, decode_state_token


def test_state_round_trip() -> None:
    token = build_state_token(
        secret="secret-1",
        tenant_id="tenant-a",
        connection_id="conn-1",
        provider="meta",
        user_id="alice",
        name="Meta Prod",
    )
    payload = decode_state_token(token=token, secret="secret-1")
    assert payload["tenant_id"] == "tenant-a"
    assert payload["connection_id"] == "conn-1"
    assert payload["provider"] == "meta"
    assert payload["user_id"] == "alice"
    assert payload["name"] == "Meta Prod"


def test_state_rejects_bad_signature() -> None:
    token = build_state_token(
        secret="secret-1",
        tenant_id="tenant-a",
        connection_id="conn-1",
        provider="meta",
        user_id="alice",
    )
    with pytest.raises(InvalidOAuthStateError):
        decode_state_token(token=token, secret="different-secret")


def test_state_rejects_expired_token() -> None:
    token = build_state_token(
        secret="secret-1",
        tenant_id="tenant-a",
        connection_id="conn-1",
        provider="meta",
        user_id="alice",
        ttl_seconds=-1,
    )
    with pytest.raises(InvalidOAuthStateError):
        decode_state_token(token=token, secret="secret-1")

