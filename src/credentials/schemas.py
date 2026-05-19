"""Pydantic schemas for credentials persistence.

These models define the in-process contract used by the repository and tests.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ConnectionStatus(str, Enum):
    """Allowed lifecycle states for a connection record."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    REVOKED = "revoked"


class ConnectionCreate(BaseModel):
    """Input model for creating a tenant-scoped connection."""

    tenant_id: str = Field(..., min_length=1)
    provider: str = Field(..., min_length=1)
    secret_id: str = Field(..., min_length=1)
    name: str | None = None
    status: ConnectionStatus = ConnectionStatus.ACTIVE


class ConnectionRecord(BaseModel):
    """Canonical metadata model returned by repository methods."""

    model_config = ConfigDict(from_attributes=True)

    connection_id: str
    tenant_id: str
    provider: str
    secret_id: str
    status: ConnectionStatus
    name: str | None = None
    created_at: datetime
    updated_at: datetime
