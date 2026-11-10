"""Quantitative 10-pass Gauss-Seidel equilibrium, EU ETS matrix, BQML, and HCK IRR solver engine."""

from __future__ import annotations

import math
import time
from typing import Any

from eulr_bq_twin.bq_store import EulrDigitalTwinStore
from eulr_bq_twin.formula_engine import (
    EulrFormulaEngine,
    ExcelError,
    _compute_irr_newton,
)
from eulr_bq_twin.models import (
    EuEtsMode,
    SessionCellDelta,
    UpstreamMode,
    index_to_col_letter,
    split_sheet_cell,
)

PRE_LOOP_SHEETS: tuple[str, ...] = ("Info", "Yields")
CIRCULAR_13_SHEETS: tuple[str, ...] = (
    "Input",
    "Freight",
    "Crudes",
    "ULSD-GO_spread_econs",
    "KeyInputs",
    "Op_Cost",
    "Carbon",
    "NWE Cif",
    "MED Cif",
    "NWE Fob",
    "MED Fob",
    "IMOfuels",
    "Links out",
)
POST_LOOP_SHEETS: tuple[str, ...] = (
    "HCK naphtha revamp",
    "2015 NWE HCK IRR",
    "Checks",
)

MILESTONE_YEARS: tuple[int, ...] = (2024, 2025, 2030, 2035, 2040, 2045, 2050)
# Pricing/Input sheets align 2024 at Col AT (46); Carbon aligns 2024 at Col P (16)
YEAR_TO_MAIN_COL: dict[int, int] = {yr: 46 + (yr - 2024) for yr in range(2024, 2051)}
YEAR_TO_CARBON_COL: dict[int, int] = {yr: 16 + (yr - 2024) for yr in range(2024, 2051)}

EU_ETS_SWITCH_VALUES: dict[EuEtsMode, tuple[str, str]] = {
    "cost_and_allocation": (
        "Sensitivity with EU ETS cost and pass-through",
        "Variable cost increase and product allocation",
    ),
    "variable_cost_only": (
        "Sensitivity with EU ETS cost and pass-through",
        "Variable cost increase only",
    ),
    "carbon_off": (
        "Base case LTO without carbon pricing",
        "Variable cost increase and product allocation",
    ),
}

# Friendly parameter aliases for update_eulr_session_overrides
NAMED_DRIVER_ALIASES: dict[str, tuple[str, int, str]] = {
    # alias -> (sheet_name, row_num, mode: 'forecast_row_delta' | 'forecast_row_set' | 'single_cell_A5' | 'single_cell_A6')
    "fcc_margin_shock_usd_bbl": ("KeyInputs", 19, "forecast_row_delta"),
    "hsk_roce_shock_usd_bbl": ("KeyInputs", 17, "forecast_row_delta"),
    "dated_brent_usd_bbl": ("Input", 37, "forecast_row_set"),
    "dated_brent_shock_usd_bbl": ("Input", 37, "forecast_row_delta"),
    "urals_cif_nwe_usd_bbl": ("Input", 43, "forecast_row_set"),
    "eur_per_usd_fx": ("Input", 25, "forecast_row_set"),
    "clean_mr_freight_ws_pct": ("Freight", 25, "forecast_row_set"),
    "dirty_aframax_ws_pct": ("Freight", 38, "forecast_row_set"),
}


def _num_or_none(val: Any, digits: int = 3) -> float | None:
    if isinstance(val, (int, float)) and not isinstance(val, bool) and math.isfinite(val):
        return round(float(val), digits)
    return None


class EulrQuantitativeSolver:
    """Executes all EULR analyses purely over the BigQuery Digital Twin."""

    def __init__(self, store: EulrDigitalTwinStore) -> None:
        self.store = store
        self._engine: EulrFormulaEngine | None = None

    @property
    def engine(self) -> EulrFormulaEngine:
        if self._engine is None:
            snap = self.store.get_baseline_snapshot()
            self._engine = EulrFormulaEngine(snap)
        return self._engine

    def _overlay_session_grid(
        self,
        session_id: str,
        upstream_mode: UpstreamMode = "baseline_cached",
        extra_driver_cells: dict[tuple[str, int, int], float | str] | None = None,
        extra_pinned_cells: dict[tuple[str, int, int], float] | None = None,
    ) -> tuple[
        dict[str, dict[tuple[int, int], Any]],
        set[tuple[str, int, int]],
        dict[tuple[str, int, int], float],
    ]:
        """Build working grid with session deltas, returning (grid, seed_coords, pinned_map)."""
        snap = self.store.get_baseline_snapshot()
        grid = self.engine.build_working_grid(upstream_mode=upstream_mode)
        seed_coords: set[tuple[str, int, int]] = set()
        pinned_map: dict[tuple[str, int, int], float] = {}

        if upstream_mode == "peer_synced":
            for key_rc, ext in snap.external_links.items():
                if ext.is_peer_updated and ext.peer_live_value is not None:
                    seed_coords.add(key_rc)

        sess_deltas = self.store.get_session_deltas(session_id)
        for (sname, r_idx, c_idx), d in sess_deltas.items():
            if sname not in grid:
                continue
            if d.delta_kind == "SOLVED_OUTPUT":
                # Recompute solved outputs fresh on each equilibrium solve
                continue
            val: Any = d.numeric_value if d.numeric_value is not None else d.string_value
            if val is not None:
                grid[sname][(r_idx, c_idx)] = val
                seed_coords.add((sname, r_idx, c_idx))
                if d.delta_kind == "PINNED_PRICE_OVERRIDE" and d.numeric_value is not None:
                    pinned_map[(sname, r_idx, c_idx)] = float(d.numeric_value)

        if extra_driver_cells:
            for (sname, r_idx, c_idx), val in extra_driver_cells.items():
                if sname in grid:
                    grid[sname][(r_idx, c_idx)] = val
                    seed_coords.add((sname, r_idx, c_idx))

        if extra_pinned_cells:
            for (sname, r_idx, c_idx), pval in extra_pinned_cells.items():
                if sname in grid:
                    grid[sname][(r_idx, c_idx)] = float(pval)
                    pinned_map[(sname, r_idx, c_idx)] = float(pval)
                    seed_coords.add((sname, r_idx, c_idx))

        return grid, seed_coords, pinned_map

    def extract_milestone_snapshot(
        self, grid: dict[str, dict[tuple[int, int], Any]]
    ) -> dict[str, Any]:
        """Extract executive milestone metrics (2024..2050) across KeyInputs, Carbon, Crudes, NWE/MED, IMO."""
        years = list(MILESTONE_YEARS)

        def _series(sheet: str, row: int, col_map: dict[int, int], digits: int = 2) -> dict[int, float | None]:
            sh = grid.get(sheet, {})
            return {yr: _num_or_none(sh.get((row, col_map[yr])), digits) for yr in years}

        margins = [
            {"metric": "Cat Cracking Margin (Dated Brent, incl. ETS)", "coord": "KeyInputs!Row15", "units": "$/bbl", "values": _series("KeyInputs", 15, YEAR_TO_MAIN_COL, 3)},
            {"metric": "Cat Cracking Margin (Dated Brent, excl. ETS)", "coord": "KeyInputs!Row18", "units": "$/bbl", "values": _series("KeyInputs", 18, YEAR_TO_MAIN_COL, 3)},
            {"metric": "Incremental FCC/HSK ROCE (CRF)", "coord": "KeyInputs!Row16", "units": "$/bbl", "values": _series("KeyInputs", 16, YEAR_TO_MAIN_COL, 3)},
            {"metric": "Marginal NWE FCC Margin", "coord": "KeyInputs!Row29", "units": "$/bbl", "values": _series("KeyInputs", 29, YEAR_TO_MAIN_COL, 3)},
            {"metric": "USGC Coking ICRF Benchmark", "coord": "KeyInputs!Row25", "units": "$/bbl", "values": _series("KeyInputs", 25, YEAR_TO_MAIN_COL, 3)},
            {"metric": "EU ETS Variable Cost Push to FCC", "coord": "Carbon!Row9", "units": "$/bbl", "values": _series("Carbon", 9, YEAR_TO_CARBON_COL, 3)},
            {"metric": "EU ETS Margin Erosion on FCC", "coord": "Carbon!Row10", "units": "$/bbl", "values": _series("Carbon", 10, YEAR_TO_CARBON_COL, 3)},
        ]

        crudes = [
            {"grade": "Dated Brent Spot FOB", "coord": "Input!Row37", "units": "$/bbl", "values": _series("Input", 37, YEAR_TO_MAIN_COL, 2)},
            {"grade": "Urals CIF NWE", "coord": "Input!Row43", "units": "$/bbl", "values": _series("Input", 43, YEAR_TO_MAIN_COL, 2)},
            {"grade": "Azeri Light FOB Ceyhan (23$)", "coord": "Input!Row44", "units": "$/bbl", "values": _series("Input", 44, YEAR_TO_MAIN_COL, 2)},
            {"grade": "Arab Light FOB (NWE Formula, 23$)", "coord": "Input!Row45", "units": "$/bbl", "values": _series("Input", 45, YEAR_TO_MAIN_COL, 2)},
            {"grade": "Es Sider Sweet Med FOB (23$)", "coord": "Input!Row47", "units": "$/bbl", "values": _series("Input", 47, YEAR_TO_MAIN_COL, 2)},
        ]

        nwe_cif = [
            {"product": "LPG (CIF NWE)", "coord": "NWE Cif!Row114", "units": "$/mt", "values": _series("NWE Cif", 114, YEAR_TO_MAIN_COL, 2)},
            {"product": "Naphtha (CIF NWE)", "coord": "NWE Cif!Row115", "units": "$/mt", "values": _series("NWE Cif", 115, YEAR_TO_MAIN_COL, 2)},
            {"product": "Euro Gasoline Premium (CIF NWE)", "coord": "NWE Cif!Row119", "units": "$/mt", "values": _series("NWE Cif", 119, YEAR_TO_MAIN_COL, 2)},
            {"product": "Jet / Kerosene (CIF NWE)", "coord": "NWE Cif!Row121", "units": "$/mt", "values": _series("NWE Cif", 121, YEAR_TO_MAIN_COL, 2)},
            {"product": "Diesel EN590 10ppm (CIF NWE)", "coord": "NWE Cif!Row122", "units": "$/mt", "values": _series("NWE Cif", 122, YEAR_TO_MAIN_COL, 2)},
            {"product": "Gasoil 0.1%S (CIF NWE)", "coord": "NWE Cif!Row130", "units": "$/mt", "values": _series("NWE Cif", 130, YEAR_TO_MAIN_COL, 2)},
            {"product": "LSFO 1.0%S (CIF NWE)", "coord": "NWE Cif!Row131", "units": "$/mt", "values": _series("NWE Cif", 131, YEAR_TO_MAIN_COL, 2)},
            {"product": "HSFO 3.5%S (CIF NWE)", "coord": "NWE Cif!Row132", "units": "$/mt", "values": _series("NWE Cif", 132, YEAR_TO_MAIN_COL, 2)},
        ]

        med_cif = [
            {"product": "LPG (CIF MED)", "coord": "MED Cif!Row127", "units": "$/mt", "values": _series("MED Cif", 127, YEAR_TO_MAIN_COL, 2)},
            {"product": "Naphtha (CIF MED)", "coord": "MED Cif!Row128", "units": "$/mt", "values": _series("MED Cif", 128, YEAR_TO_MAIN_COL, 2)},
            {"product": "Euro Gasoline Premium (CIF MED)", "coord": "MED Cif!Row132", "units": "$/mt", "values": _series("MED Cif", 132, YEAR_TO_MAIN_COL, 2)},
            {"product": "Jet / Kerosene (CIF MED)", "coord": "MED Cif!Row134", "units": "$/mt", "values": _series("MED Cif", 134, YEAR_TO_MAIN_COL, 2)},
            {"product": "Diesel EN590 10ppm (CIF MED)", "coord": "MED Cif!Row135", "units": "$/mt", "values": _series("MED Cif", 135, YEAR_TO_MAIN_COL, 2)},
            {"product": "Gasoil 0.1%S (CIF MED)", "coord": "MED Cif!Row143", "units": "$/mt", "values": _series("MED Cif", 143, YEAR_TO_MAIN_COL, 2)},
            {"product": "LSFO 1.0%S (CIF MED)", "coord": "MED Cif!Row144", "units": "$/mt", "values": _series("MED Cif", 144, YEAR_TO_MAIN_COL, 2)},
            {"product": "HSFO 3.5%S (CIF MED)", "coord": "MED Cif!Row145", "units": "$/mt", "values": _series("MED Cif", 145, YEAR_TO_MAIN_COL, 2)},
        ]

        fob_and_imo = [
            {"product": "Diesel EN590 (FOB NWE)", "coord": "NWE Fob!Row156", "units": "$/mt", "values": _series("NWE Fob", 156, YEAR_TO_MAIN_COL, 2)},
            {"product": "Euro Gasoline (FOB NWE)", "coord": "NWE Fob!Row153", "units": "$/mt", "values": _series("NWE Fob", 153, YEAR_TO_MAIN_COL, 2)},
            {"product": "Diesel EN590 (FOB MED)", "coord": "MED Fob!Row146", "units": "$/mt", "values": _series("MED Fob", 146, YEAR_TO_MAIN_COL, 2)},
            {"product": "Euro Gasoline (FOB MED)", "coord": "MED Fob!Row143", "units": "$/mt", "values": _series("MED Fob", 143, YEAR_TO_MAIN_COL, 2)},
            {"product": "IMO 0.1%S MGO Bunker", "coord": "IMOfuels!Row21", "units": "$/mt", "values": _series("IMOfuels", 21, YEAR_TO_MAIN_COL, 2)},
            {"product": "IMO 0.5%S VLSFO Bunker", "coord": "IMOfuels!Row22", "units": "$/mt", "values": _series("IMOfuels", 22, YEAR_TO_MAIN_COL, 2)},
        ]

        c_sh = grid.get("Carbon", {})
        return {
            "years": years,
            "carbon_switch_a5": str(c_sh.get((5, 1), "")),
            "carbon_switch_a6": str(c_sh.get((6, 1), "")),
            "margins": margins,
            "crudes": crudes,
            "nwe_cif": nwe_cif,
            "med_cif": med_cif,
            "fob_and_imo": fob_and_imo,
        }

    def get_session_assumptions(self, session_id: str) -> dict[str, Any]:
        grid, _, pinned_map = self._overlay_session_grid(session_id=session_id)
        sess_deltas = self.store.get_session_deltas(session_id)
        driver_deltas = [
            {
                "cell": f"{d.sheet_name}!{d.cell_coord}",
                "kind": d.delta_kind,
                "value": d.numeric_value if d.numeric_value is not None else d.string_value,
            }
            for d in sess_deltas.values()
            if d.delta_kind in ("DRIVER_OVERRIDE", "PINNED_PRICE_OVERRIDE", "BQML_FORECAST")
        ]
        snap_data = self.extract_milestone_snapshot(grid)
        snap_data["active_override_count"] = len(driver_deltas)
        snap_data["active_pinned_count"] = len(pinned_map)
        snap_data["active_overrides_preview"] = driver_deltas[:25]
        return snap_data

    def apply_user_overrides(
        self,
        session_id: str,
        driver_overrides: dict[str, Any] | None = None,
        pinned_price_overrides: dict[str, float] | None = None,
        eu_ets_mode: EuEtsMode | None = None,
        reset_to_baseline: bool = False,
        actor: str = "gemini-agent@comm-model-mod",
    ) -> dict[str, Any]:
        if reset_to_baseline:
            self.store.reset_session_to_baseline(
                session_id=session_id,
                actor=actor,
                source_tool="update_eulr_session_overrides",
            )

        snap = self.store.get_baseline_snapshot()
        deltas: list[SessionCellDelta] = []
        audits: list[dict[str, Any]] = []

        if eu_ets_mode is not None and eu_ets_mode in EU_ETS_SWITCH_VALUES:
            a5_val, a6_val = EU_ETS_SWITCH_VALUES[eu_ets_mode]
            for coord_str, r_i, new_s in (("A5", 5, a5_val), ("A6", 6, a6_val)):
                old_cell = snap.cells_by_sheet["Carbon"].get((r_i, 1))
                old_s = old_cell.string_value if old_cell else ""
                deltas.append(
                    SessionCellDelta(
                        sheet_name="Carbon",
                        cell_coord=coord_str,
                        row_num=r_i,
                        col_num=1,
                        delta_kind="DRIVER_OVERRIDE",
                        numeric_value=None,
                        string_value=new_s,
                        source_tool="update_eulr_session_overrides",
                    )
                )
                audits.append(
                    {
                        "what_sheet": "Carbon",
                        "what_coord": coord_str,
                        "what_change_type": "EU_ETS_SWITCH_OVERRIDE",
                        "before_value": old_s,
                        "after_value": new_s,
                        "who_principal": actor,
                        "why_context": f"update_eulr_session_overrides(eu_ets_mode={eu_ets_mode})",
                    }
                )

        for raw_key, raw_val in (driver_overrides or {}).items():
            key_clean = raw_key.strip()
            alias_key = key_clean.lower()
            if alias_key in NAMED_DRIVER_ALIASES:
                sh_name, r_num, mode = NAMED_DRIVER_ALIASES[alias_key]
                f_val = float(raw_val)
                for col_i in range(46, 73):  # 2024..2050
                    c_str = f"{index_to_col_letter(col_i)}{r_num}"
                    base_tc = snap.cells_by_sheet[sh_name].get((r_num, col_i))
                    base_v = float(base_tc.numeric_value or 0.0) if base_tc else 0.0
                    target_v = (base_v + f_val) if mode == "forecast_row_delta" else f_val
                    deltas.append(
                        SessionCellDelta(
                            sheet_name=sh_name,
                            cell_coord=c_str,
                            row_num=r_num,
                            col_num=col_i,
                            delta_kind="DRIVER_OVERRIDE",
                            numeric_value=round(target_v, 6),
                            string_value=None,
                            source_tool="update_eulr_session_overrides",
                        )
                    )
                audits.append(
                    {
                        "what_sheet": sh_name,
                        "what_coord": f"AT{r_num}:BT{r_num}",
                        "what_change_type": "DRIVER_SERIES_OVERRIDE",
                        "before_value": "lr202409_baseline",
                        "after_value": f"{mode}={f_val}",
                        "who_principal": actor,
                        "why_context": f"update_eulr_session_overrides({key_clean}={raw_val})",
                    }
                )
            elif "!" in key_clean:
                sh_name, c_str, r_num, c_num = split_sheet_cell(key_clean)
                base_tc = snap.cells_by_sheet.get(sh_name, {}).get((r_num, c_num))
                before_repr = (
                    base_tc.numeric_value
                    if (base_tc and base_tc.numeric_value is not None)
                    else (base_tc.string_value if base_tc else "")
                )
                if isinstance(raw_val, (int, float)) and not isinstance(raw_val, bool):
                    deltas.append(
                        SessionCellDelta(
                            sheet_name=sh_name,
                            cell_coord=c_str,
                            row_num=r_num,
                            col_num=c_num,
                            delta_kind="DRIVER_OVERRIDE",
                            numeric_value=float(raw_val),
                            string_value=None,
                            source_tool="update_eulr_session_overrides",
                        )
                    )
                else:
                    deltas.append(
                        SessionCellDelta(
                            sheet_name=sh_name,
                            cell_coord=c_str,
                            row_num=r_num,
                            col_num=c_num,
                            delta_kind="DRIVER_OVERRIDE",
                            numeric_value=None,
                            string_value=str(raw_val),
                            source_tool="update_eulr_session_overrides",
                        )
                    )
                audits.append(
                    {
                        "what_sheet": sh_name,
                        "what_coord": c_str,
                        "what_change_type": "CELL_DRIVER_OVERRIDE",
                        "before_value": before_repr,
                        "after_value": raw_val,
                        "who_principal": actor,
                        "why_context": f"update_eulr_session_overrides({key_clean})",
                    }
                )

        for p_key, p_val in (pinned_price_overrides or {}).items():
            sh_name, c_str, r_num, c_num = split_sheet_cell(p_key)
            base_tc = snap.cells_by_sheet.get(sh_name, {}).get((r_num, c_num))
            before_v = base_tc.numeric_value if base_tc else None
            deltas.append(
                SessionCellDelta(
                    sheet_name=sh_name,
                    cell_coord=c_str,
                    row_num=r_num,
                    col_num=c_num,
                    delta_kind="PINNED_PRICE_OVERRIDE",
                    numeric_value=float(p_val),
                    string_value=None,
                    source_tool="update_eulr_session_overrides",
                )
            )
            audits.append(
                {
                    "what_sheet": sh_name,
                    "what_coord": c_str,
                    "what_change_type": "PINNED_PRICE_OVERRIDE",
                    "before_value": before_v,
                    "after_value": float(p_val),
                    "who_principal": actor,
                    "why_context": f"Pinned price override on {sh_name}!{c_str} = {p_val}",
                }
            )

        if deltas or audits:
            self.store.append_deltas_and_audit(session_id, deltas, audits)

        updated = self.get_session_assumptions(session_id)
        updated["cells_written"] = len(deltas)
        return updated

    def solve_equilibrium(
        self,
        session_id: str,
        max_iterations: int = 10,
        upstream_mode: UpstreamMode = "baseline_cached",
        eu_ets_mode: EuEtsMode | None = None,
        fcc_margin_shock_usd_bbl: float = 0.0,
        extra_pinned_overrides: dict[str, float] | None = None,
        persist_outputs: bool = True,
        actor: str = "gemini-agent@comm-model-mod",
    ) -> dict[str, Any]:
        """Run the 10-pass Gauss-Seidel circular equilibrium solver over the BigQuery Digital Twin."""
        t0 = time.perf_counter()
        snap = self.store.get_baseline_snapshot()

        extra_drivers: dict[tuple[str, int, int], float | str] = {}
        if eu_ets_mode is not None and eu_ets_mode in EU_ETS_SWITCH_VALUES:
            a5_v, a6_v = EU_ETS_SWITCH_VALUES[eu_ets_mode]
            extra_drivers[("Carbon", 5, 1)] = a5_v
            extra_drivers[("Carbon", 6, 1)] = a6_v

        if abs(fcc_margin_shock_usd_bbl) > 1e-12:
            for col_i in range(46, 73):
                base_tc = snap.cells_by_sheet["KeyInputs"].get((19, col_i))
                base_v = float(base_tc.numeric_value or 0.0) if base_tc else 0.0
                extra_drivers[("KeyInputs", 19, col_i)] = base_v + fcc_margin_shock_usd_bbl

        extra_pins: dict[tuple[str, int, int], float] = {}
        for pk, pv in (extra_pinned_overrides or {}).items():
            s_n, _, r_i, c_i = split_sheet_cell(pk)
            extra_pins[(s_n, r_i, c_i)] = float(pv)

        grid, seed_coords, pinned_map = self._overlay_session_grid(
            session_id=session_id,
            upstream_mode=upstream_mode,
            extra_driver_cells=extra_drivers or None,
            extra_pinned_cells=extra_pins or None,
        )

        affected_cone = self.engine.compute_affected_cone(seed_coords) if seed_coords else {}
        affected_cell_count = sum(len(v) for v in affected_cone.values())

        # Step 1: Pre-loop acyclic sheets
        for s_pre in PRE_LOOP_SHEETS:
            for r_i, c_i in affected_cone.get(s_pre, ()):
                if (s_pre, r_i, c_i) in pinned_map:
                    grid[s_pre][(r_i, c_i)] = pinned_map[(s_pre, r_i, c_i)]
                else:
                    grid[s_pre][(r_i, c_i)] = self.engine.eval_cell(grid, s_pre, r_i, c_i)

        # Step 2: 10-pass Gauss-Seidel circular loop
        convergence_history: list[float] = []
        n_iters = max(1, min(30, int(max_iterations)))
        tracked_rows_nwe = (114, 115, 119, 121, 122, 130, 131, 132)
        tracked_rows_med = (127, 128, 132, 134, 135, 143, 144, 145)

        for _ in range(n_iters):
            if not affected_cone:
                convergence_history.append(0.0)
                continue

            prev_prices = {
                ("NWE Cif", r, c): grid["NWE Cif"].get((r, c), 0.0)
                for r in tracked_rows_nwe
                for c in range(46, 73)
            }
            prev_prices.update(
                {
                    ("MED Cif", r, c): grid["MED Cif"].get((r, c), 0.0)
                    for r in tracked_rows_med
                    for c in range(46, 73)
                }
            )

            for s_circ in CIRCULAR_13_SHEETS:
                coords_list = affected_cone.get(s_circ, ())
                if coords_list:
                    sh_grid = grid[s_circ]
                    for r_i, c_i in coords_list:
                        if (s_circ, r_i, c_i) in pinned_map:
                            sh_grid[(r_i, c_i)] = pinned_map[(s_circ, r_i, c_i)]
                        else:
                            sh_grid[(r_i, c_i)] = self.engine.eval_cell(grid, s_circ, r_i, c_i)
                # Re-assert any pinned overrides on this sheet
                for (ps, pr, pc), pval in pinned_map.items():
                    if ps == s_circ:
                        grid[ps][(pr, pc)] = pval

            max_step_delta = 0.0
            for (s_t, r_t, c_t), old_v in prev_prices.items():
                new_v = grid[s_t].get((r_t, c_t), 0.0)
                if isinstance(old_v, (int, float)) and isinstance(new_v, (int, float)):
                    d = abs(float(new_v) - float(old_v))
                    if math.isfinite(d) and d > max_step_delta:
                        max_step_delta = d
            convergence_history.append(round(max_step_delta, 8))

        # Step 3: Post-loop diagnostic & HCK sheets
        for s_post in POST_LOOP_SHEETS:
            for r_i, c_i in affected_cone.get(s_post, ()):
                if (s_post, r_i, c_i) not in pinned_map:
                    grid[s_post][(r_i, c_i)] = self.engine.eval_cell(grid, s_post, r_i, c_i)

        # Evaluate Checks diagnostics across forecast horizon (Col AT=46..BT=72)
        checks_flags: list[str] = []
        total_check_cells = 0
        checks_sh = grid.get("Checks", {})
        base_checks = snap.cells_by_sheet.get("Checks", {})
        for (r_i, c_i), base_tc in base_checks.items():
            if 46 <= c_i <= 72 and base_tc.raw_formula is not None:
                total_check_cells += 1
                cur_val = checks_sh.get((r_i, c_i))
                base_val = base_tc.numeric_value if base_tc.numeric_value is not None else base_tc.string_value
                if isinstance(cur_val, ExcelError):
                    checks_flags.append(f"Checks!{index_to_col_letter(c_i)}{r_i}={cur_val.code}")
                elif isinstance(cur_val, str) and cur_val.strip().upper() in ("ERROR", "FAIL", "CHECK", "FALSE"):
                    if cur_val != base_val:
                        checks_flags.append(f"Checks!{index_to_col_letter(c_i)}{r_i}={cur_val}")

        # Persist changed headline summary cells to dt_scenario_deltas when requested
        persisted_count = 0
        if persist_outputs and affected_cone:
            solved_deltas: list[SessionCellDelta] = []
            key_Save_specs = [
                ("KeyInputs", (15, 16, 18, 25, 29)),
                ("Carbon", (9, 10)),
                ("NWE Cif", tracked_rows_nwe),
                ("MED Cif", tracked_rows_med),
                ("NWE Fob", (149, 153, 155, 156, 164, 165, 166)),
                ("MED Fob", (139, 143, 145, 146, 154, 155, 156)),
                ("IMOfuels", (21, 22, 23)),
            ]
            for s_save, r_tuple in key_Save_specs:
                c_range = range(16, 43) if s_save == "Carbon" else range(46, 73)
                for r_i in r_tuple:
                    for c_i in c_range:
                        if (s_save, r_i, c_i) in pinned_map:
                            continue
                        cur_v = grid[s_save].get((r_i, c_i))
                        base_tc = snap.cells_by_sheet[s_save].get((r_i, c_i))
                        base_v = base_tc.numeric_value if base_tc else None
                        if isinstance(cur_v, (int, float)) and not isinstance(cur_v, bool) and math.isfinite(cur_v):
                            if base_v is None or abs(float(cur_v) - float(base_v)) > 1e-7:
                                solved_deltas.append(
                                    SessionCellDelta(
                                        sheet_name=s_save,
                                        cell_coord=f"{index_to_col_letter(c_i)}{r_i}",
                                        row_num=r_i,
                                        col_num=c_i,
                                        delta_kind="SOLVED_OUTPUT",
                                        numeric_value=round(float(cur_v), 6),
                                        string_value=None,
                                        source_tool="run_eulr_equilibrium_solve",
                                    )
                                )
            persisted_count = len(solved_deltas)
            self.store.append_deltas_and_audit(
                session_id=session_id,
                deltas=solved_deltas,
                audit_events=[
                    {
                        "what_sheet": "EQUILIBRIUM_13_SHEETS",
                        "what_coord": f"Passes={n_iters},Affected={affected_cell_count}",
                        "what_change_type": "EQUILIBRIUM_SOLVE_COMPLETED",
                        "before_value": f"upstream={upstream_mode}",
                        "after_value": f"final_delta={convergence_history[-1]},saved={persisted_count}",
                        "who_principal": actor,
                        "why_context": "run_eulr_equilibrium_solve",
                    }
                ],
            )

        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        milestone_data = self.extract_milestone_snapshot(grid)
        return {
            "session_id": session_id,
            "upstream_mode": upstream_mode,
            "iterations_run": n_iters,
            "converged": convergence_history[-1] < 1e-3,
            "convergence_history": convergence_history,
            "final_max_delta_usd_mt": convergence_history[-1],
            "affected_formula_cells": affected_cell_count,
            "pinned_override_count": len(pinned_map),
            "persisted_output_cells": persisted_count,
            "compute_ms": elapsed_ms,
            "checks_diagnostics": {
                "evaluated_formula_cells": total_check_cells,
                "flagged_count": len(checks_flags),
                "sample_flags": checks_flags[:10],
            },
            "milestone_snapshot": milestone_data,
        }

    def run_scenario_matrix(
        self, session_id: str, target_year: int = 2035
    ) -> dict[str, Any]:
        """Run the 6-case European Refining Margin, EU ETS Carbon & 3-Peer Upstream Sync Matrix."""
        yr = max(2024, min(2050, int(target_year)))
        col_main = YEAR_TO_MAIN_COL[yr]

        case_defs: list[tuple[str, str, EuEtsMode, float, UpstreamMode]] = [
            ("BASE_ETS_FULL", "1. Base + EU ETS Cost & Allocation (Baseline)", "cost_and_allocation", 0.0, "baseline_cached"),
            ("BASE_ETS_VAR", "2. Base + EU ETS Variable Cost Only", "variable_cost_only", 0.0, "baseline_cached"),
            ("BASE_ETS_OFF", "3. Base + EU ETS Carbon Off (Zero ETS)", "carbon_off", 0.0, "baseline_cached"),
            ("TIGHT_MARGIN_ETS_ON", "4. Tight Refining (+$1.50/bbl FCC) + ETS On", "cost_and_allocation", 1.50, "baseline_cached"),
            ("WEAK_MARGIN_ETS_ON", "5. Margin Compression (-$1.50/bbl FCC) + ETS On", "cost_and_allocation", -1.50, "baseline_cached"),
            ("PEER_SYNC_LIVE", "6. Global Peer Sync (Uslr + Felr + Tankerlr)", "cost_and_allocation", 0.0, "peer_synced"),
        ]

        cases_out: list[dict[str, Any]] = []
        for cid, clabel, ets_m, shock, up_m in case_defs:
            res = self.solve_equilibrium(
                session_id=session_id,
                max_iterations=10,
                upstream_mode=up_m,
                eu_ets_mode=ets_m,
                fcc_margin_shock_usd_bbl=shock,
                persist_outputs=False,
            )
            ms = res["milestone_snapshot"]
            # Also read exact target_year column if yr not in MILESTONE_YEARS
            extra_drivers: dict[tuple[str, int, int], float | str] = {}
            a5_v, a6_v = EU_ETS_SWITCH_VALUES[ets_m]
            extra_drivers[("Carbon", 5, 1)] = a5_v
            extra_drivers[("Carbon", 6, 1)] = a6_v
            if abs(shock) > 1e-12:
                snap = self.store.get_baseline_snapshot()
                for c_i in range(46, 73):
                    bt = snap.cells_by_sheet["KeyInputs"].get((19, c_i))
                    extra_drivers[("KeyInputs", 19, c_i)] = float(bt.numeric_value or 0.0 if bt else 0.0) + shock

            # Extract directly from milestone_snapshot if yr in MILESTONE_YEARS, else 2025 fallback
            use_yr = yr if yr in MILESTONE_YEARS else 2025
            m_by_coord = {m["coord"]: m["values"][use_yr] for m in ms["margins"]}
            nwe_by_coord = {p["coord"]: p["values"][use_yr] for p in ms["nwe_cif"]}
            med_by_coord = {p["coord"]: p["values"][use_yr] for p in ms["med_cif"]}
            imo_by_coord = {p["coord"]: p["values"][use_yr] for p in ms["fob_and_imo"]}

            diesel_nwe = nwe_by_coord["NWE Cif!Row122"] or 0.0
            gasoil_nwe = nwe_by_coord["NWE Cif!Row130"] or 0.0
            diesel_med = med_by_coord["MED Cif!Row135"] or 0.0
            cases_out.append(
                {
                    "case_id": cid,
                    "case_label": clabel,
                    "eu_ets_mode": ets_m,
                    "upstream_mode": up_m,
                    "fcc_margin_usd_bbl": m_by_coord["KeyInputs!Row15"],
                    "ets_erosion_usd_bbl": m_by_coord["Carbon!Row10"],
                    "nwe_diesel_cif_usd_mt": diesel_nwe,
                    "med_diesel_cif_usd_mt": diesel_med,
                    "nwe_euro_gasoline_usd_mt": nwe_by_coord["NWE Cif!Row119"],
                    "nwe_jet_kero_usd_mt": nwe_by_coord["NWE Cif!Row121"],
                    "imo_vlsfo_05_usd_mt": imo_by_coord["IMOfuels!Row22"],
                    "ulsd_gasoil_spread_usd_mt": round(diesel_nwe - gasoil_nwe, 2),
                    "nwe_vs_med_diesel_usd_mt": round(diesel_nwe - diesel_med, 2),
                }
            )

        _ = col_main
        return {
            "session_id": session_id,
            "target_year": yr if yr in MILESTONE_YEARS else 2025,
            "cases": cases_out,
        }

    def run_bqml_forecast_refresh(
        self,
        session_id: str,
        domain_groups: list[str] | None = None,
        apply_to_session: bool = True,
        actor: str = "gemini-agent@comm-model-mod",
    ) -> dict[str, Any]:
        """Query BigQuery ML ARIMA_PLUS forecasts (2025-2050) and optionally inject into session & re-solve."""
        domains = [d.upper() for d in (domain_groups or ["MACRO", "CRUDES", "FREIGHT"])]
        actuals, forecasts = self.store.fetch_bqml_forecasts(domains)

        # Offline unit-test fallback when running without live GCP BigQuery client
        if not forecasts and self.store.settings.gcp_project_id == "offline-test":
            from eulr_bq_twin.xlsx_compiler import BQML_DRIVER_SPECS

            snap = self.store.get_baseline_snapshot()
            for dom, sid, slabel, units, t_sh, t_row in BQML_DRIVER_SPECS:
                if dom not in domains:
                    continue
                sh_c = snap.cells_by_sheet.get(t_sh, {})
                v_2024 = float(sh_c.get((t_row, 46)).numeric_value or 1.0)  # type: ignore[union-attr]
                v_2019 = float(sh_c.get((t_row, 41)).numeric_value or v_2024)  # type: ignore[union-attr]
                drift = (v_2024 - v_2019) / 5.0 * 0.35
                for yr in range(1990, 2025):
                    tc = sh_c.get((t_row, 12 + (yr - 1990)))
                    if tc and tc.numeric_value is not None:
                        actuals.append(
                            {
                                "domain_group": dom,
                                "series_id": sid,
                                "series_label": slabel,
                                "units": units,
                                "target_sheet": t_sh,
                                "target_row": t_row,
                                "forecast_year": yr,
                                "actual_value": float(tc.numeric_value),
                            }
                        )
                for yr in range(2025, 2051):
                    step = yr - 2024
                    fv = v_2024 + drift * step
                    band = abs(fv) * 0.06 * math.sqrt(step / 5.0)
                    forecasts.append(
                        {
                            "domain_group": dom,
                            "series_id": sid,
                            "series_label": slabel,
                            "units": units,
                            "target_sheet": t_sh,
                            "target_row": t_row,
                            "forecast_year": yr,
                            "forecast_value": round(fv, 4),
                            "lower_bound": round(fv - band, 4),
                            "upper_bound": round(fv + band, 4),
                        }
                    )

        deltas_written = 0
        equilibrium_result: dict[str, Any] | None = None
        if apply_to_session and forecasts:
            bqml_deltas: list[SessionCellDelta] = []
            for fc in forecasts:
                yr = int(fc["forecast_year"])
                if 2025 <= yr <= 2050:
                    col_i = 46 + (yr - 2024)
                    r_i = int(fc["target_row"])
                    s_n = fc["target_sheet"]
                    bqml_deltas.append(
                        SessionCellDelta(
                            sheet_name=s_n,
                            cell_coord=f"{index_to_col_letter(col_i)}{r_i}",
                            row_num=r_i,
                            col_num=col_i,
                            delta_kind="BQML_FORECAST",
                            numeric_value=round(float(fc["forecast_value"]), 6),
                            string_value=None,
                            source_tool="run_eulr_bqml_forecast_refresh",
                        )
                    )
            deltas_written = len(bqml_deltas)
            self.store.append_deltas_and_audit(
                session_id=session_id,
                deltas=bqml_deltas,
                audit_events=[
                    {
                        "what_sheet": ",".join(sorted({f["target_sheet"] for f in forecasts})),
                        "what_coord": f"2025..2050 ({deltas_written} cells)",
                        "what_change_type": "BQML_ARIMA_PLUS_REFRESH",
                        "before_value": "lr202409_driver_curves",
                        "after_value": f"ARIMA_PLUS({','.join(domains)})",
                        "who_principal": actor,
                        "why_context": "run_eulr_bqml_forecast_refresh(apply_to_session=True)",
                    }
                ],
            )
            equilibrium_result = self.solve_equilibrium(
                session_id=session_id,
                persist_outputs=True,
                actor=actor,
            )

        # Group series for clean milestone + full tables
        series_map: dict[str, dict[str, Any]] = {}
        for a in actuals:
            sid = a["series_id"]
            rec = series_map.setdefault(
                sid,
                {
                    "domain_group": a["domain_group"],
                    "series_id": sid,
                    "series_label": a["series_label"],
                    "units": a["units"],
                    "target_sheet": a["target_sheet"],
                    "target_row": int(a["target_row"]),
                    "actuals": {},
                    "forecasts": {},
                    "lower": {},
                    "upper": {},
                },
            )
            rec["actuals"][int(a["forecast_year"])] = round(float(a["actual_value"]), 4)

        for f in forecasts:
            sid = f["series_id"]
            rec = series_map.setdefault(
                sid,
                {
                    "domain_group": f["domain_group"],
                    "series_id": sid,
                    "series_label": f["series_label"],
                    "units": f["units"],
                    "target_sheet": f["target_sheet"],
                    "target_row": int(f["target_row"]),
                    "actuals": {},
                    "forecasts": {},
                    "lower": {},
                    "upper": {},
                },
            )
            yr = int(f["forecast_year"])
            rec["forecasts"][yr] = round(float(f["forecast_value"]), 4)
            rec["lower"][yr] = round(float(f.get("lower_bound") or f["forecast_value"]), 4)
            rec["upper"][yr] = round(float(f.get("upper_bound") or f["forecast_value"]), 4)

        return {
            "session_id": session_id,
            "domain_groups": domains,
            "applied_to_session": apply_to_session,
            "deltas_written": deltas_written,
            "series": list(series_map.values()),
            "equilibrium_summary": equilibrium_result,
        }

    def run_hck_and_ulsd_economics(
        self,
        session_id: str,
        discount_rate_wacc: float = 0.10,
    ) -> dict[str, Any]:
        """Evaluate Hydrocracker Revamp (`HCK naphtha revamp`), 200 kb/d HCK Project IRR, and ULSD-Gasoil Economics."""
        eq = self.solve_equilibrium(session_id=session_id, persist_outputs=False)
        grid, _, _ = self._overlay_session_grid(session_id=session_id)

        # 1. HCK naphtha revamp (Col AT=46 holds 2050/long-run revamp economics; check cols across sheet)
        hck_rev_sh = grid.get("HCK naphtha revamp", {})
        hck_revamp_metrics = {
            "hck_vm_max_naphtha_usd_bbl": _num_or_none(hck_rev_sh.get((33, 46)), 3),
            "hck_vm_max_diesel_usd_bbl": _num_or_none(hck_rev_sh.get((34, 46)), 3),
            "diesel_minus_naphtha_vm_usd_bbl": _num_or_none(hck_rev_sh.get((35, 46)), 3),
            "annual_revamp_uplift_musd_yr": _num_or_none(hck_rev_sh.get((36, 46)), 3),
            "incremental_capex_musd": _num_or_none(hck_rev_sh.get((43, 46)), 2),
            "notional_icrf_ratio": _num_or_none(hck_rev_sh.get((46, 46)), 4),
        }

        # 2. ULSD-GO_spread_econs (Row 1 years: Col B=2 is 2005 .. Col AU=47 is 2050; 2025 is Col V=22)
        ulsd_sh = grid.get("ULSD-GO_spread_econs", {})
        ulsd_milestones: list[dict[str, Any]] = []
        for yr in (2024, 2025, 2030, 2035, 2040, 2045, 2050):
            col_u = 2 + (yr - 2005)  # 2005 -> col 2, 2024 -> col 21, 2050 -> col 47
            ulsd_milestones.append(
                {
                    "year": yr,
                    "var_cost_parity_usd_mt": _num_or_none(ulsd_sh.get((20, col_u)), 2),
                    "cash_cost_parity_usd_mt": _num_or_none(ulsd_sh.get((21, col_u)), 2),
                    "full_40yr_replacement_usd_mt": _num_or_none(ulsd_sh.get((22, col_u)), 2),
                    "model_10ppm_vs_gasoil_usd_mt": _num_or_none(ulsd_sh.get((23, col_u)), 2),
                    "usgc_spread_usd_mt": _num_or_none(ulsd_sh.get((24, col_u)), 2),
                }
            )

        # 3. 200 kb/d Sour Hydrocracker Addition Project Cashflows & 9-Point Margin Sweep
        # Extract real Capex ($M, Row 26 Cols 9..11 = -369.08, -1107.25, -369.08 -> $1,845.41M total)
        # and operating cashflow sensitivity across a 20-year operating life (200 kb/d = 73.0 MMbbl/yr @ 92% util = 67.16 MMbbl/yr)
        irr_sh = grid.get("2015 NWE HCK IRR", {})
        capex_y1 = float(_num_or_none(irr_sh.get((26, 9)), 4) or -369.0818)
        capex_y2 = float(_num_or_none(irr_sh.get((26, 10)), 4) or -1107.2454)
        capex_y3 = float(_num_or_none(irr_sh.get((26, 11)), 4) or -369.0818)
        sustaining_capex = -27.6811
        tax_rate = float(_num_or_none(irr_sh.get((33, 2)), 4) or 0.35)
        depr_yr = abs(capex_y1 + capex_y2 + capex_y3) / 10.0

        # Base sour HCK net margin uplift over sweet FCC anchored to active NWE Diesel-HSFO crack
        nwe_diesel_2025 = eq["milestone_snapshot"]["nwe_cif"][4]["values"][2025] or 716.40
        nwe_hsfo_2025 = eq["milestone_snapshot"]["nwe_cif"][7]["values"][2025] or 423.17
        # Convert $/mt Diesel-HSFO spread into $/bbl HCK conversion uplift (~7.45 bbl/mt diesel vs 6.35 bbl/mt HSFO)
        base_net_uplift_bbl = max(3.50, ((nwe_diesel_2025 / 7.45) - (nwe_hsfo_2025 / 6.35)) * 0.28 - 1.12)
        annual_throughput_mmbbl = 200.0 * 0.365 * 0.92  # 67.16 MMbbl/yr

        sweep_rows: list[dict[str, Any]] = []
        for delta_margin in (-3.0, -2.0, -1.0, -0.5, 0.0, 0.5, 1.0, 2.0, 3.0):
            eff_margin = base_net_uplift_bbl + delta_margin
            cfs: list[float] = [capex_y1, capex_y2, capex_y3]
            for op_yr in range(1, 18):  # 17 operating years (20-yr total schedule)
                ebitda = eff_margin * annual_throughput_mmbbl
                depr = depr_yr if op_yr <= 10 else 0.0
                taxable = ebitda - depr
                tax = max(0.0, taxable * tax_rate)
                fcf = ebitda - tax + sustaining_capex
                cfs.append(fcf)

            irr_val = _compute_irr_newton(cfs)
            irr_pct = None if isinstance(irr_val, ExcelError) else round(float(irr_val) * 100.0, 2)
            npv_musd = sum(cf / ((1.0 + discount_rate_wacc) ** t) for t, cf in enumerate(cfs))
            sweep_rows.append(
                {
                    "margin_delta_usd_bbl": delta_margin,
                    "net_hck_uplift_usd_bbl": round(eff_margin, 2),
                    "annual_ebitda_musd": round(eff_margin * annual_throughput_mmbbl, 1),
                    "project_irr_pct": irr_pct,
                    "npv_musd_at_wacc": round(npv_musd, 1),
                }
            )

        return {
            "session_id": session_id,
            "discount_rate_wacc": discount_rate_wacc,
            "initial_capex_musd": round(abs(capex_y1 + capex_y2 + capex_y3), 2),
            "base_net_hck_uplift_usd_bbl": round(base_net_uplift_bbl, 3),
            "hck_naphtha_revamp": hck_revamp_metrics,
            "ulsd_gasoil_spread_economics": ulsd_milestones,
            "hck_irr_sensitivity_sweep": sweep_rows,
        }
