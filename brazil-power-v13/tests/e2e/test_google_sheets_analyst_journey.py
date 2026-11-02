"""End-to-End verification of the Google Sheets Analyst & Governance Lead Journey (TEST-E2E-01)."""

from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.api.main import create_app
from src.api.routes.health import get_db_session
from src.db.bigquery_sink import BigQueryAnalyticalSink
from src.storage.snapshot_store import LocalFilesystemSnapshotStore


@pytest.mark.asyncio
async def test_e2e_01_full_google_sheets_analyst_and_governance_journey(
    seed_xlsm_path: Path,
    tmp_path: Path,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """TEST-E2E-01: Full analyst and governance lifecycle across Pillar A and Pillar B."""
    store = LocalFilesystemSnapshotStore(
        base_dir=tmp_path / "e2e_snapshots",
        bucket_name="comm-model-mod-sheets-mod-snapshots",
    )
    bq_sink = BigQueryAnalyticalSink()
    app = create_app(snapshot_store=store, bq_sink=bq_sink)

    async def _override_db():
        async with db_session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = _override_db
    spreadsheet_id = "google-sheets-e2e-brazil-v13"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://127.0.0.1:8000") as client:
        # 1. Verify liveness, deep readiness, regional config (us-central1 + us Gemini), and security headers
        h_resp = await client.get("/health")
        assert h_resp.status_code == 200
        h_data = h_resp.json()
        assert h_data["gcp_project_id"] == "comm-model-mod"
        assert h_data["gcp_region"] == "us-central1"
        assert h_data["gemini_location"] == "us"
        assert h_data["registered_macros"] == 38
        assert h_resp.headers["X-Content-Type-Options"] == "nosniff"
        assert h_resp.headers["X-Frame-Options"] == "DENY"

        deep_resp = await client.get("/v1/health/deep")
        assert deep_resp.status_code == 200
        assert deep_resp.json()["status"] == "healthy"

        # 2. Commit Baseline Checkpoint (Path 2)
        cp_resp = await client.post(
            "/v1/ingest/checkpoint",
            json={
                "spreadsheet_id": spreadsheet_id,
                "workbook_name": "Regional Power Generation Techno-Economic Model",
                "xlsm_file_path": str(seed_xlsm_path),
                "commit_comment": "Initial v13 baseline import into Google Sheets",
                "who_google_user": "lead.analyst@enterprise.com",
            },
        )
        assert cp_resp.status_code == 200
        cp_data = cp_resp.json()
        assert cp_data["version_seq_num"] == 1
        assert cp_data["total_sheets"] == 22
        assert cp_data["total_populated_cells"] == 35655
        assert cp_data["total_named_ranges"] == 3400
        assert cp_data["broken_named_ranges"] == 1123
        assert cp_data["gcs_snapshot_uri"].startswith(
            "gs://comm-model-mod-sheets-mod-snapshots/"
        )

        # 3. Routine Scenario Input Edit (Path 1) -> Suppressed
        rt_suppressed = await client.post(
            "/v1/ingest/edit-event",
            json={
                "spreadsheet_id": spreadsheet_id,
                "sheet_name": "_01_CF",
                "cell_coord": "B16",
                "row_num": 16,
                "col_num": 2,
                "old_value": "567.601",
                "new_value": "575.000",
                "new_formula": None,
                "who_google_user": "lead.analyst@enterprise.com",
            },
        )
        assert rt_suppressed.status_code == 200
        assert rt_suppressed.json()["status"] == "SUPPRESSED"

        # 4. Execute Pillar A Solver: Single-Sheet Tornado (calcule_tir1) & Master LCOE (lcoe_exec)
        solve_tir1 = await client.post(
            "/v1/solve/calcule_tir1",
            json={
                "spreadsheet_id": spreadsheet_id,
                "caller_google_user": "lead.analyst@enterprise.com",
                "parity_mode": "strict_legacy_vba",
            },
        )
        assert solve_tir1.status_code == 200
        tir1_data = solve_tir1.json()
        assert tir1_data["solve_count"] == 21
        assert tir1_data["execution_time_ms"] < 800.0
        assert len(tir1_data["cell_updates"]) >= 1

        solve_lcoe = await client.post(
            "/v1/solve/lcoe_exec",
            json={
                "spreadsheet_id": spreadsheet_id,
                "caller_google_user": "lead.analyst@enterprise.com",
                "parity_mode": "strict_legacy_vba",
            },
        )
        assert solve_lcoe.status_code == 200
        lcoe_data = solve_lcoe.json()
        assert lcoe_data["solve_count"] == 184
        assert lcoe_data["execution_time_ms"] < 2000.0

        # Also verify BigQuery Remote Function endpoint (/v1/bqml/solve)
        bqml_resp = await client.post(
            "/v1/bqml/solve",
            json={
                "calls": [
                    ["fator_i", {"spreadsheet_id": spreadsheet_id}],
                ]
            },
        )
        assert bqml_resp.status_code == 200
        assert len(bqml_resp.json()["replies"]) == 1
        assert bqml_resp.json()["replies"][0]["macro_name"] == "fator_i"

        # 5. Undocumented Manual Formula Override on _01_CF!G23 -> CRITICAL MANUAL_OVERRIDE
        rt_override = await client.post(
            "/v1/ingest/edit-event",
            json={
                "spreadsheet_id": spreadsheet_id,
                "sheet_name": "_01_CF",
                "cell_coord": "G23",
                "row_num": 23,
                "col_num": 7,
                "old_value": "-1125000000",
                "new_value": "-1250000000",
                "new_formula": None,
                "who_google_user": "rogue.editor@enterprise.com",
            },
        )
        assert rt_override.status_code == 200
        ov_data = rt_override.json()
        assert ov_data["status"] == "LOGGED"
        assert ov_data["change_type"] == "MANUAL_OVERRIDE"
        assert ov_data["severity"] == "CRITICAL"

        # 6. Governance Lead queries Version History, Audit Log, Cell Lineage, and Technical Debt
        ver_resp = await client.get(f"/v1/workbooks/{spreadsheet_id}/versions")
        assert ver_resp.status_code == 200
        assert ver_resp.json()["version_count"] == 1

        audit_resp = await client.get(
            f"/v1/workbooks/{spreadsheet_id}/audit-log",
            params={"change_type": "MANUAL_OVERRIDE"},
        )
        assert audit_resp.status_code == 200
        audit_data = audit_resp.json()
        assert audit_data["total_events"] == 1
        assert audit_data["events"][0]["who_google_user"] == "rogue.editor@enterprise.com"
        assert audit_data["events"][0]["cell_coord"] == "G23"

        lineage_resp = await client.get(
            f"/v1/workbooks/{spreadsheet_id}/lineage",
            params={"sheet_name": "_01_CF", "cell_coord": "G23", "max_depth": 3},
        )
        assert lineage_resp.status_code == 200
        lineage_data = lineage_resp.json()
        assert len(lineage_data["upstream_precedents"]) >= 1
        assert len(lineage_data["downstream_dependents"]) >= 1

        debt_resp = await client.get(f"/v1/workbooks/{spreadsheet_id}/technical-debt")
        assert debt_resp.status_code == 200
        debt_data = debt_resp.json()
        assert debt_data["broken_named_ranges_count"] == 1123
        assert debt_data["total_technical_debt_items"] == 1130
