"""Integration tests for the Brazil Power (v13) Cloud Execution Telemetry Web App and Tracker."""

from __future__ import annotations

import copy

from fastapi.testclient import TestClient

from src.api.main import create_app
from src.solver.workbook_context import get_baseline_solver_context
from src.telemetry.tracker import telemetry_tracker


def test_manager_demo_script_grouped_execution_units() -> None:
    """
    Verify the exact Manager Demo Script and per-unit local copy snapshot progression:
    1. Unit #1 (Tornado 5 / calcule_tir5): Compares against Golden Copy baseline -> captures G11 & G20 edits.
    2. Unit #2 (Forecast LCOE / lcoe_exec): Compares against snapshot at end of Unit #1 -> 0 repeated input edits.
    3. Unit #3 (Tornado 4 / calcule_tir4 after editing F11): Compares against snapshot at end of Unit #2 -> captures only F11.
    4. Clear Trail (/v1/telemetry/clear): Clears displayed units while preserving local copy snapshot.
    """
    app = create_app()
    telemetry_tracker.clear(preserve_sheet_snapshots=False)

    base_ctx = get_baseline_solver_context()
    modified_general = copy.deepcopy(base_ctx.general_c5_n40)
    # Row 11 -> index 6 (11 - 5), Col G -> index 4 (Utility Solar PV)
    modified_general[6][4] = 3850.0
    # Row 20 -> index 15 (20 - 5), Col G -> index 4 (Fuel Cost)
    modified_general[15][4] = 12.5

    headers = {"Authorization": "Bearer manager-demo@enterprise.com"}

    with TestClient(app) as client:
        # 1. Trigger Unit #1: Tornado 5 (calcule_tir5) with edited General!C5:N40
        r1 = client.post(
            "/v1/solve/calcule_tir5",
            headers=headers,
            json={
                "workbook_id": "Copy of Brazil_TT_v13_RJEB_Gcloud",
                "spreadsheet_id": "local-copy-sheet-v13",
                "caller_google_user": "ferozmulla@google.com",
                "general_overrides": {
                    "general_c5_n40": modified_general,
                },
            },
        )
        assert r1.status_code == 200

        # 2. Trigger Unit #2: Forecast LCOE (lcoe_exec) immediately after (no new edits since end of Unit #1)
        r2 = client.post(
            "/v1/solve/lcoe_exec",
            headers=headers,
            json={
                "workbook_id": "Copy of Brazil_TT_v13_RJEB_Gcloud",
                "spreadsheet_id": "local-copy-sheet-v13",
                "caller_google_user": "ferozmulla@google.com",
                "general_overrides": {
                    "general_c5_n40": modified_general,
                },
            },
        )
        assert r2.status_code == 200

        # 3. Edit F11 (Onshore Wind Capex) and trigger Unit #3: Tornado 4 (calcule_tir4)
        modified_general_u3 = copy.deepcopy(modified_general)
        modified_general_u3[6][3] = 8000.0  # Row 11, Col F (index 3)
        r3 = client.post(
            "/v1/solve/calcule_tir4",
            headers=headers,
            json={
                "workbook_id": "Copy of Brazil_TT_v13_RJEB_Gcloud",
                "spreadsheet_id": "local-copy-sheet-v13",
                "caller_google_user": "ferozmulla@google.com",
                "general_overrides": {
                    "general_c5_n40": modified_general_u3,
                },
            },
        )
        assert r3.status_code == 200

        feed_resp = client.get("/v1/telemetry/units")
        assert feed_resp.status_code == 200
        feed = feed_resp.json()
        assert feed["total_units"] == 3

        unit_tornado4 = feed["units"][0]
        unit_lcoe = feed["units"][1]
        unit_tornado5 = feed["units"][2]

        # Unit #1 (Tornado 5) diffed against Golden Copy baseline -> 2 input changes (G11 & G20)
        assert unit_tornado5["unit_seq"] == 1
        assert unit_tornado5["macro_name"] == "calcule_tir5"
        assert unit_tornado5["input_change_count"] == 2
        tornado5_steps = unit_tornado5["steps"]
        assert len(tornado5_steps) == 6
        assert "G11" in tornado5_steps[0]["action"]
        assert "G20" in tornado5_steps[1]["action"]

        # Unit #2 (Forecast LCOE) diffed against snapshot at end of Unit #1 -> 0 new input changes
        assert unit_lcoe["unit_seq"] == 2
        assert unit_lcoe["macro_name"] == "lcoe_exec"
        assert unit_lcoe["input_change_count"] == 0
        assert unit_lcoe["solve_count"] == 184
        lcoe_steps = unit_lcoe["steps"]
        assert lcoe_steps[0]["system"] == "Apps Script"
        assert any(s["system"] == "Solver Engine" and "184" in s["action"] for s in lcoe_steps)

        # Unit #3 (Tornado 4) diffed against snapshot at end of Unit #2 -> ONLY F11 (not G11 or G20!)
        assert unit_tornado4["unit_seq"] == 3
        assert unit_tornado4["macro_name"] == "calcule_tir4"
        assert unit_tornado4["input_change_count"] == 1
        tornado4_steps = unit_tornado4["steps"]
        assert tornado4_steps[0]["system"] == "Google Sheets"
        assert "F11" in tornado4_steps[0]["action"]
        assert not any("G11" in s["action"] or "G20" in s["action"] for s in tornado4_steps)

        # 4. Click Clear Trail -> preserves local copy snapshot so a subsequent run doesn't re-report F11/G11/G20
        client.post("/v1/telemetry/clear")
        r4 = client.post(
            "/v1/solve/calcule_tir4",
            headers=headers,
            json={
                "workbook_id": "Copy of Brazil_TT_v13_RJEB_Gcloud",
                "spreadsheet_id": "local-copy-sheet-v13",
                "caller_google_user": "ferozmulla@google.com",
                "general_overrides": {
                    "general_c5_n40": modified_general_u3,
                },
            },
        )
        assert r4.status_code == 200
        after_clear_unit = client.get("/v1/telemetry/units").json()["units"][0]
        assert after_clear_unit["unit_seq"] == 1
        assert after_clear_unit["input_change_count"] == 0


def test_bqml_refresh_and_metadata_exclusion() -> None:
    """Verify BQML remote solves are tracked while metadata/audit ingest events are excluded."""
    app = create_app()
    telemetry_tracker.clear(preserve_sheet_snapshots=False)
    headers = {"Authorization": "Bearer analyst@enterprise.com"}

    with TestClient(app) as client:
        # 1. Send a structural audit/metadata event -> MUST NOT appear in execution telemetry
        client.post(
            "/v1/ingest/edit-event",
            headers=headers,
            json={
                "spreadsheet_id": "demo-sheet-v13",
                "workbook_name": "Brazil_TT_v13_RJEB_Gcloud",
                "sheet_name": "_01_CF",
                "cell_coord": "B16",
                "row_num": 16,
                "col_num": 2,
                "old_value": "100.0",
                "new_value": "125.0",
                "new_formula": None,
                "who_google_user": "analyst@enterprise.com",
            },
        )
        assert client.get("/v1/telemetry/units").json()["total_units"] == 0

        # 2. Send a BQML Remote Function request -> MUST appear as a bqml_refresh ExecutionUnit
        r_bq = client.post(
            "/v1/bqml/solve",
            headers=headers,
            json={
                "calls": [
                    ["lcoe_forecast", "{}"],
                ]
            },
        )
        assert r_bq.status_code == 200
        feed = client.get("/v1/telemetry/units").json()
        assert feed["total_units"] == 1
        assert feed["units"][0]["unit_type"] == "bqml_refresh"
        assert len(feed["units"][0]["steps"]) == 3

        # 3. Trigger a Connected Sheets BQML refresh (without any preceding sheet edits) -> MUST appear as Unit #2
        r_cs_bqml = client.post(
            "/v1/telemetry/bqml-refresh",
            headers=headers,
            json={
                "workbook_id": "FM Copy of Brazil_TT_v13_RJEB_Gcloud",
                "spreadsheet_id": "10o2DB74gNLS6z49IOAJU34t1zT6XhYfLxSo-8_aLlgM",
                "caller_google_user": "admin@ferozmulla.altostrat.com",
                "active_tab": "LT_Capex_BQML",
                "view_type": "lt_forecasts",
                "duration_ms": 413.0,
                "job_id": "sheets_dataconnector_test_job_01",
            },
        )
        assert r_cs_bqml.status_code == 200
        feed2 = r_cs_bqml.json()
        assert feed2["total_units"] == 2
        latest_bqml = feed2["units"][0]
        assert latest_bqml["unit_type"] == "bqml_refresh"
        assert latest_bqml["macro_name"] == "refreshBqmlForecasts"
        assert latest_bqml["input_change_count"] == 0
        assert latest_bqml["solve_count"] == 33
        assert len(latest_bqml["steps"]) == 4
        assert any("ARIMA_PLUS" in s["action"] for s in latest_bqml["steps"])


def test_telemetry_web_ui_and_demo_seed_endpoints() -> None:
    """Verify /telemetry HTML, CSS, JS, and /v1/telemetry/demo-seed routes."""
    app = create_app()
    telemetry_tracker.clear(preserve_sheet_snapshots=False)

    with TestClient(app) as client:
        html_resp = client.get("/telemetry")
        assert html_resp.status_code == 200
        assert "Brazil Power Model (v13)" in html_resp.text
        assert "/telemetry/styles.css" in html_resp.text
        assert "/telemetry/app.js" in html_resp.text

        css_resp = client.get("/telemetry/styles.css")
        assert css_resp.status_code == 200
        assert "--accent-blue" in css_resp.text

        js_resp = client.get("/telemetry/app.js")
        assert js_resp.status_code == 200
        assert "/v1/telemetry/units" in js_resp.text

        seed_resp = client.post("/v1/telemetry/demo-seed")
        assert seed_resp.status_code == 200
        seeded = seed_resp.json()
        assert seeded["total_units"] == 2
        assert seeded["units"][0]["macro_name"] == "lcoe_exec"
        assert seeded["units"][1]["macro_name"] == "calcule_tir5"

        gov_html = client.get("/governance")
        assert gov_html.status_code == 200
        assert "Brazil_TT_v13_RJEB" in gov_html.text
        assert "vw_audit_dashboard_lean" in gov_html.text
        assert "4-Ws Metadata Audit Trail</h2>" in gov_html.text
        assert "BRAZIL_TT_V13_RJEB GOVERNANCE AI ASSISTANT" in gov_html.text

        gov_css = client.get("/governance/styles.css")
        assert gov_css.status_code == 200
        assert "#CADCFA" in gov_css.text

        gov_api = client.get("/v1/governance/dashboard?timeframe=30d")
        assert gov_api.status_code == 200
        gov_payload = gov_api.json()
        assert gov_payload["kpis"]["total_modifications"] >= 1
        assert "by_tab" in gov_payload["charts"]
        assert "by_change_type" in gov_payload["charts"]
        assert "by_workbook_drift" in gov_payload["charts"]
        assert "lookerstudio.google.com" in gov_payload["looker_studio_url"]
        assert all(ev["change_type_code"] != "INITIAL_BASELINE_INGESTED" for ev in gov_payload["events"])

        chat_resp = client.post(
            "/v1/governance/chat",
            json={"question": "Which formulas were overwritten with hardcoded values?", "timeframe": "30d"},
        )
        assert chat_resp.status_code == 200
        chat_data = chat_resp.json()
        assert "Manual Formula Override" in chat_data["answer"]


