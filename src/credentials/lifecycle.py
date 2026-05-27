"""Connection lifecycle rules for status transitions and write access."""

from __future__ import annotations

from credentials.exceptions import InvalidStatusTransitionError
from credentials.schemas import ConnectionStatus

_ALLOWED_TRANSITIONS: dict[ConnectionStatus, frozenset[ConnectionStatus]] = {
    ConnectionStatus.ACTIVE: frozenset(
        {ConnectionStatus.INACTIVE, ConnectionStatus.REVOKED}
    ),
    ConnectionStatus.INACTIVE: frozenset(
        {ConnectionStatus.ACTIVE, ConnectionStatus.REVOKED}
    ),
    ConnectionStatus.REVOKED: frozenset(),
}


def validate_status_transition(
    current: ConnectionStatus, target: ConnectionStatus
) -> None:
    if current == target:
        return
    allowed = _ALLOWED_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise InvalidStatusTransitionError(
            f"cannot transition connection status from '{current.value}' to '{target.value}'"
        )


def connection_allows_secret_write(status: ConnectionStatus) -> bool:
    return status == ConnectionStatus.ACTIVE
