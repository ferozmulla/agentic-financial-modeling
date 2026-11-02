"""Tier 3 Integration Tests: TEST-A01..TEST-A06 Numerical Parity (<= 1e-8) and Latency SLAs."""

from __future__ import annotations

from fastapi.testclient import TestClient

from src.bqml.remote_function_handler import handle_bqml_remote_calls
from src.bqml.surrogate_trainer import BQMLConnectedSheetsEngine
from src.schemas.solver import (
    BQMLRemoteFunctionRequest,
    SolveMacroRequest,
)
from src.solver.macros.registry import MacroExecutionRegistry
from src.solver.workbook_context import WorkbookSolverContext
from src.vertex.predictor_server import vertex_app
from src.vertex.registry_client import get_vertex_endpoint_config


def _assert_macro_parity(
    macro_name: str,
    solver_context: WorkbookSolverContext,
    max_latency_ms: float,
) -> int:
    res = MacroExecutionRegistry.execute(
        SolveMacroRequest(macro_name=macro_name),
        base_context=solver_context,
    )
    assert res.execution_time_ms <= max_latency_ms, (
        f"{macro_name} exceeded SLA: {res.execution_time_ms:.1f} ms > {max_latency_ms} ms"
    )
    expected_flat = solver_context.macros[macro_name]["flat_outputs"]
    checked = 0
    for coord, exp_val in expected_flat.items():
        if isinstance(exp_val, (int, float)):
            assert coord in res.flat_outputs, f"Missing output cell {coord} in {macro_name}"
            act_val = float(res.flat_outputs[coord])
            rel_err = abs(act_val - float(exp_val)) / max(abs(float(exp_val)), 1e-12)
            assert rel_err <= 1e-8, (
                f"Parity failure on {macro_name} {coord}: actual={act_val}, expected={exp_val}, rel_err={rel_err}"
            )
            checked += 1
    return checked


def test_a01_cvu_sweeps_12_macros_parity_and_quirks(solver_context: WorkbookSolverContext) -> None:
    """TEST-A01: Verify all 12 calculo_cvu1..12 macros (102 cells), selective rst_scenario, and H6/H7 quirks."""
    total_cells = 0
    for i in range(1, 13):
        mname = f"calculo_cvu{i}"
        total_cells += _assert_macro_parity(mname, solver_context, max_latency_ms=800.0)
        res = MacroExecutionRegistry.execute(
            SolveMacroRequest(macro_name=mname),
            base_context=solver_context,
        )
        if i <= 10:
            expected_rst = i in {1, 4, 5, 6, 10}
            assert res.metadata["rst_scenario_executed"] is expected_rst
            expected_h = "H6" if i == 5 else "H7"
            assert res.metadata["mutated_observer_cell"] == expected_h
    assert total_cells == 102


def test_a02_tornado_irr_12_macros_parity_and_quirks(solver_context: WorkbookSolverContext) -> None:
    """TEST-A02: Verify all 12 calcule_tir1..12 macros (234 cells), thermal C16 vs renewable B16, and tir11/12 8.0001%."""
    total_cells = 0
    for i in range(1, 13):
        mname = f"calcule_tir{i}"
        total_cells += _assert_macro_parity(mname, solver_context, max_latency_ms=800.0)
        res = MacroExecutionRegistry.execute(
            SolveMacroRequest(macro_name=mname),
            base_context=solver_context,
        )
        if i in {1, 7, 8, 9, 10}:
            assert res.metadata["output_variable"] == "fxd_revenue_C16"
        else:
            assert res.metadata["output_variable"] == "price_lst_B16"
        assert res.metadata["stage1_only_8pct_quirk"] is (i in {11, 12})
    assert total_cells == 234


def test_a03_specialized_1d_2d_matrices_and_unbound_routines(
    solver_context: WorkbookSolverContext,
) -> None:
    """TEST-A03: Verify 6 1D/2D matrices (460 cells) + lcoe_forecast (12 cells) + fator_i (10 cells) = 482 cells."""
    macros = [
        "calculo_capexvscf",
        "calculo_priceirr",
        "calculo_cvu2bi",
        "calculo_cvu4bi",
        "calculo_capexvscfbi",
        "calculo_priceirr_bi",
        "lcoe_forecast",
        "fator_i",
    ]
    total_cells = 0
    for mname in macros:
        total_cells += _assert_macro_parity(mname, solver_context, max_latency_ms=2000.0)
    assert total_cells == 482


def test_a04_master_lcoe_exec_184_solves_and_thermal_icb(
    solver_context: WorkbookSolverContext,
) -> None:
    """TEST-A04: Verify master 23-year x 8-tech lcoe_exec (184 cells on Output_3!B9:J31 + B3 timestamp + ICB)."""
    checked = _assert_macro_parity("lcoe_exec", solver_context, max_latency_ms=2000.0)
    assert checked == 184

    res = MacroExecutionRegistry.execute(
        SolveMacroRequest(macro_name="lcoe_exec"),
        base_context=solver_context,
    )
    assert res.solve_count == 184
    assert res.metadata["skipped_output3_column"] == "D"
    icb_diag = res.metadata["thermal_icb_diagnostics"]
    assert icb_diag["_01_CF"]["icb_row"] == 81
    assert icb_diag["_07_CF"]["icb_row"] == 81
    assert icb_diag["_09_CF"]["icb_row"] == 81
    assert icb_diag["_08_CF"]["icb_row"] == 105


def test_a05_vertex_ai_custom_prediction_container_contract() -> None:
    """TEST-A05: Verify Vertex AI Custom Prediction container (/health and /predict) and endpoint config."""
    client = TestClient(vertex_app)
    health_resp = client.get("/health")
    assert health_resp.status_code == 200
    assert health_resp.json()["supported_macros_count"] == 38

    pred_resp = client.post(
        "/predict",
        json={
            "instances": [
                {"macro_name": "calculo_cvu11"},
                {"macro_name": "calcule_tir1"},
            ]
        },
    )
    assert pred_resp.status_code == 200
    preds = pred_resp.json()["predictions"]
    assert len(preds) == 2
    assert preds[0]["solve_count"] == 1
    assert preds[1]["solve_count"] == 21

    # Verify us-central1 service region and 'us' multi-region Gemini endpoint
    vcfg = get_vertex_endpoint_config()
    assert vcfg.service_region == "us-central1"
    assert vcfg.gemini_location == "us"
    assert vcfg.gemini_api_endpoint == "us-aiplatform.googleapis.com"


def test_a06_bqml_remote_function_surrogate_and_connected_sheets_forecasts(
    solver_context: WorkbookSolverContext,
) -> None:
    """TEST-A06: Verify BigQuery ML Remote Function fn_solve_lcoe, Surrogate Model, and 23-year LT forecasts."""
    bq_req = BQMLRemoteFunctionRequest(
        calls=[
            ["calculo_cvu11", {"parity_mode": "strict_legacy_vba"}],
            ["calculo_cvu12", {"parity_mode": "strict_legacy_vba"}],
        ]
    )
    bq_resp = handle_bqml_remote_calls(bq_req)
    assert bq_resp.errorMessage is None
    assert len(bq_resp.replies) == 2
    assert "_11_CF!B16" in bq_resp.replies[0]["flat_outputs"]
    assert "_12_CF!B16" in bq_resp.replies[1]["flat_outputs"]

    bq_engine = BQMLConnectedSheetsEngine(solver_context)
    lt_rows = bq_engine.generate_connected_sheets_lt_forecasts(horizon=23)
    assert len(lt_rows) == 3 * 23 * 8  # 3 curve families x 23 years x 8 technologies = 552 rows

    surrogate = bq_engine.predict_surrogate_lcoe("_05_CF", capex_multiplier=0.9, capacity_factor_multiplier=1.05)
    assert surrogate["model_id"] == "sheets-commodity-mod-bqml-surrogate"
    assert surrogate["predicted_lcoe"] > 0.0
