"""Path 1 real-time edit event handler implementing FR-B04 & FR-B06."""

from __future__ import annotations

import time
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncSession

from src.cli.extract_baseline_fixtures import col_letter_to_index, split_coord
from src.core.config import get_settings
from src.db.bigquery_sink import BigQueryAnalyticalSink
from src.db.repositories import GovernanceRepository
from src.parser.formula_normalizer import a1_to_r1c1, canonicalize_a1_formula
from src.parser.openxml_extractor import OpenXMLExtractor
from src.parser.semantic_classifier import CellSemanticClassifier
from src.schemas.ast_dag import CellSemanticRole, ExtractedCellRecord
from src.schemas.audit import (
    AuditEventRecord,
    AuditSeverity,
    ChangeType,
    RealTimeEditEventRequest,
    RealTimeEditEventResponse,
)


@lru_cache(maxsize=1)
def _get_seed_baseline_cell_map() -> dict[tuple[str, str], ExtractedCellRecord]:
    """Cache the 35,655 baseline cells from the seed workbook for newly copied sheets."""
    seed_path = get_settings().seed_workbook_path
    if not seed_path.exists():
        return {}
    graph = OpenXMLExtractor.extract_from_bytes(
        raw_bytes=seed_path.read_bytes(),
        spreadsheet_id="seed-baseline",
        workbook_name="Regional Power Generation Techno-Economic Model",
    )
    return {(c.sheet_name, c.cell_coord): c for c in graph.cells}


STRUCTURAL_CHANGE_MAP: dict[str, tuple[ChangeType, AuditSeverity]] = {
    "INSERT_ROW": (ChangeType.ROW_INSERTED, AuditSeverity.WARNING),
    "REMOVE_ROW": (ChangeType.ROW_DELETED, AuditSeverity.CRITICAL),
    "INSERT_COLUMN": (ChangeType.COL_INSERTED, AuditSeverity.WARNING),
    "REMOVE_COLUMN": (ChangeType.COL_DELETED, AuditSeverity.CRITICAL),
    "INSERT_GRID": (ChangeType.SHEET_ADDED, AuditSeverity.WARNING),
    "REMOVE_GRID": (ChangeType.SHEET_DELETED, AuditSeverity.CRITICAL),
    "OTHER": (ChangeType.METADATA_CHANGED, AuditSeverity.INFO),
}


async def handle_realtime_edit_event(
    session: AsyncSession,
    request: RealTimeEditEventRequest,
    who_iam_principal: str = "user:analyst@enterprise.com",
    who_client_platform: str = "Google Sheets Web UI / Apps Script V8",
    bq_sink: BigQueryAnalyticalSink | None = None,
) -> RealTimeEditEventResponse:
    """Evaluate a real-time Google Sheets onEdit / onChange event against the baseline AST.

    Rules (FR-B06):
    - Scalar value edits to SCENARIO_INPUT_CELL or SOLVER_OUTPUT_CELL are routine
      analyst modeling operations and MUST be suppressed (zero alert noise).
    - Replacing a FORMULA_CELL (from the prior baseline) with a hardcoded literal
      (new_formula is None) emits a CRITICAL MANUAL_OVERRIDE event.
    - Changing a formula's canonical R1C1 structure emits a WARNING FORMULA_MODIFIED event.
    - Editing a LABEL_OR_STATIC_CELL text cell (e.g., table header or row label) emits a
      WARNING HEADER_OR_LABEL_MODIFIED event.
    - Structural metadata mutations (row/column/sheet insertions or deletions via onChange)
      emit ROW_INSERTED, ROW_DELETED, COL_INSERTED, COL_DELETED, SHEET_ADDED, or SHEET_DELETED.
    """
    t0 = time.perf_counter()
    repo = GovernanceRepository(session)
    latest_v, baseline_cell = await repo.get_cell_in_latest_version(
        spreadsheet_id=request.spreadsheet_id,
        sheet_name=request.sheet_name,
        cell_coord=request.cell_coord,
    )

    resolved_location_uri = (
        request.spreadsheet_url
        or (latest_v.gcs_snapshot_uri if latest_v else "gs://realtime-on-edit/unsnapshotted")
    )

    # Category 3: Structural / Metadata change from Apps Script onChange(e) trigger
    if request.structural_change_type:
        mapped = STRUCTURAL_CHANGE_MAP.get(request.structural_change_type.upper())
        if mapped is None:
            elapsed = (time.perf_counter() - t0) * 1000.0
            return RealTimeEditEventResponse(
                status="SUPPRESSED",
                change_type=None,
                severity=None,
                event_id=None,
                processing_time_ms=round(elapsed, 3),
            )
        change_type, severity = mapped
        event = AuditEventRecord(
            workbook_id=request.workbook_name,
            spreadsheet_id=request.spreadsheet_id,
            version_id=latest_v.version_id if latest_v else None,
            parent_version_id=latest_v.parent_version_id if latest_v else None,
            version_seq_num=latest_v.version_seq_num if latest_v else 1,
            sheet_name=request.sheet_name,
            cell_coord=request.cell_coord,
            what_element_coord=f"{request.workbook_name} -> {request.sheet_name}!{request.cell_coord}",
            what_semantic_role=CellSemanticRole.LABEL_OR_STATIC_CELL,
            what_change_type=change_type,
            severity=severity,
            before_state={
                "formula": None,
                "value": request.old_value,
                "structural_change_type": request.structural_change_type,
            },
            after_state={
                "formula": None,
                "value": request.new_value or request.structural_change_type,
                "sheet_name": request.sheet_name,
                "active_coord": request.cell_coord,
            },
            who_google_user=request.who_google_user,
            who_iam_principal=who_iam_principal,
            who_client_platform=who_client_platform,
            who_spreadsheet_id=request.spreadsheet_id,
            when_event_utc=request.when_event_utc,
            gcs_snapshot_uri=resolved_location_uri,
        )
        await repo.append_audit_events([event])
        if bq_sink is not None:
            bq_sink.stream_audit_events([event])
        elapsed = (time.perf_counter() - t0) * 1000.0
        return RealTimeEditEventResponse(
            status="LOGGED",
            change_type=change_type,
            severity=severity,
            event_id=event.event_id,
            processing_time_ms=round(elapsed, 3),
        )

    col_str, r_num = split_coord(request.cell_coord)
    c_num = col_letter_to_index(col_str) if col_str else request.col_num
    r_num = r_num or request.row_num

    new_canonical = canonicalize_a1_formula(request.new_formula)
    new_r1c1 = a1_to_r1c1(new_canonical, r_num, c_num)

    prior_canonical: str | None = None
    prior_r1c1: str | None = None
    prior_role: CellSemanticRole | None = None
    prior_raw_value: str | None = None
    if baseline_cell is not None:
        prior_canonical = baseline_cell.canonical_formula
        prior_r1c1 = baseline_cell.r1c1_formula
        prior_role = CellSemanticRole(baseline_cell.semantic_role)
        prior_raw_value = baseline_cell.raw_value
    else:
        seed_cell = _get_seed_baseline_cell_map().get((request.sheet_name, request.cell_coord))
        if seed_cell is not None:
            prior_canonical = seed_cell.canonical_formula
            prior_r1c1 = seed_cell.r1c1_formula
            prior_role = seed_cell.semantic_role
            prior_raw_value = seed_cell.raw_value

    try:
        num_val = float(request.new_value) if request.new_value is not None else None
    except ValueError:
        num_val = None

    effective_role = prior_role or CellSemanticClassifier.classify(
        sheet_name=request.sheet_name,
        cell_coord=request.cell_coord,
        row_num=r_num,
        col_num=c_num,
        canonical_formula=prior_canonical,
        numeric_value=num_val,
    )

    # Suppress routine scalar edits on SCENARIO_INPUT_CELL and SOLVER_OUTPUT_CELL
    if (
        effective_role
        in (CellSemanticRole.SCENARIO_INPUT_CELL, CellSemanticRole.SOLVER_OUTPUT_CELL)
        and not prior_canonical
        and not new_canonical
    ):
        elapsed = (time.perf_counter() - t0) * 1000.0
        return RealTimeEditEventResponse(
            status="SUPPRESSED",
            change_type=None,
            severity=None,
            event_id=None,
            processing_time_ms=round(elapsed, 3),
        )

    # Category 1a: Detect CRITICAL MANUAL_OVERRIDE: prior cell had a formula, new cell has no formula
    if prior_canonical and not new_canonical:
        event = AuditEventRecord(
            workbook_id=request.workbook_name,
            spreadsheet_id=request.spreadsheet_id,
            version_id=latest_v.version_id if latest_v else None,
            parent_version_id=latest_v.parent_version_id if latest_v else None,
            version_seq_num=latest_v.version_seq_num if latest_v else 1,
            sheet_name=request.sheet_name,
            cell_coord=request.cell_coord,
            what_element_coord=f"{request.workbook_name} -> {request.sheet_name}!{request.cell_coord}",
            what_semantic_role=CellSemanticRole.FORMULA_CELL,
            what_change_type=ChangeType.MANUAL_OVERRIDE,
            severity=AuditSeverity.CRITICAL,
            before_state={
                "formula": prior_canonical,
                "r1c1_formula": prior_r1c1,
                "value": request.old_value if request.old_value is not None else prior_raw_value,
            },
            after_state={
                "formula": None,
                "value": request.new_value,
            },
            who_google_user=request.who_google_user,
            who_iam_principal=who_iam_principal,
            who_client_platform=who_client_platform,
            who_spreadsheet_id=request.spreadsheet_id,
            when_event_utc=request.when_event_utc,
            gcs_snapshot_uri=resolved_location_uri,
        )
        await repo.append_audit_events([event])
        if bq_sink is not None:
            bq_sink.stream_audit_events([event])
        elapsed = (time.perf_counter() - t0) * 1000.0
        return RealTimeEditEventResponse(
            status="LOGGED",
            change_type=ChangeType.MANUAL_OVERRIDE,
            severity=AuditSeverity.CRITICAL,
            event_id=event.event_id,
            processing_time_ms=round(elapsed, 3),
        )

    # Category 1b: Detect WARNING FORMULA_MODIFIED / INFO FORMULA_ADDED: formula logic changed
    if new_canonical and prior_r1c1 != new_r1c1:
        change_type = ChangeType.FORMULA_MODIFIED if prior_canonical else ChangeType.FORMULA_ADDED
        severity = AuditSeverity.WARNING if prior_canonical else AuditSeverity.INFO
        event = AuditEventRecord(
            workbook_id=request.workbook_name,
            spreadsheet_id=request.spreadsheet_id,
            version_id=latest_v.version_id if latest_v else None,
            parent_version_id=latest_v.parent_version_id if latest_v else None,
            version_seq_num=latest_v.version_seq_num if latest_v else 1,
            sheet_name=request.sheet_name,
            cell_coord=request.cell_coord,
            what_element_coord=f"{request.workbook_name} -> {request.sheet_name}!{request.cell_coord}",
            what_semantic_role=CellSemanticRole.FORMULA_CELL,
            what_change_type=change_type,
            severity=severity,
            before_state={
                "formula": prior_canonical,
                "r1c1_formula": prior_r1c1,
                "value": request.old_value if request.old_value is not None else prior_raw_value,
            },
            after_state={
                "formula": new_canonical,
                "r1c1_formula": new_r1c1,
                "value": request.new_value,
            },
            who_google_user=request.who_google_user,
            who_iam_principal=who_iam_principal,
            who_client_platform=who_client_platform,
            who_spreadsheet_id=request.spreadsheet_id,
            when_event_utc=request.when_event_utc,
            gcs_snapshot_uri=resolved_location_uri,
        )
        await repo.append_audit_events([event])
        if bq_sink is not None:
            bq_sink.stream_audit_events([event])
        elapsed = (time.perf_counter() - t0) * 1000.0
        return RealTimeEditEventResponse(
            status="LOGGED",
            change_type=change_type,
            severity=severity,
            event_id=event.event_id,
            processing_time_ms=round(elapsed, 3),
        )

    # Category 2: Detect WARNING HEADER_OR_LABEL_MODIFIED on LABEL_OR_STATIC_CELL
    if (
        effective_role == CellSemanticRole.LABEL_OR_STATIC_CELL
        and not prior_canonical
        and not new_canonical
    ):
        before_val = request.old_value if request.old_value is not None else prior_raw_value
        if str(before_val or "") != str(request.new_value or ""):
            event = AuditEventRecord(
                workbook_id=request.workbook_name,
                spreadsheet_id=request.spreadsheet_id,
                version_id=latest_v.version_id if latest_v else None,
                parent_version_id=latest_v.parent_version_id if latest_v else None,
                version_seq_num=latest_v.version_seq_num if latest_v else 1,
                sheet_name=request.sheet_name,
                cell_coord=request.cell_coord,
                what_element_coord=f"{request.workbook_name} -> {request.sheet_name}!{request.cell_coord}",
                what_semantic_role=CellSemanticRole.LABEL_OR_STATIC_CELL,
                what_change_type=ChangeType.HEADER_OR_LABEL_MODIFIED,
                severity=AuditSeverity.WARNING,
                before_state={
                    "formula": None,
                    "value": before_val,
                },
                after_state={
                    "formula": None,
                    "value": request.new_value,
                },
                who_google_user=request.who_google_user,
                who_iam_principal=who_iam_principal,
                who_client_platform=who_client_platform,
                who_spreadsheet_id=request.spreadsheet_id,
                when_event_utc=request.when_event_utc,
                gcs_snapshot_uri=resolved_location_uri,
            )
            await repo.append_audit_events([event])
            if bq_sink is not None:
                bq_sink.stream_audit_events([event])
            elapsed = (time.perf_counter() - t0) * 1000.0
            return RealTimeEditEventResponse(
                status="LOGGED",
                change_type=ChangeType.HEADER_OR_LABEL_MODIFIED,
                severity=AuditSeverity.WARNING,
                event_id=event.event_id,
                processing_time_ms=round(elapsed, 3),
            )

    elapsed = (time.perf_counter() - t0) * 1000.0
    return RealTimeEditEventResponse(
        status="SUPPRESSED",
        change_type=None,
        severity=None,
        event_id=None,
        processing_time_ms=round(elapsed, 3),
    )
