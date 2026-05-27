"""Import existing GCP Secret Manager secrets into the credentials DB.

Usage (from repo root):
    PYTHONPATH=src python src/scripts/import_gcp_secrets.py \
        --project monks-mds-dev \
        --tenants dev,cliente1

The script reverse-parses secret names using the format
``{tenant}-{provider}-{connection_id}`` established by Facundo's branch,
creates DB records for each valid secret, and stores the payloads in the
local secrets file (or GCP SM if MDS_SECRETS_BACKEND=gcp).

Requires valid gcloud credentials:
    gcloud auth login
    gcloud auth application-default login
"""

from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
from pathlib import Path

# Make sure src/ is in path when called directly
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from credentials.db import init_db, get_session
from credentials.repository import ConnectionRepository
from credentials.schemas import ConnectionCreate, ConnectionStatus
from credentials.secrets import build_secret_id

KNOWN_PROVIDERS = ["meta", "tiktok", "youtube", "cm360", "dv360", "google_ads", "google-ads"]


def gcloud(*args: str) -> str:
    result = subprocess.run(["gcloud", *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"gcloud error: {result.stderr.strip()}")
    return result.stdout.strip()


def list_secrets(project: str) -> list[dict]:
    out = gcloud("secrets", "list", f"--project={project}", "--format=json")
    return json.loads(out) if out else []


def access_secret_raw(project: str, secret_id: str) -> str:
    """Return the latest version payload as a plain string."""
    return gcloud(
        "secrets", "versions", "access", "latest",
        f"--secret={secret_id}",
        f"--project={project}",
    )


# ---------------------------------------------------------------------------
# Format parsers
# ---------------------------------------------------------------------------

def parse_facundo_format(name: str, tenants: list[str]) -> tuple[str, str, str] | None:
    """Parse ``{tenant}-{provider}-{connection_id}`` (Facundo's convention)."""
    for tenant in sorted(tenants, key=len, reverse=True):
        if not name.startswith(f"{tenant}-"):
            continue
        rest = name[len(tenant) + 1:]
        for provider in sorted(KNOWN_PROVIDERS, key=len, reverse=True):
            if rest.startswith(f"{provider}-"):
                connection_id = rest[len(provider) + 1:]
                if connection_id:
                    return tenant, provider, connection_id
    return None


def parse_client_format(name: str, tenants: list[str]) -> tuple[str, str, str] | None:
    """Parse ``client_{tenant}_{provider}_{field}`` (existing secrets convention).

    Returns (tenant, provider, field_name) or None.
    """
    if not name.startswith("client_"):
        return None
    rest = name[len("client_"):]
    for tenant in sorted(tenants, key=len, reverse=True):
        if not rest.startswith(f"{tenant}_"):
            continue
        rest2 = rest[len(tenant) + 1:]
        for provider in sorted(KNOWN_PROVIDERS, key=len, reverse=True):
            prov_key = provider.replace("-", "_")
            if rest2.startswith(f"{prov_key}_"):
                field = rest2[len(prov_key) + 1:]
                if field:
                    return tenant, provider, field
    return None


# ---------------------------------------------------------------------------
# Import logic
# ---------------------------------------------------------------------------

def import_secrets(project: str, tenants: list[str], dry_run: bool = False) -> None:
    init_db()
    print(f"\nListing secrets in project '{project}'...")
    try:
        secrets = list_secrets(project)
    except RuntimeError as e:
        print(f"\nERROR: {e}")
        print("\nRun these commands first and try again:")
        print("  gcloud auth login")
        print("  gcloud auth application-default login")
        sys.exit(1)

    if not secrets:
        print("No secrets found in project.")
        return

    print(f"Found {len(secrets)} secret(s). Parsing...\n")

    # Group secrets by (tenant, provider) for the client_ format
    # Each group becomes ONE connection with a combined payload
    client_groups: dict[tuple[str, str], dict[str, str]] = {}  # (tenant, provider) → {field: value}
    facundo_secrets: list[tuple[str, str, str, str]] = []       # (secret_id, tenant, provider, conn_id)
    unmatched: list[str] = []

    for secret in secrets:
        secret_id: str = secret["name"].split("/")[-1]

        client_parsed = parse_client_format(secret_id, tenants)
        if client_parsed:
            tenant_id, provider, field = client_parsed
            key = (tenant_id, provider)
            if key not in client_groups:
                client_groups[key] = {}
            # Read the field value now
            print(f"  FOUND (client format)  {secret_id}")
            print(f"         → tenant={tenant_id}, provider={provider}, field={field}")
            if not dry_run:
                try:
                    value = access_secret_raw(project, secret_id)
                    client_groups[key][field] = value
                    print(f"         → value read OK")
                except RuntimeError as e:
                    print(f"         → ERROR reading: {e}")
            continue

        facundo_parsed = parse_facundo_format(secret_id, tenants)
        if facundo_parsed:
            tenant_id, provider, connection_id = facundo_parsed
            print(f"  FOUND (facu format)    {secret_id}")
            print(f"         → tenant={tenant_id}, provider={provider}, connection_id={connection_id}")
            facundo_secrets.append((secret_id, tenant_id, provider, connection_id))
            continue

        print(f"  SKIP   {secret_id}  (unrecognized format)")
        unmatched.append(secret_id)

    if dry_run:
        print(f"\nDRY RUN — no DB writes.")
        print(f"  client_ groups that would become connections: {len(client_groups)}")
        for (t, p), fields in client_groups.items():
            print(f"    → tenant={t}, provider={p}, connection_id={p}_{t}, fields=[{', '.join(fields.keys()) if fields else '<not read in dry-run>'}]")
        print(f"  facu-format connections: {len(facundo_secrets)}")
        print(f"  unmatched (skipped): {len(unmatched)}")
        return

    # --- Write client_ groups to DB ---
    from credentials.secrets_backends import LocalSecretsBackend
    backend = LocalSecretsBackend()
    imported = 0
    errors = 0

    for (tenant_id, provider), fields in client_groups.items():
        if not fields:
            print(f"\n  ERROR: no fields read for {tenant_id}/{provider}, skipping")
            errors += 1
            continue

        connection_id = f"{provider}_{tenant_id}"
        db_secret_id = build_secret_id(tenant_id=tenant_id, provider=provider, connection_id=connection_id)

        with get_session() as session:
            repo = ConnectionRepository(session)
            existing = repo.get(tenant_id=tenant_id, connection_id=connection_id)

        if existing is not None:
            print(f"\n  SKIP  {connection_id} already in DB (status={existing.status.value})")
            continue

        payload = json.dumps(fields).encode("utf-8")
        backend.ensure_secret(db_secret_id)
        backend.add_secret_version(db_secret_id, payload)

        with get_session() as session:
            repo = ConnectionRepository(session)
            repo.create_with_connection_id(
                connection_id=connection_id,
                data=ConnectionCreate(
                    tenant_id=tenant_id,
                    provider=provider,
                    secret_id=db_secret_id,
                    name=json.dumps({"n": f"{provider.capitalize()} {tenant_id}", "b": "", "m": ""}),
                    status=ConnectionStatus.ACTIVE,
                ),
            )
        print(f"\n  IMPORTED  tenant={tenant_id}, provider={provider}")
        print(f"             connection_id={connection_id}")
        print(f"             payload fields: {list(fields.keys())}")
        imported += 1

    # --- Write facundo-format secrets to DB ---
    for secret_id, tenant_id, provider, connection_id in facundo_secrets:
        db_secret_id = build_secret_id(tenant_id=tenant_id, provider=provider, connection_id=connection_id)

        with get_session() as session:
            repo = ConnectionRepository(session)
            existing = repo.get(tenant_id=tenant_id, connection_id=connection_id)

        if existing is not None:
            print(f"\n  SKIP  {connection_id} already in DB")
            continue

        try:
            value = access_secret_raw(project, secret_id)
            payload = value.encode("utf-8") if isinstance(value, str) else value
        except RuntimeError as e:
            print(f"\n  ERROR reading {secret_id}: {e}")
            errors += 1
            continue

        backend.ensure_secret(db_secret_id)
        backend.add_secret_version(db_secret_id, payload)

        with get_session() as session:
            repo = ConnectionRepository(session)
            repo.create_with_connection_id(
                connection_id=connection_id,
                data=ConnectionCreate(
                    tenant_id=tenant_id,
                    provider=provider,
                    secret_id=db_secret_id,
                    name=None,
                    status=ConnectionStatus.ACTIVE,
                ),
            )
        print(f"\n  IMPORTED  {connection_id} (tenant={tenant_id}, provider={provider})")
        imported += 1

    print(f"\nDone: {imported} imported, {len(unmatched)} unmatched/skipped, {errors} errors.")
    if imported > 0:
        print("\nPayloads stored in .credentials_secrets.json")
        print("Metadata stored in mds_credentials.db")
        print("\nRestart the backend and refresh the Credentials Library page.")
    if imported > 0 and not dry_run:
        print("\nPayloads stored in .credentials_secrets.json")
        print("Metadata stored in mds_credentials.db")
        print("\nRestart the backend and refresh the Credentials Library page.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import GCP Secret Manager secrets into credentials DB.")
    parser.add_argument("--project", default="monks-mds-dev", help="GCP project ID")
    parser.add_argument(
        "--tenants",
        default="dev,cliente1",
        help="Comma-separated list of known tenant IDs (e.g. dev,cliente1,monks-mds)",
    )
    parser.add_argument("--dry-run", action="store_true", help="List matches without writing to DB")
    args = parser.parse_args()

    tenants = [t.strip() for t in args.tenants.split(",") if t.strip()]
    import_secrets(project=args.project, tenants=tenants, dry_run=args.dry_run)
