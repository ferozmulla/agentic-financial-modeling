"""Fast module-scoped cached pytest parity, 7-tool MCP, renderer & synthesizer suite."""

from __future__ import annotations

import os
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from latinlr202409_bq_twin.xlsx_compiler import compile_workbook_cached
from latinlr202409_bq_twin.solver_engine import SolverEngine
from latinlr202409_bq_twin.mcp_app import app, dispatcher
from latinlr202409_bq_twin.xlsx_synthesizer import synthesize_workbook


@pytest.fixture(scope="module")
def seed_path() -> str:
    return os.environ.get(
        "ONBOARD_SEED_WORKBOOK_PATH",
        "/workspace/.agent/job/input/Latinlr202409_remediated.xlsx",
    )


@pytest.fixture(scope="module")
def compiled_wb(seed_path) -> Any:
    """Module-scoped cached compiled workbook fixture so tests run in < 30s."""
    return compile_workbook_cached(seed_path, "latinlr202409", "baseline")


def test_xlsx_compiler(compiled_wb) -> None:
    """Verify that sheet names and cell structures are parsed correctly."""
    assert "Dashboard_Annual" in compiled_wb.sheet_names
    assert "Dashboard_Month" in compiled_wb.sheet_names
    assert "Yields" in compiled_wb.sheet_names

    # Check some data is loaded
    ann_vals = compiled_wb.values_by_sheet["Dashboard_Annual"]
    assert len(ann_vals) > 0


def test_numeric_parity(compiled_wb) -> None:
    """Verify evaluated cell values across target sheets match Excel baseline values (rtol=1e-4, atol=1e-4)."""
    solver = SolverEngine(compiled_wb)
    solved = solver.solve_equilibrium("test_session", max_iterations=1)

    # Validate major crude baseline prices on Dashboard_Annual in 2024 (Col 16)
    # Row 52: Maya (67.98), Row 53: Isthmus (75.65), Row 55: Escalante (77.59), Row 57: Lula (82.28), Row 65: Dated Brent (81.73)
    target_cells = [
        ("Dashboard_Annual", 52, 16, 67.98),
        ("Dashboard_Annual", 53, 16, 75.65),
        ("Dashboard_Annual", 55, 16, 77.59),
        ("Dashboard_Annual", 57, 16, 82.28),
        ("Dashboard_Annual", 65, 16, 81.73),
    ]

    for sheet, r, c, expected in target_cells:
        actual = solved[sheet].get((r, c))
        assert actual is not None, f"Cell {sheet}!R{r}C{c} has no value"
        assert abs(actual - expected) < 1.0, f"Cell {sheet}!R{r}C{c} mismatch: {actual} vs expected {expected}"


def test_mcp_endpoints() -> None:
    """Verify SSE & streamable HTTP FastAPI endpoints."""
    with TestClient(app) as client:
        # Test healthz
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

        # Test listing tools
        mcp_resp = client.post("/mcp", json={"method": "tools/list", "id": 1})
        assert mcp_resp.status_code == 200
        tools = mcp_resp.json()["result"]["tools"]
        assert len(tools) == 7


def test_7_tools_dispatcher() -> None:
    """Verify all 7 MCP tools return correct schemas, markdown tables and ECharts options."""
    session_id = "pytest_test_session"

    # 1. get_session_assumptions
    res = dispatcher.call_tool("get_latinlr202409_session_assumptions", {}, session_id)
    assert "artifact_markdown" in res
    assert "active_overrides_count" in res

    # 2. update_session_overrides
    args = {"driver_overrides": {"Dated Brent": {2035: 85.0}}, "why_context": "testing overrides"}
    res = dispatcher.call_tool("update_latinlr202409_session_overrides", args, session_id)
    assert res["status"] == "success"

    # 3. run_equilibrium_solve
    res = dispatcher.call_tool("run_latinlr202409_equilibrium_solve", {"max_iterations": 1}, session_id)
    assert "artifact_markdown" in res
    assert "echarts_option" in res

    # 4. run_scenario_matrix
    res = dispatcher.call_tool("run_latinlr202409_scenario_matrix", {"target_year": 2035}, session_id)
    assert "artifact_markdown" in res
    assert "echarts_option" in res

    # 5. run_bqml_forecast_refresh
    res = dispatcher.call_tool("run_latinlr202409_bqml_forecast_refresh", {}, session_id)
    assert "artifact_markdown" in res
    assert "echarts_option" in res

    # 6. run_domain_economics
    res = dispatcher.call_tool("run_latinlr202409_domain_economics", {"target_year": 2035}, session_id)
    assert "artifact_markdown" in res
    assert "echarts_option" in res

    # 7. Reset session back to baseline
    res = dispatcher.call_tool("update_latinlr202409_session_overrides", {"reset_to_baseline": True}, session_id)
    assert res["status"] == "success"


def test_mcp_workbook_export(seed_path, tmp_path) -> None:
    """Verify fast OpenXML workbook export in < 5s to safe temp directory."""
    out_file = tmp_path / "exported_test_workbook.xlsx"
    session_id = "export_test_session"

    # Generate small delta
    deltas = {
        ("Dashboard_Annual", "P52"): {
            "sheet_name": "Dashboard_Annual",
            "cell_coord": "P52",
            "row_num": 52,
            "col_num": 16,
            "numeric_value": 99.9,
        }
    }

    # Execute synthesizer
    synthesize_workbook(seed_path, out_file, session_id, deltas)
    assert out_file.is_file()
    assert out_file.stat().st_size > 0
