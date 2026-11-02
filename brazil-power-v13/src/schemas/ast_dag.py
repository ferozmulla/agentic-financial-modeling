"""Pydantic schemas and enums for Pillar B AST, DAG, Cell Semantic Roles, and Technical Debt."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class CellSemanticRole(StrEnum):
    """Four mutually exclusive deterministic semantic roles for every populated cell (FR-B01)."""

    FORMULA_CELL = "FORMULA_CELL"
    SOLVER_OUTPUT_CELL = "SOLVER_OUTPUT_CELL"
    SCENARIO_INPUT_CELL = "SCENARIO_INPUT_CELL"
    LABEL_OR_STATIC_CELL = "LABEL_OR_STATIC_CELL"


class ExtractedCellRecord(BaseModel):
    """Canonical AST node representing a single populated cell in a worksheet."""

    sheet_name: str
    cell_coord: str
    row_num: int
    col_num: int
    col_letter: str
    data_type: str
    raw_value: str | None = None
    numeric_value: float | None = None
    raw_formula: str | None = None
    canonical_formula: str | None = None
    r1c1_formula: str | None = None
    formula_hash: str | None = None
    shared_group_index: int | None = None
    is_shared_master: bool = False
    semantic_role: CellSemanticRole


class DependencyEdgeRecord(BaseModel):
    """Directed Precedent -> Dependent formula dependency edge in the workbook DAG (FR-B03)."""

    precedent_sheet: str
    precedent_coord: str
    dependent_sheet: str
    dependent_coord: str
    reference_type: str = "DIRECT_CELL"  # DIRECT_CELL | RANGE_EXPANSION | NAMED_RANGE


class NamedRangeRecord(BaseModel):
    """Represents a workbook-scoped or sheet-scoped Defined Name (FR-B04)."""

    name: str
    local_sheet_id: int | None = None
    scope_sheet_name: str | None = None
    refers_to: str
    is_broken_ref: bool = False
    hidden: bool = False


class MacroBindingRecord(BaseModel):
    """Represents an interactive form/drawing button bound to a solver macro on General."""

    sheet_name: str
    anchor_cell: str
    button_label: str
    macro_target: str
    raw_macro_ref: str


class TechnicalDebtItemRecord(BaseModel):
    """Represents a cataloged legacy technical debt artifact (DEC-02 / FR-B04)."""

    debt_category: str  # BROKEN_NAMED_RANGE | BROKEN_VBA_SUB | EMPTY_MODULE | ORPHAN_SHEET_REF
    identifier: str
    location: str
    details: str
    severity: str = "WARNING"


class ExtractedSheetRecord(BaseModel):
    """Metadata and cell inventory for one of the 22 worksheets."""

    sheet_index: int
    sheet_name: str
    visibility: str = "visible"  # visible | hidden | veryHidden
    populated_cell_count: int
    formula_cell_count: int
    shared_formula_count: int = 0


class ExtractedWorkbookGraph(BaseModel):
    """Complete parsed AST and DAG representation of a 22-sheet Google Sheet / .xlsm snapshot."""

    workbook_name: str
    spreadsheet_id: str
    sha256_hash: str
    sheets: list[ExtractedSheetRecord]
    cells: list[ExtractedCellRecord]
    dag_edges: list[DependencyEdgeRecord]
    named_ranges: list[NamedRangeRecord]
    macro_bindings: list[MacroBindingRecord]
    technical_debt_items: list[TechnicalDebtItemRecord]
    summary_metrics: dict[str, Any] = Field(default_factory=dict)
