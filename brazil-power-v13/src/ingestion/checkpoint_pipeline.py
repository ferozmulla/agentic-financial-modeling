"""Path 2 checkpoint ingestion pipeline (DEC-05 GCS-first archival + AST/DAG diffing)."""

from __future__ import annotations

import json
import time
from functools import lru_cache
from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.db.bigquery_sink import BigQueryAnalyticalSink
from src.db.repositories import GovernanceRepository
from src.db.session import acquire_spreadsheet_advisory_lock
from src.diff.structural_differ import StructuralDiffer
from src.parser.openxml_extractor import OpenXMLExtractor
from src.parser.sheets_grid_extractor import SheetsGridExtractor
from src.schemas.ast_dag import ExtractedWorkbookGraph
from src.schemas.audit import CheckpointIngestResponse
from src.storage.snapshot_store import SnapshotStore, get_snapshot_store


@lru_cache(maxsize=1)
def _get_seed_baseline_graph() -> ExtractedWorkbookGraph | None:
    """Cache the canonical seed workbook graph to diff newly copied sheets on first auto-checkpoint."""
    seed_path = get_settings().seed_workbook_path
    if not seed_path.exists():
        return None
    return OpenXMLExtractor.extract_from_bytes(
        raw_bytes=seed_path.read_bytes(),
        spreadsheet_id="seed-baseline",
        workbook_name="Regional Power Generation Techno-Economic Model",
    )


async def execute_checkpoint_pipeline(
    session: AsyncSession,
    spreadsheet_id: str,
    workbook_name: str = "Regional Power Generation Techno-Economic Model",
    raw_bytes: bytes | None = None,
    grid_payload: dict[str, Any] | None = None,
    preparsed_graph: ExtractedWorkbookGraph | None = None,
    who_google_user: str = "analyst@enterprise.com",
    who_iam_principal: str = "user:analyst@enterprise.com",
    who_client_platform: str = "Google Sheets Web UI / Apps Script V8",
    commit_comment: str = "Governed model checkpoint",
    snapshot_store: SnapshotStore | None = None,
    bq_sink: BigQueryAnalyticalSink | None = None,
) -> tuple[CheckpointIngestResponse, ExtractedWorkbookGraph]:
    """Execute the Path 2 Structural Checkpoint Pipeline (FR-B05, DEC-05).

    1. Archive raw snapshot to SnapshotStore BEFORE database parsing (DEC-05).
    2. Acquire per-spreadsheet transactional advisory lock (`pg_advisory_xact_lock`).
    3. Extract complete AST & DAG (`OpenXMLExtractor` or `SheetsGridExtractor`).
    4. Load prior version snapshot (if any) and run R1C1 shift-aware `StructuralDiffer`.
    5. Bulk-persist version metadata, cell AST nodes, DAG edges, named ranges, and
       append-only audit events in a single atomic transaction.
    6. Stream analytical copies to `BigQueryAnalyticalSink`.
    """
    t0 = time.perf_counter()
    store = snapshot_store or get_snapshot_store()
    repo = GovernanceRepository(session)

    if raw_bytes is not None:
        archive_bytes = raw_bytes
        ext = ".xlsm"
    elif grid_payload is not None:
        archive_bytes = json.dumps(grid_payload, sort_keys=True).encode("utf-8")
        ext = ".json"
    elif preparsed_graph is not None:
        archive_bytes = preparsed_graph.model_dump_json().encode("utf-8")
        ext = ".json"
    else:
        raise ValueError(
            "execute_checkpoint_pipeline requires raw_bytes, grid_payload, or preparsed_graph."
        )

    # Step 1 (DEC-05): Archive raw snapshot to GCS/local store BEFORE parsing
    gcs_uri = store.archive_snapshot(
        spreadsheet_id=spreadsheet_id,
        raw_bytes=archive_bytes,
        extension=ext,
    )

    # Step 2: Parse workbook into canonical AST/DAG graph
    if preparsed_graph is not None:
        child_graph = preparsed_graph
    elif grid_payload is not None:
        child_graph = SheetsGridExtractor.extract_from_grid_json(grid_payload)
        child_graph.spreadsheet_id = spreadsheet_id
        child_graph.workbook_name = workbook_name
    else:
        assert raw_bytes is not None
        child_graph = OpenXMLExtractor.extract_from_bytes(
            raw_bytes=raw_bytes,
            spreadsheet_id=spreadsheet_id,
            workbook_name=workbook_name,
        )

    version_id = str(uuid4())
    async with acquire_spreadsheet_advisory_lock(session, spreadsheet_id):
        latest_v = await repo.get_latest_version(spreadsheet_id)
        parent_version_id = latest_v.version_id if latest_v else None
        version_seq_num = (latest_v.version_seq_num + 1) if latest_v else 1

        parent_graph: ExtractedWorkbookGraph | None = None
        if parent_version_id is not None:
            parent_graph = await repo.load_workbook_graph(parent_version_id)
        elif commit_comment.startswith("Auto-checkpoint"):
            parent_graph = _get_seed_baseline_graph()

        # Step 3: Compute R1C1 shift-aware structural diff against parent version
        diff_res = StructuralDiffer.diff_workbooks(
            parent_graph=parent_graph,
            child_graph=child_graph,
            version_id=version_id,
            parent_version_id=parent_version_id,
            version_seq_num=version_seq_num,
            who_google_user=who_google_user,
            who_iam_principal=who_iam_principal,
            gcs_snapshot_uri=gcs_uri,
            who_client_platform=who_client_platform,
        )

        # Step 4: Bulk persist to transactional database
        await repo.bulk_persist_version_graph(
            graph=child_graph,
            version_id=version_id,
            parent_version_id=parent_version_id,
            version_seq_num=version_seq_num,
            gcs_snapshot_uri=gcs_uri,
            who_google_user=who_google_user,
            who_iam_principal=who_iam_principal,
            commit_comment=commit_comment,
            audit_events=diff_res.audit_events,
            structural_mutation_count=diff_res.structural_mutation_count,
            manual_override_count=diff_res.manual_override_count,
        )

    # Step 5: Stream to BigQuery analytical sink
    if bq_sink is not None:
        bq_sink.stream_audit_events(diff_res.audit_events)

    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    total_formulas = sum(s.formula_cell_count for s in child_graph.sheets)
    broken_nrs = sum(1 for nr in child_graph.named_ranges if nr.is_broken_ref)

    response = CheckpointIngestResponse(
        version_id=version_id,
        parent_version_id=parent_version_id,
        version_seq_num=version_seq_num,
        spreadsheet_id=spreadsheet_id,
        workbook_name=child_graph.workbook_name,
        gcs_snapshot_uri=gcs_uri,
        total_sheets=len(child_graph.sheets),
        total_populated_cells=len(child_graph.cells),
        total_formula_cells=total_formulas,
        total_dag_edges=len(child_graph.dag_edges),
        total_named_ranges=len(child_graph.named_ranges),
        broken_named_ranges=broken_nrs,
        structural_mutation_count=diff_res.structural_mutation_count,
        manual_override_count=diff_res.manual_override_count,
        suppressed_noise_count=diff_res.suppressed_noise_count,
        ingestion_time_ms=round(elapsed_ms, 3),
        audit_events=diff_res.audit_events,
    )
    return response, child_graph
