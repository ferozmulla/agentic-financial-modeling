"""Integration tests for Pillar B AST/DAG extraction, shift-aware diffing, and audit immutability (TEST-B01..B07)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.db.bigquery_sink import BigQueryAnalyticalSink
from src.db.repositories import GovernanceRepository
from src.diff.structural_differ import StructuralDiffer
from src.ingestion.checkpoint_pipeline import execute_checkpoint_pipeline
from src.ingestion.realtime_edit_handler import handle_realtime_edit_event
from src.parser.formula_normalizer import a1_to_r1c1, compute_formula_hash
from src.parser.openxml_extractor import OpenXMLExtractor
from src.schemas.ast_dag import CellSemanticRole, ExtractedWorkbookGraph
from src.schemas.audit import AuditSeverity, ChangeType, RealTimeEditEventRequest
from src.storage.snapshot_store import LocalFilesystemSnapshotStore


@pytest.fixture(scope="module")
def extracted_seed_graph(seed_xlsm_path: Path) -> ExtractedWorkbookGraph:
    """Extract the full AST/DAG graph from the read-only seed .xlsm once per test module."""
    return OpenXMLExtractor.extract_from_path(
        file_path=seed_xlsm_path,
        spreadsheet_id="brazil_tt_v13_test",
    )


def test_b01_full_workbook_ast_and_dag_extraction(
    extracted_seed_graph: ExtractedWorkbookGraph,
) -> None:
    """TEST-B01: Verify exact empirical counts on seed/2023-11-27-Brazil_TT_v13_RJEB.xlsm."""
    metrics = extracted_seed_graph.summary_metrics

    assert len(extracted_seed_graph.sheets) == 22
    visible_sheets = [s for s in extracted_seed_graph.sheets if s.visibility == "visible"]
    assert len(visible_sheets) == 22

    assert len(extracted_seed_graph.cells) == 35655
    assert metrics["total_raw_f_tags"] == 17354
    assert metrics["total_shared_formula_cells"] == 10654
    assert metrics["total_named_ranges"] == 3400
    assert metrics["broken_named_ranges"] == 1123
    assert len(extracted_seed_graph.macro_bindings) == 31
    assert len(extracted_seed_graph.dag_edges) > 10000


@pytest.mark.asyncio
async def test_b02_scenario_input_and_solver_output_noise_suppression(
    extracted_seed_graph: ExtractedWorkbookGraph,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """TEST-B02: Scalar edits to SCENARIO_INPUT_CELL and SOLVER_OUTPUT_CELL emit 0 alerts."""
    async with db_session_factory() as session:
        async with session.begin():
            repo = GovernanceRepository(session)
            await repo.bulk_persist_version_graph(
                graph=extracted_seed_graph,
                version_id="v1-b02",
                parent_version_id=None,
                version_seq_num=1,
                gcs_snapshot_uri="gs://test-bucket/v1.xlsm",
                who_google_user="analyst@enterprise.com",
                who_iam_principal="user:analyst@enterprise.com",
                commit_comment="Baseline v1",
                audit_events=[],
                structural_mutation_count=0,
                manual_override_count=0,
            )

        # Path 1: Real-time edit on _01_CF!B16 (SCENARIO_INPUT_CELL)
        async with session.begin():
            resp_input = await handle_realtime_edit_event(
                session=session,
                request=RealTimeEditEventRequest(
                    spreadsheet_id=extracted_seed_graph.spreadsheet_id,
                    sheet_name="_01_CF",
                    cell_coord="B16",
                    row_num=16,
                    col_num=2,
                    old_value="567.601",
                    new_value="580.125",
                    new_formula=None,
                ),
            )
            assert resp_input.status == "SUPPRESSED"
            assert resp_input.change_type is None

            # Path 1: Real-time edit on _01_CF!E6 (SOLVER_OUTPUT_CELL)
            resp_solver = await handle_realtime_edit_event(
                session=session,
                request=RealTimeEditEventRequest(
                    spreadsheet_id=extracted_seed_graph.spreadsheet_id,
                    sheet_name="_01_CF",
                    cell_coord="E6",
                    row_num=6,
                    col_num=5,
                    old_value="0.0684",
                    new_value="0.0712",
                    new_formula=None,
                ),
            )
            assert resp_solver.status == "SUPPRESSED"
            assert resp_solver.change_type is None

    # Path 2: Checkpoint diff with mutated _01_CF!B16 and _01_CF!E6 scalar values
    mutated = extracted_seed_graph.model_copy(deep=True)
    for cell in mutated.cells:
        if cell.sheet_name == "_01_CF" and cell.cell_coord == "B16":
            cell.raw_value = "580.125"
            cell.numeric_value = 580.125
        elif cell.sheet_name == "_01_CF" and cell.cell_coord == "E6":
            cell.raw_value = "0.0712"
            cell.numeric_value = 0.0712

    diff_res = StructuralDiffer.diff_workbooks(
        parent_graph=extracted_seed_graph,
        child_graph=mutated,
        version_id="v2-b02",
        parent_version_id="v1-b02",
        version_seq_num=2,
        who_google_user="analyst@enterprise.com",
        who_iam_principal="user:analyst@enterprise.com",
        gcs_snapshot_uri="gs://test-bucket/v2.xlsm",
    )
    assert len(diff_res.audit_events) == 0
    assert diff_res.suppressed_noise_count >= 2


@pytest.mark.asyncio
async def test_b03_manual_override_detection_realtime_and_checkpoint(
    extracted_seed_graph: ExtractedWorkbookGraph,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """TEST-B03: Overwriting formula cell _01_CF!G23 with hardcoded 520.0 emits CRITICAL MANUAL_OVERRIDE."""
    spreadsheet_id = "brazil_tt_v13_b03"
    snap_v1 = extracted_seed_graph.model_copy(deep=True)
    snap_v1.spreadsheet_id = spreadsheet_id

    async with db_session_factory() as session:
        async with session.begin():
            repo = GovernanceRepository(session)
            await repo.bulk_persist_version_graph(
                graph=snap_v1,
                version_id="v1-b03",
                parent_version_id=None,
                version_seq_num=1,
                gcs_snapshot_uri="gs://test-bucket/v1-b03.xlsm",
                who_google_user="analyst@enterprise.com",
                who_iam_principal="user:analyst@enterprise.com",
                commit_comment="Baseline B03",
                audit_events=[],
                structural_mutation_count=0,
                manual_override_count=0,
            )

        async with session.begin():
            rt_resp = await handle_realtime_edit_event(
                session=session,
                request=RealTimeEditEventRequest(
                    spreadsheet_id=spreadsheet_id,
                    sheet_name="_01_CF",
                    cell_coord="G23",
                    row_num=23,
                    col_num=7,
                    old_value="539.22",
                    new_value="520.0",
                    new_formula=None,
                    who_google_user="analyst@enterprise.com",
                ),
            )
            assert rt_resp.status == "LOGGED"
            assert rt_resp.change_type == ChangeType.MANUAL_OVERRIDE
            assert rt_resp.severity == AuditSeverity.CRITICAL

    # Verify Path 2 Checkpoint Diff also detects MANUAL_OVERRIDE on _01_CF!G23
    snap_v2 = snap_v1.model_copy(deep=True)
    prior_g23_formula = None
    for cell in snap_v2.cells:
        if cell.sheet_name == "_01_CF" and cell.cell_coord == "G23":
            prior_g23_formula = cell.canonical_formula
            cell.raw_formula = None
            cell.canonical_formula = None
            cell.r1c1_formula = None
            cell.formula_hash = None
            cell.raw_value = "520.0"
            cell.numeric_value = 520.0
            cell.semantic_role = CellSemanticRole.LABEL_OR_STATIC_CELL
            break

    assert prior_g23_formula is not None
    diff_res = StructuralDiffer.diff_workbooks(
        parent_graph=snap_v1,
        child_graph=snap_v2,
        version_id="v2-b03",
        parent_version_id="v1-b03",
        version_seq_num=2,
        who_google_user="analyst@enterprise.com",
        who_iam_principal="user:analyst@enterprise.com",
        gcs_snapshot_uri="gs://test-bucket/v2-b03.xlsm",
    )
    overrides = [
        e
        for e in diff_res.audit_events
        if e.what_change_type == ChangeType.MANUAL_OVERRIDE
    ]
    assert len(overrides) == 1
    assert overrides[0].severity == AuditSeverity.CRITICAL
    assert overrides[0].sheet_name == "_01_CF"
    assert overrides[0].cell_coord == "G23"
    assert overrides[0].before_state["formula"] == prior_g23_formula
    assert overrides[0].after_state["value"] == "520.0"


def test_b04_formula_modified_detection(
    extracted_seed_graph: ExtractedWorkbookGraph,
) -> None:
    """TEST-B04: Truncating _01_CF!I60 NPV range emits WARNING FORMULA_MODIFIED."""
    snap_v2 = extracted_seed_graph.model_copy(deep=True)

    modified_formula = "=IFERROR(NPV(I58,I21:I45),0)"
    r1c1_new = a1_to_r1c1(modified_formula, cell_row=60, cell_col=9)

    found = False
    for cell in snap_v2.cells:
        if cell.sheet_name == "_01_CF" and cell.cell_coord == "I60":
            cell.raw_formula = modified_formula
            cell.canonical_formula = modified_formula
            cell.r1c1_formula = r1c1_new
            cell.formula_hash = compute_formula_hash(r1c1_new)
            found = True
            break
    assert found is True

    diff_res = StructuralDiffer.diff_workbooks(
        parent_graph=extracted_seed_graph,
        child_graph=snap_v2,
        version_id="v2-b04",
        parent_version_id="v1-b04",
        version_seq_num=2,
        who_google_user="analyst@enterprise.com",
        who_iam_principal="user:analyst@enterprise.com",
        gcs_snapshot_uri="gs://test-bucket/v2-b04.xlsm",
    )
    mod_events = [
        e
        for e in diff_res.audit_events
        if e.what_change_type == ChangeType.FORMULA_MODIFIED
    ]
    assert len(mod_events) == 1
    assert mod_events[0].severity == AuditSeverity.WARNING
    assert mod_events[0].sheet_name == "_01_CF"
    assert mod_events[0].cell_coord == "I60"
    assert mod_events[0].after_state["formula"] == modified_formula


def test_b05_row_insertion_r1c1_shift_normalization(
    extracted_seed_graph: ExtractedWorkbookGraph,
) -> None:
    """TEST-B05: Inserting 1 row at Row 30 in _01_CF emits 1 ROW_INSERTED and 0 false-positive FORMULA_MODIFIED."""
    snap_v2 = extracted_seed_graph.model_copy(deep=True)

    new_cells = []
    for cell in snap_v2.cells:
        if cell.sheet_name != "_01_CF" or cell.row_num < 30:
            new_cells.append(cell)
        else:
            shifted_row = cell.row_num + 1
            new_coord = f"{cell.col_letter}{shifted_row}"
            shifted_cell = cell.model_copy(
                update={
                    "row_num": shifted_row,
                    "cell_coord": new_coord,
                }
            )
            new_cells.append(shifted_cell)

    snap_v2.cells = new_cells

    diff_res = StructuralDiffer.diff_workbooks(
        parent_graph=extracted_seed_graph,
        child_graph=snap_v2,
        version_id="v2-b05",
        parent_version_id="v1-b05",
        version_seq_num=2,
        who_google_user="analyst@enterprise.com",
        who_iam_principal="user:analyst@enterprise.com",
        gcs_snapshot_uri="gs://test-bucket/v2-b05.xlsm",
    )

    row_inserted_events = [
        e
        for e in diff_res.audit_events
        if e.what_change_type == ChangeType.ROW_INSERTED
    ]
    formula_modified_events = [
        e
        for e in diff_res.audit_events
        if e.what_change_type == ChangeType.FORMULA_MODIFIED
        and e.sheet_name == "_01_CF"
    ]

    assert len(row_inserted_events) == 1
    assert row_inserted_events[0].sheet_name == "_01_CF"
    assert row_inserted_events[0].after_state["inserted_row"] == 30
    assert len(formula_modified_events) == 0


def test_b06_sheet_visibility_and_named_range_diffing(
    extracted_seed_graph: ExtractedWorkbookGraph,
) -> None:
    """TEST-B06: Hiding CVU_GF and repairing a named range emits SHEET_VISIBILITY_CHANGED and NAMED_RANGE_MODIFIED."""
    snap_v2 = extracted_seed_graph.model_copy(deep=True)

    for s in snap_v2.sheets:
        if s.sheet_name == "CVU_GF":
            s.visibility = "hidden"

    for nr in snap_v2.named_ranges:
        if nr.is_broken_ref:
            nr.refers_to = "General!$C$10"
            nr.is_broken_ref = False
            break

    diff_res = StructuralDiffer.diff_workbooks(
        parent_graph=extracted_seed_graph,
        child_graph=snap_v2,
        version_id="v2-b06",
        parent_version_id="v1-b06",
        version_seq_num=2,
        who_google_user="analyst@enterprise.com",
        who_iam_principal="user:analyst@enterprise.com",
        gcs_snapshot_uri="gs://test-bucket/v2-b06.xlsm",
    )

    event_types = {e.what_change_type for e in diff_res.audit_events}
    assert ChangeType.SHEET_VISIBILITY_CHANGED in event_types
    assert ChangeType.NAMED_RANGE_MODIFIED in event_types


@pytest.mark.asyncio
async def test_b07_append_only_audit_immutability_trigger(
    extracted_seed_graph: ExtractedWorkbookGraph,
    tmp_path: Path,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """TEST-B07: Database trigger blocks UPDATE and DELETE on audit_events (NFR-05)."""
    store = LocalFilesystemSnapshotStore(
        base_dir=tmp_path / "snapshots",
        bucket_name="comm-model-mod-sheets-mod-snapshots",
    )
    bq_sink = BigQueryAnalyticalSink()

    snap_b07 = extracted_seed_graph.model_copy(deep=True)
    snap_b07.spreadsheet_id = "brazil_tt_v13_b07"

    async with db_session_factory() as session:
        async with session.begin():
            resp, _graph = await execute_checkpoint_pipeline(
                session=session,
                spreadsheet_id="brazil_tt_v13_b07",
                preparsed_graph=snap_b07,
                commit_comment="Initial B07 commit",
                snapshot_store=store,
                bq_sink=bq_sink,
            )
            assert resp.total_sheets == 22
            assert resp.total_populated_cells == 35655

        # Emit a CRITICAL MANUAL_OVERRIDE event
        async with session.begin():
            rt = await handle_realtime_edit_event(
                session=session,
                request=RealTimeEditEventRequest(
                    spreadsheet_id="brazil_tt_v13_b07",
                    sheet_name="_01_CF",
                    cell_coord="G23",
                    row_num=23,
                    col_num=7,
                    old_value="539.22",
                    new_value="520.0",
                    new_formula=None,
                ),
                bq_sink=bq_sink,
            )
            assert rt.event_id is not None

        # Attempt UPDATE on audit_events -> MUST fail with NFR-05 trigger exception
        with pytest.raises(Exception) as exc_update:
            async with session.begin():
                await session.execute(
                    text("UPDATE audit_events SET severity = 'INFO' WHERE event_id = :eid"),
                    {"eid": rt.event_id},
                )
        assert "prevent_audit_events_mutation" in str(exc_update.value)

        # Attempt DELETE on audit_events -> MUST fail with NFR-05 trigger exception
        with pytest.raises(Exception) as exc_delete:
            async with session.begin():
                await session.execute(
                    text("DELETE FROM audit_events WHERE event_id = :eid"),
                    {"eid": rt.event_id},
                )
        assert "prevent_audit_events_mutation" in str(exc_delete.value)


@pytest.mark.asyncio
async def test_b08_copied_sheet_header_and_metadata_tracking(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """TEST-B08: Personal copy tracks Formula, Header/Label (LABEL_OR_STATIC_CELL), and Metadata (onChange) silently while suppressing routine inputs."""
    bq_sink = BigQueryAnalyticalSink()
    copy_id = "fhm_personal_copy_001"
    copy_name = "FHM Copy of Regional Power Generation Techno-Economic Model"
    copy_url = f"https://docs.google.com/spreadsheets/d/{copy_id}/edit"

    async with db_session_factory() as session:
        # 1. Routine scenario input tweak (General!C16 capacity factor) -> SUPPRESSED
        async with session.begin():
            res_input = await handle_realtime_edit_event(
                session=session,
                request=RealTimeEditEventRequest(
                    spreadsheet_id=copy_id,
                    workbook_name=copy_name,
                    spreadsheet_url=copy_url,
                    sheet_name="General",
                    cell_coord="C16",
                    row_num=16,
                    col_num=3,
                    old_value="0.50",
                    new_value="0.65",
                    new_formula=None,
                ),
                bq_sink=bq_sink,
            )
            assert res_input.status == "SUPPRESSED"

        # 2. Table header edit on _01_CF!B2 ("Gas" -> "Gasoline") -> HEADER_OR_LABEL_MODIFIED
        async with session.begin():
            res_header = await handle_realtime_edit_event(
                session=session,
                request=RealTimeEditEventRequest(
                    spreadsheet_id=copy_id,
                    workbook_name=copy_name,
                    spreadsheet_url=copy_url,
                    sheet_name="_01_CF",
                    cell_coord="B2",
                    row_num=2,
                    col_num=2,
                    old_value=None,  # Falls back to seed baseline "Gas"
                    new_value="Gasoline",
                    new_formula=None,
                ),
                bq_sink=bq_sink,
            )
            assert res_header.status == "LOGGED"
            assert res_header.change_type == ChangeType.HEADER_OR_LABEL_MODIFIED

        # 3. Structural metadata event (INSERT_ROW & INSERT_GRID) -> ROW_INSERTED & SHEET_ADDED
        async with session.begin():
            res_row = await handle_realtime_edit_event(
                session=session,
                request=RealTimeEditEventRequest(
                    spreadsheet_id=copy_id,
                    workbook_name=copy_name,
                    spreadsheet_url=copy_url,
                    sheet_name="_01_CF",
                    cell_coord="A15",
                    structural_change_type="INSERT_ROW",
                ),
                bq_sink=bq_sink,
            )
            assert res_row.status == "LOGGED"
            assert res_row.change_type == ChangeType.ROW_INSERTED

        async with session.begin():
            res_sheet = await handle_realtime_edit_event(
                session=session,
                request=RealTimeEditEventRequest(
                    spreadsheet_id=copy_id,
                    workbook_name=copy_name,
                    spreadsheet_url=copy_url,
                    sheet_name="New_Scenario_Tab",
                    cell_coord="A1",
                    structural_change_type="INSERT_GRID",
                ),
                bq_sink=bq_sink,
            )
            assert res_sheet.status == "LOGGED"
            assert res_sheet.change_type == ChangeType.SHEET_ADDED

