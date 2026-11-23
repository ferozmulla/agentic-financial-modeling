"""Environment-driven settings for `latinlr202409-bq-twin` with strict identifier validation."""

from __future__ import annotations

import functools
import re
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_\-]+$")


class TwinSettings(BaseSettings):
    """Configuration for the isolated Latin America Refining Digital Twin."""

    model_config = SettingsConfigDict(env_prefix="LATINLR202409_TWIN_", extra="ignore")

    gcp_project_id: str = "comm-model-mod"
    gcp_region: str = "us-central1"
    bq_dataset_id: str = "latinlr202409_digital_twin"
    workbook_id: str = "latinlr202409"
    base_version_id: str = "lr202409_baseline"
    gcs_vault_bucket: str = "comm-model-mod-onboarding-staging"
    gcs_export_prefix: str = "exports/latinlr202409_twin"
    public_service_url: str = ""
    export_local_dir: str = str(Path("/tmp/latinlr202409_runtime_exports"))
    default_session_id: str = "latinlr202409-default-session"
    default_actor: str = "gemini-agent@comm-model-mod"

    @field_validator("gcp_project_id", "bq_dataset_id", "workbook_id", "base_version_id")
    @classmethod
    def _validate_identifier(cls, value: str) -> str:
        cleaned = value.strip()
        if not _SAFE_ID_RE.match(cleaned):
            raise ValueError(f"Unsafe identifier value: {value!r}")
        return cleaned


@functools.lru_cache(maxsize=1)
def get_twin_settings() -> TwinSettings:
    return TwinSettings()
