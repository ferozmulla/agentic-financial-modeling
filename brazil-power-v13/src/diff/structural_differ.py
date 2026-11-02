"""Noise-Free Structural Diff State Machine emitting Immutable '4 Ws' AuditEventRecords (FR-B06 / FR-B08)."""

from __future__ import annotations

from dataclasses import dataclass, field

from src.diff.shift_normalizer import CoordinateShiftNormalizer
from src.schemas.ast_dag import CellSemanticRole, ExtractedCellRecord, ExtractedWorkbookGraph
from src.schemas.audit import AuditEventRecord, AuditSeverity, ChangeType


@dataclass
class StructuralDiffResult:
    """Result of diffing a child ExtractedWorkbookGraph against its parent version."""

    audit_events: list[AuditEventRecord] = field(default_factory=list)
    structural_mutation_count: int = 0
    manual_override_count: int = 0
    suppressed_noise_count: int = 0


class StructuralDiffer:
    """Computes structural mutations between two ExtractedWorkbookGraph snapshots while suppressing noise."""

    @classmethod
    def diff_workbooks(
        cls,
        parent_graph: ExtractedWorkbookGraph | None,
        child_graph: ExtractedWorkbookGraph,
        version_id: str,
        parent_version_id: str | None,
        version_seq_num: int,
        who_google_user: str,
        who_iam_principal: str,
        gcs_snapshot_uri: str,
        who_client_platform: str = "Google Sheets Web UI / Apps Script V8",
    ) -> StructuralDiffResult:
        """Compare child_graph against parent_graph and emit 4-Ws AuditEventRecords."""
        result = StructuralDiffResult()

        # Initial baseline ingestion (v1): log a single INFO baseline event
        if parent_graph is None:
            evt = AuditEventRecord(
                workbook_id=child_graph.workbook_name,
                spreadsheet_id=child_graph.spreadsheet_id,
                version_id=version_id,
                parent_version_id=None,
                version_seq_num=version_seq_num,
                sheet_name="General",
                cell_coord="A1",
                what_element_coord=f"{child_graph.workbook_name} -> General!A1",
                what_semantic_role=CellSemanticRole.LABEL_OR_STATIC_CELL,
                what_change_type=ChangeType.INITIAL_BASELINE_INGESTED,
                severity=AuditSeverity.INFO,
                before_state={},
                after_state={
                    "total_sheets": len(child_graph.sheets),
                    "total_populated_cells": len(child_graph.cells),
                    "sha256_hash": child_graph.sha256_hash,
                },
                who_google_user=who_google_user,
                who_iam_principal=who_iam_principal,
                who_client_platform=who_client_platform,
                who_spreadsheet_id=child_graph.spreadsheet_id,
                gcs_snapshot_uri=gcs_snapshot_uri,
            )
            result.audit_events.append(evt)
            return result

        # 1. Diff worksheet existence and visibility (TEST-B06)
        p_sheets = {s.sheet_name: s for s in parent_graph.sheets}
        c_sheets = {s.sheet_name: s for s in child_graph.sheets}

        for sname, c_sheet in c_sheets.items():
            if sname not in p_sheets:
                result.audit_events.append(
                    AuditEventRecord(
                        workbook_id=child_graph.workbook_name,
                        spreadsheet_id=child_graph.spreadsheet_id,
                        version_id=version_id,
                        parent_version_id=parent_version_id,
                        version_seq_num=version_seq_num,
                        sheet_name=sname,
                        cell_coord="SHEET",
                        what_element_coord=f"{child_graph.workbook_name} -> {sname}",
                        what_semantic_role=CellSemanticRole.LABEL_OR_STATIC_CELL,
                        what_change_type=ChangeType.SHEET_ADDED,
                        severity=AuditSeverity.WARNING,
                        before_state={},
                        after_state={"visibility": c_sheet.visibility},
                        who_google_user=who_google_user,
                        who_iam_principal=who_iam_principal,
                        who_client_platform=who_client_platform,
                        who_spreadsheet_id=child_graph.spreadsheet_id,
                        gcs_snapshot_uri=gcs_snapshot_uri,
                    )
                )
            elif p_sheets[sname].visibility != c_sheet.visibility:
                result.audit_events.append(
                    AuditEventRecord(
                        workbook_id=child_graph.workbook_name,
                        spreadsheet_id=child_graph.spreadsheet_id,
                        version_id=version_id,
                        parent_version_id=parent_version_id,
                        version_seq_num=version_seq_num,
                        sheet_name=sname,
                        cell_coord="SHEET_VISIBILITY",
                        what_element_coord=f"{child_graph.workbook_name} -> {sname}",
                        what_semantic_role=CellSemanticRole.LABEL_OR_STATIC_CELL,
                        what_change_type=ChangeType.SHEET_VISIBILITY_CHANGED,
                        severity=AuditSeverity.WARNING,
                        before_state={"visibility": p_sheets[sname].visibility},
                        after_state={"visibility": c_sheet.visibility},
                        who_google_user=who_google_user,
                        who_iam_principal=who_iam_principal,
                        who_client_platform=who_client_platform,
                        who_spreadsheet_id=child_graph.spreadsheet_id,
                        gcs_snapshot_uri=gcs_snapshot_uri,
                    )
                )

        for sname, p_sheet in p_sheets.items():
            if sname not in c_sheets:
                result.audit_events.append(
                    AuditEventRecord(
                        workbook_id=child_graph.workbook_name,
                        spreadsheet_id=child_graph.spreadsheet_id,
                        version_id=version_id,
                        parent_version_id=parent_version_id,
                        version_seq_num=version_seq_num,
                        sheet_name=sname,
                        cell_coord="SHEET",
                        what_element_coord=f"{child_graph.workbook_name} -> {sname}",
                        what_semantic_role=CellSemanticRole.LABEL_OR_STATIC_CELL,
                        what_change_type=ChangeType.SHEET_DELETED,
                        severity=AuditSeverity.CRITICAL,
                        before_state={"visibility": p_sheet.visibility},
                        after_state={},
                        who_google_user=who_google_user,
                        who_iam_principal=who_iam_principal,
                        who_client_platform=who_client_platform,
                        who_spreadsheet_id=child_graph.spreadsheet_id,
                        gcs_snapshot_uri=gcs_snapshot_uri,
                    )
                )

        # 2. Diff Defined Names / Named Ranges (TEST-B06)
        p_nrs = {(nr.scope_sheet_name or "GLOBAL", nr.name): nr for nr in parent_graph.named_ranges}
        c_nrs = {(nr.scope_sheet_name or "GLOBAL", nr.name): nr for nr in child_graph.named_ranges}
        for key, c_nr in c_nrs.items():
            p_nr = p_nrs.get(key)
            if p_nr is not None and p_nr.refers_to != c_nr.refers_to:
                scope_label = c_nr.scope_sheet_name or "Workbook"
                result.audit_events.append(
                    AuditEventRecord(
                        workbook_id=child_graph.workbook_name,
                        spreadsheet_id=child_graph.spreadsheet_id,
                        version_id=version_id,
                        parent_version_id=parent_version_id,
                        version_seq_num=version_seq_num,
                        sheet_name=scope_label,
                        cell_coord=f"NAME:{c_nr.name}",
                        what_element_coord=f"{child_graph.workbook_name} -> {scope_label}!{c_nr.name}",
                        what_semantic_role=CellSemanticRole.LABEL_OR_STATIC_CELL,
                        what_change_type=ChangeType.NAMED_RANGE_MODIFIED,
                        severity=AuditSeverity.INFO if p_nr.is_broken_ref and not c_nr.is_broken_ref else AuditSeverity.WARNING,
                        before_state={"refers_to": p_nr.refers_to, "is_broken_ref": p_nr.is_broken_ref},
                        after_state={"refers_to": c_nr.refers_to, "is_broken_ref": c_nr.is_broken_ref},
                        who_google_user=who_google_user,
                        who_iam_principal=who_iam_principal,
                        who_client_platform=who_client_platform,
                        who_spreadsheet_id=child_graph.spreadsheet_id,
                        gcs_snapshot_uri=gcs_snapshot_uri,
                    )
                )

        # 3. Group cells by sheet and run R1C1 Coordinate Shift Normalizer + Cell State Machine
        p_cells_by_sheet: dict[str, list[ExtractedCellRecord]] = {}
        for c in parent_graph.cells:
            p_cells_by_sheet.setdefault(c.sheet_name, []).append(c)

        c_cells_by_sheet: dict[str, list[ExtractedCellRecord]] = {}
        for c in child_graph.cells:
            c_cells_by_sheet.setdefault(c.sheet_name, []).append(c)

        for sname in c_sheets:
            if sname not in p_sheets:
                continue
            p_list = p_cells_by_sheet.get(sname, [])
            c_list = c_cells_by_sheet.get(sname, [])

            alignment = CoordinateShiftNormalizer.align_sheet(sname, p_list, c_list)

            for ins_r in alignment.inserted_rows:
                result.audit_events.append(
                    AuditEventRecord(
                        workbook_id=child_graph.workbook_name,
                        spreadsheet_id=child_graph.spreadsheet_id,
                        version_id=version_id,
                        parent_version_id=parent_version_id,
                        version_seq_num=version_seq_num,
                        sheet_name=sname,
                        cell_coord=f"ROW:{ins_r}",
                        what_element_coord=f"{child_graph.workbook_name} -> {sname}!ROW:{ins_r}",
                        what_semantic_role=CellSemanticRole.LABEL_OR_STATIC_CELL,
                        what_change_type=ChangeType.ROW_INSERTED,
                        severity=AuditSeverity.WARNING,
                        before_state={},
                        after_state={"inserted_row": ins_r},
                        who_google_user=who_google_user,
                        who_iam_principal=who_iam_principal,
                        who_client_platform=who_client_platform,
                        who_spreadsheet_id=child_graph.spreadsheet_id,
                        gcs_snapshot_uri=gcs_snapshot_uri,
                    )
                )

            for del_r in alignment.deleted_rows:
                result.audit_events.append(
                    AuditEventRecord(
                        workbook_id=child_graph.workbook_name,
                        spreadsheet_id=child_graph.spreadsheet_id,
                        version_id=version_id,
                        parent_version_id=parent_version_id,
                        version_seq_num=version_seq_num,
                        sheet_name=sname,
                        cell_coord=f"ROW:{del_r}",
                        what_element_coord=f"{child_graph.workbook_name} -> {sname}!ROW:{del_r}",
                        what_semantic_role=CellSemanticRole.LABEL_OR_STATIC_CELL,
                        what_change_type=ChangeType.ROW_DELETED,
                        severity=AuditSeverity.WARNING,
                        before_state={"deleted_row": del_r},
                        after_state={},
                        who_google_user=who_google_user,
                        who_iam_principal=who_iam_principal,
                        who_client_platform=who_client_platform,
                        who_spreadsheet_id=child_graph.spreadsheet_id,
                        gcs_snapshot_uri=gcs_snapshot_uri,
                    )
                )

            c_by_rc = {(c.row_num, c.col_num): c for c in c_list}
            matched_child_rcs: set[tuple[int, int]] = set()

            for p_cell in p_list:
                if p_cell.row_num in alignment.deleted_rows:
                    continue
                mapped_r = alignment.parent_to_child_row.get(p_cell.row_num, p_cell.row_num)
                mapped_c = alignment.parent_to_child_col.get(p_cell.col_num, p_cell.col_num)
                matched_child_rcs.add((mapped_r, mapped_c))
                c_cell = c_by_rc.get((mapped_r, mapped_c))

                if c_cell is None:
                    if p_cell.semantic_role == CellSemanticRole.FORMULA_CELL:
                        result.audit_events.append(
                            AuditEventRecord(
                                workbook_id=child_graph.workbook_name,
                                spreadsheet_id=child_graph.spreadsheet_id,
                                version_id=version_id,
                                parent_version_id=parent_version_id,
                                version_seq_num=version_seq_num,
                                sheet_name=sname,
                                cell_coord=p_cell.cell_coord,
                                what_element_coord=f"{child_graph.workbook_name} -> {sname}!{p_cell.cell_coord}",
                                what_semantic_role=CellSemanticRole.FORMULA_CELL,
                                what_change_type=ChangeType.FORMULA_DELETED,
                                severity=AuditSeverity.CRITICAL,
                                before_state={
                                    "formula": p_cell.canonical_formula,
                                    "value": p_cell.raw_value,
                                },
                                after_state={},
                                who_google_user=who_google_user,
                                who_iam_principal=who_iam_principal,
                                who_client_platform=who_client_platform,
                                who_spreadsheet_id=child_graph.spreadsheet_id,
                                gcs_snapshot_uri=gcs_snapshot_uri,
                            )
                        )
                    continue

                # Case A: Parent cell was a FORMULA_CELL
                if p_cell.semantic_role == CellSemanticRole.FORMULA_CELL:
                    if not c_cell.canonical_formula:
                        # CRITICAL MANUAL_OVERRIDE: Live formula overwritten by a hardcoded literal!
                        result.manual_override_count += 1
                        result.audit_events.append(
                            AuditEventRecord(
                                workbook_id=child_graph.workbook_name,
                                spreadsheet_id=child_graph.spreadsheet_id,
                                version_id=version_id,
                                parent_version_id=parent_version_id,
                                version_seq_num=version_seq_num,
                                sheet_name=sname,
                                cell_coord=c_cell.cell_coord,
                                what_element_coord=f"{child_graph.workbook_name} -> {sname}!{c_cell.cell_coord}",
                                what_semantic_role=CellSemanticRole.FORMULA_CELL,
                                what_change_type=ChangeType.MANUAL_OVERRIDE,
                                severity=AuditSeverity.CRITICAL,
                                before_state={
                                    "formula": p_cell.canonical_formula,
                                    "r1c1_formula": p_cell.r1c1_formula,
                                    "value": p_cell.raw_value,
                                },
                                after_state={
                                    "formula": None,
                                    "value": c_cell.raw_value,
                                },
                                who_google_user=who_google_user,
                                who_iam_principal=who_iam_principal,
                                who_client_platform=who_client_platform,
                                who_spreadsheet_id=child_graph.spreadsheet_id,
                                gcs_snapshot_uri=gcs_snapshot_uri,
                            )
                        )
                    elif not CoordinateShiftNormalizer.is_r1c1_equivalent_under_row_shift(
                        p_cell.r1c1_formula,
                        c_cell.r1c1_formula,
                        alignment.inserted_rows,
                        alignment.deleted_rows,
                    ):
                        # WARNING FORMULA_MODIFIED: Formula logic changed!
                        result.audit_events.append(
                            AuditEventRecord(
                                workbook_id=child_graph.workbook_name,
                                spreadsheet_id=child_graph.spreadsheet_id,
                                version_id=version_id,
                                parent_version_id=parent_version_id,
                                version_seq_num=version_seq_num,
                                sheet_name=sname,
                                cell_coord=c_cell.cell_coord,
                                what_element_coord=f"{child_graph.workbook_name} -> {sname}!{c_cell.cell_coord}",
                                what_semantic_role=CellSemanticRole.FORMULA_CELL,
                                what_change_type=ChangeType.FORMULA_MODIFIED,
                                severity=AuditSeverity.WARNING,
                                before_state={
                                    "formula": p_cell.canonical_formula,
                                    "r1c1_formula": p_cell.r1c1_formula,
                                    "value": p_cell.raw_value,
                                },
                                after_state={
                                    "formula": c_cell.canonical_formula,
                                    "r1c1_formula": c_cell.r1c1_formula,
                                    "value": c_cell.raw_value,
                                },
                                who_google_user=who_google_user,
                                who_iam_principal=who_iam_principal,
                                who_client_platform=who_client_platform,
                                who_spreadsheet_id=child_graph.spreadsheet_id,
                                gcs_snapshot_uri=gcs_snapshot_uri,
                            )
                        )
                    elif p_cell.raw_value != c_cell.raw_value:
                        # Formula logic unchanged; recalculated value change is suppressed noise
                        result.suppressed_noise_count += 1

                # Case B: Parent cell was non-formula (SCENARIO_INPUT_CELL, SOLVER_OUTPUT_CELL, LABEL)
                else:
                    if c_cell.canonical_formula:
                        result.audit_events.append(
                            AuditEventRecord(
                                workbook_id=child_graph.workbook_name,
                                spreadsheet_id=child_graph.spreadsheet_id,
                                version_id=version_id,
                                parent_version_id=parent_version_id,
                                version_seq_num=version_seq_num,
                                sheet_name=sname,
                                cell_coord=c_cell.cell_coord,
                                what_element_coord=f"{child_graph.workbook_name} -> {sname}!{c_cell.cell_coord}",
                                what_semantic_role=c_cell.semantic_role,
                                what_change_type=ChangeType.FORMULA_ADDED,
                                severity=AuditSeverity.INFO,
                                before_state={"formula": None, "value": p_cell.raw_value},
                                after_state={
                                    "formula": c_cell.canonical_formula,
                                    "value": c_cell.raw_value,
                                },
                                who_google_user=who_google_user,
                                who_iam_principal=who_iam_principal,
                                who_client_platform=who_client_platform,
                                who_spreadsheet_id=child_graph.spreadsheet_id,
                                gcs_snapshot_uri=gcs_snapshot_uri,
                            )
                        )
                    elif p_cell.raw_value != c_cell.raw_value:
                        # FR-B06 Noise Suppression: value edits on SCENARIO_INPUT_CELL or SOLVER_OUTPUT_CELL emit 0 audit events!
                        result.suppressed_noise_count += 1

        result.structural_mutation_count = len(result.audit_events)
        return result
