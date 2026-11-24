"""Pydantic-settings configuration for Latinlr202409 BigQuery Digital Twin."""

from __future__ import annotations

import re
from pathlib import Path
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_\-]+$")


class TwinSettings(BaseSettings):
    """Application settings with environment variable overrides."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    project_id: str = "latinlr202409-gcp"
    dataset_id: str = "latinlr202409_digital_twin"
    workbook_id: str = "latinlr202409"
    base_version_id: str = "baseline"
    export_dir: Path = Path("/tmp/runtime_exports")

    @field_validator("project_id", "dataset_id", "workbook_id", "base_version_id")
    @classmethod
    def validate_bq_ids(cls, v: str) -> str:
        if not _SAFE_ID_RE.match(v):
            raise ValueError(f"Unsafe configuration value: {v!r}")
        return v


settings = TwinSettings()
