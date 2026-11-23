"""Typed Pydantic schemas for Hygiene Exceptions, Go/No-Go Gate, Parity Verification, PRs, and Jobs."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class GoNoGoDecision(str, Enum):
    """Pre-flight onboarding recommendation based on workbook extractability and hygiene."""

    GO = "GO"
    CONDITIONAL_GO = "CONDITIONAL_GO"
    NO_GO = "NO_GO"


class HygieneExceptionItem(BaseModel):
    """Single aggregated exception surfaced during Stage 1 workbook hygiene inspection."""

    code: str
    severity: Literal["BLOCKER", "WARNING", "INFO"]
    sub_metric: str
    title: str
    affected_count: int = Field(ge=0)
    sample_locations: list[str] = Field(default_factory=list)
    remediation: str


class SubMetricSummary(BaseModel):
    """Serialized sub-metric entry for E1..E5 and H1..H5."""

    code: str
    title: str
    applicable: bool
    effective_weight: float
    score: float | None
    summary: str


class HygieneGateReport(BaseModel):
    """Complete Stage 1 pre-flight assessment, Exception Report, and Go/No-Go verdict."""

    model_slug: str
    workbook_name: str
    file_size_mb: float
    archetype: str
    vintage_tag: str
    sheet_count: int
    total_populated_cells: int
    total_formula_cells: int
    mes_score: float
    mhs_score: float
    mdr_score: float
    mri_score: float
    readiness_tier: str
    recommended_action: str
    decision: GoNoGoDecision
    decision_rationale: list[str]
    exceptions: list[HygieneExceptionItem] = Field(default_factory=list)
    extractability_metrics: list[SubMetricSummary] = Field(default_factory=list)
    hygiene_metrics: list[SubMetricSummary] = Field(default_factory=list)
    candidate_assumption_sheets: list[str] = Field(default_factory=list)
    candidate_timeseries_sheets: list[str] = Field(default_factory=list)
    vba_modules: list[str] = Field(default_factory=list)
    is_iterative_calc: bool = False
    iterate_count: int = 1
    telemetry: dict[str, Any] = Field(default_factory=dict)
    evaluated_at_utc: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class ParitySheetSummary(BaseModel):
    """Per-sheet numeric parity comparison summary against cached Excel baseline values."""

    sheet_name: str
    compared_cells: int = Field(ge=0)
    matched_cells: int = Field(ge=0)
    mismatched_cells: int = Field(ge=0)
    max_abs_error: float = Field(default=0.0, ge=0.0)
    max_rel_error: float = Field(default=0.0, ge=0.0)


class ParityVerificationReport(BaseModel):
    """Stage 2 numeric parity report verified both inside the sandbox and locally post-download."""

    model_slug: str
    passed: bool
    pytest_passed: int = Field(default=0, ge=0)
    pytest_failed: int = Field(default=0, ge=0)
    total_compared_cells: int = Field(default=0, ge=0)
    total_matched_cells: int = Field(default=0, ge=0)
    parity_rate_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    max_abs_error: float = Field(default=0.0, ge=0.0)
    max_rel_error: float = Field(default=0.0, ge=0.0)
    sheet_summaries: list[ParitySheetSummary] = Field(default_factory=list)
    documented_irreducible_exceptions: list[str] = Field(default_factory=list)
    interaction_id: str = ""
    environment_id: str = ""
    repair_turns_used: int = Field(default=0, ge=0)
    verified_locally: bool = False


class PullRequestResult(BaseModel):
    """Stage 3a Git branch and Pull Request creation summary."""

    model_slug: str
    branch_name: str
    commit_sha: str
    package_dir: str
    golden_seed_gcs_uri: str = ""
    pr_url: str = ""
    pr_number: int | None = None
    local_only: bool = False


class DeploymentSummary(BaseModel):
    """Stage 3b deterministic post-PR-merge GCP & Agent Registry deployment summary."""

    model_slug: str
    gcp_project_id: str
    bq_dataset_id: str
    bqml_trained: bool
    cloud_run_service: str
    cloud_run_url: str
    registry_project_id: str
    mcp_service_action: str
    published_skills: list[str] = Field(default_factory=list)
    deployed_at_utc: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class OnboardingJobState(str, Enum):
    """Lifecycle states of an onboarding job."""

    PENDING = "PENDING"
    ASSESSING_HYGIENE = "ASSESSING_HYGIENE"
    BLOCKED_NO_GO = "BLOCKED_NO_GO"
    RUNNING_SANDBOX_CODEGEN = "RUNNING_SANDBOX_CODEGEN"
    VERIFYING_BUNDLE = "VERIFYING_BUNDLE"
    PUBLISHING_PR = "PUBLISHING_PR"
    AWAITING_PR_APPROVAL = "AWAITING_PR_APPROVAL"
    DEPLOYING = "DEPLOYING"
    DEPLOYED = "DEPLOYED"
    FAILED = "FAILED"


class OnboardingJobStatus(BaseModel):
    """Persisted status envelope for CLI & Gemini Agent MCP polling."""

    job_id: str
    model_slug: str
    source_workbook: str
    state: OnboardingJobState
    hygiene_report: HygieneGateReport | None = None
    parity_report: ParityVerificationReport | None = None
    pr_result: PullRequestResult | None = None
    deployment: DeploymentSummary | None = None
    error_message: str = ""
    created_at_utc: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at_utc: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class UploadSessionInfo(BaseModel):
    """Signed GCS upload URL and direct `/v1/uploads` fallback for Cowork `+` session file attachments."""

    upload_id: str
    filename: str
    workbook_gcs_uri: str
    signed_put_url: str = ""
    direct_post_url: str = ""
    content_type: str
    expires_in_seconds: int = 900
