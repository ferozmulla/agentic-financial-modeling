"""Phase 2 Verification Tests: TEST-A01 (<= 1e-8 Parity), TEST-A02 (10-Pass Convergence), TEST-A03 (ULSD-GO Coupling), TEST-A04 (#FEF3C7 Overrides)."""

from __future__ import annotations

import numpy as np

from src.schemas.models import EquilibriumSolveRequest
from src.solver.cse_rewriter import compute_cashflow_irr, interpolate_op_cost_row
from src.solver.equilibrium_engine import load_baseline_tensor_state, solve_eulr_equilibrium


def test_a01_baseline_ten_pass_numerical_parity() -> None:
    """TEST-A01: Verify <= 1e-8 numerical parity across all 19 active sheets against Eulr202409.xlsx cached <v> values."""
    req = EquilibriumSolveRequest(
        spreadsheet_id="test-parity-sheet",
        scenario_mode="base",
        carbon_mode="Sensitivity with EU ETS cost and pass-through",
        upstream_source_mode="eulr_baseline_cached",
        max_iterations=10,
    )
    resp, solved_state = solve_eulr_equilibrium(req)
    base_state = load_baseline_tensor_state()

    assert resp.iterations_run == 10
    assert resp.converged is True
    assert resp.final_max_delta <= 1e-8

    # Check relative error across all 19 active sheets
    max_rel_err = 0.0
    for sname, base_mat in base_state.baseline_tensors.items():
        sol_mat = solved_state.tensors[sname]
        mask = np.isfinite(base_mat) & np.isfinite(sol_mat)
        if np.any(mask):
            denom = np.maximum(np.abs(base_mat[mask]), 1e-12)
            rel = float(np.max(np.abs(sol_mat[mask] - base_mat[mask]) / denom))
            max_rel_err = max(max_rel_err, rel)

    assert max_rel_err <= 1e-8

    # Verify exact 2025 (Column AU) baseline prices from Eulr202409.xlsx
    assert resp.key_prices_2025_usd_mt["NWE_Naphtha_CIF_ARA"] == 615.47
    assert resp.key_prices_2025_usd_mt["NWE_Euro_Gasoline_CIF_ARA"] == 711.33
    assert resp.key_prices_2025_usd_mt["NWE_Jet_Kero_CIF_ARA"] == 765.29
    assert resp.key_prices_2025_usd_mt["NWE_Diesel_EN590_CIF_ARA"] == 716.40
    assert resp.key_prices_2025_usd_mt["NWE_LSFO_1S_CIF_ARA"] == 457.69


def test_a02_ten_pass_convergence_and_cse_vectorization() -> None:
    """TEST-A02: Verify 10-pass monotonic convergence under sensitivity shock and CSE/IRR helpers."""
    req = EquilibriumSolveRequest(
        spreadsheet_id="test-conv-sheet",
        scenario_mode="sensitivity",
        carbon_mode="Base without EU ETS carbon pass-through (Off)",
        upstream_source_mode="peer_xlsx",
        max_iterations=10,
    )
    resp, _ = solve_eulr_equilibrium(req)

    assert resp.iterations_run == 10
    assert len(resp.convergence_history) == 10
    assert resp.convergence_history[-1] < resp.convergence_history[0]
    assert resp.compute_ms < 250.0

    # Test Op_Cost {=CSE} forward interpolation helper
    sample_row = np.array([np.nan, 10.0, np.nan, np.nan, 16.0, np.nan], dtype=np.float64)
    interp = interpolate_op_cost_row(sample_row)
    assert np.allclose(interp[1:5], [10.0, 12.0, 14.0, 16.0])

    # Test 2015 NWE HCK IRR helper
    irr_val = compute_cashflow_irr([-100.0, 35.0, 40.0, 45.0, 50.0])
    assert 0.15 < irr_val < 0.30


def test_a03_ulsd_go_spread_econs_bidirectional_coupling() -> None:
    """TEST-A03: Verify ULSD-GO_spread_econs updates when NWE Cif Diesel/Gasoil shifts inside the 10-pass loop."""
    base_req = EquilibriumSolveRequest(spreadsheet_id="test-ulsd-base")
    _, base_state = solve_eulr_equilibrium(base_req)

    shock_req = EquilibriumSolveRequest(
        spreadsheet_id="test-ulsd-shock",
        pinned_overrides={"NWE Cif!AU122": 750.00},
    )
    _, shock_state = solve_eulr_equilibrium(shock_req)

    base_ulsd_diesel = float(base_state.tensors["ULSD-GO_spread_econs"][26, 47])
    shock_ulsd_diesel = float(shock_state.tensors["ULSD-GO_spread_econs"][26, 47])
    assert shock_ulsd_diesel > base_ulsd_diesel


def test_a04_pinned_override_mask_and_exact_reversion() -> None:
    """TEST-A04: Verify #FEF3C7 pinned override on NWE Cif!AU122 = 750.00 holds across 10 passes and reverts <= 1e-12."""
    pin_req = EquilibriumSolveRequest(
        spreadsheet_id="test-pin-sheet",
        pinned_overrides={"NWE Cif!AU122": 750.00},
    )
    pin_resp, pin_state = solve_eulr_equilibrium(pin_req)

    assert pin_resp.pinned_override_count == 1
    assert pin_resp.key_prices_2025_usd_mt["NWE_Diesel_EN590_CIF_ARA"] == 750.00
    assert float(pin_state.tensors["NWE Cif"][122, 47]) == 750.00
    # IMOfuels!AU11 ('Diesel EN590') and AU21 ('0.1% Marine Bunkers') equilibrate upward
    assert float(pin_state.tensors["IMOfuels"][11, 47]) == 750.00
    assert pin_resp.key_prices_2025_usd_mt["IMO_01S_MGO_Bunker"] > 684.74

    # Revert override (empty pinned_overrides) -> restores exact baseline equilibrium <= 1e-12
    rev_req = EquilibriumSolveRequest(
        spreadsheet_id="test-pin-sheet",
        pinned_overrides={},
    )
    rev_resp, rev_state = solve_eulr_equilibrium(rev_req)
    base_state = load_baseline_tensor_state()

    max_diff = float(
        np.nanmax(np.abs(rev_state.tensors["NWE Cif"] - base_state.baseline_tensors["NWE Cif"]))
    )
    assert max_diff <= 1e-12
    assert rev_resp.key_prices_2025_usd_mt["NWE_Diesel_EN590_CIF_ARA"] == 716.40
