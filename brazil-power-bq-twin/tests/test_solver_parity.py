"""Quantitative solver and renderer tests for the isolated BigQuery Digital Twin."""

from __future__ import annotations

from pathlib import Path

from brazil_power_bq_twin.bq_store import InMemoryDigitalTwinStore
from brazil_power_bq_twin.solver_engine import QuantitativeTwinSolver
from brazil_power_bq_twin.xlsm_compiler import compile_workbook_to_twin_payload

from test_xlsm_compiler import _create_synthetic_22tab_workbook


def test_solver_assumptions_overrides_tornado_lcoe_and_dcf(tmp_path: Path) -> None:
    wb_path = _create_synthetic_22tab_workbook(tmp_path / "solver_v13.xlsx")
    snap = compile_workbook_to_twin_payload(wb_path).snapshot
    store = InMemoryDigitalTwinStore(snap)

    overlay0 = store.get_session_overlay("s_quant")
    assumptions = QuantitativeTwinSolver.extract_assumptions(snap, overlay0, technologies=["_01_CF", "_06_CF"])
    assert "General!B5:N40" in assumptions["full_artifact_table_md"]
    assert "| |" not in assumptions["full_artifact_table_md"]

    # Baseline Tornado & DCF on _01_CF (Gas CCGT)
    tornado_base, t_deltas = QuantitativeTwinSolver.run_tornado_sensitivity(snap, overlay0, "_01_CF")
    assert len(tornado_base["tornado_rows"]) == 7
    assert tornado_base["solve_count"] == 21
    assert len(t_deltas) > 0
    assert tornado_base["echarts_option"]["series"]

    dcf_base, dcf_deltas = QuantitativeTwinSolver.run_dcf_and_cvu(
        snap, overlay0, technology_code="_01_CF", include_cvu_sweep=True
    )
    assert len(dcf_base["annual_rows"]) == 30
    assert "cvu_gf_sweep" in dcf_base
    assert len(dcf_deltas) > 0

    # Stage fuel hike override on _01_CF (4.50 -> 7.50) and verify LCOE rises & IRR falls
    lcoe_base, _ = QuantitativeTwinSolver.run_lcoe_horizon(snap, overlay0)
    base_2024_ccgt_lcoe = lcoe_base["lcoe_grid"][0][0]

    ov_deltas, audit_rows, changes = QuantitativeTwinSolver.stage_overrides(
        snap,
        overlay0,
        overrides={"_01_CF": {"fuel_cost": 7.50}, "General!H14": 2.0},
    )
    assert len(changes) == 2
    assert len(audit_rows) == 2
    store.append_session_deltas("s_quant", ov_deltas, audit_rows=audit_rows)

    overlay1 = store.get_session_overlay("s_quant")
    lcoe_after, lcoe_deltas = QuantitativeTwinSolver.run_lcoe_horizon(snap, overlay1)
    assert len(lcoe_deltas) == 23 * 9
    assert lcoe_after["lcoe_grid"][0][0] > base_2024_ccgt_lcoe

    dcf_after, _ = QuantitativeTwinSolver.run_dcf_and_cvu(snap, overlay1, technology_code="_01_CF")
    assert dcf_after["project_irr"] < dcf_base["project_irr"]
