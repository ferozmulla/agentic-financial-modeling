"""Environment configuration and resource bindings for the EULR platform."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: Literal["local", "dev", "prod"] = "local"
    gcp_project_id: str = "comm-model-mod"
    gcp_region: str = "us-central1"
    gemini_location: str = "us"
    gemini_model_id: str = "gemini-3.8-flash"
    bigquery_dataset: str = "eulr_commodity_mod_governance"
    gcs_snapshot_bucket: str = "comm-model-mod-eulr-snapshots"
    cloud_run_service_name: str = "eulr-equilibrium-gateway"
    vertex_surrogate_model_name: str = "eulr-sheets-mod-margin-surrogate"
    enable_vertex_remote_predict: bool = False
    upstream_source_mode: Literal["eulr_baseline_cached", "peer_xlsx", "sharepoint_graph"] = (
        "eulr_baseline_cached"
    )
    eulr_seed_workbook_path: str = "seed/Eulr202409.xlsx"
    eulr_references_dir: str = "references"
    central_spreadsheet_id: str = "1rXSFn7dACfy7RTaNHxinstJAgk54ojMgDPsoxoZRgQk"
    sqlite_db_url: str = "sqlite+aiosqlite:///./data/eulr_governance_local.db"

    @property
    def resolved_seed_path(self) -> Path:
        candidate = BASE_DIR / self.eulr_seed_workbook_path
        if candidate.exists():
            return candidate
        fallback = BASE_DIR / "docs" / "Eulr202409.xlsx"
        return fallback

    @property
    def resolved_references_dir(self) -> Path:
        candidate = BASE_DIR / self.eulr_references_dir
        if candidate.exists():
            return candidate
        return BASE_DIR / "docs" / "references"

    @property
    def data_dir(self) -> Path:
        d = BASE_DIR / "data"
        d.mkdir(parents=True, exist_ok=True)
        return d


settings = Settings()
