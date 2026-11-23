"""Environment-backed settings and identifier allowlist validators for `model-onboarding`."""

from __future__ import annotations

import functools
import os
import re
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_\-]+$")
_SAFE_SLUG_RE = re.compile(r"^[a-z][a-z0-9\-]{1,47}[a-z0-9]$")
_SAFE_REPO_RE = re.compile(r"^[A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+$")


def validate_safe_identifier(value: str, field_name: str = "identifier") -> str:
    """Validate GCP project, dataset, bucket, or job IDs against strict allowlist."""
    cleaned = value.strip()
    if not cleaned or not _SAFE_ID_RE.match(cleaned) or ".." in cleaned:
        raise ValueError(f"Unsafe {field_name}: {value!r}")
    return cleaned


def validate_model_slug(slug: str) -> str:
    """Validate lowercase kebab-case model slug (3..49 chars, safe for Cloud Run & Agent Registry)."""
    cleaned = slug.strip().lower()
    if not _SAFE_SLUG_RE.match(cleaned) or "--" in cleaned:
        raise ValueError(
            f"Invalid model_slug {slug!r}: must match ^[a-z][a-z0-9-]{{1,47}}[a-z0-9]$ without '--'."
        )
    return cleaned


def derive_default_slug(workbook_name: str) -> str:
    """Derive a clean lowercase kebab-case slug from an Excel filename."""
    stem = Path(workbook_name).stem.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", stem).strip("-")
    slug = re.sub(r"^[^a-z]+", "", slug)
    slug = re.sub(r"-{2,}", "-", slug)
    if len(slug) < 3:
        slug = f"energy-{slug or 'model'}"
    return slug[:45].rstrip("-")


def resolve_github_token() -> str | None:
    """Read GitHub token from environment at call time without storing or logging secrets."""
    token = os.getenv("ONBOARD_GITHUB_TOKEN") or os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    return token.strip() if token and token.strip() else None


class OnboardingSettings(BaseSettings):
    """Configuration for Stage 1 Hygiene Gate, Stage 2 Managed Agents Worker, and Stage 3 Deployer."""

    model_config = SettingsConfigDict(env_prefix="ONBOARD_", extra="ignore")

    gcp_project_id: str = Field(default="comm-model-mod")
    gcp_region: str = Field(default="us-central1")
    managed_agents_location: str = Field(default="global")
    managed_agent_id: str = Field(default="energy-twin-onboarder")
    base_agent: str = Field(default="antigravity-preview-05-2026")
    staging_bucket: str = Field(default="comm-model-mod-onboarding-staging")
    vault_bucket: str = Field(default="comm-model-mod-sheets-mod-artifacts")
    registry_project_id: str = Field(default="comm-model-mod")
    registry_location: str = Field(default="global")
    github_repo: str = Field(default="ferozmulla/agentic-financial-modeling")
    base_git_branch: str = Field(default="main")

    # Tunable Go / Conditional-Go / No-Go policy thresholds
    no_go_min_mri: float = Field(default=50.0, ge=0.0, le=100.0)
    go_min_mri: float = Field(default=80.0, ge=0.0, le=100.0)
    go_max_mdr: float = Field(default=15.0, ge=0.0, le=100.0)
    min_external_cache_coverage: float = Field(default=0.90, ge=0.0, le=1.0)
    max_workbook_size_mb: float = Field(default=100.0, gt=0.0, le=500.0)
    max_repair_turns: int = Field(default=2, ge=0, le=5)
    interaction_timeout_sec: float = Field(default=600.0, gt=10.0, le=3600.0)

    local_jobs_dir: Path = Field(default=Path("/tmp/model_onboarding_jobs"))
    default_session_id: str = Field(default="onboarding-admin-session")
    public_service_url: str = Field(default="")
    service_account_email: str = Field(default="")

    @field_validator(
        "gcp_project_id",
        "gcp_region",
        "managed_agents_location",
        "managed_agent_id",
        "base_agent",
        "staging_bucket",
        "vault_bucket",
        "registry_project_id",
        "registry_location",
        "base_git_branch",
        "default_session_id",
    )
    @classmethod
    def _check_safe_id(cls, value: str) -> str:
        return validate_safe_identifier(value)

    @field_validator("github_repo")
    @classmethod
    def _check_repo(cls, value: str) -> str:
        cleaned = value.strip()
        if not _SAFE_REPO_RE.match(cleaned) or ".." in cleaned:
            raise ValueError(f"Unsafe github_repo format: {value!r}")
        return cleaned


@functools.lru_cache(maxsize=1)
def get_onboarding_settings() -> OnboardingSettings:
    """Return cached OnboardingSettings instance."""
    return OnboardingSettings()
