"""GCS-First Immutable Snapshot Store (DEC-05) with LocalFilesystemSnapshotStore dual-mode support."""

from __future__ import annotations

import hashlib
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from src.core.config import Settings, get_settings

SAFE_ID_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def _sanitize_component(raw: str) -> str:
    """Sanitize path components to prevent path traversal (mandatory-secure-web-skills)."""
    base = os.path.basename(raw.strip())
    cleaned = SAFE_ID_RE.sub("_", base)
    return cleaned or "snapshot"


class SnapshotStore(Protocol):
    """Protocol for immutable workbook snapshot archival (DEC-05)."""

    def archive_snapshot(
        self,
        spreadsheet_id: str,
        raw_bytes: bytes,
        extension: str = ".xlsx",
    ) -> str:
        """Persist raw_bytes immutably and return canonical gs:// URI."""
        ...


class LocalFilesystemSnapshotStore:
    """Stores immutable snapshots on local disk while returning canonical gs:// logical URIs."""

    def __init__(self, base_dir: Path, bucket_name: str) -> None:
        self.base_dir = base_dir.resolve()
        self.bucket_name = bucket_name
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def archive_snapshot(
        self,
        spreadsheet_id: str,
        raw_bytes: bytes,
        extension: str = ".xlsx",
    ) -> str:
        safe_sheet_id = _sanitize_component(spreadsheet_id)
        ext = extension if extension.startswith(".") else f".{extension}"
        safe_ext = _sanitize_component(ext)
        sha256_hex = hashlib.sha256(raw_bytes).hexdigest()
        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        filename = f"{ts}_{sha256_hex}{safe_ext}"

        target_dir = (self.base_dir / safe_sheet_id).resolve()
        if not str(target_dir).startswith(str(self.base_dir) + os.sep):
            raise ValueError("Path boundary violation in LocalFilesystemSnapshotStore")
        target_dir.mkdir(parents=True, exist_ok=True)

        target_file = (target_dir / filename).resolve()
        if not str(target_file).startswith(str(target_dir) + os.sep):
            raise ValueError("File boundary violation in LocalFilesystemSnapshotStore")

        target_file.write_bytes(raw_bytes)
        return f"gs://{self.bucket_name}/{safe_sheet_id}/{filename}"


class GCSSnapshotStore:
    """Uploads immutable snapshots directly to Google Cloud Storage in us-central1."""

    def __init__(self, project_id: str, bucket_name: str) -> None:
        self.project_id = project_id
        self.bucket_name = bucket_name

    def archive_snapshot(
        self,
        spreadsheet_id: str,
        raw_bytes: bytes,
        extension: str = ".xlsx",
    ) -> str:
        from google.cloud import storage  # type: ignore[import-untyped]

        safe_sheet_id = _sanitize_component(spreadsheet_id)
        ext = extension if extension.startswith(".") else f".{extension}"
        sha256_hex = hashlib.sha256(raw_bytes).hexdigest()
        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        blob_name = f"{safe_sheet_id}/{ts}_{sha256_hex}{ext}"

        client = storage.Client(project=self.project_id)
        bucket = client.bucket(self.bucket_name)
        blob = bucket.blob(blob_name)
        blob.upload_from_string(
            raw_bytes,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        return f"gs://{self.bucket_name}/{blob_name}"


def get_snapshot_store(settings: Settings | None = None) -> SnapshotStore:
    """Factory returning LocalFilesystemSnapshotStore in ENV=local or GCSSnapshotStore in ENV=gcp."""
    cfg = settings or get_settings()
    if cfg.env == "gcp":
        return GCSSnapshotStore(project_id=cfg.gcp_project_id, bucket_name=cfg.gcs_snapshot_bucket)
    return LocalFilesystemSnapshotStore(
        base_dir=cfg.local_snapshot_dir,
        bucket_name=cfg.gcs_snapshot_bucket,
    )
