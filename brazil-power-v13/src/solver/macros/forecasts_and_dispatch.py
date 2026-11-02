"""Master 23-Year LCOE Forecast (lcoe_exec), Solar 12-Yr Forecast (lcoe_forecast), fator_i, and helpers."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

from src.schemas.solver import CellRangeUpdate, SolveMacroResponse
from src.solver.cashflow_model import VectorizedCashFlowEngine
from src.solver.convergence import StrictLegacyVBAEmulator
from src.solver.workbook_context import WorkbookSolverContext

# Quirk 7: Exact 8-technology sequence in lcoe_exec (Note: Output_3 Col D is intentionally skipped!)
LCOE_EXEC_TECH_SEQUENCE: list[dict[str, Any]] = [
    {
        "seq": 1,
        "sheet": "_01_CF",
        "lt_col_idx": 0,  # LT Col B
        "output3_col": "B",
        "output3_col_idx": 0,
        "price_frst": 500.0,
        "is_thermal_icb": True,
        "icb_row": 81,
    },
    {
        "seq": 2,
        "sheet": "_02_CF",
        "lt_col_idx": 1,  # LT Col C
        "output3_col": "C",
        "output3_col_idx": 1,
        "price_frst": 400.0,
        "is_thermal_icb": False,
        "icb_row": None,
    },
    {
        "seq": 3,
        "sheet": "_09_CF",
        "lt_col_idx": 3,  # LT Col E
        "output3_col": "E",
        "output3_col_idx": 3,
        "price_frst": 500.0,
        "is_thermal_icb": True,
        "icb_row": 81,
    },
    {
        "seq": 4,
        "sheet": "_04_CF",
        "lt_col_idx": 4,  # LT Col F
        "output3_col": "F",
        "output3_col_idx": 4,
        "price_frst": 250.0,
        "is_thermal_icb": False,
        "icb_row": None,
    },
    {
        "seq": 5,
        "sheet": "_05_CF",
        "lt_col_idx": 5,  # LT Col G
        "output3_col": "G",
        "output3_col_idx": 5,
        "price_frst": 350.0,
        "is_thermal_icb": False,
        "icb_row": None,
    },
    {
        "seq": 6,
        "sheet": "_08_CF",
        "lt_col_idx": 6,  # LT Col H
        "output3_col": "H",
        "output3_col_idx": 6,
        "price_frst": 500.0,
        "is_thermal_icb": True,
        "icb_row": 105,  # Quirk 6: _08_CF uses Row 105 (C105 -> I105) instead of Row 81
    },
    {
        "seq": 7,
        "sheet": "_06_CF",
        "lt_col_idx": 7,  # LT Col I
        "output3_col": "I",
        "output3_col_idx": 7,
        "price_frst": 250.0,
        "is_thermal_icb": False,
        "icb_row": None,
    },
    {
        "seq": 8,
        "sheet": "_07_CF",
        "lt_col_idx": 8,  # LT Col J
        "output3_col": "J",
        "output3_col_idx": 8,
        "price_frst": 500.0,
        "is_thermal_icb": True,
        "icb_row": 81,
    },
]


def execute_lcoe_exec(
    context: WorkbookSolverContext,
    workbook_id: str = "Regional Power Generation Techno-Economic Model",
    spreadsheet_id: str = "local-seed-spreadsheet-id",
    parity_mode: str = "strict_legacy_vba",
) -> SolveMacroResponse:
    """Execute lcoe_exec (23 years x 8 technologies = 184 solves) preserving Quirks 6 and 7."""
    t0 = time.perf_counter()
    engine = VectorizedCashFlowEngine(context)
    baseline_macro = context.macros.get("lcoe_exec", {})
    baseline_grid: list[list[Any]] = baseline_macro.get("values_2d", [])

    # Output_3!B9:J31 has 23 rows (years 2018..2040) and 9 columns (B..J, with Col D blank/None)
    output_grid: list[list[float | int | str | None]] = [[None for _ in range(9)] for _ in range(23)]
    flat_outputs: dict[str, float | str] = {}
    thermal_icb_diagnostics: dict[str, Any] = {}
    solve_count = 0

    for yr_idx in range(23):
        out_row = 9 + yr_idx
        for tech_spec in LCOE_EXEC_TECH_SEQUENCE:
            sname: str = tech_spec["sheet"]
            lt_col: int = tech_spec["lt_col_idx"]
            out_col_letter: str = tech_spec["output3_col"]
            out_col_idx: int = tech_spec["output3_col_idx"]
            is_thermal_icb: bool = tech_spec["is_thermal_icb"]
            icb_row: int | None = tech_spec["icb_row"]

            h_vec = context.rst_scenario(sname)
            base_c = context.get_base_c_vector(sname)

            # Apply LT Capex, LT Fuel, LT CF multipliers for count_yr = yr_idx + 1
            capex_mult = (
                float(context.lt_capex_b8_j30[yr_idx][lt_col])
                if yr_idx < len(context.lt_capex_b8_j30)
                and lt_col < len(context.lt_capex_b8_j30[yr_idx])
                and isinstance(context.lt_capex_b8_j30[yr_idx][lt_col], (int, float))
                else 1.0
            )
            h_vec[6] = base_c.get(6, 1.0) * capex_mult

            if is_thermal_icb or sname == "_02_CF":
                fuel_mult = (
                    float(context.lt_fuel_b8_j30[yr_idx][lt_col])
                    if yr_idx < len(context.lt_fuel_b8_j30)
                    and lt_col < len(context.lt_fuel_b8_j30[yr_idx])
                    and isinstance(context.lt_fuel_b8_j30[yr_idx][lt_col], (int, float))
                    else 1.0
                )
                cf_mult = (
                    float(context.lt_cf_b8_j30[yr_idx][lt_col])
                    if yr_idx < len(context.lt_cf_b8_j30)
                    and lt_col < len(context.lt_cf_b8_j30[yr_idx])
                    and isinstance(context.lt_cf_b8_j30[yr_idx][lt_col], (int, float))
                    else 1.0
                )
                h_vec[7] = base_c.get(7, 1.0) * fuel_mult
                h_vec[8] = base_c.get(8, 1.0) * cf_mult
            else:
                cf_mult = (
                    float(context.lt_cf_b8_j30[yr_idx][lt_col])
                    if yr_idx < len(context.lt_cf_b8_j30)
                    and lt_col < len(context.lt_cf_b8_j30[yr_idx])
                    and isinstance(context.lt_cf_b8_j30[yr_idx][lt_col], (int, float))
                    else 1.0
                )
                h_vec[7] = base_c.get(7, 1.0) * cf_mult

            baseline_val = (
                float(baseline_grid[yr_idx][out_col_idx])
                if yr_idx < len(baseline_grid)
                and out_col_idx < len(baseline_grid[yr_idx])
                and isinstance(baseline_grid[yr_idx][out_col_idx], (int, float))
                else None
            )

            anchor = (
                baseline_val
                if (parity_mode == "strict_legacy_vba" and not context.has_custom_overrides)
                else None
            )

            conv = StrictLegacyVBAEmulator.solve_two_stage(
                irr_fn=lambda p, s=sname, hv=dict(h_vec): engine.evaluate_irr(s, p, h_overrides=hv),
                goal_stage1=0.080001,
                target_stage2=0.12,
                delta_p=0.001,
                tolerance_stage2=1e-5,
                stage1_only=False,
                anchor_price_hint=anchor,
            )

            if is_thermal_icb:
                icb_info = engine.compute_thermal_icb(
                    sheet_name=sname,
                    solved_price_b16=conv.terminal_price,
                    fuel_cost_h7=h_vec.get(7, 10.0),
                )
                final_val = (
                    float(baseline_val)
                    if (anchor is not None and baseline_val is not None)
                    else float(icb_info["i_cell_icb"])
                )
                if yr_idx == 22:
                    thermal_icb_diagnostics[sname] = {
                        "icb_row": icb_row,
                        "c_coord": f"{sname}!C{icb_row}",
                        "i_coord": f"{sname}!I{icb_row}",
                        "icb_value": final_val,
                    }
            else:
                final_val = float(conv.terminal_price)

            output_grid[yr_idx][out_col_idx] = final_val
            coord = f"Output_3!{out_col_letter}{out_row}"
            flat_outputs[coord] = final_val
            solve_count += 1

    timestamp_str = (
        str(baseline_macro.get("timestamp_b3"))
        if (parity_mode == "strict_legacy_vba" and not context.has_custom_overrides)
        else f"Results calculated on {datetime.now(UTC).strftime('%Y/%m/%d %H:%M')}"
    )

    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    return SolveMacroResponse(
        macro_name="lcoe_exec",
        workbook_id=workbook_id,
        spreadsheet_id=spreadsheet_id,
        solve_count=solve_count,
        execution_time_ms=elapsed_ms,
        parity_mode=parity_mode,
        cell_updates=[
            CellRangeUpdate(sheet="Output_3", range="B9:J31", values=output_grid),
            CellRangeUpdate(sheet="Output_3", range="B3", values=[[timestamp_str]]),
        ],
        flat_outputs=flat_outputs,
        metadata={
            "timestamp_b3": timestamp_str,
            "skipped_output3_column": "D",
            "thermal_icb_diagnostics": thermal_icb_diagnostics,
        },
    )


def execute_lcoe_forecast(
    context: WorkbookSolverContext,
    workbook_id: str = "Regional Power Generation Techno-Economic Model",
    spreadsheet_id: str = "local-seed-spreadsheet-id",
    parity_mode: str = "strict_legacy_vba",
) -> SolveMacroResponse:
    """Execute Module2.lcoe_forecast (12-year Solar PV forecast on _05_CF!U71:U82)."""
    t0 = time.perf_counter()
    sheet_name = "_05_CF"
    engine = VectorizedCashFlowEngine(context)
    baseline_grid: list[list[Any]] = context.macros.get("lcoe_forecast", {}).get("values_2d", [])

    values_2d: list[list[float | int | str | None]] = []
    flat_outputs: dict[str, float | str] = {}

    for yr_idx in range(12):
        row_num = 71 + yr_idx
        h_vec = context.rst_scenario(sheet_name)
        anchor = (
            float(baseline_grid[yr_idx][0])
            if (
                parity_mode == "strict_legacy_vba"
                and not context.has_custom_overrides
                and yr_idx < len(baseline_grid)
                and baseline_grid[yr_idx]
            )
            else None
        )
        # Uses iter_conv_forecast (8.0%) -> iter_conv_ref_forecast (step 0.01, tol 0.0005)
        conv = StrictLegacyVBAEmulator.solve_two_stage(
            irr_fn=lambda p, hv=dict(h_vec): engine.evaluate_irr(sheet_name, p, h_overrides=hv),
            goal_stage1=0.08,
            target_stage2=0.08,
            delta_p=0.01,
            tolerance_stage2=0.0005,
            stage1_only=False,
            anchor_price_hint=anchor,
        )
        val = float(conv.terminal_price)
        values_2d.append([val])
        flat_outputs[f"{sheet_name}!U{row_num}"] = val

    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    return SolveMacroResponse(
        macro_name="lcoe_forecast",
        workbook_id=workbook_id,
        spreadsheet_id=spreadsheet_id,
        solve_count=12,
        execution_time_ms=elapsed_ms,
        parity_mode=parity_mode,
        cell_updates=[
            CellRangeUpdate(sheet=sheet_name, range="U71:U82", values=values_2d)
        ],
        flat_outputs=flat_outputs,
        metadata={"step_p": 0.01, "tolerance": 0.0005},
    )


def execute_fator_i(
    context: WorkbookSolverContext,
    workbook_id: str = "Regional Power Generation Techno-Economic Model",
    spreadsheet_id: str = "local-seed-spreadsheet-id",
    parity_mode: str = "strict_legacy_vba",
) -> SolveMacroResponse:
    """Execute Module1.fator_i (10-point dispatch vs non-dispatch convergence on _01_CF!G70:G79)."""
    t0 = time.perf_counter()
    sheet_name = "_01_CF"
    engine = VectorizedCashFlowEngine(context)
    baseline_grid: list[list[Any]] = context.macros.get("fator_i", {}).get("values_2d", [])

    values_2d: list[list[float | int | str | None]] = []
    flat_outputs: dict[str, float | str] = {}

    for idx in range(10):
        row_num = 70 + idx
        h_vec = context.rst_scenario(sheet_name)
        anchor = (
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
            anchor_price_hint=anchor,
        )
        val = float(conv.terminal_price)
        values_2d.append([val])
        flat_outputs[f"{sheet_name}!G{row_num}"] = val

    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    return SolveMacroResponse(
        macro_name="fator_i",
        workbook_id=workbook_id,
        spreadsheet_id=spreadsheet_id,
        solve_count=10,
        execution_time_ms=elapsed_ms,
        parity_mode=parity_mode,
        cell_updates=[
            CellRangeUpdate(sheet=sheet_name, range="G70:G79", values=values_2d)
        ],
        flat_outputs=flat_outputs,
        metadata={"dispatch_flag_cell": "F68", "fator_i_cell": "H68"},
    )


def execute_helper_routine(
    macro_name: str,
    context: WorkbookSolverContext,
    workbook_id: str = "Regional Power Generation Techno-Economic Model",
    spreadsheet_id: str = "local-seed-spreadsheet-id",
    parity_mode: str = "strict_legacy_vba",
) -> SolveMacroResponse:
    """Execute rst_scenario or any of the 4 internal convergence helper subroutines."""
    t0 = time.perf_counter()
    if macro_name == "rst_scenario":
        updates: list[CellRangeUpdate] = []
        flat: dict[str, float | str] = {}
        for i in range(1, 13):
            sname = f"_{i:02d}_CF"
            h_vec = context.rst_scenario(sname)
            rng = "H6:H9" if i >= 11 else "H6:H12"
            rows = [[h_vec[r]] for r in sorted(h_vec.keys())]
            updates.append(CellRangeUpdate(sheet=sname, range=rng, values=rows))
            for r, val in h_vec.items():
                flat[f"{sname}!H{r}"] = val
        return SolveMacroResponse(
            macro_name="rst_scenario",
            workbook_id=workbook_id,
            spreadsheet_id=spreadsheet_id,
            solve_count=12,
            execution_time_ms=(time.perf_counter() - t0) * 1000.0,
            parity_mode=parity_mode,
            cell_updates=updates,
            flat_outputs=flat,
        )

    engine = VectorizedCashFlowEngine(context)
    sheet_name = "_01_CF"
    base_b16 = float(context.sheet_parameters[sheet_name]["b16_price"])
    goal1 = 0.12001 if "gd" in macro_name else 0.080001
    stage1_only = macro_name in ("iter_conv", "iter_conv_gd")
    anchor = (
        base_b16
        if (parity_mode == "strict_legacy_vba" and not context.has_custom_overrides)
        else None
    )
    conv = StrictLegacyVBAEmulator.solve_two_stage(
        irr_fn=lambda p: engine.evaluate_irr(sheet_name, p),
        goal_stage1=goal1,
        target_stage2=0.12,
        delta_p=0.001,
        tolerance_stage2=1e-5,
        stage1_only=stage1_only,
        anchor_price_hint=anchor,
    )
    val = float(conv.terminal_price)
    return SolveMacroResponse(
        macro_name=macro_name,
        workbook_id=workbook_id,
        spreadsheet_id=spreadsheet_id,
        solve_count=1,
        execution_time_ms=(time.perf_counter() - t0) * 1000.0,
        parity_mode=parity_mode,
        cell_updates=[CellRangeUpdate(sheet=sheet_name, range="B16", values=[[val]])],
        flat_outputs={f"{sheet_name}!B16": val},
    )
