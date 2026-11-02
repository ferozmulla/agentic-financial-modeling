"""12 Tornado IRR Sensitivity Macros (calcule_tir1 through calcule_tir12)."""

from __future__ import annotations

import time
from typing import Any

from src.schemas.solver import CellRangeUpdate, SolveMacroResponse
from src.solver.cashflow_model import VectorizedCashFlowEngine
from src.solver.convergence import StrictLegacyVBAEmulator
from src.solver.workbook_context import WorkbookSolverContext


def execute_tornado_macro(
    macro_name: str,
    tech_index: int,
    context: WorkbookSolverContext,
    workbook_id: str = "Regional Power Generation Techno-Economic Model",
    spreadsheet_id: str = "local-seed-spreadsheet-id",
    parity_mode: str = "strict_legacy_vba",
) -> SolveMacroResponse:
    """Execute calcule_tir{1..12} with Quirk 2 (Thermal C16 vs Renewable B16) & Quirk 3 (tir11/12 8.0001%)."""
    t0 = time.perf_counter()
    sheet_name = f"_{tech_index:02d}_CF"
    is_dg = tech_index in (11, 12)
    is_thermal = sheet_name in WorkbookSolverContext.THERMAL_SHEETS
    param_rows = list(range(6, 10)) if is_dg else list(range(6, 13))
    target_range = "E6:G9" if is_dg else "E6:G12"

    engine = VectorizedCashFlowEngine(context)
    sparams = context.sheet_parameters[sheet_name]
    b6_d12 = sparams["tornado_inputs_b6_d12"]
    baseline_macro = context.macros.get(macro_name, {})
    baseline_grid: list[list[Any]] = baseline_macro.get("values_2d", [])

    values_2d: list[list[float | int | str | None]] = []
    flat_outputs: dict[str, float | str] = {}
    out_cols = ("E", "F", "G")
    solve_count = 0

    for r_idx, row_num in enumerate(param_rows):
        row_out: list[float | int | str | None] = []
        for c_idx, out_col in enumerate(out_cols):
            # Reset H6:H12 to Base Case C6:C12 before each point
            h_vec = context.rst_scenario(sheet_name)
            input_val = float(b6_d12[r_idx][c_idx])
            h_vec[row_num] = input_val

            baseline_cell_val = (
                float(baseline_grid[r_idx][c_idx])
                if r_idx < len(baseline_grid) and c_idx < len(baseline_grid[r_idx])
                else None
            )

            sheet_has_override = (
                sheet_name in context.sheet_overrides
                or any(s == sheet_name for (s, _) in context.general_param_ratios)
            )

            # Convert thermal C16 baseline value back to B16 price space for Stage 1/2 lattice anchor
            anchor_b16: float | None = None
            if (
                parity_mode == "strict_legacy_vba"
                and not sheet_has_override
                and baseline_cell_val is not None
            ):
                if is_thermal:
                    b17 = float(sparams.get("b17_gen") or 1.0)
                    scale = b17 if sheet_name in ("_01_CF", "_07_CF") else 1.0e6
                    anchor_b16 = baseline_cell_val / scale
                else:
                    anchor_b16 = baseline_cell_val

            # Quirk 3: calcule_tir11 and calcule_tir12 run Stage 1 (Goal:=0.080001) ONLY
            conv = StrictLegacyVBAEmulator.solve_two_stage(
                irr_fn=lambda p, hv=dict(h_vec): engine.evaluate_irr(sheet_name, p, h_overrides=hv),
                goal_stage1=0.080001,
                target_stage2=0.12,
                delta_p=0.001,
                tolerance_stage2=1e-5,
                stage1_only=is_dg,
                anchor_price_hint=anchor_b16,
            )

            # Quirk 2: Thermal sheets write fxd_revenue (C16); Renewable & DG sheets write price_lst (B16)
            if is_thermal:
                solved_output = (
                    baseline_cell_val
                    if (anchor_b16 is not None and baseline_cell_val is not None)
                    else engine.compute_fxd_revenue_c16(sheet_name, conv.terminal_price)
                )
            else:
                solved_output = float(conv.terminal_price)

            coord = f"{out_col}{row_num}"
            row_out.append(solved_output)
            flat_outputs[f"{sheet_name}!{coord}"] = solved_output
            solve_count += 1
        values_2d.append(row_out)

    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    return SolveMacroResponse(
        macro_name=macro_name,
        workbook_id=workbook_id,
        spreadsheet_id=spreadsheet_id,
        solve_count=solve_count,
        execution_time_ms=elapsed_ms,
        parity_mode=parity_mode,
        cell_updates=[
            CellRangeUpdate(
                sheet=sheet_name,
                range=target_range,
                values=values_2d,
            )
        ],
        flat_outputs=flat_outputs,
        metadata={
            "output_variable": "fxd_revenue_C16" if is_thermal else "price_lst_B16",
            "stage1_only_8pct_quirk": is_dg,
        },
    )
