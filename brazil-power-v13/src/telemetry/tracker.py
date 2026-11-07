"""In-memory Cloud Execution Telemetry Tracker for Macro Solves and BQML Refreshes."""

from __future__ import annotations

import copy
import os
import threading
import time
import uuid
from collections import deque
from datetime import UTC, datetime, timedelta
from typing import Any

from src.core.config import get_settings
from src.schemas.solver import (
    BQMLRemoteFunctionRequest,
    BQMLRemoteFunctionResponse,
    GeneralOverrides,
    SolveMacroRequest,
    SolveMacroResponse,
)
from src.schemas.telemetry import (
    ExecutionUnit,
    TelemetryFeedResponse,
    TelemetryStep,
    TelemetryStepStatus,
)
from src.solver.workbook_context import cells_differ, get_baseline_solver_context

# Column C..N (0..11 in General!C5:N40) -> Human-readable technology label
GENERAL_TECH_COLUMNS: dict[int, tuple[str, str]] = {
    0: ("C", "Tech 01 · Gas CCGT (_01_CF)"),
    1: ("D", "Tech 02 · Sugarcane Biomass (_02_CF)"),
    2: ("E", "Tech 03 · Biomass Retrofit (_03_CF)"),
    3: ("F", "Tech 04 · Onshore Wind (_04_CF)"),
    4: ("G", "Tech 05 · Utility Solar PV (_05_CF)"),
    5: ("H", "Tech 06 · Small Hydro SHP (_06_CF)"),
    6: ("I", "Tech 07 · Local Coal CFBC (_07_CF)"),
    7: ("J", "Tech 08 · Imported Coal PC (_08_CF)"),
    8: ("K", "Tech 09 · Woodchip Biomass (_09_CF)"),
    9: ("L", "Tech 10 · LNG-Fired OCGT (_10_CF)"),
    10: ("M", "Tech 11 · Solar DG Residential (_11_CF)"),
    11: ("N", "Tech 12 · Solar DG Commercial (_12_CF)"),
}

# Row numbers 5..40 on General -> Parameter business label
GENERAL_ROW_LABELS: dict[int, str] = {
    8: "Installed Capacity (MW)",
    9: "Net Capacity (MW)",
    10: "General Losses (%)",
    11: "Base Capital Cost (R$/kW)",
    12: "Lower Capital Cost (R$/kW)",
    13: "Upper Capital Cost (R$/kW)",
    14: "Construction Lead Time (yrs)",
    15: "Plant Economic Life (yrs)",
    16: "Capacity Factor (%)",
    17: "Heat Rate",
    18: "Availability (MWmed)",
    19: "Fuel Cost (Primary)",
    20: "Fuel Cost (R$/MMBtu)",
    23: "Fixed O&M Cost (R$/kW-yr)",
    24: "Variable O&M Cost (R$/MWh)",
    25: "Operation Insurance (% yr)",
    26: "Warranty Insurance (% yr)",
    27: "Transmission Cost (R$/kWh·mo)",
    28: "Administration Cost (%)",
    29: "Land / Rental Cost",
    30: "Water Cost (US$/MWh)",
    32: "Equity Share (%)",
    33: "Debt Share (%)",
    34: "Interest Rate / WACC (%)",
    35: "Credit Period (yrs)",
    36: "Target IRR (%)",
    38: "Income Tax (%)",
    39: "Projected Inflation (%)",
    40: "Exchange Rate (R$/US$)",
}

# Macro button metadata: (Button Label, Button Cell on General, Engine Component, Solver Action Summary)
MACRO_METADATA: dict[str, tuple[str, str, str, str]] = {
    "lcoe_exec": (
        "Forecast LCOE",
        "General!B43",
        "_01_CF .. _10_CF (23-Year Multi-Tech Horizon)",
        "Executed 184 binary-search LCOE solves (2024–2046) & Thermal ICB dispatch",
    ),
    "lcoe_forecast": (
        "LCOE Forecast (Single Year)",
        "General!B43",
        "_01_CF .. _10_CF Cashflow Engines",
        "Executed 8-technology binary-search LCOE tariff convergence",
    ),
    "fator_i": (
        "Thermal ICB Dispatch (fator_i)",
        "CVU_GF!C8",
        "CVU_GF Merit-Order Dispatch",
        "Solved non-linear Thermal ICB capacity factor & CVU merit-order loop",
    ),
    "calculo_cvu2bi": (
        "BI LCOE (Biomass 2D)",
        "General!D48",
        "_02_CF (Sugarcane Biomass 2D Matrix)",
        "Solved 2D Capex × Fuel Cost LCOE sensitivity surface (45 solves)",
    ),
    "calculo_cvu4bi": (
        "BI LCOE (Wind 2D)",
        "General!F48",
        "_04_CF (Onshore Wind 2D Matrix)",
        "Solved 2D Capex × Capacity Factor LCOE sensitivity surface (30 solves)",
    ),
    "calculo_capexvscf": (
        "Capex vs IRR (Solar 1D)",
        "General!G48",
        "_05_CF (Utility Solar PV 1D Sweep)",
        "Solved 1D Capex vs. IRR / LCOE sensitivity vector (5 solves)",
    ),
    "calculo_priceirr": (
        "Price vs IRR (Hydro 1D)",
        "General!H48",
        "_06_CF (Small Hydro SHP 1D Sweep)",
        "Solved 1D Power Price vs. Project IRR sensitivity vector (5 solves)",
    ),
    "calculo_capexvscfbi": (
        "BI LCOE (Solar 2D)",
        "General!G52",
        "_05_CF (Utility Solar PV 2D Matrix)",
        "Solved 2D Capex × Capacity Factor LCOE sensitivity surface (30 solves)",
    ),
    "calculo_priceirr_bi": (
        "BI LCOE (Hydro 2D)",
        "General!H52",
        "_06_CF (Small Hydro SHP 2D Matrix)",
        "Solved 2D Capex × Capacity Factor LCOE sensitivity surface (30 solves)",
    ),
}

for _i in range(1, 13):
    _col_letter, _tech_desc = GENERAL_TECH_COLUMNS[_i - 1]
    _solves = 12 if _i >= 11 else 21
    MACRO_METADATA[f"calcule_tir{_i}"] = (
        f"Tornado {_i}",
        f"General!{_col_letter}42",
        f"_{_i:02d}_CF ({_tech_desc})",
        f"Executed 2-Stage Discrete Lattice Binary Search IRR ({_solves} sensitivity solves)",
    )
    _cvu_solves = 1 if _i >= 11 else 10
    MACRO_METADATA[f"calculo_cvu{_i}"] = (
        f"Fuel/CVU{_i}",
        f"General!{_col_letter}45",
        f"_{_i:02d}_CF ({_tech_desc})",
        f"Executed 1D Fuel / CVU LCOE sweep ({_cvu_solves} binary-search solves)",
    )


def _format_val(val: Any) -> str:
    if val is None or val == "":
        return "∅"
    if isinstance(val, float):
        if abs(val) < 1.0 and val != 0.0:
            return f"{val:.4f}"
        if abs(val - round(val)) < 1e-6:
            return f"{round(val):,}"
        return f"{val:,.2f}"
    if isinstance(val, int):
        return f"{val:,}"
    return str(val)


def _count_range_cells(values_2d: list[list[Any]]) -> int:
    return sum(len(row) for row in values_2d)


class ExecutionTelemetryTracker:
    """Thread-safe ring buffer recording Cloud Execution Units and step-by-step trails."""

    def __init__(self, max_units: int = 80) -> None:
        self._lock = threading.Lock()
        self._units: deque[ExecutionUnit] = deque(maxlen=max_units)
        self._seq_counter: int = 0
        # Per-spreadsheet last-seen General!C5:N40 and LT curves so consecutive runs diff cleanly
        self._last_general_by_sheet: dict[str, list[list[Any]]] = {}
        self._last_lt_by_sheet: dict[str, dict[str, list[list[Any]]]] = {}
        # Active workbook context for attributing Connected Sheets BQML jobs
        self._active_workbook_id: str = "FHM Copy of Brazil_TT_v13_RJEB_Gcloud"
        self._active_spreadsheet_id: str = "11qpwhT85btyy_U2xEgxzJm4W4PcTL6YvJiNOUCgD4HU"
        # BigQuery INFORMATION_SCHEMA Connected Sheets job tracking
        self._seen_bq_job_ids: set[str] = set()
        self._bq_sync_watermark_utc: datetime = datetime.now(UTC) - timedelta(hours=12)
        self._last_bq_poll_mono: float = 0.0

    def _resequence_units_locked(self) -> None:
        """Sort units newest-first by completed_at_utc and assign chronological unit_seq (1..N)."""
        sorted_asc = sorted(
            self._units,
            key=lambda u: u.completed_at_utc,
        )
        for idx, u in enumerate(sorted_asc, start=1):
            u.unit_seq = idx
        self._seq_counter = len(sorted_asc)
        self._units.clear()
        for u in reversed(sorted_asc):
            self._units.append(u)

    def _extract_input_change_steps(
        self,
        spreadsheet_id: str,
        workbook_name: str,
        general_overrides: GeneralOverrides | None,
        sheet_inputs: dict[str, dict[str, Any]],
        base_ts: datetime,
    ) -> tuple[list[TelemetryStep], int]:
        """
        Compare incoming General!C5:N40 and LT curves against:
        - Initial Unit #1 for this spreadsheet_id: the Golden Copy baseline (Brazil_TT_v13_RJEB_Gcloud)
        - Every subsequent Unit #2, #3, ...: the snapshot of this local copy at the end of the previous unit.
        Then save the current local copy's snapshot as the baseline for the next unit.
        """
        steps: list[TelemetryStep] = []
        base_ctx = get_baseline_solver_context()
        golden_gen = base_ctx.general_c5_n40
        prior_gen = self._last_general_by_sheet.get(spreadsheet_id, golden_gen)

        newly_changed_descriptions: list[tuple[str, str]] = []

        if general_overrides and general_overrides.general_c5_n40:
            new_gen = general_overrides.general_c5_n40
            for r_idx, row in enumerate(new_gen):
                excel_row = 5 + r_idx
                row_label = GENERAL_ROW_LABELS.get(excel_row, f"Row {excel_row} Parameter")
                for c_idx, new_val in enumerate(row):
                    if c_idx not in GENERAL_TECH_COLUMNS:
                        continue
                    col_letter, tech_label = GENERAL_TECH_COLUMNS[c_idx]
                    coord = f"{col_letter}{excel_row}"
                    prior_val = (
                        prior_gen[r_idx][c_idx]
                        if r_idx < len(prior_gen) and c_idx < len(prior_gen[r_idx])
                        else None
                    )
                    if cells_differ(new_val, prior_val):
                        newly_changed_descriptions.append(
                            (
                                "General tab",
                                f"{coord} ({tech_label} · {row_label}) change to {_format_val(new_val)} (from {_format_val(prior_val)})",
                            )
                        )
            # Save the local copy's current snapshot at the end of this unit for the next unit
            self._last_general_by_sheet[spreadsheet_id] = copy.deepcopy(new_gen)

        # Also inspect LT Capex / LT Fuel / LT CF curve edits against the previous unit's snapshot
        if general_overrides:
            prior_lt_map = self._last_lt_by_sheet.setdefault(
                spreadsheet_id,
                {
                    "LT Capex tab": base_ctx.lt_capex_b8_j30,
                    "LT Fuel tab": base_ctx.lt_fuel_b8_j30,
                    "LT CF tab": base_ctx.lt_cf_b8_j30,
                },
            )
            lt_grids = [
                ("LT Capex tab", general_overrides.lt_capex_b8_j30),
                ("LT Fuel tab", general_overrides.lt_fuel_b8_j30),
                ("LT CF tab", general_overrides.lt_cf_b8_j30),
            ]
            for tab_label, grid in lt_grids:
                if not grid:
                    continue
                prior_grid = prior_lt_map.get(tab_label, [])
                changed_coords: list[str] = []
                for r_i, r_vals in enumerate(grid):
                    for c_i, val in enumerate(r_vals):
                        p_val = (
                            prior_grid[r_i][c_i]
                            if r_i < len(prior_grid) and c_i < len(prior_grid[r_i])
                            else None
                        )
                        if cells_differ(val, p_val):
                            col_l = chr(ord("B") + c_i)
                            changed_coords.append(f"{col_l}{8 + r_i}→{_format_val(val)}")
                if changed_coords:
                    preview = ", ".join(changed_coords[:4])
                    if len(changed_coords) > 4:
                        preview += f" (+{len(changed_coords) - 4} more)"
                    newly_changed_descriptions.append(
                        (
                            tab_label,
                            f"23-Year trajectory cells updated: {preview}",
                        )
                    )
                prior_lt_map[tab_label] = copy.deepcopy(grid)

        # Inspect direct sheet_inputs overrides
        for sname, sdict in sheet_inputs.items():
            for coord, val in sdict.items():
                newly_changed_descriptions.append(
                    (f"{sname} tab", f"{coord} change to {_format_val(val)}")
                )

        cursor_ts = base_ts
        for idx, (comp, action_text) in enumerate(newly_changed_descriptions[:8], start=1):
            step_end = cursor_ts + timedelta(milliseconds=6)
            steps.append(
                TelemetryStep(
                    step_index=idx,
                    system="Google Sheets",
                    artifact=workbook_name,
                    component=comp,
                    action=action_text,
                    started_at_utc=cursor_ts.isoformat(),
                    completed_at_utc=step_end.isoformat(),
                    duration_ms=6.0,
                    status=TelemetryStepStatus.SUCCESS,
                )
            )
            cursor_ts = step_end

        return steps, len(newly_changed_descriptions)

    def record_macro_solve(
        self,
        request: SolveMacroRequest,
        response: SolveMacroResponse,
        gateway_overhead_ms: float = 3.2,
        override_completed_at_utc: datetime | None = None,
    ) -> ExecutionUnit:
        """Build and append a grouped ExecutionUnit for a quantitative macro execution."""
        with self._lock:
            self._seq_counter += 1
            unit_seq = self._seq_counter

            macro_name = request.macro_name.strip()
            btn_label, btn_coord, engine_comp, solver_desc = MACRO_METADATA.get(
                macro_name,
                (
                    macro_name,
                    "General!B42:N52",
                    "WorkbookSolverContext",
                    f"Executed quantitative routine {macro_name}",
                ),
            )
            workbook_name = request.workbook_id or "Regional Power Generation Techno-Economic Model"
            if request.workbook_id and request.workbook_id != "Regional Power Generation Techno-Economic Model":
                self._active_workbook_id = request.workbook_id
            if request.spreadsheet_id and request.spreadsheet_id != "local-seed-spreadsheet-id":
                self._active_spreadsheet_id = request.spreadsheet_id

            now_utc = override_completed_at_utc or datetime.now(UTC)
            solve_ms = round(max(float(response.execution_time_ms), 1.0), 2)
            dispatch_ms = 18.0
            writeback_ms = 24.0 if response.cell_updates else 4.0
            total_before_ms = solve_ms + gateway_overhead_ms + dispatch_ms + writeback_ms
            start_utc = now_utc - timedelta(milliseconds=total_before_ms + 20)

            steps, input_change_count = self._extract_input_change_steps(
                spreadsheet_id=request.spreadsheet_id,
                workbook_name=workbook_name,
                general_overrides=request.general_overrides,
                sheet_inputs=request.sheet_inputs,
                base_ts=start_utc,
            )

            cursor = (
                datetime.fromisoformat(steps[-1].completed_at_utc)
                if steps
                else start_utc
            )

            # Step: Apps Script button trigger & batch range capture
            gas_end = cursor + timedelta(milliseconds=dispatch_ms)
            steps.append(
                TelemetryStep(
                    step_index=len(steps) + 1,
                    system="Apps Script",
                    artifact=workbook_name,
                    component=f"{btn_coord} ({btn_label})",
                    action=f"Button '{btn_label}' clicked → captured General!C5:N40 & LT curves, invoked /v1/solve/{macro_name}",
                    started_at_utc=cursor.isoformat(),
                    completed_at_utc=gas_end.isoformat(),
                    duration_ms=dispatch_ms,
                    status=TelemetryStepStatus.SUCCESS,
                )
            )
            cursor = gas_end

            # Step: Cloud Run Gateway request validation & context hydration
            cr_end = cursor + timedelta(milliseconds=gateway_overhead_ms)
            steps.append(
                TelemetryStep(
                    step_index=len(steps) + 1,
                    system="Cloud Run",
                    artifact="sheets-commodity-mod-gateway",
                    component=f"POST /v1/solve/{macro_name}",
                    action="Authenticated OIDC caller & hydrated isolated WorkbookSolverContext",
                    started_at_utc=cursor.isoformat(),
                    completed_at_utc=cr_end.isoformat(),
                    duration_ms=round(gateway_overhead_ms, 2),
                    status=TelemetryStepStatus.SUCCESS,
                )
            )
            cursor = cr_end

            # Step: Quantitative Solver Engine execution
            solver_end = cursor + timedelta(milliseconds=solve_ms)
            steps.append(
                TelemetryStep(
                    step_index=len(steps) + 1,
                    system="Solver Engine",
                    artifact="MacroExecutionRegistry",
                    component=engine_comp,
                    action=f"{solver_desc} ({response.solve_count} solves)",
                    started_at_utc=cursor.isoformat(),
                    completed_at_utc=solver_end.isoformat(),
                    duration_ms=solve_ms,
                    status=TelemetryStepStatus.SUCCESS,
                )
            )
            cursor = solver_end

            # Step(s): Output range write-back to Google Sheets
            target_ranges: list[str] = []
            if response.cell_updates:
                per_update_ms = round(writeback_ms / len(response.cell_updates), 2)
                for upd in response.cell_updates:
                    upd_end = cursor + timedelta(milliseconds=per_update_ms)
                    cell_cnt = _count_range_cells(upd.values)
                    full_rng = f"{upd.sheet}!{upd.range}"
                    target_ranges.append(full_rng)
                    extra_note = ""
                    if upd.sheet.startswith("_") and upd.sheet.endswith("_CF") and upd.range.startswith("E6:G"):
                        extra_note = " → live-linked to Tornado tab sensitivity table"
                    elif upd.sheet in ("Output_3", "Output3"):
                        extra_note = " → 23-year LCOE forecast table (2024–2046) updated"
                    steps.append(
                        TelemetryStep(
                            step_index=len(steps) + 1,
                            system="Google Sheets",
                            artifact=workbook_name,
                            component=f"{upd.sheet} tab",
                            action=f"Wrote {full_rng} ({cell_cnt} cells updated){extra_note}",
                            started_at_utc=cursor.isoformat(),
                            completed_at_utc=upd_end.isoformat(),
                            duration_ms=per_update_ms,
                            status=TelemetryStepStatus.SUCCESS,
                        )
                    )
                    cursor = upd_end

            total_ms = round(sum(s.duration_ms for s in steps), 2)
            unit = ExecutionUnit(
                unit_id=f"unit-{unit_seq:04d}-{uuid.uuid4().hex[:6]}",
                unit_seq=unit_seq,
                unit_type="macro_solve",
                macro_name=macro_name,
                display_title=f"{btn_label} ({macro_name})",
                button_label=btn_label,
                workbook_id=workbook_name,
                spreadsheet_id=request.spreadsheet_id,
                triggered_by=request.caller_google_user,
                started_at_utc=steps[0].started_at_utc,
                completed_at_utc=steps[-1].completed_at_utc,
                total_duration_ms=total_ms,
                status=TelemetryStepStatus.SUCCESS,
                solve_count=response.solve_count,
                input_change_count=input_change_count,
                target_ranges=target_ranges,
                steps=steps,
            )
            self._units.appendleft(unit)
            self._resequence_units_locked()
            return unit

    def record_connected_sheets_bqml_refresh(
        self,
        job_id: str,
        user_email: str,
        started_at_utc: datetime,
        completed_at_utc: datetime,
        duration_ms: float,
        trigger_source: str = "apps-script",
        view_type: str = "lt_forecasts",
        workbook_id: str | None = None,
        spreadsheet_id: str | None = None,
        active_tab: str | None = None,
    ) -> ExecutionUnit | None:
        """
        Record a Connected Sheets BigQuery ML Refresh execution unit (`refreshBqmlForecasts`
        or native Connected Sheets refresh on `vw_connected_sheets_lt_forecasts` / `vw_bqml_lcoe_surrogate_predictions`).
        Deduplicates by `job_id` or overlapping timestamp window.
        """
        with self._lock:
            if job_id in self._seen_bq_job_ids:
                return None
            # Also check if a bqml_refresh unit was already recorded within 8 seconds of this timestamp
            for existing in self._units:
                if existing.unit_type == "bqml_refresh":
                    try:
                        ex_start = datetime.fromisoformat(existing.started_at_utc)
                        if abs((started_at_utc - ex_start).total_seconds()) < 8.0 and existing.macro_name in (
                            "refreshBqmlForecasts",
                            "refreshBqmlSurrogate",
                        ):
                            self._seen_bq_job_ids.add(job_id)
                            return None
                    except ValueError:
                        pass

            self._seen_bq_job_ids.add(job_id)
            wb_name = workbook_id or self._active_workbook_id or "Brazil_TT_v13_RJEB_Gcloud"
            ss_id = spreadsheet_id or self._active_spreadsheet_id or "1apbos5xVpK4yBLiRFxQqAEyPVNkkYQ2ZvgAASibYYJI"

            bq_ms = round(max(float(duration_ms), 25.0), 1)
            trigger_ms = 14.0
            connector_ms = 18.0
            sync_ms = 22.0

            t0 = started_at_utc - timedelta(milliseconds=trigger_ms + connector_ms)
            t1 = t0 + timedelta(milliseconds=trigger_ms)
            t2 = t1 + timedelta(milliseconds=connector_ms)
            t3 = t2 + timedelta(milliseconds=bq_ms)
            t4 = max(completed_at_utc, t3 + timedelta(milliseconds=sync_ms))

            short_job = job_id.replace("sheets_dataconnector_", "")[:8]
            if view_type == "surrogate":
                macro_name = "refreshBqmlSurrogate"
                display_title = "Refresh BQML Surrogate (Linear Reg LCOE)"
                button_label = "Refresh BQML"
                solve_count = 72
                target_ranges = ["BQML_LCOE_Surrogate!A1:I73"]
                steps = [
                    TelemetryStep(
                        step_index=1,
                        system="Google Sheets",
                        artifact=wb_name,
                        component="BQML_LCOE_Surrogate tab",
                        action="Triggered Connected Sheets refresh on BQML_LCOE_Surrogate",
                        started_at_utc=t0.isoformat(),
                        completed_at_utc=t1.isoformat(),
                        duration_ms=trigger_ms,
                        status=TelemetryStepStatus.SUCCESS,
                    ),
                    TelemetryStep(
                        step_index=2,
                        system="BigQuery",
                        artifact="comm-model-mod",
                        component=f"BQ Job #{short_job}",
                        action="Connected Sheets queried vw_bqml_lcoe_surrogate_predictions (BigQuery us-central1)",
                        started_at_utc=t1.isoformat(),
                        completed_at_utc=t2.isoformat(),
                        duration_ms=connector_ms,
                        status=TelemetryStepStatus.SUCCESS,
                    ),
                    TelemetryStep(
                        step_index=3,
                        system="Solver Engine",
                        artifact="Vertex AI / BigQuery ML",
                        component="ML.PREDICT (Linear Reg)",
                        action="Evaluated LCOE Linear Regression surrogate predictions vs. exact binary-search solver (72 scenarios)",
                        started_at_utc=t2.isoformat(),
                        completed_at_utc=t3.isoformat(),
                        duration_ms=bq_ms,
                        status=TelemetryStepStatus.SUCCESS,
                    ),
                    TelemetryStep(
                        step_index=4,
                        system="Google Sheets",
                        artifact=wb_name,
                        component="BQML_LCOE_Surrogate tab",
                        action="Synced 72 surrogate prediction rows & residuals into BQML_LCOE_Surrogate",
                        started_at_utc=t3.isoformat(),
                        completed_at_utc=t4.isoformat(),
                        duration_ms=sync_ms,
                        status=TelemetryStepStatus.SUCCESS,
                    ),
                ]
            else:
                macro_name = "refreshBqmlForecasts"
                display_title = "Refresh BQML (ARIMA_PLUS 2026–2040)"
                button_label = "Refresh BQML"
                solve_count = 33
                target_ranges = ["LT_*_BQML!A8:M30 (3 tabs)"]
                tab_comp = active_tab if (active_tab and "/" not in active_tab) else "LT_*_BQML"
                first_sys = "Apps Script" if trigger_source == "apps-script" else "Google Sheets"
                first_action = (
                    "Button 'Refresh BQML' clicked → invoked forceRefreshData() on BQML_LT_Forecasts"
                    if trigger_source == "apps-script"
                    else "Triggered Connected Sheets refresh on BQML_LT_Forecasts extract"
                )
                steps = [
                    TelemetryStep(
                        step_index=1,
                        system=first_sys,
                        artifact=wb_name,
                        component=f"{tab_comp} (Refresh BQML)",
                        action=first_action,
                        started_at_utc=t0.isoformat(),
                        completed_at_utc=t1.isoformat(),
                        duration_ms=trigger_ms,
                        status=TelemetryStepStatus.SUCCESS,
                    ),
                    TelemetryStep(
                        step_index=2,
                        system="BigQuery",
                        artifact="comm-model-mod",
                        component=f"BQ Job #{short_job}",
                        action="Connected Sheets queried vw_connected_sheets_lt_forecasts (BigQuery us-central1)",
                        started_at_utc=t1.isoformat(),
                        completed_at_utc=t2.isoformat(),
                        duration_ms=connector_ms,
                        status=TelemetryStepStatus.SUCCESS,
                    ),
                    TelemetryStep(
                        step_index=3,
                        system="Solver Engine",
                        artifact="BigQuery ML (ARIMA_PLUS)",
                        component="ML.FORECAST (2026–2040)",
                        action="Evaluated 15-year ARIMA_PLUS trajectories (2026–2040, 95% CI) across 11 technologies × 3 curves (33 series)",
                        started_at_utc=t2.isoformat(),
                        completed_at_utc=t3.isoformat(),
                        duration_ms=bq_ms,
                        status=TelemetryStepStatus.SUCCESS,
                    ),
                    TelemetryStep(
                        step_index=4,
                        system="Google Sheets",
                        artifact=wb_name,
                        component="LT_Capex / Fuel / CF_BQML",
                        action="Synced 69 trajectory rows into BQML_LT_Forecasts → live =FILTER() updated LT_Capex_BQML, LT_Fuel_BQML & LT_CF_BQML",
                        started_at_utc=t3.isoformat(),
                        completed_at_utc=t4.isoformat(),
                        duration_ms=sync_ms,
                        status=TelemetryStepStatus.SUCCESS,
                    ),
                ]

            self._seq_counter += 1
            unit_seq = self._seq_counter
            total_ms = round(sum(s.duration_ms for s in steps), 2)
            unit = ExecutionUnit(
                unit_id=f"unit-{unit_seq:04d}-{uuid.uuid4().hex[:6]}",
                unit_seq=unit_seq,
                unit_type="bqml_refresh",
                macro_name=macro_name,
                display_title=display_title,
                button_label=button_label,
                workbook_id=wb_name,
                spreadsheet_id=ss_id,
                triggered_by=user_email or "admin@ferozmulla.altostrat.com",
                started_at_utc=steps[0].started_at_utc,
                completed_at_utc=steps[-1].completed_at_utc,
                total_duration_ms=total_ms,
                status=TelemetryStepStatus.SUCCESS,
                solve_count=solve_count,
                input_change_count=0,
                target_ranges=target_ranges,
                steps=steps,
            )
            self._units.appendleft(unit)
            self._resequence_units_locked()
            return unit

    def sync_bigquery_connected_sheets_jobs(self, force: bool = False) -> int:
        """
        Poll BigQuery `region-us-central1.INFORMATION_SCHEMA.JOBS_BY_PROJECT` (cached every 3.5s)
        for Connected Sheets BQML refreshes (`sheets_dataconnector_*`) that execute directly
        between Google Sheets and BigQuery without hitting the Cloud Run gateway.
        """
        if os.environ.get("PYTEST_CURRENT_TEST") and not force:
            return 0
        now_mono = time.monotonic()
        if not force and (now_mono - self._last_bq_poll_mono) < 3.5:
            return 0
        self._last_bq_poll_mono = now_mono

        try:
            from google.cloud import bigquery

            settings = get_settings()
            client = bigquery.Client(project=settings.gcp_project_id)
            watermark_iso = self._bq_sync_watermark_utc.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            query = f"""
            SELECT
              job_id,
              user_email,
              creation_time,
              start_time,
              end_time,
              TIMESTAMP_DIFF(end_time, COALESCE(start_time, creation_time), MILLISECOND) AS duration_ms,
              labels,
              query
            FROM `{settings.gcp_project_id}`.`region-{settings.bq_location}`.INFORMATION_SCHEMA.JOBS_BY_PROJECT
            WHERE creation_time >= TIMESTAMP('{watermark_iso}')
              AND state = 'DONE'
              AND error_result IS NULL
              AND job_id LIKE 'sheets_dataconnector_%'
              AND (
                LOWER(query) LIKE '%vw_connected_sheets_lt_forecasts%'
                OR LOWER(query) LIKE '%vw_bqml_lcoe_surrogate_predictions%'
                OR LOWER(query) LIKE '%curve_sheet%'
                OR LOWER(query) LIKE '%bqml_predicted_lcoe%'
              )
            ORDER BY creation_time ASC
            LIMIT 25
            """
            rows = list(client.query(query).result(timeout=4.0))
            ingested = 0
            for r in rows:
                job_id = str(r["job_id"])
                user_email = str(r["user_email"] or "admin@ferozmulla.altostrat.com")
                c_time: datetime = r["start_time"] or r["creation_time"] or datetime.now(UTC)
                e_time: datetime = r["end_time"] or (c_time + timedelta(milliseconds=250))
                if c_time.tzinfo is None:
                    c_time = c_time.replace(tzinfo=UTC)
                if e_time.tzinfo is None:
                    e_time = e_time.replace(tzinfo=UTC)
                dur_ms = float(r["duration_ms"] or 180.0)
                labels = r["labels"] or []
                trigger_src = "apps-script"
                for lbl in labels:
                    if isinstance(lbl, dict) and lbl.get("key") == "sheets_trigger":
                        trigger_src = str(lbl.get("value") or "apps-script")
                q_lower = str(r["query"] or "").lower()
                v_type = (
                    "surrogate"
                    if ("vw_bqml_lcoe_surrogate_predictions" in q_lower or "bqml_predicted_lcoe" in q_lower)
                    else "lt_forecasts"
                )
                unit = self.record_connected_sheets_bqml_refresh(
                    job_id=job_id,
                    user_email=user_email,
                    started_at_utc=c_time,
                    completed_at_utc=e_time,
                    duration_ms=dur_ms,
                    trigger_source=trigger_src,
                    view_type=v_type,
                )
                if unit is not None:
                    ingested += 1
            return ingested
        except Exception:  # noqa: BLE001
            return 0

    def record_bqml_solve(
        self,
        request: BQMLRemoteFunctionRequest,
        response: BQMLRemoteFunctionResponse,
        elapsed_ms: float,
    ) -> ExecutionUnit:
        """Record a BigQuery ML / Remote Function (`fn_solve_lcoe`) execution unit."""
        with self._lock:
            self._seq_counter += 1
            unit_seq = self._seq_counter
            now_utc = datetime.now(UTC)
            call_count = len(request.calls)
            solve_ms = round(max(elapsed_ms, 2.0), 2)
            start_utc = now_utc - timedelta(milliseconds=solve_ms + 30.0)

            s1_end = start_utc + timedelta(milliseconds=12.0)
            s2_end = s1_end + timedelta(milliseconds=solve_ms)
            s3_end = s2_end + timedelta(milliseconds=15.0)

            status = (
                TelemetryStepStatus.FAILED
                if response.errorMessage
                else TelemetryStepStatus.SUCCESS
            )

            steps = [
                TelemetryStep(
                    step_index=1,
                    system="BigQuery",
                    artifact="commodity_mod_governance",
                    component="Remote Function fn_solve_lcoe",
                    action=f"Dispatched {call_count} vectorized BQML forecast batch row(s) to Cloud Run",
                    started_at_utc=start_utc.isoformat(),
                    completed_at_utc=s1_end.isoformat(),
                    duration_ms=12.0,
                    status=TelemetryStepStatus.SUCCESS,
                ),
                TelemetryStep(
                    step_index=2,
                    system="Solver Engine",
                    artifact="sheets-commodity-mod-gateway",
                    component="POST /v1/bqml/solve",
                    action=f"Evaluated LCOE & IRR surrogate across {call_count} ARIMA_PLUS trajectory row(s)",
                    started_at_utc=s1_end.isoformat(),
                    completed_at_utc=s2_end.isoformat(),
                    duration_ms=solve_ms,
                    status=status,
                ),
                TelemetryStep(
                    step_index=3,
                    system="Google Sheets",
                    artifact="Brazil_TT_v13_RJEB_Gcloud",
                    component="Connected Sheets (LT Capex / LT Fuel / LT CF)",
                    action=f"Returned {len(response.replies)} forecast series payload(s) to Connected Sheets",
                    started_at_utc=s2_end.isoformat(),
                    completed_at_utc=s3_end.isoformat(),
                    duration_ms=15.0,
                    status=status,
                ),
            ]
            total_ms = round(sum(s.duration_ms for s in steps), 2)
            unit = ExecutionUnit(
                unit_id=f"unit-{unit_seq:04d}-{uuid.uuid4().hex[:6]}",
                unit_seq=unit_seq,
                unit_type="bqml_refresh",
                macro_name="bqml_forecast_refresh",
                display_title="BQML Connected Sheets Refresh (fn_solve_lcoe)",
                button_label="Refresh BQML",
                workbook_id=self._active_workbook_id or "Brazil_TT_v13_RJEB_Gcloud",
                spreadsheet_id=self._active_spreadsheet_id or "1apbos5xVpK4yBLiRFxQqAEyPVNkkYQ2ZvgAASibYYJI",
                triggered_by=request.sessionUser or request.caller or "bigquery-dts@comm-model-mod",
                started_at_utc=steps[0].started_at_utc,
                completed_at_utc=steps[-1].completed_at_utc,
                total_duration_ms=total_ms,
                status=status,
                solve_count=call_count,
                input_change_count=0,
                target_ranges=["LT Capex!B8:J30", "LT Fuel!B8:J30", "LT CF!B8:J30"],
                steps=steps,
            )
            self._units.appendleft(unit)
            self._resequence_units_locked()
            return unit

    def list_units(
        self,
        unit_type: str | None = None,
        status: str | None = None,
    ) -> TelemetryFeedResponse:
        """Return filtered list of ExecutionUnits ordered newest-first."""
        self.sync_bigquery_connected_sheets_jobs()
        with self._lock:
            items = list(self._units)
            latest_seq = self._seq_counter

        if unit_type and unit_type != "all":
            items = [u for u in items if u.unit_type == unit_type]
        if status and status != "all":
            items = [u for u in items if u.status == status]

        avg_ms = (
            round(sum(u.total_duration_ms for u in items) / len(items), 2)
            if items
            else 0.0
        )
        return TelemetryFeedResponse(
            total_units=len(items),
            latest_unit_seq=latest_seq,
            avg_duration_ms=avg_ms,
            units=items,
        )

    def clear(self, preserve_sheet_snapshots: bool = True) -> None:
        """
        Clear the displayed execution units.
        When preserve_sheet_snapshots=True (default for UI 'Clear Trail'), each local copy's
        last-known General/LT snapshot is retained so the next unit still diffs against
        the state at the end of the previous unit rather than reverting to the initial seed.
        """
        with self._lock:
            self._units.clear()
            self._seq_counter = 0
            self._bq_sync_watermark_utc = datetime.now(UTC)
            if not preserve_sheet_snapshots:
                self._last_general_by_sheet.clear()
                self._last_lt_by_sheet.clear()


telemetry_tracker = ExecutionTelemetryTracker()
