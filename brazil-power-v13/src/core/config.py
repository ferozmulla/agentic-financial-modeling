"""Application configuration and environment settings (ENV=local | ENV=gcp)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Centralized settings supporting dual-mode execution (ENV=local vs ENV=gcp)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: Literal["local", "gcp"] = Field(default="local", validation_alias="ENV")
    gcp_project_id: str = Field(default="comm-model-mod", validation_alias="GCP_PROJECT_ID")
    gcp_region: str = Field(default="us-central1", validation_alias="GCP_REGION")
    gcp_zone: str = Field(default="us-central1-a", validation_alias="GCP_ZONE")
    bq_location: str = Field(default="us-central1", validation_alias="BQ_LOCATION")
    gemini_location: str = Field(default="us", validation_alias="GEMINI_LOCATION")
    bq_dataset_id: str = Field(
        default="sheets_commodity_mod_governance",
        validation_alias="BQ_DATASET_ID",
    )
    app_label: str = Field(default="sheets-commodity-mod", validation_alias="APP_LABEL")

    seed_workbook_path: Path = Field(
        default=PROJECT_ROOT / "seed" / "2023-11-27-Brazil_TT_v13_RJEB.xlsm",
        validation_alias="SEED_WORKBOOK_PATH",
    )
    golden_spreadsheet_id: str = Field(
        default="1apbos5xVpK4yBLiRFxQqAEyPVNkkYQ2ZvgAASibYYJI",
        validation_alias="GOLDEN_SPREADSHEET_ID",
    )
    baseline_fixture_path: Path = Field(
        default=PROJECT_ROOT / "data" / "fixtures" / "brazil_tt_v13_baseline.json",
        validation_alias="BASELINE_FIXTURE_PATH",
    )

    database_url: str = Field(
        default=f"sqlite+aiosqlite:///{PROJECT_ROOT / 'data' / 'local_alloydb_parity.db'}",
        validation_alias="DATABASE_URL",
    )
    local_snapshot_dir: Path = Field(
        default=PROJECT_ROOT / "data" / "snapshots",
        validation_alias="LOCAL_SNAPSHOT_DIR",
    )
    local_bq_sink_dir: Path = Field(
        default=PROJECT_ROOT / "data" / "bigquery_sink",
        validation_alias="LOCAL_BQ_SINK_DIR",
    )
    gcs_snapshot_bucket: str = Field(
        default="comm-model-mod-sheets-mod-snapshots",
        validation_alias="GCS_SNAPSHOT_BUCKET",
    )
    gcs_artifacts_bucket: str = Field(
        default="comm-model-mod-sheets-mod-artifacts",
        validation_alias="GCS_ARTIFACTS_BUCKET",
    )

    enable_vertex_remote_predict: bool = Field(
        default=False,
        validation_alias="ENABLE_VERTEX_REMOTE_PREDICT",
    )
    vertex_endpoint_id: str = Field(
        default="sheets-commodity-mod-solver-ep",
        validation_alias="VERTEX_ENDPOINT_ID",
    )
    vertex_model_name: str = Field(
        default="sheets-commodity-mod-lcoe-solver",
        validation_alias="VERTEX_MODEL_NAME",
    )
    local_dev_auth_bypass: bool = Field(
        default=True,
        validation_alias="LOCAL_DEV_AUTH_BYPASS",
    )
    gateway_host: str = Field(default="127.0.0.1", validation_alias="GATEWAY_HOST")
    gateway_port: int = Field(default=8000, validation_alias="GATEWAY_PORT")
    max_upload_bytes: int = Field(default=25 * 1024 * 1024, validation_alias="MAX_UPLOAD_BYTES")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached Settings instance."""
    return Settings()
