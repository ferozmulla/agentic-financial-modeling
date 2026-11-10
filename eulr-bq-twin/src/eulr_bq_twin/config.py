"""Environment-driven settings for the isolated EULR BigQuery Digital Twin (`eulr-bq-twin`)."""

from __future__ import annotations

import functools
import re
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_\-]+$")


class EulrTwinSettings(BaseSettings):
    """Configuration strictly segregated from Brazil Power resources."""

    model_config = SettingsConfigDict(
        env_prefix="EULR_TWIN_",
        extra="ignore",
    )

    gcp_project_id: str = "comm-model-mod"
    gcp_region: str = "us-central1"
    bq_dataset_id: str = "eulr_digital_twin"
    workbook_id: str = "eulr_refining_202409"
    base_version_id: str = "lr202409_baseline"
    gcs_vault_bucket: str = "comm-model-mod-eulr-twin-vault"
    gcs_export_prefix: str = "exports/eulr_twin"
    public_service_url: str = ""
    export_local_dir: str = str(
        (Path(__file__).resolve().parents[2] / "runtime_exports")
        if "site-packages" not in str(Path(__file__).resolve())
        else Path("/tmp/eulr_runtime_exports")
    )
    default_session_id: str = "eulr-default-session"
    default_actor: str = "gemini-agent@comm-model-mod"

    @field_validator("gcp_project_id", "bq_dataset_id", "workbook_id", "base_version_id")
    @classmethod
    def _validate_identifier(cls, value: str) -> str:
        cleaned = value.strip()
        if not _SAFE_ID_RE.match(cleaned):
            raise ValueError(f"Unsafe identifier format: {value!r}")
        return cleaned


@functools.lru_cache(maxsize=1)
def get_eulr_twin_settings() -> EulrTwinSettings:
    return EulrTwinSettings()
