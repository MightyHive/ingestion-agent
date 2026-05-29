"""Backends for storing credential payloads outside the metadata database.

Three backends are available:
- ``LocalSecretsBackend``: stores payloads in a local JSON file (default for dev).
- ``GcpCliSecretsBackend``: uses gcloud CLI — no SDK needed, works with existing auth.
- ``GcpSecretsBackend``: uses google-cloud-secretmanager SDK (optional, for prod).

Set ``MDS_SECRETS_BACKEND=gcp`` to use GCP. Defaults to ``local``.
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path

from credentials.exceptions import SecretManagerError


class SecretsBackend(ABC):
    @abstractmethod
    def ensure_secret(self, secret_id: str) -> None:
        """Create backing storage for a secret if it does not exist."""

    @abstractmethod
    def add_secret_version(self, secret_id: str, payload: bytes) -> str:
        """Persist a new payload version and return a version identifier."""

    @abstractmethod
    def access_secret_version(self, secret_id: str, version: str = "latest") -> bytes:
        """Read one payload version and return raw bytes."""

    @abstractmethod
    def disable_all_secret_versions(self, secret_id: str) -> int:
        """Disable all enabled versions; return count disabled."""

    @abstractmethod
    def secret_exists(self, secret_id: str) -> bool:
        """Return True if the secret exists and has an accessible latest version."""

    @abstractmethod
    def list_secret_ids(self, prefix: str) -> list[str]:
        """Return all secret IDs whose name starts with *prefix*."""


class LocalSecretsBackend(SecretsBackend):
    """File-based secrets backend for local development.

    Payloads are stored in a JSON file at ``MDS_LOCAL_SECRETS_PATH`` or
    ``<repo_root>/.credentials_secrets.json`` by default.
    """

    def __init__(self, store_path: Path | None = None):
        if store_path is None:
            default_path = os.getenv("MDS_LOCAL_SECRETS_PATH", "")
            if default_path:
                store_path = Path(default_path)
            else:
                repo_root = Path(__file__).resolve().parents[2]
                store_path = repo_root / ".credentials_secrets.json"
        self._path = store_path

    def _load(self) -> dict:
        if not self._path.exists():
            return {}
        return json.loads(self._path.read_text())

    def _save(self, data: dict) -> None:
        self._path.write_text(json.dumps(data, indent=2))

    def ensure_secret(self, secret_id: str) -> None:
        data = self._load()
        if secret_id not in data:
            data[secret_id] = {"versions": [], "disabled": False}
            self._save(data)

    def add_secret_version(self, secret_id: str, payload: bytes) -> str:
        data = self._load()
        if secret_id not in data:
            data[secret_id] = {"versions": [], "disabled": False}
        encoded = base64.b64encode(payload).decode("ascii")
        data[secret_id]["versions"].append(encoded)
        data[secret_id]["disabled"] = False
        self._save(data)
        return f"{secret_id}/versions/{len(data[secret_id]['versions'])}"

    def access_secret_version(self, secret_id: str, version: str = "latest") -> bytes:
        data = self._load()
        entry = data.get(secret_id)
        if not entry or not entry["versions"]:
            raise SecretManagerError(f"secret '{secret_id}' not found or has no versions")
        if entry.get("disabled"):
            raise SecretManagerError(f"secret '{secret_id}' is disabled")
        encoded = entry["versions"][-1]
        return base64.b64decode(encoded)

    def disable_all_secret_versions(self, secret_id: str) -> int:
        data = self._load()
        entry = data.get(secret_id)
        if not entry:
            return 0
        count = len(entry["versions"])
        entry["disabled"] = True
        self._save(data)
        return count

    def secret_exists(self, secret_id: str) -> bool:
        data = self._load()
        entry = data.get(secret_id)
        if not entry or not entry.get("versions"):
            return False
        return not entry.get("disabled", False)

    def list_secret_ids(self, prefix: str) -> list[str]:
        data = self._load()
        return [sid for sid in data.keys() if sid.startswith(prefix)]


class GcpCliSecretsBackend(SecretsBackend):
    """GCP Secret Manager backend via gcloud CLI.

    Does not require the google-cloud-secretmanager SDK.
    Relies on ``gcloud`` being installed and authenticated
    (run ``gcloud auth login && gcloud auth application-default login``).
    """

    def __init__(self, project_id: str):
        self._project = project_id

    def _run(self, *args: str) -> str:
        result = subprocess.run(["gcloud", *args], capture_output=True, text=True)
        if result.returncode != 0:
            err = result.stderr.strip()
            if "Reauthentication" in err or "auth" in err.lower():
                raise SecretManagerError(
                    "gcloud not authenticated. Run: gcloud auth login && gcloud auth application-default login"
                )
            raise SecretManagerError(f"gcloud error: {err}")
        return result.stdout.strip()

    def ensure_secret(self, secret_id: str) -> None:
        check = subprocess.run(
            ["gcloud", "secrets", "describe", secret_id, f"--project={self._project}"],
            capture_output=True, text=True,
        )
        if check.returncode == 0:
            return
        self._run("secrets", "create", secret_id,
                  f"--project={self._project}", "--replication-policy=automatic")

    def add_secret_version(self, secret_id: str, payload: bytes) -> str:
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(payload)
            tmp = f.name
        try:
            out = self._run("secrets", "versions", "add", secret_id,
                            f"--project={self._project}", f"--data-file={tmp}")
        finally:
            os.unlink(tmp)
        return out

    def access_secret_version(self, secret_id: str, version: str = "latest") -> bytes:
        out = self._run("secrets", "versions", "access", version,
                        f"--secret={secret_id}", f"--project={self._project}")
        return out.encode("utf-8")

    def disable_all_secret_versions(self, secret_id: str) -> int:
        out = self._run("secrets", "versions", "list", secret_id,
                        f"--project={self._project}", "--format=json")
        versions = json.loads(out) if out.strip() else []
        enabled = [v for v in versions if v.get("state") == "ENABLED"]
        for v in enabled:
            version_id = v["name"].split("/")[-1]
            self._run("secrets", "versions", "disable", version_id,
                      f"--secret={secret_id}", f"--project={self._project}")
        return len(enabled)

    def secret_exists(self, secret_id: str) -> bool:
        check = subprocess.run(
            ["gcloud", "secrets", "describe", secret_id, f"--project={self._project}"],
            capture_output=True, text=True,
        )
        if check.returncode == 0:
            return True
        # Only treat as non-existent on an explicit NOT_FOUND response.
        # Any other failure (PERMISSION_DENIED, network error, etc.)
        # returns True so the health check never deletes a record it
        # cannot confidently confirm is gone.
        err = check.stderr
        return not ("NOT_FOUND" in err or "not found" in err.lower())

    def list_secret_ids(self, prefix: str) -> list[str]:
        check = subprocess.run(
            [
                "gcloud", "secrets", "list",
                f"--project={self._project}",
                "--format=value(name)",
            ],
            capture_output=True, text=True,
        )
        if check.returncode != 0:
            return []
        ids = []
        for line in check.stdout.splitlines():
            # Full resource name: projects/PROJECT/secrets/SECRET_ID
            secret_id = line.strip().split("/")[-1]
            if secret_id.startswith(prefix):
                ids.append(secret_id)
        return ids


class GcpSecretsBackend(SecretsBackend):
    """Google Secret Manager backend via Python SDK (requires google-cloud-secretmanager)."""

    def __init__(self, project_id: str, client=None):
        self._project_id = project_id
        self._client = client

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            from google.cloud import secretmanager
            return secretmanager.SecretManagerServiceClient()
        except ImportError as exc:
            raise SecretManagerError(
                "google-cloud-secretmanager is not installed. "
                "Run: pip install google-cloud-secretmanager"
            ) from exc

    def ensure_secret(self, secret_id: str) -> None:
        try:
            from google.api_core.exceptions import AlreadyExists, GoogleAPICallError
            from google.cloud import secretmanager
        except ImportError as exc:
            raise SecretManagerError("google-cloud-secretmanager not installed") from exc

        client = self._get_client()
        parent = f"projects/{self._project_id}"
        secret = secretmanager.Secret(
            replication=secretmanager.Replication(
                automatic=secretmanager.Replication.Automatic()
            )
        )
        try:
            client.create_secret(
                request={"parent": parent, "secret_id": secret_id, "secret": secret}
            )
        except AlreadyExists:
            return
        except GoogleAPICallError as exc:
            raise SecretManagerError(
                f"failed to create secret '{secret_id}' in project '{self._project_id}'"
            ) from exc

    def add_secret_version(self, secret_id: str, payload: bytes) -> str:
        try:
            from google.api_core.exceptions import GoogleAPICallError
        except ImportError as exc:
            raise SecretManagerError("google-cloud-secretmanager not installed") from exc

        client = self._get_client()
        parent = f"projects/{self._project_id}/secrets/{secret_id}"
        try:
            response = client.add_secret_version(
                request={"parent": parent, "payload": {"data": payload}}
            )
        except GoogleAPICallError as exc:
            raise SecretManagerError(f"failed to add version for secret '{secret_id}'") from exc
        return response.name

    def access_secret_version(self, secret_id: str, version: str = "latest") -> bytes:
        try:
            from google.api_core.exceptions import GoogleAPICallError
        except ImportError as exc:
            raise SecretManagerError("google-cloud-secretmanager not installed") from exc

        client = self._get_client()
        name = f"projects/{self._project_id}/secrets/{secret_id}/versions/{version}"
        try:
            response = client.access_secret_version(request={"name": name})
        except GoogleAPICallError as exc:
            raise SecretManagerError(
                f"failed to access version '{version}' for secret '{secret_id}'"
            ) from exc
        return bytes(response.payload.data)

    def disable_all_secret_versions(self, secret_id: str) -> int:
        try:
            from google.api_core.exceptions import GoogleAPICallError
            from google.cloud import secretmanager
        except ImportError as exc:
            raise SecretManagerError("google-cloud-secretmanager not installed") from exc

        client = self._get_client()
        parent = f"projects/{self._project_id}/secrets/{secret_id}"
        disabled = 0
        try:
            for version in client.list_secret_versions(request={"parent": parent}):
                if version.state != secretmanager.SecretVersion.State.ENABLED:
                    continue
                client.disable_secret_version(request={"name": version.name})
                disabled += 1
        except GoogleAPICallError as exc:
            raise SecretManagerError(
                f"failed to disable versions for secret '{secret_id}'"
            ) from exc
        return disabled

    def secret_exists(self, secret_id: str) -> bool:
        try:
            from google.api_core.exceptions import GoogleAPICallError, NotFound
        except ImportError:
            return False
        client = self._get_client()
        name = f"projects/{self._project_id}/secrets/{secret_id}/versions/latest"
        try:
            client.access_secret_version(request={"name": name})
            return True
        except NotFound:
            return False
        except GoogleAPICallError:
            return True  # Unknown error → assume intact

    def list_secret_ids(self, prefix: str) -> list[str]:
        try:
            from google.api_core.exceptions import GoogleAPICallError
        except ImportError:
            return []
        client = self._get_client()
        parent = f"projects/{self._project_id}"
        try:
            ids = []
            for secret in client.list_secrets(request={"parent": parent}):
                # Full name: projects/PROJECT/secrets/SECRET_ID
                secret_id = secret.name.split("/")[-1]
                if secret_id.startswith(prefix):
                    ids.append(secret_id)
            return ids
        except GoogleAPICallError:
            return []
