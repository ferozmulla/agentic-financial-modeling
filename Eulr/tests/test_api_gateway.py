"""Phase 4 Verification Tests: TEST-E2E-01 (FastAPI Gateway Endpoints & Apps Script Contract)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.api.main import app

client = TestClient(app)


def test_e2e_01_fastapi_gateway_full_lifecycle() -> None:
    """TEST-E2E-01: Verify /healthz, /v1/eulr/solve, /scenario-matrix, /sync-upstream, /ingest/edit-event, /override/revert, /publish, and /bqml/refresh."""
    # 1. Healthz check
    r_health = client.get("/healthz")
    assert r_health.status_code == 200
    h_data = r_health.json()
    assert h_data["status"] == "ok"
    assert h_data["total_formula_cells"] == 357708
    assert h_data["unique_r1c1_row_equations"] == 8028
    assert h_data["upstream_external_link_cells"] == 14162

    # 2. Baseline 10-pass equilibrium solve
    r_solve = client.post(
        "/v1/eulr/solve",
        json={
            "spreadsheet_id": "e2e-sheet-001",
            "scenario_mode": "base",
            "carbon_mode": "Sensitivity with EU ETS cost and pass-through",
            "upstream_source_mode": "eulr_baseline_cached",
        },
    )
    assert r_solve.status_code == 200
    s_data = r_solve.json()
    assert s_data["converged"] is True
    assert s_data["iterations_run"] == 10
    assert s_data["key_prices_2025_usd_mt"]["NWE_Diesel_EN590_CIF_ARA"] == 716.40

    # 3. Silent #FEF3C7 Pinned Trader Price Override via /v1/ingest/edit-event
    r_edit = client.post(
        "/v1/ingest/edit-event",
        json={
            "spreadsheet_id": "e2e-sheet-001",
            "copy_location_url": "https://docs.google.com/spreadsheets/d/e2e-sheet-001/edit",
            "actor_email": "trader@spglobal.com",
            "sheet_name": "NWE Cif",
            "cell_a1": "AU122",
            "before_value": 716.40,
            "new_value": 750.00,
        },
    )
    assert r_edit.status_code == 200
    e_data = r_edit.json()
    assert e_data["classification"] == "PINNED_PRICE_OVERRIDE"
    assert e_data["highlight_hex"] == "#FEF3C7"
    assert e_data["pinned_override_registered"] is True

    # 4. Solve again for e2e-sheet-001 -> persisted #FEF3C7 override holds AU122 at $750.00/mt
    r_solve_pinned = client.post(
        "/v1/eulr/solve",
        json={"spreadsheet_id": "e2e-sheet-001"},
    )
    assert r_solve_pinned.status_code == 200
    sp_data = r_solve_pinned.json()
    assert sp_data["pinned_override_count"] == 1
    assert sp_data["key_prices_2025_usd_mt"]["NWE_Diesel_EN590_CIF_ARA"] == 750.00

    # 5. Revert pinned override via /v1/eulr/override/revert -> restores $716.40/mt
    r_rev = client.post(
        "/v1/eulr/override/revert",
        json={"spreadsheet_id": "e2e-sheet-001"},
    )
    assert r_rev.status_code == 200
    rev_data = r_rev.json()
    assert rev_data["reverted_cells"] == ["NWE Cif!AU122"]
    assert rev_data["remaining_override_count"] == 0
    assert rev_data["solve_result"]["key_prices_2025_usd_mt"]["NWE_Diesel_EN590_CIF_ARA"] == 716.40

    # 6. Parallel 4-Way Scenario & Carbon Matrix
    r_mat = client.post(
        "/v1/eulr/scenario-matrix",
        json={"spreadsheet_id": "e2e-sheet-001"},
    )
    assert r_mat.status_code == 200
    m_data = r_mat.json()
    assert len(m_data["cases"]) == 4
    assert "gemini-3.8-flash" in m_data["ai_attribution_summary"]

    # 7. Sync Upstream Peer Workbooks (Uslr, Felr, Tankerlr)
    r_sync = client.post(
        "/v1/eulr/sync-upstream",
        json={"spreadsheet_id": "e2e-sheet-001", "target_mode": "peer_xlsx"},
    )
    assert r_sync.status_code == 200
    sync_data = r_sync.json()
    assert sync_data["total_external_cells"] == 14162
    assert sync_data["updated_peer_cells"] == 1104

    # 8. Publish UPLOAD (1,273 series) & Links out (234 series)
    r_pub = client.post(
        "/v1/eulr/publish",
        json={"spreadsheet_id": "e2e-sheet-001", "vintage_tag": "202409"},
    )
    assert r_pub.status_code == 200
    pub_data = r_pub.json()
    assert pub_data["upload_series_count"] == 1273
    assert pub_data["links_out_series_count"] == 234
    assert pub_data["retired_shooju_addin"] is True

    # 9. Refresh Breakout BQML Tab
    r_bqml = client.post(
        "/v1/eulr/bqml/refresh",
        json={"tab_name": "Crudes_BQML", "horizon_end_year": 2050},
    )
    assert r_bqml.status_code == 200
    assert r_bqml.json()["tab_name"] == "Crudes_BQML"
