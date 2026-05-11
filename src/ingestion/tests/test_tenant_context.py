"""Unit tests for ``ingestion.auth.tenant_context``."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ingestion.auth.tenant_context import (
    MissingContextKeyError,
    TenantConfigError,
    TenantContext,
    UnknownTenantError,
    set_loader_for_testing,
)


@pytest.fixture
def tenants_file(tmp_path: Path) -> Path:
    file = tmp_path / "tenants.json"
    file.write_text(
        json.dumps(
            {
                "tenants": {
                    "demo": {
                        "gcp_project": "monks-mds-demo",
                        "service_account": "mds-runner@monks-mds-demo.iam.gserviceaccount.com",
                        "context": {
                            "ad_account_id": "12345",
                            "access_token": "EAA-redacted",
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    return file


def test_resolve_loads_from_file(tenants_file: Path) -> None:
    ctx = TenantContext.resolve("demo", path=tenants_file)
    assert ctx.tenant_id == "demo"
    assert ctx.gcp_project == "monks-mds-demo"
    assert ctx.context["ad_account_id"] == "12345"


def test_resolve_unknown_tenant_raises(tenants_file: Path) -> None:
    with pytest.raises(UnknownTenantError):
        TenantContext.resolve("does-not-exist", path=tenants_file)


def test_resolve_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(TenantConfigError):
        TenantContext.resolve("demo", path=tmp_path / "missing.json")


def test_resolve_invalid_json_raises(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(TenantConfigError):
        TenantContext.resolve("demo", path=bad)


def test_assert_satisfies_passes_when_all_keys_present() -> None:
    ctx = TenantContext(
        tenant_id="t",
        gcp_project="p",
        service_account="s",
        context={"a": 1, "b": 2},
    )
    ctx.assert_satisfies(["a", "b"])  # should not raise


def test_assert_satisfies_raises_on_missing_key() -> None:
    ctx = TenantContext(
        tenant_id="t",
        gcp_project="p",
        service_account="s",
        context={"a": 1},
    )
    with pytest.raises(MissingContextKeyError):
        ctx.assert_satisfies(["a", "b"])


def test_loader_override_short_circuits_filesystem(tenants_file: Path) -> None:
    custom = TenantContext(
        tenant_id="injected",
        gcp_project="x",
        service_account="y",
        context={"k": "v"},
    )
    set_loader_for_testing(lambda tid: custom if tid == "injected" else None)
    try:
        assert TenantContext.resolve("injected", path=tenants_file) is custom
        with pytest.raises(UnknownTenantError):
            TenantContext.resolve("anything-else", path=tenants_file)
    finally:
        set_loader_for_testing(None)
