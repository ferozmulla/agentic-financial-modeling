"""SQLAlchemy 2.0 ORM models for all 10 AlloyDB / PostgreSQL Governance, AST, DAG & Audit tables."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for all 10 AlloyDB governance tables."""


class WorkbookModel(Base):
    __tablename__ = "workbooks"

    workbook_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    spreadsheet_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    workbook_name: Mapped[str] = mapped_column(String(256), nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    latest_version_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    latest_version_seq_num: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class WorkbookVersionModel(Base):
    __tablename__ = "workbook_versions"

    version_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workbook_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("workbooks.workbook_id"), nullable=False
    )
    spreadsheet_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    parent_version_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    version_seq_num: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    gcs_snapshot_uri: Mapped[str] = mapped_column(Text, nullable=False)
    committed_by_google_user: Mapped[str] = mapped_column(String(256), nullable=False)
    committed_by_iam_principal: Mapped[str] = mapped_column(String(256), nullable=False)
    commit_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_sheets: Mapped[int] = mapped_column(Integer, nullable=False)
    total_populated_cells: Mapped[int] = mapped_column(Integer, nullable=False)
    total_formula_cells: Mapped[int] = mapped_column(Integer, nullable=False)
    total_dag_edges: Mapped[int] = mapped_column(Integer, nullable=False)
    structural_mutation_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    manual_override_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class WorksheetModel(Base):
    __tablename__ = "worksheets"

    worksheet_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    version_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("workbook_versions.version_id"), nullable=False, index=True
    )
    sheet_index: Mapped[int] = mapped_column(Integer, nullable=False)
    sheet_name: Mapped[str] = mapped_column(String(128), nullable=False)
    visibility: Mapped[str] = mapped_column(String(32), default="visible", nullable=False)
    populated_cell_count: Mapped[int] = mapped_column(Integer, nullable=False)
    formula_cell_count: Mapped[int] = mapped_column(Integer, nullable=False)
    shared_formula_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class CellModel(Base):
    __tablename__ = "cells"

    cell_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    version_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("workbook_versions.version_id"), nullable=False, index=True
    )
    sheet_name: Mapped[str] = mapped_column(String(128), nullable=False)
    cell_coord: Mapped[str] = mapped_column(String(24), nullable=False)
    row_num: Mapped[int] = mapped_column(Integer, nullable=False)
    col_num: Mapped[int] = mapped_column(Integer, nullable=False)
    col_letter: Mapped[str] = mapped_column(String(8), nullable=False)
    data_type: Mapped[str] = mapped_column(String(16), nullable=False)
    raw_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    numeric_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_formula: Mapped[str | None] = mapped_column(Text, nullable=True)
    canonical_formula: Mapped[str | None] = mapped_column(Text, nullable=True)
    r1c1_formula: Mapped[str | None] = mapped_column(Text, nullable=True)
    formula_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    shared_group_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_shared_master: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    semantic_role: Mapped[str] = mapped_column(String(32), nullable=False)


class CellDependencyEdgeModel(Base):
    __tablename__ = "cell_dependency_edges"

    edge_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    version_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("workbook_versions.version_id"), nullable=False, index=True
    )
    precedent_sheet: Mapped[str] = mapped_column(String(128), nullable=False)
    precedent_coord: Mapped[str] = mapped_column(String(24), nullable=False)
    dependent_sheet: Mapped[str] = mapped_column(String(128), nullable=False)
    dependent_coord: Mapped[str] = mapped_column(String(24), nullable=False)
    reference_type: Mapped[str] = mapped_column(String(32), default="DIRECT_CELL", nullable=False)


class NamedRangeModel(Base):
    __tablename__ = "named_ranges"

    named_range_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    version_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("workbook_versions.version_id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    local_sheet_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scope_sheet_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    refers_to: Mapped[str] = mapped_column(Text, nullable=False)
    is_broken_ref: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class MacroBindingModel(Base):
    __tablename__ = "macro_bindings"

    binding_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    version_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("workbook_versions.version_id"), nullable=False, index=True
    )
    sheet_name: Mapped[str] = mapped_column(String(128), nullable=False)
    anchor_cell: Mapped[str] = mapped_column(String(24), nullable=False)
    button_label: Mapped[str] = mapped_column(String(256), nullable=False)
    macro_target: Mapped[str] = mapped_column(String(128), nullable=False)
    raw_macro_ref: Mapped[str] = mapped_column(String(256), nullable=False)


class TechnicalDebtItemModel(Base):
    __tablename__ = "technical_debt_items"

    debt_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    version_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("workbook_versions.version_id"), nullable=False, index=True
    )
    debt_category: Mapped[str] = mapped_column(String(64), nullable=False)
    identifier: Mapped[str] = mapped_column(String(256), nullable=False)
    location: Mapped[str] = mapped_column(String(256), nullable=False)
    details: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(32), default="WARNING", nullable=False)


class AuditEventModel(Base):
    __tablename__ = "audit_events"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workbook_id: Mapped[str] = mapped_column(String(128), nullable=False)
    spreadsheet_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    version_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    parent_version_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    version_seq_num: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    sheet_name: Mapped[str] = mapped_column(String(128), nullable=False)
    cell_coord: Mapped[str] = mapped_column(String(32), nullable=False)
    what_element_coord: Mapped[str] = mapped_column(String(256), nullable=False)
    what_semantic_role: Mapped[str] = mapped_column(String(32), nullable=False)
    what_change_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    before_state: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    after_state: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    who_google_user: Mapped[str] = mapped_column(String(256), nullable=False)
    who_iam_principal: Mapped[str] = mapped_column(String(256), nullable=False)
    who_client_platform: Mapped[str] = mapped_column(String(128), nullable=False)
    who_spreadsheet_id: Mapped[str] = mapped_column(String(128), nullable=False)
    when_event_utc: Mapped[str] = mapped_column(String(64), nullable=False)
    gcs_snapshot_uri: Mapped[str] = mapped_column(Text, nullable=False)


class SolverRunTelemetryModel(Base):
    __tablename__ = "solver_run_telemetry"

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    spreadsheet_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    workbook_id: Mapped[str] = mapped_column(String(128), nullable=False)
    macro_name: Mapped[str] = mapped_column(String(64), nullable=False)
    caller_google_user: Mapped[str] = mapped_column(String(256), nullable=False)
    solve_count: Mapped[int] = mapped_column(Integer, nullable=False)
    execution_time_ms: Mapped[float] = mapped_column(Float, nullable=False)
    execution_engine: Mapped[str] = mapped_column(String(64), nullable=False)
    parity_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    executed_at_utc: Mapped[str] = mapped_column(String(64), nullable=False)
