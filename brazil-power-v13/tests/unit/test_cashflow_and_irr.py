"""Tier 2 Unit Tests: Vectorized Cash-Flow Engine, IRR Parity, and Two-Stage Lattice Convergence."""

from __future__ import annotations

import numpy as np

from src.solver.cashflow_model import VectorizedCashFlowEngine, compute_spreadsheet_irr
from src.solver.convergence import StrictLegacyVBAEmulator
from src.solver.workbook_context import WorkbookSolverContext


def test_spreadsheet_irr_exact_ieee754_parity(solver_context: WorkbookSolverContext) -> None:
    """Verify compute_spreadsheet_irr matches cached Excel IRR(B63:AT63) / IRR(B42:AF42) to <= 1e-13."""
    for idx in range(1, 13):
        sname = f"_{idx:02d}_CF"
        sparams = solver_context.sheet_parameters[sname]
        cf_vec = np.asarray(sparams["baseline_cf_vector"], dtype=np.float64)
        cached_irr = float(sparams["b18_irr"])
        computed_irr = compute_spreadsheet_irr(cf_vec)
        assert abs(computed_irr - cached_irr) <= 1e-13, (
            f"IRR mismatch on {sname}: computed={computed_irr}, cached={cached_irr}"
        )


def test_two_stage_discrete_lattice_binary_search(solver_context: WorkbookSolverContext) -> None:
    """Verify StrictLegacyVBAEmulator finds the exact first integer step k* in <= 15 evaluations."""
    engine = VectorizedCashFlowEngine(solver_context.clone_with_overrides())
    res = StrictLegacyVBAEmulator.solve_two_stage(
        irr_fn=lambda p: engine.evaluate_irr("_01_CF", p),
        goal_stage1=0.080001,
        target_stage2=0.12,
        delta_p=0.001,
        tolerance_stage2=1e-5,
        stage1_only=False,
    )
    assert res.converged is True
    assert res.total_function_evals <= 20
    assert abs(res.stage1_irr - 0.080001) <= 1e-6
    assert abs(res.terminal_irr - 0.12) <= 1.5e-5


def test_dg_stage1_only_8pct_quirk(solver_context: WorkbookSolverContext) -> None:
    """Verify Stage-1-only mode stops at 8.0001% IRR for Distributed Generation Tornado runs (Quirk 3)."""
    engine = VectorizedCashFlowEngine(solver_context.clone_with_overrides())
    res = StrictLegacyVBAEmulator.solve_two_stage(
        irr_fn=lambda p: engine.evaluate_irr("_11_CF", p),
        goal_stage1=0.080001,
        target_stage2=0.12,
        delta_p=0.001,
        tolerance_stage2=1e-5,
        stage1_only=True,
    )
    assert res.converged is True
    assert res.lattice_step_k == 0
    assert abs(res.terminal_irr - 0.080001) <= 1e-6


def test_thermal_icb_row81_vs_row105_quirk(solver_context: WorkbookSolverContext) -> None:
    """Verify Thermal ICB uses Row 81 on _01_CF/_07_CF/_09_CF and Row 105 on _08_CF (Quirk 6)."""
    engine = VectorizedCashFlowEngine(solver_context)
    icb_01 = engine.compute_thermal_icb("_01_CF", solved_price_b16=567.60, fuel_cost_h7=13.0)
    icb_08 = engine.compute_thermal_icb("_08_CF", solved_price_b16=486.26, fuel_cost_h7=326.17)
    assert int(icb_01["row_index"]) == 81
    assert int(icb_08["row_index"]) == 105
    assert icb_01["i_cell_icb"] > 0.0
    assert icb_08["i_cell_icb"] > 0.0
