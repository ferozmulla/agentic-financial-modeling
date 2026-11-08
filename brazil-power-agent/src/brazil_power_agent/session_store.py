"""Stateful 22-Tab Scenario Session Manager for the Brazil Energy Model (v13) Gemini Agent."""

from __future__ import annotations

import copy
import json
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
V13_ROOT = WORKSPACE_ROOT / "brazil-power-v13"
AGENT_SRC_ROOT = Path(__file__).resolve().parents[1]

for _p in (str(AGENT_SRC_ROOT), str(V13_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from src.bqml.surrogate_trainer import BQMLConnectedSheetsEngine
from src.cli.extract_baseline_fixtures import (
    col_letter_to_index,
    index_to_col_letter,
    parse_workbook_xml,
    split_coord,
)
from src.schemas.solver import GeneralOverrides, SolveMacroRequest
from src.solver.cashflow_model import VectorizedCashFlowEngine, compute_spreadsheet_irr
from src.solver.convergence import StrictLegacyVBAEmulator
from src.solver.macros.registry import MacroExecutionRegistry
from src.solver.workbook_context import WorkbookSolverContext, get_baseline_solver_context

from brazil_power_agent.excel_renderer import (
     ExcelLayoutRenderer,
    GENERAL_ROW_BY_NUM,
    OUTPUT3_COLUMNS,
    TECH_SPECS,
)

DEFAULT_SEED_WORKBOOK_PATH = V13_ROOT / "seed" / "2023-11-27-Brazil_TT_v13_RJEB.xlsm"
DEFAULT_SESSION_PATH = Path.home() / ".gemini" / "jetski" / "brazil_power_agent_session.json"

PARAMETER_ALIAS_TO_GENERAL_ROW: dict[str, int] = {
    "capacity": 8,
    "installed_capacity_mw": 8,
    "net_capacity_mw": 9,
    "losses": 10,
    "general_losses": 10,
    "capex": 11,
    "specific_capex": 11,
    "base_capital_cost": 11,
    "capex_r_per_kw": 11,
    "lower_capital_cost": 12,
    "upper_capital_cost": 13,
    "lead_time": 14,
    "lead_time_years": 14,
    "construction_lead_time": 14,
    "economic_life": 15,
    "economic_life_years": 15,
    "plant_economic_life": 15,
    "capacity_factor": 16,
    "cf": 16,
    "heat_rate": 17,
    "availability": 18,
    "fuel_cost": 20,
    "fuel_price": 20,
    "fuel_cost_r_per_mmbtu": 20,
    "fuel_cost_usd_per_mmbtu": 20,
    "fixed_om": 23,
    "fixed_o&m": 23,
    "fixed_om_r_per_kw_yr": 23,
    "variable_om": 24,
    "variable_o&m": 24,
    "variable_om_r_per_mwh": 24,
    "operation_insurance": 25,
    "warranty_insurance": 26,
    "transmission_cost": 27,
    "transmission_tariff": 27,
    "administration_cost": 28,
    "rental": 29,
    "water": 30,
    "equity": 32,
    "equity_share": 32,
    "debt": 33,
    "debt_share": 33,
    "interest_rate": 34,
    "wacc": 34,
    "real_wacc": 34,
    "credit_period": 35,
    "irr": 36,
    "target_irr": 36,
    "income_tax": 38,
    "inflation": 39,
    "exchange_rate": 40,
}

GENERAL_COL_TO_TECH: dict[str, str] = {
    spec["general_col"]: code for code, spec in TECH_SPECS.items()
}


@lru_cache(maxsize=1)
def _cached_parsed_seed_xml(xlsm_path_str: str) -> dict[str, Any]:
    """Parse and cache all 22 worksheets from the seed .xlsm workbook."""
    return parse_workbook_xml(Path(xlsm_path_str))


class SeedWorkbookLoader:
    """Fast cached loader for the 22-tab 2023-11-27-Brazil_TT_v13_RJEB.xlsm seed workbook."""

    def __init__(self, seed_workbook_path: Path | None = None) -> None:
        self.seed_workbook_path = Path(seed_workbook_path or DEFAULT_SEED_WORKBOOK_PATH)

    def load_context(self) -> WorkbookSolverContext:
        """Return pre-warmed baseline WorkbookSolverContext."""
        return get_baseline_solver_context()

    def load_parsed_xml(self) -> dict[str, Any]:
        """Return cached OpenXML dictionary of all 22 sheets and cell maps."""
        return _cached_parsed_seed_xml(str(self.seed_workbook_path))


def normalize_technology_code(tech_code: str) -> str:
    """Normalize '_01_CF', '01_CF', '1', or display names into canonical '_XX_CF' or 'ALL'."""
    cleaned = tech_code.strip().upper()
    if cleaned == "ALL":
        return "ALL"
    if cleaned in TECH_SPECS:
        return cleaned
    if not cleaned.startswith("_") and f"_{cleaned}" in TECH_SPECS:
        return f"_{cleaned}"
    digits = "".join(ch for ch in cleaned if ch.isdigit())
    if digits:
        idx = int(digits)
        if 1 <= idx <= 12:
            return f"_{idx:02d}_CF"
    for code, spec in TECH_SPECS.items():
        if cleaned in (spec["fuel"].upper(), spec["tech"].upper(), spec["display_name"].upper()):
            return code
    raise ValueError(f"Unknown technology code '{tech_code}'. Expected '_01_CF'..'_12_CF' or 'ALL'.")


class BrazilPowerSessionManager:
    """Manages per-session scenario overrides, solver executions, and Excel-layout outputs."""

    def __init__(
        self,
        session_path: Path | str | None = None,
        seed_workbook_path: Path | None = None,
    ) -> None:
        self.session_path = Path(session_path) if session_path is not None else DEFAULT_SESSION_PATH
        self.loader = SeedWorkbookLoader(seed_workbook_path=seed_workbook_path)
        self.seed_workbook_path = self.loader.seed_workbook_path
        self._base_ctx = self.loader.load_context()

        self.cell_overrides: dict[str, float | int | str] = {}
        self.solved_outputs: dict[str, float | int | str] = {}
        self.cell_range_updates: list[dict[str, Any]] = []
        self.override_history: list[dict[str, Any]] = []
        self.last_runs: dict[str, Any] = {}

        if self.session_path.exists():
            self._load_state()
        else:
            self._save_state()

    def _load_state(self) -> None:
        """Load persisted session JSON if present."""
        try:
            raw = json.loads(self.session_path.read_text(encoding="utf-8"))
            self.cell_overrides = dict(raw.get("cell_overrides", {}))
            self.solved_outputs = dict(raw.get("solved_outputs", {}))
            self.cell_range_updates = list(raw.get("cell_range_updates", []))
            self.override_history = list(raw.get("override_history", []))
            self.last_runs = dict(raw.get("last_runs", {}))
        except Exception:
            self.cell_overrides = {}
            self.solved_outputs = {}
            self.cell_range_updates = []
            self.override_history = []
            self.last_runs = {}

    def _save_state(self) -> None:
        """Persist current session state to self.session_path."""
        self.session_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "seed_workbook": str(self.seed_workbook_path),
            "cell_overrides": self.cell_overrides,
            "solved_outputs": self.solved_outputs,
            "cell_range_updates": self.cell_range_updates,
            "override_history": self.override_history,
            "last_runs": self.last_runs,
        }
        self.session_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    @property
    def state(self) -> dict[str, Any]:
        """Return a snapshot dictionary of the active session state."""
        return {
            "seed_workbook": str(self.seed_workbook_path),
            "cell_overrides": dict(self.cell_overrides),
            "solved_outputs": dict(self.solved_outputs),
            "cell_range_updates": list(self.cell_range_updates),
            "override_history": list(self.override_history),
            "last_runs": dict(self.last_runs),
        }

    def get_all_cell_writes(self) -> dict[str, float | int | str]:
        """Return merged map of all solved output cells and user override cells ('Sheet!Coord' -> val)."""
        merged: dict[str, float | int | str] = {}
        merged.update(self.solved_outputs)
        merged.update(self.cell_overrides)
        return merged

    def _build_general_overrides_and_sheet_inputs(
        self,
    ) -> tuple[GeneralOverrides, dict[str, dict[str, Any]], list[list[Any]]]:
        """Translate self.cell_overrides into GeneralOverrides, sheet_inputs, and updated general_c5_n40."""
        gen_grid = copy.deepcopy(self._base_ctx.general_c5_n40)
        lt_capex = copy.deepcopy(self._base_ctx.lt_capex_b8_j30)
        lt_fuel = copy.deepcopy(self._base_ctx.lt_fuel_b8_j30)
        lt_cf = copy.deepcopy(self._base_ctx.lt_cf_b8_j30)
        sheet_inputs: dict[str, dict[str, Any]] = {}

        for full_coord, val in self.cell_overrides.items():
            sheet_name, coord = full_coord.split("!", 1) if "!" in full_coord else ("General", full_coord)
            col_str, row_num = split_coord(coord)
            col_num = col_letter_to_index(col_str)

            if sheet_name == "General":
                r_idx = row_num - 5
                c_idx = col_num - 3  # Col C is index 0
                if 0 <= r_idx < len(gen_grid) and 0 <= c_idx < len(gen_grid[r_idx]):
                    gen_grid[r_idx][c_idx] = val
                    # If row 14 (Construction lead time) or row 8 (Capacity) is edited, also mark sheet_inputs
                    tech_code = GENERAL_COL_TO_TECH.get(col_str)
                    if tech_code and row_num not in WorkbookSolverContext.GENERAL_TO_TORNADO_ROWS.get(tech_code, ()):
                        sheet_inputs.setdefault(tech_code, {})[f"General_{col_str}{row_num}"] = val
            elif sheet_name in ("LT Capex", "LT Fuel", "LT CF"):
                r_idx = row_num - 8
                c_idx = col_num - 2  # Col B is index 0
                target_lt = (
                    lt_capex if sheet_name == "LT Capex" else (lt_fuel if sheet_name == "LT Fuel" else lt_cf)
                )
                if 0 <= r_idx < len(target_lt) and 0 <= c_idx < len(target_lt[r_idx]):
                    target_lt[r_idx][c_idx] = val
            else:
                sheet_inputs.setdefault(sheet_name, {})[coord] = val

        gen_overrides = GeneralOverrides(
            general_c5_n40=gen_grid,
            lt_capex_b8_j30=lt_capex,
            lt_fuel_b8_j30=lt_fuel,
            lt_cf_b8_j30=lt_cf,
        )
        return gen_overrides, sheet_inputs, gen_grid

    def build_active_solver_context(self) -> WorkbookSolverContext:
        """Return an isolated WorkbookSolverContext with all session overrides applied."""
        gen_overrides, sheet_inputs, _ = self._build_general_overrides_and_sheet_inputs()
        return self._base_ctx.clone_with_overrides(
            general_overrides=gen_overrides,
            sheet_inputs=sheet_inputs,
        )

    def _lookup_baseline_cell_value(self, sheet_name: str, coord: str) -> Any:
        """Look up original baseline value in General, LT tabs, or parsed XML."""
        col_str, row_num = split_coord(coord)
        col_num = col_letter_to_index(col_str)
        if sheet_name == "General":
            r_idx = row_num - 5
            c_idx = col_num - 3
            base_gen = self._base_ctx.general_c5_n40
            if 0 <= r_idx < len(base_gen) and 0 <= c_idx < len(base_gen[r_idx]):
                return base_gen[r_idx][c_idx]
        parsed = self.loader.load_parsed_xml()
        return parsed["sheets_data"].get(sheet_name, {}).get(coord, {}).get("value")

    def get_assumptions(
        self,
        technologies: list[str] | None = None,
        include_full_general_tab: bool = True,
    ) -> dict[str, Any]:
        """Return current General!C5:N40 assumptions with inline and full Excel-coordinate Markdown tables."""
        norm_techs = (
            [normalize_technology_code(t) for t in technologies if normalize_technology_code(t) != "ALL"]
            if technologies
            else ["_01_CF", "_04_CF", "_05_CF", "_06_CF"]
        )
        _, _, gen_grid = self._build_general_overrides_and_sheet_inputs()
        base_grid = self._base_ctx.general_c5_n40

        inline_md, full_md = ExcelLayoutRenderer.render_general_assumptions_tables(
            general_grid=gen_grid,
            baseline_grid=base_grid,
            technologies=norm_techs,
            active_overrides=self.cell_overrides,
        )

        params_by_tech: dict[str, dict[str, Any]] = {}
        for tc in norm_techs:
            spec = TECH_SPECS[tc]
            c_idx = spec["general_col_idx"]
            col_let = spec["general_col"]
            t_rows: dict[str, Any] = {}
            for r_num, r_meta in GENERAL_ROW_BY_NUM.items():
                r_idx = r_num - 5
                val = gen_grid[r_idx][c_idx] if 0 <= r_idx < len(gen_grid) else None
                t_rows[f"General!{col_let}{r_num}"] = {
                    "row": r_num,
                    "parameter": r_meta["label"],
                    "unit": r_meta["unit"],
                    "value": val,
                }
            params_by_tech[tc] = t_rows

        return {
            "session_path": str(self.session_path),
            "technologies": norm_techs,
            "modified_count": len(self.cell_overrides),
            "active_overrides": dict(self.cell_overrides),
            "parameters_by_technology": params_by_tech,
            "inline_excel_table_md": inline_md,
            "full_artifact_table_md": full_md if include_full_general_tab else inline_md,
        }

    def update_assumptions(
        self,
        overrides: dict[str, dict[str, float]] | dict[str, float] | None = None,
        reset_to_baseline: bool = False,
    ) -> dict[str, Any]:
        """Stage cell or semantic parameter overrides into the session and return Excel diff table."""
        if reset_to_baseline:
            self.cell_overrides.clear()
            self.solved_outputs.clear()
            self.cell_range_updates.clear()
            self.override_history.clear()

        overrides = overrides or {}
        flat_resolved: dict[str, float | int | str] = {}
        affected_techs: list[str] = []

        for key, val in overrides.items():
            if isinstance(val, dict):
                # Nested form: {"_01_CF": {"fuel_cost_r_per_mmbtu": 6.50, "C20": 6.50}}
                tc = normalize_technology_code(key)
                if tc not in affected_techs:
                    affected_techs.append(tc)
                col_let = TECH_SPECS[tc]["general_col"]
                for sub_key, sub_val in val.items():
                    sk_clean = sub_key.strip()
                    if "!" in sk_clean:
                        flat_resolved[sk_clean] = sub_val
                    elif sk_clean.lower() in PARAMETER_ALIAS_TO_GENERAL_ROW:
                        r_num = PARAMETER_ALIAS_TO_GENERAL_ROW[sk_clean.lower()]
                        flat_resolved[f"General!{col_let}{r_num}"] = sub_val
                    elif sk_clean[0].isalpha() and sk_clean[1:].isdigit():
                        flat_resolved[f"General!{sk_clean.upper()}"] = sub_val
                    else:
                        raise ValueError(f"Unrecognized parameter override key '{sub_key}' for {tc}.")
            else:
                # Direct cell coordinate form: {"General!C20": 6.50, "General!H14": 2.0}
                k_clean = key.strip()
                full_coord = k_clean if "!" in k_clean else f"General!{k_clean.upper()}"
                flat_resolved[full_coord] = val
                s_name, c_part = full_coord.split("!", 1)
                c_let, _ = split_coord(c_part)
                if s_name == "General" and c_let in GENERAL_COL_TO_TECH:
                    tc = GENERAL_COL_TO_TECH[c_let]
                    if tc not in affected_techs:
                        affected_techs.append(tc)

        changes: list[dict[str, Any]] = []
        for full_coord, new_val in flat_resolved.items():
            s_name, coord = full_coord.split("!", 1)
            col_let, row_num = split_coord(coord)
            base_val = self._lookup_baseline_cell_value(s_name, coord)
            num_new = float(new_val) if isinstance(new_val, (int, float)) else new_val
            self.cell_overrides[full_coord] = num_new

            tc = GENERAL_COL_TO_TECH.get(col_let, "-") if s_name == "General" else s_name
            t_label = TECH_SPECS[tc]["display_name"] if tc in TECH_SPECS else s_name
            r_meta = GENERAL_ROW_BY_NUM.get(row_num, {"label": f"Row {row_num}", "unit": "-"})
            delta_abs = (
                float(num_new) - float(base_val)
                if isinstance(num_new, (int, float)) and isinstance(base_val, (int, float))
                else None
            )
            delta_pct = (
                (delta_abs / abs(float(base_val))) * 100.0
                if delta_abs is not None and isinstance(base_val, (int, float)) and abs(float(base_val)) > 1e-12
                else None
            )
            change_entry = {
                "cell_coord": full_coord,
                "sheet": s_name,
                "coord": coord,
                "row": row_num,
                "col": col_let,
                "technology_code": tc,
                "technology_label": t_label,
                "parameter": r_meta["label"],
                "unit": r_meta["unit"],
                "baseline_value": base_val,
                "current_value": num_new,
                "delta_abs": delta_abs,
                "delta_pct": delta_pct,
            }
            changes.append(change_entry)

        self.override_history = changes
        self._save_state()

        diff_md = ExcelLayoutRenderer.render_assumptions_diff_table(changes)
        assumptions_view = self.get_assumptions(technologies=affected_techs or ["_01_CF", "_06_CF"])
        return {
            "modified_count": len(self.cell_overrides),
            "updated_in_call": len(changes),
            "reset_to_baseline": reset_to_baseline,
            "changes": changes,
            "active_overrides": dict(self.cell_overrides),
            "diff_table_md": diff_md,
            "inline_excel_table_md": diff_md + "\n\n" + assumptions_view["inline_excel_table_md"],
            "full_artifact_table_md": assumptions_view["full_artifact_table_md"],
        }

    def _upsert_cell_range_update(self, sheet: str, cell_range: str, values: list[list[Any]]) -> None:
        """Insert or replace a 2D cell range update keyed by (sheet, range), preserving latest update order."""
        self.cell_range_updates = [
            item
            for item in self.cell_range_updates
            if not (item.get("sheet") == sheet and item.get("range") == cell_range)
        ]
        self.cell_range_updates.append({"sheet": sheet, "range": cell_range, "values": values})

    def _record_macro_outputs(self, response: Any) -> None:
        """Persist solved macro cell updates and flat outputs into the session."""
        for k, v in response.flat_outputs.items():
            self.solved_outputs[k] = v
        for cu in response.cell_updates:
            self._upsert_cell_range_update(cu.sheet, cu.range, cu.values)

    def run_tornado(
        self,
        technology_code: str = "_06_CF",
        parity_mode: str = "strict_legacy_vba",
    ) -> dict[str, Any]:
        """Execute calcule_tir<N> Tornado IRR sensitivity and build Excel table + ECharts spec."""
        norm_code = normalize_technology_code(technology_code)
        if norm_code == "ALL":
            all_results = [self.run_tornado(tc, parity_mode=parity_mode) for tc in TECH_SPECS]
            combined_md = "\n\n---\n\n".join(r["inline_excel_table_md"] for r in all_results)
            return {
                "technology_code": "ALL",
                "results": all_results,
                "inline_excel_table_md": combined_md,
                "full_artifact_table_md": combined_md,
                "echarts_spec": all_results[5]["echarts_spec"],  # _06_CF featured chart
            }

        spec = TECH_SPECS[norm_code]
        tech_idx = spec["index"]
        macro_name = f"calcule_tir{tech_idx}"
        gen_overrides, sheet_inputs, _ = self._build_general_overrides_and_sheet_inputs()

        req = SolveMacroRequest(
            macro_name=macro_name,
            general_overrides=gen_overrides,
            sheet_inputs=sheet_inputs,
            parity_mode=parity_mode,  # type: ignore[arg-type]
        )
        resp = MacroExecutionRegistry.execute(req, base_context=self._base_ctx)
        self._record_macro_outputs(resp)

        active_ctx = self.build_active_solver_context()
        sparams = active_ctx.sheet_parameters[norm_code]
        b6_d12 = sparams["tornado_inputs_b6_d12"]
        h_vec = active_ctx.rst_scenario(norm_code)
        parsed = self.loader.load_parsed_xml()
        sheet_cells = parsed["sheets_data"].get(norm_code, {})
        values_2d = resp.cell_updates[0].values if resp.cell_updates else []

        param_rows = list(range(6, 10)) if spec["is_dg"] else list(range(6, 13))
        tornado_rows: list[dict[str, Any]] = []
        for idx, r_num in enumerate(param_rows):
            param_label = str(sheet_cells.get(f"A{r_num}", {}).get("value") or f"Param Row {r_num}")
            in_low = float(b6_d12[idx][0])
            in_base = float(b6_d12[idx][1])
            in_high = float(b6_d12[idx][2])
            out_low = float(values_2d[idx][0])
            out_base = float(values_2d[idx][1])
            out_high = float(values_2d[idx][2])
            spread = abs(out_high - out_low)
            tornado_rows.append(
                {
                    "row_num": r_num,
                    "parameter": param_label,
                    "in_low": in_low,
                    "in_base": in_base,
                    "in_high": in_high,
                    "out_low": out_low,
                    "out_base": out_base,
                    "out_high": out_high,
                    "active_h": float(h_vec.get(r_num, in_base)),
                    "spread": spread,
                }
            )

        output_var = str(resp.metadata.get("output_variable", "price_lst_B16"))
        base_out = tornado_rows[0]["out_base"] if tornado_rows else 0.0
        table_md = ExcelLayoutRenderer.render_tornado_table(
            technology_code=norm_code,
            tornado_rows=tornado_rows,
            output_var=output_var,
            baseline_output=base_out,
        )
        echarts_spec = ExcelLayoutRenderer.build_tornado_echarts(
            technology_code=norm_code,
            tornado_rows=tornado_rows,
            output_var=output_var,
            baseline_output=base_out,
        )

        self.last_runs["tornado"] = {
            "technology_code": norm_code,
            "macro_name": macro_name,
            "solve_count": resp.solve_count,
            "execution_time_ms": round(resp.execution_time_ms, 3),
        }
        self._save_state()

        return {
            "technology_code": norm_code,
            "macro_name": macro_name,
            "solve_count": resp.solve_count,
            "execution_time_ms": round(resp.execution_time_ms, 3),
            "output_variable": output_var,
            "tornado_rows": tornado_rows,
            "flat_outputs": resp.flat_outputs,
            "inline_excel_table_md": table_md,
            "full_artifact_table_md": table_md,
            "echarts_spec": echarts_spec,
        }

    def run_lcoe_horizon(
        self,
        parity_mode: str = "strict_legacy_vba",
    ) -> dict[str, Any]:
        """Execute lcoe_exec (184 solves across 23 years x 8 technologies on Output_3!B9:J31)."""
        gen_overrides, sheet_inputs, _ = self._build_general_overrides_and_sheet_inputs()
        req = SolveMacroRequest(
            macro_name="lcoe_exec",
            general_overrides=gen_overrides,
            sheet_inputs=sheet_inputs,
            parity_mode=parity_mode,  # type: ignore[arg-type]
        )
        resp = MacroExecutionRegistry.execute(req, base_context=self._base_ctx)
        self._record_macro_outputs(resp)

        output_grid = resp.cell_updates[0].values if resp.cell_updates else []
        timestamp_b3 = str(resp.metadata.get("timestamp_b3", ""))
        self.solved_outputs["Output_3!B3"] = timestamp_b3
        icb_diag = resp.metadata.get("thermal_icb_diagnostics", {})

        inline_md, full_md = ExcelLayoutRenderer.render_lcoe_output3_tables(
            output_grid=output_grid,
            timestamp_b3=timestamp_b3,
            thermal_icb_diagnostics=icb_diag,
        )
        echarts_spec = ExcelLayoutRenderer.build_lcoe_horizon_echarts(output_grid=output_grid)

        self.last_runs["lcoe_horizon"] = {
            "macro_name": "lcoe_exec",
            "solve_count": resp.solve_count,
            "timestamp_b3": timestamp_b3,
            "execution_time_ms": round(resp.execution_time_ms, 3),
        }
        self._save_state()

        return {
            "macro_name": "lcoe_exec",
            "solve_count": resp.solve_count,
            "execution_time_ms": round(resp.execution_time_ms, 3),
            "timestamp_b3": timestamp_b3,
            "thermal_icb_diagnostics": icb_diag,
            "flat_outputs": resp.flat_outputs,
            "inline_excel_table_md": inline_md,
            "full_artifact_table_md": full_md,
            "echarts_spec": echarts_spec,
        }

    def run_bqml_refresh(
        self,
        curve_types: list[str] | None = None,
        apply_to_session_lt_tabs: bool = True,
    ) -> dict[str, Any]:
        """Refresh 23-year LT Capex, LT Fuel, and LT CF trajectories from BigQuery ML ARIMA_PLUS."""
        selected_curves = curve_types or ["CAPEX", "FUEL", "CF"]
        active_ctx = self.build_active_solver_context()
        bqml_engine = BQMLConnectedSheetsEngine(context=active_ctx)
        forecast_rows = bqml_engine.generate_connected_sheets_lt_forecasts(horizon=23)

        lt_grids = {
            "lt_capex_b8_j30": copy.deepcopy(active_ctx.lt_capex_b8_j30),
            "lt_fuel_b8_j30": copy.deepcopy(active_ctx.lt_fuel_b8_j30),
            "lt_cf_b8_j30": copy.deepcopy(active_ctx.lt_cf_b8_j30),
        }

        if apply_to_session_lt_tabs:
            tab_mapping = [
                ("CAPEX", "LT Capex", lt_grids["lt_capex_b8_j30"]),
                ("FUEL", "LT Fuel", lt_grids["lt_fuel_b8_j30"]),
                ("CF", "LT CF", lt_grids["lt_cf_b8_j30"]),
            ]
            upper_set = {c.upper().replace("LT_", "") for c in selected_curves}
            for c_key, sheet_name, grid in tab_mapping:
                if c_key not in upper_set:
                    continue
                self._upsert_cell_range_update(sheet_name, "B8:J30", grid)
                for yr_idx, row in enumerate(grid):
                    r_num = 8 + yr_idx
                    for c_meta in OUTPUT3_COLUMNS:
                        c_idx = c_meta["col_idx"]
                        c_let = c_meta["col_letter"]
                        if c_idx < len(row) and isinstance(row[c_idx], (int, float)):
                            self.solved_outputs[f"{sheet_name}!{c_let}{r_num}"] = float(row[c_idx])

        inline_md, full_md = ExcelLayoutRenderer.render_bqml_lt_tables(
            lt_grids=lt_grids,
            curve_types=selected_curves,
        )
        echarts_spec = ExcelLayoutRenderer.build_bqml_echarts(lt_grids=lt_grids)

        self.last_runs["bqml_refresh"] = {
            "curve_types": selected_curves,
            "row_count": len(forecast_rows),
            "applied_to_lt_tabs": apply_to_session_lt_tabs,
        }
        self._save_state()

        return {
            "source_view": "comm-model-mod.sheets_commodity_mod_governance.vw_connected_sheets_lt_forecasts",
            "curve_types": selected_curves,
            "forecast_row_count": len(forecast_rows),
            "applied_to_session_lt_tabs": apply_to_session_lt_tabs,
            "inline_excel_table_md": inline_md,
            "full_artifact_table_md": full_md,
            "echarts_spec": echarts_spec,
        }

    def run_dcf(
        self,
        technology_code: str = "_01_CF",
        start_year: int = 2024,
        end_year: int = 2053,
    ) -> dict[str, Any]:
        """Compute 30-year Project & Shareholder DCF Cash Flow schedule for any _01_CF.._12_CF tab."""
        norm_code = normalize_technology_code(technology_code)
        if norm_code == "ALL":
            norm_code = "_01_CF"
        spec = TECH_SPECS[norm_code]
        active_ctx = self.build_active_solver_context()
        engine = VectorizedCashFlowEngine(active_ctx)
        sparams = active_ctx.sheet_parameters[norm_code]
        h_vec = active_ctx.rst_scenario(norm_code)

        # Solve break-even LCOE price B16 under current assumptions
        base_b16 = float(sparams["b16_price"])
        sheet_modified = (
            norm_code in active_ctx.sheet_overrides
            or any(s == norm_code for (s, _) in active_ctx.general_param_ratios)
        )
        anchor = None if sheet_modified else base_b16
        conv = StrictLegacyVBAEmulator.solve_two_stage(
            irr_fn=lambda p, hv=dict(h_vec): engine.evaluate_irr(norm_code, p, h_overrides=hv),
            goal_stage1=0.080001,
            target_stage2=0.12,
            delta_p=0.001,
            tolerance_stage2=1e-5,
            stage1_only=spec["is_dg"],
            anchor_price_hint=anchor,
        )
        solved_b16 = float(conv.terminal_price)
        cf_full = engine.evaluate_cashflows(norm_code, solved_b16, h_overrides=h_vec)
        solved_irr = compute_spreadsheet_irr(cf_full)

        # Extract General parameters for this technology
        c_idx = spec["general_col_idx"]
        gen_grid = active_ctx.general_c5_n40

        def _gen_val(row_num: int, default: float) -> float:
            r_idx = row_num - 5
            if 0 <= r_idx < len(gen_grid) and c_idx < len(gen_grid[r_idx]):
                v = gen_grid[r_idx][c_idx]
                if isinstance(v, (int, float)):
                    return float(v)
            return default

        capacity_mw = _gen_val(8, 100.0)
        capex_r_kw = float(h_vec.get(6, _gen_val(11, 3500.0)))
        lead_time_yrs = _gen_val(14, 3.0)
        econ_life_yrs = _gen_val(15, 30.0)
        wacc_rate = float(h_vec.get(11 if not spec["is_dg"] else 9, _gen_val(34, 0.08)))
        h7_val = float(h_vec.get(7, _gen_val(16, 0.5)))
        gen_b17 = float(sparams.get("b17_gen") or (capacity_mw * 8760.0 * 0.5))

        years = list(range(start_year, end_year + 1))
        n_years = len(years)
        col_letters = [index_to_col_letter(2 + i) for i in range(n_years)]

        # Slice or pad cash flow vector to n_years (default 30 years: 2024..2053)
        cf_30 = [
            float(cf_full[i]) if i < cf_full.size else float(cf_full[-1])
            for i in range(n_years)
        ]

        # Extract exact line items from the seed worksheet and scale proportionally
        parsed = self.loader.load_parsed_xml()
        sheet_cells = parsed["sheets_data"].get(norm_code, {})
        base_cf_vec = sparams["baseline_cf_vector"]

        key_rows = (
            [
                (23, "(+) Gross Income"),
                (24, "(+) Financing"),
                (25, "(+) Equity"),
                (26, "(=) Income"),
                (29, "(-) Total Investment"),
                (30, "(=) Sales taxes"),
                (33, "(=) Total Expenses"),
                (34, "(=) Operational Expenses"),
                (35, "(-) Fixed Opex"),
                (36, "(-) Variable Opex"),
                (37, "(-) Transmission"),
                (38, "(-) Fuel / Lease cost"),
                (42, "(=) Charges"),
                (47, "(=) Insurance"),
                (51, "(=) EBITDA"),
                (52, "(-) Depreciation"),
                (54, "(=) EBIT"),
                (55, "(-) Financing Payments"),
                (60, "(-) Income tax"),
                (61, "(=) Net Income"),
                (63, "Shareholder Cash Flow"),
            ]
            if not spec["is_dg"]
            else [
                (19, "(+) Gross Income"),
                (22, "(-) Total Investment"),
                (26, "(=) Operational Expenses"),
                (32, "(=) EBITDA"),
                (42, "Shareholder Cash Flow"),
            ]
        )

        statement_rows: list[dict[str, Any]] = []
        ebitda_series: list[float] = [0.0] * n_years

        for r_num, default_label in key_rows:
            actual_label = str(sheet_cells.get(f"A{r_num}", {}).get("value") or default_label)
            if r_num in (63, 42) and "Cash Flow" in default_label:
                row_vals = cf_30
            else:
                row_vals = []
                for i in range(n_years):
                    c_let = col_letters[i]
                    raw_v = sheet_cells.get(f"{c_let}{r_num}", {}).get("value")
                    fv = float(raw_v) if isinstance(raw_v, (int, float)) else 0.0
                    # Scale investment rows by capex ratio and operating rows by cashflow ratio
                    if i < len(base_cf_vec) and abs(float(base_cf_vec[i])) > 1e-6:
                        scale = abs(cf_30[i]) / abs(float(base_cf_vec[i]))
                        fv = fv * scale
                    row_vals.append(fv)
            if "EBITDA" in actual_label:
                ebitda_series = list(row_vals)
            statement_rows.append({"row_num": r_num, "label": actual_label, "values": row_vals})

        # Compute Discounted Cash Flow & Cumulative Discounted NPV @ WACC
        disc_cf: list[float] = []
        cum_dcf: list[float] = []
        running = 0.0
        payback_yrs = float(n_years)
        payback_found = False
        for t_idx, val in enumerate(cf_30):
            d_val = val / ((1.0 + max(wacc_rate, 0.001)) ** t_idx)
            disc_cf.append(d_val)
            prev_running = running
            running += d_val
            cum_dcf.append(running)
            if not payback_found and t_idx > 0 and running >= 0.0 and prev_running < 0.0:
                frac = abs(prev_running) / max(abs(d_val), 1e-9)
                payback_yrs = float(t_idx - 1) + frac
                payback_found = True

        statement_rows.append(
            {"row_num": 64, "label": "Cumulative Discounted Cash Flow (NPV @ WACC)", "values": cum_dcf}
        )

        npv_at_wacc = float(sum(disc_cf))
        summary_metrics = {
            "capacity_mw": capacity_mw,
            "capex_r_per_kw": capex_r_kw,
            "lead_time_yrs": lead_time_yrs,
            "economic_life_yrs": econ_life_yrs,
            "h7_input": h7_val,
            "wacc_rate": wacc_rate,
            "lcoe_b16": solved_b16,
            "generation_b17": gen_b17,
            "irr_b18": solved_irr,
            "npv_at_wacc": npv_at_wacc,
            "payback_yrs": payback_yrs,
        }

        self.solved_outputs[f"{norm_code}!B16"] = solved_b16
        self.solved_outputs[f"{norm_code}!B18"] = solved_irr
        if spec["is_thermal"]:
            self.solved_outputs[f"{norm_code}!C16"] = engine.compute_fxd_revenue_c16(norm_code, solved_b16)

        inline_md, full_md = ExcelLayoutRenderer.render_dcf_tables(
            technology_code=norm_code,
            summary_metrics=summary_metrics,
            years=years,
            col_letters=col_letters,
            statement_rows=statement_rows,
        )
        echarts_spec = ExcelLayoutRenderer.build_dcf_echarts(
            technology_code=norm_code,
            years=years,
            shareholder_cf=cf_30,
            cumulative_dcf=cum_dcf,
            ebitda_series=ebitda_series,
        )

        self.last_runs["dcf"] = {
            "technology_code": norm_code,
            "start_year": start_year,
            "end_year": end_year,
            "lcoe_b16": round(solved_b16, 4),
            "irr_b18": round(solved_irr, 6),
            "npv_at_wacc": round(npv_at_wacc, 2),
        }
        self._save_state()

        return {
            "technology_code": norm_code,
            "start_year": start_year,
            "end_year": end_year,
            "summary_metrics": summary_metrics,
            "years": years,
            "shareholder_cashflow": cf_30,
            "cumulative_discounted_cashflow": cum_dcf,
            "inline_summary_table_md": inline_md,
            "inline_excel_table_md": inline_md,
            "full_artifact_table_md": full_md,
            "echarts_spec": echarts_spec,
        }

    def run_cvu_sweep(
        self,
        technology_code: str = "_01_CF",
        parity_mode: str = "strict_legacy_vba",
    ) -> dict[str, Any]:
        """Execute calculo_cvu<N> 1D Fuel/CVU/Capex sweep + Thermal Physical Guarantee (GF & ICB)."""
        norm_code = normalize_technology_code(technology_code)
        if norm_code == "ALL":
            norm_code = "_01_CF"
        spec = TECH_SPECS[norm_code]
        tech_idx = spec["index"]
        macro_name = f"calculo_cvu{tech_idx}"
        gen_overrides, sheet_inputs, _ = self._build_general_overrides_and_sheet_inputs()

        req = SolveMacroRequest(
            macro_name=macro_name,
            general_overrides=gen_overrides,
            sheet_inputs=sheet_inputs,
            parity_mode=parity_mode,  # type: ignore[arg-type]
        )
        resp = MacroExecutionRegistry.execute(req, base_context=self._base_ctx)
        self._record_macro_outputs(resp)

        active_ctx = self.build_active_solver_context()
        sparams = active_ctx.sheet_parameters[norm_code]
        b70_b79 = sparams.get("cvu_inputs_b70_b79", [])
        values_2d = resp.cell_updates[0].values if resp.cell_updates else []

        sweep_rows: list[dict[str, Any]] = []
        for idx, row_vals in enumerate(values_2d):
            r_num = 16 if spec["is_dg"] else (70 + idx)
            s_in = float(b70_b79[idx]) if idx < len(b70_b79) and b70_b79[idx] is not None else 1.0
            s_price = float(row_vals[0]) if row_vals and row_vals[0] is not None else 0.0
            icb_info = VectorizedCashFlowEngine.compute_thermal_icb(
                sheet_name=norm_code,
                solved_price_b16=s_price,
                fuel_cost_h7=s_in,
            )
            sweep_rows.append(
                {
                    "row_num": r_num,
                    "sweep_input": s_in,
                    "solved_price": s_price,
                    "fxd_rev": icb_info["d_cell_fxd_rev"],
                    "cvu": icb_info["e_cell_cvu"],
                    "gf_mw": icb_info["f_cell_gf"],
                    "fator_k": icb_info["h_cell_fator_k"],
                    "icb": icb_info["i_cell_icb"],
                }
            )

        mutated_cell = str(resp.metadata.get("mutated_observer_cell", "H7"))
        inline_md, full_md = ExcelLayoutRenderer.render_cvu_sweep_tables(
            technology_code=norm_code,
            sweep_rows=sweep_rows,
            mutated_cell=mutated_cell,
        )
        echarts_spec = ExcelLayoutRenderer.build_cvu_sweep_echarts(
            technology_code=norm_code,
            sweep_rows=sweep_rows,
        )

        self.last_runs["cvu_sweep"] = {
            "technology_code": norm_code,
            "macro_name": macro_name,
            "solve_count": resp.solve_count,
            "execution_time_ms": round(resp.execution_time_ms, 3),
        }
        self._save_state()

        return {
            "technology_code": norm_code,
            "macro_name": macro_name,
            "solve_count": resp.solve_count,
            "execution_time_ms": round(resp.execution_time_ms, 3),
            "mutated_observer_cell": mutated_cell,
            "sweep_rows": sweep_rows,
            "flat_outputs": resp.flat_outputs,
            "inline_excel_table_md": inline_md,
            "full_artifact_table_md": full_md,
            "echarts_spec": echarts_spec,
        }
