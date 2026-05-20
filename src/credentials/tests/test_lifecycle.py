"""Unit tests for connection lifecycle rules."""

from __future__ import annotations

import pytest

from credentials.exceptions import InvalidStatusTransitionError
from credentials.lifecycle import (
    connection_allows_secret_write,
    validate_status_transition,
)
from credentials.schemas import ConnectionStatus


def test_validate_status_transition_allows_expected_paths() -> None:
    validate_status_transition(ConnectionStatus.ACTIVE, ConnectionStatus.INACTIVE)
    validate_status_transition(ConnectionStatus.INACTIVE, ConnectionStatus.ACTIVE)
    validate_status_transition(ConnectionStatus.INACTIVE, ConnectionStatus.REVOKED)


def test_validate_status_transition_rejects_revoked_changes() -> None:
    with pytest.raises(InvalidStatusTransitionError):
        validate_status_transition(ConnectionStatus.REVOKED, ConnectionStatus.ACTIVE)


def test_connection_allows_secret_write_only_when_active() -> None:
    assert connection_allows_secret_write(ConnectionStatus.ACTIVE) is True
    assert connection_allows_secret_write(ConnectionStatus.INACTIVE) is False
    assert connection_allows_secret_write(ConnectionStatus.REVOKED) is False
