"""Pydantic schemas for Pillar B Structural Diffing and Immutable '4 Ws' Governance Audit Log."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from src.schemas.ast_dag import CellSemanticRole


class ChangeType(StrEnum):
    """Enumeration of governed structural change types (FR-B06 / FR-B08)."""

    MANUAL_OVERRIDE = "MANUAL_OVERRIDE"
    FORMULA_MODIFIED = "FORMULA_MODIFIED"
    FORMULA_ADDED = "FORMULA_ADDED"
    FORMULA_DELETED = "FORMULA_DELETED"
    HEADER_OR_LABEL_MODIFIED = "HEADER_OR_LABEL_MODIFIED"
    ROW_INSERTED = "ROW_INSERTED"
    ROW_DELETED = "ROW_DELETED"
    COL_INSERTED = "COL_INSERTED"
    COL_DELETED = "COL_DELETED"
    SHEET_ADDED = "SHEET_ADDED"
    SHEET_DELETED = "SHEET_DELETED"
    SHEET_VISIBILITY_CHANGED = "SHEET_VISIBILITY_CHANGED"
    NAMED_RANGE_MODIFIED = "NAMED_RANGE_MODIFIED"
    METADATA_CHANGED = "METADATA_CHANGED"
    INITIAL_BASELINE_INGESTED = "INITIAL_BASELINE_INGESTED"


class AuditSeverity(StrEnum):
    """Severity levels for 4-Ws governance events."""

    CRITICAL = "CRITICAL"
    WARNING = "WARNING"
    INFO = "INFO"


class AuditEventRecord(BaseModel):
    """Immutable '4 Ws' Audit Event Record (What Element, What Change, Who, When - FR-B08)."""

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    workbook_id: str
    spreadsheet_id: str
    version_id: str | None = None
    parent_version_id: str | None = None
    version_seq_num: int = 1

    # 1st W: What Element
    sheet_name: str
    cell_coord: str
    what_element_coord: str
    what_semantic_role: CellSemanticRole

    # 2nd W: What Change
    what_change_type: ChangeType
    severity: AuditSeverity
    before_state: dict[str, Any] = Field(default_factory=dict)
    after_state: dict[str, Any] = Field(default_factory=dict)

    # 3rd W: Who
    who_google_user: str
    who_iam_principal: str
    who_client_platform: str = "Google Sheets Web UI / Apps Script V8"
    who_spreadsheet_id: str

    # 4th W: When
    when_event_utc: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )
    gcs_snapshot_uri: str


class RealTimeEditEventRequest(BaseModel):
    """Payload sent by Apps Script onGovernedSheetEdit(e) / onGovernedSheetChange(e) to POST /v1/ingest/edit-event."""

    spreadsheet_id: str = Field(..., min_length=1, max_length=128)
    workbook_name: str = Field(default="Regional Power Generation Techno-Economic Model")
    spreadsheet_url: str | None = None
    sheet_name: str = Field(..., min_length=1, max_length=128)
    cell_coord: str = Field(default="A1", min_length=1, max_length=64)
    row_num: int = Field(default=1, ge=1)
    col_num: int = Field(default=1, ge=1)
    old_value: str | None = None
    new_value: str | None = None
    new_formula: str | None = None
    structural_change_type: str | None = None
    who_google_user: str = Field(default="analyst@enterprise.com")
    when_event_utc: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )


class RealTimeEditEventResponse(BaseModel):
    """Response returned to Apps Script onGovernedSheetEdit(e)."""

    status: str  # LOGGED | SUPPRESSED
    change_type: ChangeType | None = None
    severity: AuditSeverity | None = None
    event_id: str | None = None
    processing_time_ms: float


class CheckpointIngestResponse(BaseModel):
    """Response returned by POST /v1/ingest/checkpoint."""

    version_id: str
    parent_version_id: str | None = None
    version_seq_num: int
    spreadsheet_id: str
    workbook_name: str
    gcs_snapshot_uri: str
    total_sheets: int
    total_populated_cells: int
    total_formula_cells: int
    total_dag_edges: int
    total_named_ranges: int
    broken_named_ranges: int
    structural_mutation_count: int
    manual_override_count: int
    suppressed_noise_count: int
    ingestion_time_ms: float
    audit_events: list[AuditEventRecord] = Field(default_factory=list)
