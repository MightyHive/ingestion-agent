"""Optional integration smoke tests for GCP Secret Manager backend."""

from __future__ import annotations

import os
import uuid

import pytest
from google.api_core.exceptions import NotFound
from google.cloud import secretmanager
from google.oauth2 import service_account

from credentials.exceptions import SecretManagerError
from credentials.secrets import (
    build_secret_id,
    get_connection_secret,
    revoke_connection_secret,
    rotate_connection_secret,
    secret_resource_name,
    store_connection_secret,
)


def _has_file(path: str | None) -> bool:
    value = (path or "").strip()
    return bool(value) and "$" not in value and os.path.exists(value)


def _has_writer_and_reader_credentials() -> bool:
    return _has_file(os.getenv("MDS_SA_CONNECTION_KEY")) and _has_file(
        os.getenv("MDS_SA_INGESTION_KEY")
    )


@pytest.mark.gcp
@pytest.mark.skipif(
    not _has_writer_and_reader_credentials(),
    reason="MDS_SA_CONNECTION_KEY and MDS_SA_INGESTION_KEY must point to valid files",
)
def test_gcp_writer_reader_revoke_and_delete_smoke(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Create/read/rotate/revoke/delete a secret using writer+reader SAs per operation."""

    project = os.getenv("MDS_GCP_PROJECT", "monks-mds-dev")
    monkeypatch.setenv("MDS_GCP_PROJECT", project)
    writer_sa = os.getenv("MDS_SA_CONNECTION_KEY", "").strip()
    reader_sa = os.getenv("MDS_SA_INGESTION_KEY", "").strip()

    connection_id = f"itest-{uuid.uuid4()}"
    secret_id = build_secret_id("dev", "meta", connection_id)
    secret_resource = secret_resource_name(project, secret_id)

    try:
        saved = store_connection_secret(
            tenant_id="dev",
            provider="meta",
            connection_id=connection_id,
            payload={"access_token": "integration-token-1"},
        )
        assert saved == secret_id

        payload_v1 = get_connection_secret(
            tenant_id="dev",
            provider="meta",
            connection_id=connection_id,
        )
        assert payload_v1["access_token"] == "integration-token-1"

        version_name = rotate_connection_secret(
            tenant_id="dev",
            provider="meta",
            connection_id=connection_id,
            payload={"access_token": "integration-token-2"},
        )
        assert "/versions/" in version_name

        payload_v2 = get_connection_secret(
            tenant_id="dev",
            provider="meta",
            connection_id=connection_id,
        )
        assert payload_v2["access_token"] == "integration-token-2"

        disabled_count = revoke_connection_secret(
            tenant_id="dev",
            provider="meta",
            connection_id=connection_id,
        )
        assert disabled_count >= 1

        with pytest.raises(SecretManagerError):
            get_connection_secret(
                tenant_id="dev",
                provider="meta",
                connection_id=connection_id,
            )
    finally:
        writer_creds = service_account.Credentials.from_service_account_file(writer_sa)
        client = secretmanager.SecretManagerServiceClient(credentials=writer_creds)
        try:
            client.delete_secret(request={"name": secret_resource})
        except NotFound:
            pass
