"""Pydantic schemas for Cloud Execution Telemetry Units and Step Trails."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class TelemetryStepStatus(StrEnum):
    """Execution status for an individual telemetry step or unit."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class TelemetryStep(BaseModel):
    """Single step inside a Unit of Execution."""

    step_index: int = Field(..., ge=1, description="1-based step sequence number inside the unit")
    system: Literal["Google Sheets", "Apps Script", "Cloud Run", "Solver Engine", "BigQuery"]
    artifact: str = Field(..., description="Artifact name, e.g. 'Regional Power Model (v13)'")
    component: str = Field(..., description="Tab, endpoint, or module name, e.g. 'General tab'")
    action: str = Field(..., description="Concise human-readable description of the specific action")
    started_at_utc: str = Field(..., description="ISO-8601 UTC start timestamp")
    completed_at_utc: str = Field(..., description="ISO-8601 UTC completion timestamp")
    duration_ms: float = Field(..., ge=0.0, description="Elapsed step duration in milliseconds")
    status: TelemetryStepStatus = Field(default=TelemetryStepStatus.SUCCESS)


class ExecutionUnit(BaseModel):
    """Grouped Unit of Execution representing a complete Macro Solve or BQML Refresh trail."""

    unit_id: str
    unit_seq: int
    unit_type: Literal["macro_solve", "bqml_refresh"]
    macro_name: str
    display_title: str
    button_label: str
    workbook_id: str
    spreadsheet_id: str
    triggered_by: str
    started_at_utc: str
    completed_at_utc: str
    total_duration_ms: float
    status: TelemetryStepStatus = Field(default=TelemetryStepStatus.SUCCESS)
    solve_count: int = Field(default=0)
    input_change_count: int = Field(default=0)
    target_ranges: list[str] = Field(default_factory=list)
    steps: list[TelemetryStep] = Field(default_factory=list)


class TelemetryFeedResponse(BaseModel):
    """Response payload returned by GET /v1/telemetry/units."""

    service: str = Field(default="sheets-commodity-mod-gateway")
    model_name: str = Field(default="Regional Power Generation Techno-Economic Model (v13)")
    total_units: int
    latest_unit_seq: int
    avg_duration_ms: float
    units: list[ExecutionUnit]
