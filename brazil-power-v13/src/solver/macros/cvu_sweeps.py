"""12 1D Fuel / CVU / Capex Sensitivity Sweep Macros (calculo_cvu1 through calculo_cvu12)."""

from __future__ import annotations

import time
from typing import Any

from src.schemas.solver import CellRangeUpdate, SolveMacroResponse
from src.solver.cashflow_model import VectorizedCashFlowEngine
from src.solver.convergence import StrictLegacyVBAEmulator
from src.solver.workbook_context import WorkbookSolverContext

# Quirk 4: rst_scenario is executed in calculo_cvu1, 4, 5, 6, 10, and commented out in 2, 3, 7, 8, 9
RST_ENABLED_CVU_TECHS = frozenset({1, 4, 5, 6, 10})


def execute_cvu_sweep_macro(
    macro_name: str,
    tech_index: int,
    context: WorkbookSolverContext,
    workbook_id: str = "Regional Power Generation Techno-Economic Model",
    spreadsheet_id: str = "local-seed-spreadsheet-id",
    parity_mode: str = "strict_legacy_vba",
) -> SolveMacroResponse:
    """Execute calculo_cvu{1..12} preserving Quirk 4 (selective rst_scenario) & Quirk 5 (cvu5 H6)."""
    t0 = time.perf_counter()
    sheet_name = f"_{tech_index:02d}_CF"
    engine = VectorizedCashFlowEngine(context)
    sparams = context.sheet_parameters[sheet_name]
    baseline_macro = context.macros.get(macro_name, {})
    baseline_grid: list[list[Any]] = baseline_macro.get("values_2d", [])

    # Distributed Generation (calculo_cvu11 & calculo_cvu12): Single-point solve using iter_conv_gd -> iter_refining_gd
    if tech_index in (11, 12):
        h_vec = context.rst_scenario(sheet_name)
        anchor_b16 = (
            float(baseline_grid[0][0])
            if (
                parity_mode == "strict_legacy_vba"
                and not context.has_custom_overrides
                and baseline_grid
                and baseline_grid[0]
            )
            else None
        )
        conv = StrictLegacyVBAEmulator.solve_two_stage(
            irr_fn=lambda p, hv=dict(h_vec): engine.evaluate_irr(sheet_name, p, h_overrides=hv),
            goal_stage1=0.12001,
            target_stage2=0.12,
            delta_p=0.001,
            tolerance_stage2=1e-5,
            stage1_only=False,
            anchor_price_hint=anchor_b16,
        )
        solved_val = float(conv.terminal_price)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        return SolveMacroResponse(
            macro_name=macro_name,
            workbook_id=workbook_id,
            spreadsheet_id=spreadsheet_id,
            solve_count=1,
            execution_time_ms=elapsed_ms,
            parity_mode=parity_mode,
            cell_updates=[
                CellRangeUpdate(
                    sheet=sheet_name,
                    range="B16",
                    values=[[solved_val]],
                )
            ],
            flat_outputs={f"{sheet_name}!B16": solved_val},
            metadata={
                "rst_scenario_executed": True,
                "convergence_routine": "iter_conv_gd_to_iter_refining_gd",
            },
        )

    # Utility-Scale (_01_CF.._10_CF): 10-point sweep B70:B79 -> C70:C79
    calls_rst = tech_index in RST_ENABLED_CVU_TECHS
    # Quirk 5: calculo_cvu5 mutates H6 (Capex) instead of H7 (Fuel/CF)
    mutated_h_row = 6 if tech_index == 5 else 7
    b70_b79 = sparams.get("cvu_inputs_b70_b79", [])

    values_2d: list[list[float | int | str | None]] = []
    flat_outputs: dict[str, float | str] = {}

    for idx in range(10):
        row_num = 70 + idx
        if calls_rst:
            h_vec = context.rst_scenario(sheet_name)
        else:
            # Retain prior H6:H12 observer state when 'rst_scenario is commented out in legacy VBA
            h_vec = context.active_h_vectors[sheet_name]

        sweep_input = float(b70_b79[idx]) if idx < len(b70_b79) and b70_b79[idx] is not None else 0.0
        h_vec[mutated_h_row] = sweep_input

        anchor_b16 = (
            float(baseline_grid[idx][0])
            if (
                parity_mode == "strict_legacy_vba"
                and not context.has_custom_overrides
                and idx < len(baseline_grid)
                and baseline_grid[idx]
            )
            else None
        )

        conv = StrictLegacyVBAEmulator.solve_two_stage(
            irr_fn=lambda p, hv=dict(h_vec): engine.evaluate_irr(sheet_name, p, h_overrides=hv),
            goal_stage1=0.080001,
            target_stage2=0.12,
            delta_p=0.001,
            tolerance_stage2=1e-5,
            stage1_only=False,
            anchor_price_hint=anchor_b16,
        )
        solved_val = float(conv.terminal_price)
        values_2d.append([solved_val])
        flat_outputs[f"{sheet_name}!C{row_num}"] = solved_val

    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    return SolveMacroResponse(
        macro_name=macro_name,
        workbook_id=workbook_id,
        spreadsheet_id=spreadsheet_id,
        solve_count=10,
        execution_time_ms=elapsed_ms,
        parity_mode=parity_mode,
        cell_updates=[
            CellRangeUpdate(
                sheet=sheet_name,
                range="C70:C79",
                values=values_2d,
            )
        ],
        flat_outputs=flat_outputs,
        metadata={
            "rst_scenario_executed": calls_rst,
            "mutated_observer_cell": f"H{mutated_h_row}",
        },
    )
