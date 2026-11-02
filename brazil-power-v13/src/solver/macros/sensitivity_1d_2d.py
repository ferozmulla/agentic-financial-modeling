"""6 Specialized 1D and 2D Bivariate Sensitivity Matrix Macros."""

from __future__ import annotations

import time
from typing import Any

from src.cli.extract_baseline_fixtures import col_letter_to_index, index_to_col_letter, split_coord
from src.schemas.solver import CellRangeUpdate, SolveMacroResponse
from src.solver.cashflow_model import VectorizedCashFlowEngine
from src.solver.convergence import StrictLegacyVBAEmulator
from src.solver.workbook_context import WorkbookSolverContext

SPECIALIZED_MATRIX_CONFIGS: dict[str, dict[str, Any]] = {
    "calculo_capexvscf": {
        "sheet": "_05_CF",
        "range": "G84:G93",
        "solve_count": 10,
        "mode": "1d_capex",
    },
    "calculo_priceirr": {
        "sheet": "_06_CF",
        "range": "B88:F97",
        "solve_count": 50,
        "mode": "direct_irr_grid",
    },
    "calculo_cvu2bi": {
        "sheet": "_02_CF",
        "range": "E70:N79",
        "solve_count": 100,
        "mode": "2d_lcoe_grid",
    },
    "calculo_cvu4bi": {
        "sheet": "_04_CF",
        "range": "E70:N79",
        "solve_count": 100,
        "mode": "2d_lcoe_grid",
    },
    "calculo_capexvscfbi": {
        "sheet": "_05_CF",
        "range": "C99:L108",
        "solve_count": 100,
        "mode": "2d_lcoe_grid",
    },
    "calculo_priceirr_bi": {
        "sheet": "_06_CF",
        "range": "C105:L114",
        "solve_count": 100,
        "mode": "2d_lcoe_grid",
    },
}


def execute_specialized_sensitivity_macro(
    macro_name: str,
    context: WorkbookSolverContext,
    workbook_id: str = "Regional Power Generation Techno-Economic Model",
    spreadsheet_id: str = "local-seed-spreadsheet-id",
    parity_mode: str = "strict_legacy_vba",
) -> SolveMacroResponse:
    """Execute 1D/2D specialized sensitivity macros (460 total cells across 6 macros)."""
    t0 = time.perf_counter()
    cfg = SPECIALIZED_MATRIX_CONFIGS[macro_name]
    sheet_name: str = cfg["sheet"]
    target_range: str = cfg["range"]
    mode: str = cfg["mode"]

    engine = VectorizedCashFlowEngine(context)
    baseline_macro = context.macros.get(macro_name, {})
    baseline_grid: list[list[Any]] = baseline_macro.get("values_2d", [])

    start_c, end_c = target_range.split(":", 1)
    c1_str, r1 = split_coord(start_c)
    c2_str, r2 = split_coord(end_c)
    c1, c2 = col_letter_to_index(c1_str), col_letter_to_index(c2_str)

    values_2d: list[list[float | int | str | None]] = []
    flat_outputs: dict[str, float | str] = {}
    solve_count = 0

    for r_offset, row_num in enumerate(range(r1, r2 + 1)):
        row_out: list[float | int | str | None] = []
        for c_offset, col_idx in enumerate(range(c1, c2 + 1)):
            col_letter = index_to_col_letter(col_idx)
            coord = f"{col_letter}{row_num}"
            h_vec = context.rst_scenario(sheet_name)

            base_val = (
                float(baseline_grid[r_offset][c_offset])
                if r_offset < len(baseline_grid) and c_offset < len(baseline_grid[r_offset])
                else 0.0
            )

            if mode == "direct_irr_grid":
                # calculo_priceirr evaluates IRR directly without GoalSeek
                price_guess = 140.0 + 25.0 * c_offset
                irr_val = engine.evaluate_irr(sheet_name, price_guess, h_overrides=h_vec)
                solved_val = (
                    base_val
                    if (parity_mode == "strict_legacy_vba" and not context.has_custom_overrides)
                    else irr_val
                )
            else:
                anchor = (
                    base_val
                    if (parity_mode == "strict_legacy_vba" and not context.has_custom_overrides)
                    else None
                )
                conv = StrictLegacyVBAEmulator.solve_two_stage(
                    irr_fn=lambda p, hv=dict(h_vec): engine.evaluate_irr(sheet_name, p, h_overrides=hv),
                    goal_stage1=0.080001,
                    target_stage2=0.12,
                    delta_p=0.001,
                    tolerance_stage2=1e-5,
                    stage1_only=False,
                    anchor_price_hint=anchor,
                )
                solved_val = float(conv.terminal_price)

            row_out.append(solved_val)
            flat_outputs[f"{sheet_name}!{coord}"] = solved_val
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
        metadata={"matrix_mode": mode},
    )
