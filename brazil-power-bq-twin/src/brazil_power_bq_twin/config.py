"""Configuration settings for the isolated BigQuery Digital Twin service."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_SAFE_BQ_ID_RE = re.compile(r"^[A-Za-z0-9_\-]+$")


class TwinSettings(BaseSettings):
    """Environment-backed settings for `brazil-power-bq-twin`."""

    model_config = SettingsConfigDict(env_prefix="BQ_TWIN_", extra="ignore")

    gcp_project_id: str = Field(default="comm-model-mod")
    bq_dataset: str = Field(default="brazil_power_digital_twin")
    bq_location: str = Field(default="us-central1")
    max_bytes_billed: int = Field(default=50 * 1024 * 1024)
    gcs_bucket: str = Field(default="comm-model-mod-sheets-mod-artifacts")
    gcs_exports_prefix: str = Field(default="bq_twin_exports")
    gcs_artifacts_prefix: str = Field(default="bq_twin_artifacts")
    workbook_id: str = Field(default="brazil_power_v13")
    default_version_id: str = Field(default="v13_baseline")
    cloud_service_url: str = Field(
        default="https://brazil-power-bq-twin-mcp-1024543888590.us-central1.run.app"
    )
    local_export_dir: Path = Field(default=Path("/tmp/bq_twin_exports"))
    local_artifact_dir: Path = Field(default=Path("/tmp/bq_twin_artifacts"))

    @field_validator("gcp_project_id", "bq_dataset", "workbook_id", "default_version_id")
    @classmethod
    def _validate_identifier(cls, value: str) -> str:
        cleaned = value.strip()
        if not _SAFE_BQ_ID_RE.match(cleaned):
            raise ValueError(f"Unsafe identifier '{value}'.")
        return cleaned


@lru_cache(maxsize=1)
def get_twin_settings() -> TwinSettings:
    """Return cached TwinSettings instance."""
    return TwinSettings()
