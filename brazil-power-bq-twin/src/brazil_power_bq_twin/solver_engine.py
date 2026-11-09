"""Self-contained quantitative solver (Tornado IRR, 23-Year LCOE, 30-Year DCF & CVU/GF) for the BigQuery Digital Twin."""

from __future__ import annotations

import copy
import uuid
from datetime import UTC, datetime
from typing import Any

import numpy as np

from brazil_power_bq_twin.bq_store import resolve_effective_cell_value, resolve_effective_grid
from brazil_power_bq_twin.models import (
    AuditRow,
    BaselineTwinSnapshot,
    CellDelta,
    SessionOverlay,
    col_letter_to_index,
    index_to_col_letter,
    split_a1_coord,
)
from brazil_power_bq_twin.renderer import (
    GENERAL_ROWS_SPEC,
    OUTPUT3_COLS,
    TECH_CATALOG,
    TwinMarkdownAndChartRenderer,
)

PARAM_ALIAS_TO_ROW: dict[str, int] = {
    "capacity": 8,
    "capacity_mw": 8,
    "installed_capacity_mw": 8,
    "losses": 10,
    "losses_pct": 10,
    "capex": 11,
    "capex_brl_kw": 11,
    "base_capital_cost": 11,
    "lead_time": 14,
    "lead_time_years": 14,
    "lead_time_yrs": 14,
    "economic_life": 15,
    "economic_life_years": 15,
    "capacity_factor": 16,
    "cf": 16,
    "heat_rate": 17,
    "fuel_cost": 20,
    "fuel_cost_r_per_mmbtu": 20,
    "fuel_cost_usd_per_mmbtu": 20,
    "fixed_om": 23,
    "fixed_om_brl_kw_yr": 23,
    "variable_om": 24,
    "variable_om_brl_mwh": 24,
    "transmission_cost": 27,
    "equity_share": 32,
    "debt_share": 33,
    "wacc": 34,
    "real_wacc": 34,
    "interest_rate": 34,
    "credit_period": 35,
    "loan_tenor_yrs": 35,
    "target_irr": 36,
    "income_tax": 38,
    "exchange_rate": 40,
}


def normalize_tech_code(raw: str) -> str:
    cleaned = raw.strip().upper()
    if cleaned == "ALL":
        return "ALL"
    if not cleaned.startswith("_"):
        cleaned = f"_{cleaned}"
    if not cleaned.endswith("_CF"):
        cleaned = f"{cleaned}_CF"
    if cleaned in TECH_CATALOG:
        return cleaned
    raise ValueError(f"Unknown technology code '{raw}'. Expected one of {sorted(TECH_CATALOG.keys())}.")


def _compute_npv(rate: float, cashflows: np.ndarray) -> float:
    periods = np.arange(len(cashflows), dtype=np.float64)
    return float(np.sum(cashflows / np.power(1.0 + rate, periods)))


def _solve_irr(cashflows: np.ndarray) -> float:
    """Solve periodic IRR via bracketed bisection over [-0.50, 1.50]."""
    if len(cashflows) < 2 or np.all(cashflows >= 0) or np.all(cashflows <= 0):
        return 0.0
    low, high = -0.45, 1.50
    f_low = _compute_npv(low, cashflows)
    f_high = _compute_npv(high, cashflows)
    if f_low * f_high > 0:
        # Grid scan for sign change
        grid = np.linspace(-0.40, 1.20, 81)
        vals = [_compute_npv(float(r), cashflows) for r in grid]
        for i in range(len(grid) - 1):
            if vals[i] * vals[i + 1] <= 0:
                low, high = float(grid[i]), float(grid[i + 1])
                f_low = vals[i]
                break
        else:
            return 0.0
    for _ in range(52):
        mid = 0.5 * (low + high)
        f_mid = _compute_npv(mid, cashflows)
        if abs(f_mid) < 1e-8 or (high - low) < 1e-8:
            return float(mid)
        if f_low * f_mid <= 0:
            high = mid
        else:
            low = mid
            f_low = f_mid
    return float(0.5 * (low + high))


def _resolve_tech_params(
    snapshot: BaselineTwinSnapshot,
    overlay: SessionOverlay,
    tech_code: str,
) -> dict[str, float]:
    """Hydrate active technology parameters by overlaying `General` cells onto `snapshot.solver_parameters`."""
    col_letter = TECH_CATALOG[tech_code]["col"]
    base_p = copy.deepcopy(snapshot.solver_parameters.get(tech_code, {}))

    def _cell_num(row_num: int, fallback: float) -> float:
        val = resolve_effective_cell_value(snapshot, overlay, "General", f"{col_letter}{row_num}")
        if isinstance(val, (int, float)):
            return float(val)
        return fallback

    cap_mw = max(0.1, _cell_num(8, float(base_p.get("capacity_mw", 100.0))))
    losses = min(0.25, max(0.0, _cell_num(10, float(base_p.get("losses_pct", 0.025)))))
    capex_kw = max(100.0, _cell_num(11, float(base_p.get("capex_brl_kw", 4500.0))))
    lead_yrs = max(1, min(8, int(round(_cell_num(14, float(base_p.get("lead_time_yrs", 3.0)))))))
    life_yrs = max(10, min(35, int(round(_cell_num(15, float(base_p.get("economic_life_yrs", 25.0)))))))
    cf_raw = _cell_num(16, float(base_p.get("capacity_factor", 0.50)))
    cf = cf_raw if cf_raw > 0.05 else (0.55 if TECH_CATALOG[tech_code]["group"] == "thermal" else 0.35)
    heat_rate = max(0.0, _cell_num(17, float(base_p.get("heat_rate", 0.0))))
    fuel_cost = max(0.0, _cell_num(20, float(base_p.get("fuel_cost", 0.0))))
    fixed_om = max(0.0, _cell_num(23, float(base_p.get("fixed_om_brl_kw_yr", 40.0))))
    var_om = max(0.0, _cell_num(24, float(base_p.get("variable_om_brl_mwh", 0.0))))
    tust = max(0.0, _cell_num(27, float(base_p.get("transmission_brl_kw_mo", 4.5))))
    eq_share = min(1.0, max(0.05, _cell_num(32, float(base_p.get("equity_share", 0.30)))))
    debt_share = max(0.0, 1.0 - eq_share)
    wacc = min(0.30, max(0.02, _cell_num(34, float(base_p.get("real_wacc", 0.08)))))
    tenor = max(1, min(25, int(round(_cell_num(35, float(base_p.get("loan_tenor_yrs", 16.0)))))))
    target_irr = min(0.35, max(0.03, _cell_num(36, float(base_p.get("target_irr", 0.10)))))
    tax_rate = min(0.45, max(0.0, _cell_num(38, float(base_p.get("income_tax_rate", 0.34)))))
    fx = max(1.0, _cell_num(40, float(base_p.get("fx_brl_per_usd", 3.70))))

    fuel_unit = str(base_p.get("fuel_unit", "")).upper()
    # Convert fuel cost into BRL/MWh
    if heat_rate > 100.0:
        mmbtu_per_mwh = heat_rate / 1000.0
        fuel_brl_mmbtu = fuel_cost * fx if "USD" in fuel_unit else fuel_cost
        fuel_brl_mwh = mmbtu_per_mwh * fuel_brl_mmbtu
    elif fuel_cost > 0 and TECH_CATALOG[tech_code]["group"] != "dg":
        fuel_brl_mwh = fuel_cost * 0.45
    else:
        fuel_brl_mwh = 0.0

    return {
        "capacity_mw": cap_mw,
        "losses_pct": losses,
        "capex_brl_kw": capex_kw,
        "lead_time_yrs": float(lead_yrs),
        "economic_life_yrs": float(life_yrs),
        "capacity_factor": cf,
        "heat_rate": heat_rate,
        "fuel_cost": fuel_cost,
        "fuel_brl_mwh": fuel_brl_mwh,
        "fixed_om_brl_kw_yr": fixed_om,
        "variable_om_brl_mwh": var_om,
        "transmission_brl_kw_mo": tust,
        "equity_share": eq_share,
        "debt_share": debt_share,
        "real_wacc": wacc,
        "loan_tenor_yrs": float(tenor),
        "target_irr": target_irr,
        "income_tax_rate": tax_rate,
        "fx_brl_per_usd": fx,
    }


def _simulate_cashflows(params: dict[str, float], tariff_brl_mwh: float, horizon_years: int = 30) -> dict[str, Any]:
    """Run a 30-year project and equity cash-flow simulation (in Million BRL)."""
    cap_mw = params["capacity_mw"]
    cap_kw = cap_mw * 1000.0
    lead = max(1, int(round(params["lead_time_yrs"])))
    life = max(5, int(round(params["economic_life_yrs"])))
    total_capex_m = (cap_kw * params["capex_brl_kw"]) / 1e6
    annual_net_mwh = cap_mw * 8760.0 * params["capacity_factor"] * (1.0 - params["losses_pct"])

    fixed_opex_m = (cap_kw * (params["fixed_om_brl_kw_yr"] + 12.0 * params["transmission_brl_kw_mo"])) / 1e6
    var_opex_per_mwh = params["fuel_brl_mwh"] + params["variable_om_brl_mwh"]

    debt_total_m = total_capex_m * params["debt_share"]
    tenor = max(1, int(round(params["loan_tenor_yrs"])))
    debt_rate = max(0.03, params["real_wacc"] * 0.85)
    annual_depr_m = total_capex_m / min(life, 20)

    proj_fcf = np.zeros(horizon_years, dtype=np.float64)
    eq_fcf = np.zeros(horizon_years, dtype=np.float64)
    rows: list[dict[str, Any]] = []

    rem_debt = debt_total_m
    cum_npv = 0.0
    wacc = params["real_wacc"]

    for t in range(horizon_years):
        yr = 2024 + t
        if t < lead:
            capex_t = total_capex_m / lead
            eq_capex_t = capex_t * params["equity_share"]
            proj_fcf[t] = -capex_t
            eq_fcf[t] = -eq_capex_t
            cum_npv += proj_fcf[t] / ((1.0 + wacc) ** t)
            rows.append(
                {
                    "year": yr,
                    "net_gen_gwh": 0.0,
                    "revenue_m_brl": 0.0,
                    "opex_m_brl": 0.0,
                    "ebitda_m_brl": 0.0,
                    "capex_m_brl": capex_t,
                    "tax_m_brl": 0.0,
                    "project_fcf_m_brl": proj_fcf[t],
                    "equity_fcf_m_brl": eq_fcf[t],
                    "cum_npv_m_brl": cum_npv,
                }
            )
        elif t < lead + life:
            op_idx = t - lead
            rev_m = (annual_net_mwh * tariff_brl_mwh) / 1e6
            # 9.25% PIS/COFINS net revenue deduction approximation
            net_rev_m = rev_m * 0.9075
            opex_m = fixed_opex_m + (annual_net_mwh * var_opex_per_mwh) / 1e6
            ebitda_m = net_rev_m - opex_m
            depr_m = annual_depr_m if op_idx < 20 else 0.0

            interest_m = rem_debt * debt_rate if (op_idx < tenor and rem_debt > 0) else 0.0
            principal_m = (debt_total_m / tenor) if (op_idx < tenor and rem_debt > 0) else 0.0
            rem_debt = max(0.0, rem_debt - principal_m)

            ebt_unlev = max(0.0, ebitda_m - depr_m)
            tax_unlev = ebt_unlev * params["income_tax_rate"]
            pfcf = ebitda_m - tax_unlev

            ebt_lev = max(0.0, ebitda_m - depr_m - interest_m)
            tax_lev = ebt_lev * params["income_tax_rate"]
            efcf = ebitda_m - tax_lev - interest_m - principal_m

            proj_fcf[t] = pfcf
            eq_fcf[t] = efcf
            cum_npv += pfcf / ((1.0 + wacc) ** t)
            rows.append(
                {
                    "year": yr,
                    "net_gen_gwh": annual_net_mwh / 1000.0,
                    "revenue_m_brl": rev_m,
                    "opex_m_brl": opex_m,
                    "ebitda_m_brl": ebitda_m,
                    "capex_m_brl": 0.0,
                    "tax_m_brl": tax_unlev,
                    "project_fcf_m_brl": pfcf,
                    "equity_fcf_m_brl": efcf,
                    "cum_npv_m_brl": cum_npv,
                }
            )
        else:
            rows.append(
                {
                    "year": yr,
                    "net_gen_gwh": 0.0,
                    "revenue_m_brl": 0.0,
                    "opex_m_brl": 0.0,
                    "ebitda_m_brl": 0.0,
                    "capex_m_brl": 0.0,
                    "tax_m_brl": 0.0,
                    "project_fcf_m_brl": 0.0,
                    "equity_fcf_m_brl": 0.0,
                    "cum_npv_m_brl": cum_npv,
                }
            )

    return {
        "total_capex_m_brl": total_capex_m,
        "project_fcf": proj_fcf,
        "equity_fcf": eq_fcf,
        "project_irr": _solve_irr(proj_fcf),
        "equity_irr": _solve_irr(eq_fcf),
        "project_npv_m_brl": cum_npv,
        "annual_rows": rows,
    }


def _solve_lcoe_tariff(params: dict[str, float], target_discount_rate: float | None = None) -> float:
    """Binary-search the break-even tariff (BRL/MWh) where Project NPV == 0 at `target_discount_rate`."""
    disc = target_discount_rate if target_discount_rate is not None else params["target_irr"]
    p_copy = dict(params)
    p_copy["real_wacc"] = disc

    low_t, high_t = 10.0, 3500.0
    for _ in range(44):
        mid_t = 0.5 * (low_t + high_t)
        sim = _simulate_cashflows(p_copy, tariff_brl_mwh=mid_t)
        if sim["project_npv_m_brl"] < 0:
            low_t = mid_t
        else:
            high_t = mid_t
    return float(0.5 * (low_t + high_t))


class QuantitativeTwinSolver:
    """Stateless quantitative solver operating over `BaselineTwinSnapshot` + `SessionOverlay`."""

    @staticmethod
    def extract_assumptions(
        snapshot: BaselineTwinSnapshot,
        overlay: SessionOverlay,
        technologies: list[str] | None = None,
    ) -> dict[str, Any]:
        inline_techs = (
            [normalize_tech_code(t) for t in technologies if normalize_tech_code(t) != "ALL"]
            if technologies
            else ["_01_CF", "_04_CF", "_05_CF", "_06_CF"]
        )
        active_by_tech: dict[str, dict[int, Any]] = {}
        base_by_tech: dict[str, dict[int, Any]] = {}
        for t_code, meta in TECH_CATALOG.items():
            col = meta["col"]
            active_by_tech[t_code] = {}
            base_by_tech[t_code] = {}
            for r_num, _, _, _ in GENERAL_ROWS_SPEC:
                coord = f"{col}{r_num}"
                base_cell = snapshot.get_cell("General", coord)
                base_val = base_cell.effective_baseline_value if base_cell else None
                base_by_tech[t_code][r_num] = base_val
                active_by_tech[t_code][r_num] = resolve_effective_cell_value(snapshot, overlay, "General", coord)

        inline_md, full_md = TwinMarkdownAndChartRenderer.render_assumptions_tables(
            active_by_tech=active_by_tech,
            base_by_tech=base_by_tech,
            inline_techs=inline_techs,
        )
        return {
            "inline_markdown": inline_md,
            "artifact_markdown": full_md,
            "full_artifact_table_md": full_md,
            "active_overrides": overlay.user_overrides_flat(),
        }

    @staticmethod
    def stage_overrides(
        snapshot: BaselineTwinSnapshot,
        overlay: SessionOverlay,
        overrides: dict[str, Any] | None,
        who_principal: str = "cowork-analyst@comm-model-mod",
    ) -> tuple[list[CellDelta], list[AuditRow], list[dict[str, Any]]]:
        deltas: list[CellDelta] = []
        audits: list[AuditRow] = []
        changes: list[dict[str, Any]] = []
        now_iso = datetime.now(UTC).isoformat()

        for key, raw_val in (overrides or {}).items():
            if isinstance(raw_val, dict):
                t_code = normalize_tech_code(key)
                col_letter = TECH_CATALOG[t_code]["col"]
                for param_name, p_val in raw_val.items():
                    clean_p = param_name.strip().lower()
                    if clean_p not in PARAM_ALIAS_TO_ROW:
                        raise ValueError(f"Unsupported parameter alias '{param_name}' for {t_code}.")
                    row_num = PARAM_ALIAS_TO_ROW[clean_p]
                    coord = f"{col_letter}{row_num}"
                    col_idx = col_letter_to_index(col_letter)
                    old_val = resolve_effective_cell_value(snapshot, overlay, "General", coord)
                    f_val = float(p_val)
                    deltas.append(
                        CellDelta(
                            sheet_name="General",
                            cell_coord=coord,
                            row_num=row_num,
                            col_num=col_idx,
                            delta_kind="USER_OVERRIDE",
                            numeric_value=f_val,
                            source_tool="update_session_assumptions",
                            updated_at=now_iso,
                        )
                    )
                    audits.append(
                        AuditRow(
                            event_id=str(uuid.uuid4()),
                            session_id=overlay.session_id,
                            what_sheet="General",
                            what_coord=coord,
                            what_change_type="USER_OVERRIDE",
                            before_value=str(old_val),
                            after_value=str(f_val),
                            who_principal=who_principal,
                            when_event_utc=now_iso,
                            why_context=f"Digital Twin override on {t_code} ({param_name})",
                        )
                    )
                    changes.append(
                        {
                            "sheet": "General",
                            "cell": coord,
                            "technology_code": t_code,
                            "parameter": param_name,
                            "old_value": old_val,
                            "new_value": f_val,
                        }
                    )
            else:
                sheet_name, raw_coord = key.split("!", 1) if "!" in key else ("General", key)
                col_letter, row_num = split_a1_coord(raw_coord)
                coord = f"{col_letter}{row_num}"
                col_idx = col_letter_to_index(col_letter)
                old_val = resolve_effective_cell_value(snapshot, overlay, sheet_name, coord)
                f_val = float(raw_val)
                deltas.append(
                    CellDelta(
                        sheet_name=sheet_name,
                        cell_coord=coord,
                        row_num=row_num,
                        col_num=col_idx,
                        delta_kind="USER_OVERRIDE",
                        numeric_value=f_val,
                        source_tool="update_session_assumptions",
                        updated_at=now_iso,
                    )
                )
                audits.append(
                    AuditRow(
                        event_id=str(uuid.uuid4()),
                        session_id=overlay.session_id,
                        what_sheet=sheet_name,
                        what_coord=coord,
                        what_change_type="USER_OVERRIDE",
                        before_value=str(old_val),
                        after_value=str(f_val),
                        who_principal=who_principal,
                        when_event_utc=now_iso,
                        why_context=f"Direct cell override on {sheet_name}!{coord}",
                    )
                )
                changes.append(
                    {
                        "sheet": sheet_name,
                        "cell": coord,
                        "old_value": old_val,
                        "new_value": f_val,
                    }
                )
        return deltas, audits, changes

    @staticmethod
    def run_tornado_sensitivity(
        snapshot: BaselineTwinSnapshot,
        overlay: SessionOverlay,
        technology_code: str = "_06_CF",
    ) -> tuple[dict[str, Any], list[CellDelta]]:
        norm = normalize_tech_code(technology_code)
        target_code = "_06_CF" if norm == "ALL" else norm
        params = _resolve_tech_params(snapshot, overlay, target_code)
        eq_tariff = _solve_lcoe_tariff(params, target_discount_rate=params["target_irr"])
        # Evaluate at slight commercial premium so base IRR aligns near target_irr
        tariff = eq_tariff
        base_irr = _simulate_cashflows(params, tariff)["project_irr"]

        levers = [
            (6, "CAPEX (BRL/kW)", "capex_brl_kw"),
            (7, "Fuel / Capacity Factor", "fuel_brl_mwh" if params["fuel_brl_mwh"] > 0 else "capacity_factor"),
            (8, "Transmission Tariff (TUST)", "transmission_brl_kw_mo"),
            (9, "Fixed O&M (BRL/kW-yr)", "fixed_om_brl_kw_yr"),
            (10, "Variable O&M (BRL/MWh)", "variable_om_brl_mwh"),
            (11, "Real WACC (%)", "real_wacc"),
            (12, "Economic Life (yrs)", "economic_life_yrs"),
        ]

        tornado_rows: list[dict[str, Any]] = []
        deltas: list[CellDelta] = []
        now_iso = datetime.now(UTC).isoformat()

        for excel_row, label, p_key in levers:
            base_in = float(params[p_key])
            low_in = base_in * 0.85
            high_in = base_in * 1.15

            p_low = dict(params)
            p_low[p_key] = low_in
            irr_low = _simulate_cashflows(p_low, tariff)["project_irr"]

            p_high = dict(params)
            p_high[p_key] = high_in
            irr_high = _simulate_cashflows(p_high, tariff)["project_irr"]

            tornado_rows.append(
                {
                    "excel_row": excel_row,
                    "parameter": label,
                    "low_input": low_in,
                    "base_input": base_in,
                    "high_input": high_in,
                    "irr_low": irr_low,
                    "irr_base": base_irr,
                    "irr_high": irr_high,
                }
            )
            for col_let, col_num, val in (("E", 5, irr_low), ("F", 6, base_irr), ("G", 7, irr_high)):
                deltas.append(
                    CellDelta(
                        sheet_name=target_code,
                        cell_coord=f"{col_let}{excel_row}",
                        row_num=excel_row,
                        col_num=col_num,
                        delta_kind="SOLVED_OUTPUT",
                        numeric_value=val,
                        source_tool="run_tornado_sensitivity",
                        updated_at=now_iso,
                    )
                )

        inline_md, full_md, echarts = TwinMarkdownAndChartRenderer.render_tornado_outputs(
            technology_code=target_code,
            tech_label=TECH_CATALOG[target_code]["label"],
            base_irr=base_irr,
            tornado_rows=tornado_rows,
        )
        return (
            {
                "technology_code": target_code,
                "technology_label": TECH_CATALOG[target_code]["label"],
                "base_irr": base_irr,
                "equilibrium_tariff_brl_mwh": tariff,
                "solve_count": len(levers) * 3,
                "tornado_rows": tornado_rows,
                "inline_markdown": inline_md,
                "artifact_markdown": full_md,
                "full_artifact_table_md": full_md,
                "echarts_option": echarts,
            },
            deltas,
        )

    @staticmethod
    def run_lcoe_horizon(
        snapshot: BaselineTwinSnapshot,
        overlay: SessionOverlay,
    ) -> tuple[dict[str, Any], list[CellDelta]]:
        years = list(range(2024, 2047))
        capex_grid = resolve_effective_grid(snapshot, overlay, "LT Capex", "B8", "J30")
        fuel_grid = resolve_effective_grid(snapshot, overlay, "LT Fuel", "B8", "J30")
        cf_grid = resolve_effective_grid(snapshot, overlay, "LT CF", "B8", "J30")

        base_params = {
            t_code: _resolve_tech_params(snapshot, overlay, t_code)
            for _, t_code, _ in OUTPUT3_COLS
        }

        lcoe_grid: list[list[float | None]] = []
        deltas: list[CellDelta] = []
        now_iso = datetime.now(UTC).isoformat()

        for yr_idx, _ in enumerate(years):
            row_num = 9 + yr_idx
            row_vals: list[float | None] = []
            for c_offset, (out_col, t_code, _) in enumerate(OUTPUT3_COLS):
                p = dict(base_params[t_code])
                cap_mult = capex_grid[yr_idx][c_offset] if yr_idx < len(capex_grid) else 1.0
                fuel_mult = fuel_grid[yr_idx][c_offset] if yr_idx < len(fuel_grid) else 1.0
                cf_entry = cf_grid[yr_idx][c_offset] if yr_idx < len(cf_grid) else None

                if isinstance(cap_mult, (int, float)) and cap_mult > 0:
                    p["capex_brl_kw"] = p["capex_brl_kw"] * (float(cap_mult) if cap_mult < 10 else float(cap_mult) / max(1.0, p["capex_brl_kw"]))
                if isinstance(fuel_mult, (int, float)) and fuel_mult > 0 and p["fuel_brl_mwh"] > 0:
                    if fuel_mult < 10.0:
                        p["fuel_brl_mwh"] = p["fuel_brl_mwh"] * float(fuel_mult)
                if isinstance(cf_entry, (int, float)) and 0.05 < float(cf_entry) <= 1.0:
                    p["capacity_factor"] = float(cf_entry)

                solved_lcoe = _solve_lcoe_tariff(p, target_discount_rate=p["real_wacc"])
                row_vals.append(solved_lcoe)
                deltas.append(
                    CellDelta(
                        sheet_name="Output_3",
                        cell_coord=f"{out_col}{row_num}",
                        row_num=row_num,
                        col_num=col_letter_to_index(out_col),
                        delta_kind="SOLVED_OUTPUT",
                        numeric_value=solved_lcoe,
                        source_tool="run_lcoe_horizon_forecast",
                        updated_at=now_iso,
                    )
                )
            lcoe_grid.append(row_vals)

        inline_md, full_md, echarts = TwinMarkdownAndChartRenderer.render_lcoe_outputs(years, lcoe_grid)
        return (
            {
                "years": years,
                "solve_count": len(years) * len(OUTPUT3_COLS),
                "lcoe_grid": lcoe_grid,
                "inline_markdown": inline_md,
                "artifact_markdown": full_md,
                "full_artifact_table_md": full_md,
                "echarts_option": echarts,
            },
            deltas,
        )

    @staticmethod
    def run_dcf_and_cvu(
        snapshot: BaselineTwinSnapshot,
        overlay: SessionOverlay,
        technology_code: str = "_01_CF",
        start_year: int = 2024,
        end_year: int = 2053,
        include_cvu_sweep: bool | None = None,
    ) -> tuple[dict[str, Any], list[CellDelta]]:
        norm = normalize_tech_code(technology_code)
        target_code = "_01_CF" if norm == "ALL" else norm
        params = _resolve_tech_params(snapshot, overlay, target_code)

        # Solve baseline equilibrium tariff using seed parameters (without active overrides) so overrides move IRR/NPV realistically
        seed_overlay = SessionOverlay(
            session_id="baseline_ref",
            workbook_id=snapshot.workbook_id,
            base_version_id=snapshot.version_id,
        )
        seed_params = _resolve_tech_params(snapshot, seed_overlay, target_code)
        ref_tariff = _solve_lcoe_tariff(seed_params, target_discount_rate=seed_params["target_irr"])

        horizon = max(10, end_year - start_year + 1)
        sim = _simulate_cashflows(params, tariff_brl_mwh=ref_tariff, horizon_years=horizon)

        deltas: list[CellDelta] = []
        now_iso = datetime.now(UTC).isoformat()
        for idx, r in enumerate(sim["annual_rows"][:30]):
            col_idx = 11 + idx  # Col K..AN
            col_let = index_to_col_letter(col_idx)
            deltas.append(
                CellDelta(
                    sheet_name=target_code,
                    cell_coord=f"{col_let}65",
                    row_num=65,
                    col_num=col_idx,
                    delta_kind="SOLVED_OUTPUT",
                    numeric_value=float(r["project_fcf_m_brl"]),
                    source_tool="run_dcf_cashflow_analysis",
                    updated_at=now_iso,
                )
            )

        do_cvu = (
            include_cvu_sweep
            if include_cvu_sweep is not None
            else (TECH_CATALOG[target_code]["group"] == "thermal")
        )
        cvu_rows: list[dict[str, Any]] | None = None
        if do_cvu:
            cvu_rows = []
            for step_idx, disp in enumerate(np.linspace(0.10, 1.00, 10), start=1):
                p_disp = dict(params)
                p_disp["capacity_factor"] = float(disp) * 0.92
                cvu_val = params["fuel_brl_mwh"] + params["variable_om_brl_mwh"]
                gf_mwmed = params["capacity_mw"] * float(disp) * (1.0 - params["losses_pct"])
                icb_val = _solve_lcoe_tariff(p_disp, target_discount_rate=params["real_wacc"])
                cvu_rows.append(
                    {
                        "dispatch_pct": float(disp),
                        "cvu_brl_mwh": cvu_val,
                        "gf_mwmed": gf_mwmed,
                        "icb_brl_mwh": icb_val,
                    }
                )
                deltas.append(
                    CellDelta(
                        sheet_name="CVU_GF",
                        cell_coord=f"D{5 + step_idx}",
                        row_num=5 + step_idx,
                        col_num=4,
                        delta_kind="SOLVED_OUTPUT",
                        numeric_value=icb_val,
                        source_tool="run_dcf_cashflow_analysis",
                        updated_at=now_iso,
                    )
                )

        summary = {
            "capacity_mw": params["capacity_mw"],
            "total_capex_m_brl": sim["total_capex_m_brl"],
            "tariff_brl_mwh": ref_tariff,
            "project_irr": sim["project_irr"],
            "equity_irr": sim["equity_irr"],
            "project_npv_m_brl": sim["project_npv_m_brl"],
        }
        inline_md, full_md, echarts = TwinMarkdownAndChartRenderer.render_dcf_outputs(
            technology_code=target_code,
            tech_label=TECH_CATALOG[target_code]["label"],
            summary=summary,
            annual_rows=sim["annual_rows"],
            cvu_rows=cvu_rows,
        )
        res: dict[str, Any] = {
            "technology_code": target_code,
            "technology_label": TECH_CATALOG[target_code]["label"],
            **summary,
            "annual_rows": sim["annual_rows"],
            "inline_markdown": inline_md,
            "artifact_markdown": full_md,
            "full_artifact_table_md": full_md,
            "echarts_option": echarts,
        }
        if cvu_rows is not None:
            res["cvu_gf_sweep"] = cvu_rows
        return res, deltas
