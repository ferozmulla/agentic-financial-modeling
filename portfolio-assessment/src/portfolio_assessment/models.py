"""Typed data structures for LES, MHS, MRI scorecards and cell-level defects."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SubMetricScore:
    code: str
    title: str
    base_weight: float
    applicable: bool
    effective_weight: float
    score: float | None
    summary: str


@dataclass(frozen=True)
class PillarScore:
    name: str
    acronym: str
    score: float
    sub_metrics: list[SubMetricScore]


@dataclass(frozen=True)
class CellDefectRecord:
    workbook_name: str
    sheet_name: str
    cell_coord: str
    sub_metric: str
    defect_type: str
    severity: str
    detail: str


@dataclass(frozen=True)
class ExternalLinkAuditRecord:
    workbook_name: str
    link_index: str
    raw_target: str
    link_health_tier: str
    syntactic_score: float
    active_formula_refs: int
    resolution_status: str
    resolved_local_path: str
    missing_sheets_count: int
    exact_match_cells: int
    drifted_cells: int
    max_rel_drift: float


@dataclass(frozen=True)
class WorkbookScorecard:
    workbook_name: str
    workbook_path: str
    file_size_mb: float
    archetype: str
    vintage_tag: str
    sheet_count: int
    total_populated_cells: int
    total_formula_cells: int
    les: PillarScore
    mhs: PillarScore
    defect_rate: float
    mri: float
    readiness_tier: str
    recommended_action: str
    telemetry: dict[str, Any] = field(default_factory=dict)
