"""Optional integration smoke tests for GCP Secret Manager backend."""

from __future__ import annotations

import os
import uuid

import pytest

from credentials.secrets import build_secret_id, rotate_connection_secret, store_connection_secret


@pytest.mark.gcp
@pytest.mark.skipif(
    not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"),
    reason="GOOGLE_APPLICATION_CREDENTIALS is not set",
)
def test_gcp_store_and_rotate_smoke(monkeypatch: pytest.MonkeyPatch) -> None:
    """Write two versions for one secret in the configured GCP project."""

    project = os.getenv("MDS_GCP_PROJECT", "monks-mds-dev")
    monkeypatch.setenv("MDS_GCP_PROJECT", project)

    connection_id = f"itest-{uuid.uuid4()}"
    secret_id = build_secret_id("dev", "meta", connection_id)

    saved = store_connection_secret(
        tenant_id="dev",
        provider="meta",
        connection_id=connection_id,
        payload={"access_token": "integration-token-1"},
    )
    assert saved == secret_id

    version_name = rotate_connection_secret(
        tenant_id="dev",
        provider="meta",
        connection_id=connection_id,
        payload={"access_token": "integration-token-2"},
    )
    assert "/versions/" in version_name
