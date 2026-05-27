"""SQL CRUD operations for credential connections.

Every query is constrained by tenant_id for isolation.
"""

from __future__ import annotations

from datetime import datetime, timezone
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from credentials.exceptions import (
    ConnectionAlreadyExistsError,
    ConnectionNotFoundError,
)
from credentials.schemas import ConnectionCreate, ConnectionRecord, ConnectionStatus
from credentials.tables import ConnectionRow


class ConnectionRepository:
    def __init__(self, session: Session):
        self._session = session

    def create(self, data: ConnectionCreate) -> ConnectionRecord:
        return self.create_with_connection_id(
            connection_id=str(uuid.uuid4()),
            data=data,
        )

    def create_with_connection_id(
        self, *, connection_id: str, data: ConnectionCreate
    ) -> ConnectionRecord:
        now = datetime.now(timezone.utc)
        row = ConnectionRow(
            connection_id=connection_id,
            tenant_id=data.tenant_id,
            provider=data.provider,
            secret_id=data.secret_id,
            name=data.name,
            status=data.status.value,
            created_at=now,
            updated_at=now,
        )
        self._session.add(row)
        try:
            self._session.commit()
        except IntegrityError as exc:
            self._session.rollback()
            raise ConnectionAlreadyExistsError(str(exc)) from exc
        self._session.refresh(row)
        return self._to_record(row)

    def get(self, tenant_id: str, connection_id: str) -> ConnectionRecord | None:
        stmt = select(ConnectionRow).where(
            ConnectionRow.tenant_id == tenant_id,
            ConnectionRow.connection_id == connection_id,
        )
        row = self._session.scalar(stmt)
        return self._to_record(row) if row is not None else None

    def list_by_tenant(
        self,
        tenant_id: str,
        *,
        status: ConnectionStatus | None = None,
    ) -> list[ConnectionRecord]:
        stmt = select(ConnectionRow).where(ConnectionRow.tenant_id == tenant_id)
        if status is not None:
            stmt = stmt.where(ConnectionRow.status == status.value)
        stmt = stmt.order_by(ConnectionRow.created_at.desc())
        rows = self._session.scalars(stmt).all()
        return [self._to_record(row) for row in rows]

    def update_status(
        self,
        tenant_id: str,
        connection_id: str,
        status: ConnectionStatus,
    ) -> ConnectionRecord:
        row = self._require_connection(tenant_id=tenant_id, connection_id=connection_id)
        row.status = status.value
        row.updated_at = datetime.now(timezone.utc)
        self._session.commit()
        self._session.refresh(row)
        return self._to_record(row)

    def delete(self, tenant_id: str, connection_id: str) -> None:
        row = self._require_connection(tenant_id=tenant_id, connection_id=connection_id)
        self._session.delete(row)
        self._session.commit()

    def update_metadata(
        self,
        tenant_id: str,
        connection_id: str,
        *,
        name: str | None = None,
        secret_id: str | None = None,
    ) -> ConnectionRecord:
        row = self._require_connection(tenant_id=tenant_id, connection_id=connection_id)
        has_changes = False

        if name is not None and name != row.name:
            row.name = name
            has_changes = True

        if secret_id is not None and secret_id != row.secret_id:
            row.secret_id = secret_id
            has_changes = True

        if has_changes:
            row.updated_at = datetime.now(timezone.utc)
            self._session.commit()
            self._session.refresh(row)

        return self._to_record(row)

    def _require_connection(self, *, tenant_id: str, connection_id: str) -> ConnectionRow:
        stmt = select(ConnectionRow).where(
            ConnectionRow.tenant_id == tenant_id,
            ConnectionRow.connection_id == connection_id,
        )
        row = self._session.scalar(stmt)
        if row is None:
            raise ConnectionNotFoundError(
                f"connection '{connection_id}' not found for tenant '{tenant_id}'"
            )
        return row

    @staticmethod
    def _to_record(row: ConnectionRow) -> ConnectionRecord:
        return ConnectionRecord.model_validate(row)
