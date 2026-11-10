"""Markdown Excel-coordinate table and Apache ECharts V5 specification renderer for the BigQuery Digital Twin."""

from __future__ import annotations

import re
from typing import Any

TECH_CATALOG: dict[str, dict[str, Any]] = {
    "_01_CF": {"col": "C", "label": "Gas CCGT", "group": "thermal", "lt_idx": 0},
    "_02_CF": {"col": "D", "label": "Biomass CHP", "group": "renewable", "lt_idx": 1},
    "_03_CF": {"col": "E", "label": "Biomass Retrofit", "group": "renewable", "lt_idx": 2},
    "_04_CF": {"col": "F", "label": "Onshore Wind", "group": "renewable", "lt_idx": 4},
    "_05_CF": {"col": "G", "label": "Utility Solar PV", "group": "renewable", "lt_idx": 5},
    "_06_CF": {"col": "H", "label": "Small Hydro (SHP)", "group": "renewable", "lt_idx": 7},
    "_07_CF": {"col": "I", "label": "Local Coal (CFBC)", "group": "thermal", "lt_idx": 8},
    "_08_CF": {"col": "J", "label": "Imported Coal (PC)", "group": "thermal", "lt_idx": 6},
    "_09_CF": {"col": "K", "label": "Biomass Woodchip", "group": "renewable", "lt_idx": 3},
    "_10_CF": {"col": "L", "label": "LNG CCGT", "group": "thermal", "lt_idx": 0},
    "_11_CF": {"col": "M", "label": "DG Solar Residential", "group": "dg", "lt_idx": 5},
    "_12_CF": {"col": "N", "label": "DG Solar Commercial", "group": "dg", "lt_idx": 5},
}

OUTPUT3_COLS: tuple[tuple[str, str, str], ...] = (
    ("B", "_01_CF", "Gas CCGT"),
    ("C", "_02_CF", "Biomass CHP"),
    ("D", "_03_CF", "Biomass Retrofit"),
    ("E", "_09_CF", "Biomass Woodchip"),
    ("F", "_04_CF", "Onshore Wind"),
    ("G", "_05_CF", "Utility Solar PV"),
    ("H", "_08_CF", "Imported Coal PC"),
    ("I", "_06_CF", "Small Hydro SHP"),
    ("J", "_07_CF", "Local Coal CFBC"),
)

GENERAL_ROWS_SPEC: tuple[tuple[int, str, str, str], ...] = (
    (8, "Capacity (MW / kW)", "MW/kW", "num1"),
    (9, "Net capacity (MW)", "MW", "num2"),
    (10, "General losses (%)", "%", "pct1"),
    (11, "Base capital cost (BRL/kW)", "BRL/kW", "num2"),
    (14, "Construction lead time (yrs)", "yrs", "num1"),
    (15, "Plant economic life (yrs)", "yrs", "num1"),
    (16, "Capacity factor", "%", "pct1"),
    (17, "Heat rate", "Btu/kWh", "num0"),
    (20, "Fuel cost", "USD or BRL/MMBtu", "num2"),
    (23, "Fixed O&M (BRL/kW-yr)", "BRL/kW-yr", "num2"),
    (24, "Variable O&M (BRL/MWh)", "BRL/MWh", "num2"),
    (27, "Transmission tariff (BRL/kW-mo)", "BRL/kW-mo", "num2"),
    (32, "Equity share", "%", "pct1"),
    (33, "Debt share", "%", "pct1"),
    (34, "Real WACC / Interest Rate", "%", "pct2"),
    (35, "Credit period (yrs)", "yrs", "num1"),
    (36, "Target IRR", "%", "pct2"),
    (38, "Income tax rate", "%", "pct1"),
    (40, "Exchange rate (BRL/USD)", "BRL/USD", "num2"),
)


def normalize_multiline_markdown(md: str) -> str:
    """Guarantee every Markdown table row terminates with a physical newline and avoid '$' currency math triggers."""
    cleaned = md.replace("R$", "BRL ").replace("US$", "USD ")
    cleaned = re.sub(r"\|\s+\|(?=\s*[:\-`A-Za-z0-9_*])", "|\n|", cleaned)
    return cleaned.strip() + "\n"


def _fmt_cell(val: Any, fmt_kind: str) -> str:
    if val is None or val == "":
        return "-"
    if not isinstance(val, (int, float)):
        return str(val)
    fval = float(val)
    if fmt_kind == "pct1":
        return f"{fval * 100.0:.1f}%"
    if fmt_kind == "pct2":
        return f"{fval * 100.0:.2f}%"
    if fmt_kind == "num0":
        return f"{fval:,.0f}"
    if fmt_kind == "num1":
        return f"{fval:,.1f}"
    return f"{fval:,.2f}"


class TwinMarkdownAndChartRenderer:
    """Renders Markdown Excel-coordinate tables and Apache ECharts V5 JSON specs."""

    @staticmethod
    def render_assumptions_tables(
        active_by_tech: dict[str, dict[int, Any]],
        base_by_tech: dict[str, dict[int, Any]],
        inline_techs: list[str],
    ) -> tuple[str, str]:
        all_techs = list(TECH_CATALOG.keys())

        def _build_table(title: str, tech_list: list[str]) -> str:
            headers = ["Row", "Parameter (`General!B`)", "Unit"] + [
                f"Col {TECH_CATALOG[t]['col']}: {TECH_CATALOG[t]['label']} (`{t}`)" for t in tech_list
            ]
            align = [":---:", ":---", ":---:"] + ["---:" for _ in tech_list]
            lines = [
                f"# {title}",
                "",
                "| " + " | ".join(headers) + " |",
                "| " + " | ".join(align) + " |",
            ]
            for row_num, label, unit, fmt_kind in GENERAL_ROWS_SPEC:
                row_cells = [f"`{row_num}`", f"**{label}**", unit]
                for t in tech_list:
                    cur = active_by_tech.get(t, {}).get(row_num)
                    base = base_by_tech.get(t, {}).get(row_num)
                    cur_str = _fmt_cell(cur, fmt_kind)
                    if isinstance(cur, (int, float)) and isinstance(base, (int, float)) and abs(float(cur) - float(base)) > 1e-6:
                        row_cells.append(f"**{cur_str}** *(was {_fmt_cell(base, fmt_kind)})*")
                    else:
                        row_cells.append(cur_str)
                lines.append("| " + " | ".join(row_cells) + " |")
            return normalize_multiline_markdown("\n".join(lines))

        inline_md = _build_table("BigQuery Digital Twin — Selected `General!C5:N40` Assumptions", inline_techs)
        full_md = _build_table("Full 12-Technology BigQuery Digital Twin Replica: `General!B5:N40`", all_techs)
        return inline_md, full_md

    @staticmethod
    def render_tornado_outputs(
        technology_code: str,
        tech_label: str,
        base_irr: float,
        tornado_rows: list[dict[str, Any]],
    ) -> tuple[str, str, dict[str, Any]]:
        lines = [
            f"### Tornado IRR Sensitivity (`{technology_code}!A4:H12` — {tech_label})",
            f"- **Base Case Project IRR**: `{base_irr * 100.0:.2f}%` | **Backend**: `BigQuery Digital Twin (0 Excel files)`",
            "",
            "| Excel Row | Parameter | Low Input (`Col B`) | Base Input (`Col C`) | High Input (`Col D`) | IRR @ Low (`Col E`) | Base IRR (`Col F`) | IRR @ High (`Col G`) | Swing (bps) |",
            "| :---: | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
        sorted_rows = sorted(tornado_rows, key=lambda r: abs(r["irr_high"] - r["irr_low"]), reverse=True)
        for r in tornado_rows:
            swing_bps = abs(r["irr_high"] - r["irr_low"]) * 10000.0
            lines.append(
                f"| `{r['excel_row']}` | **{r['parameter']}** | {r['low_input']:,.2f} | {r['base_input']:,.2f} | "
                f"{r['high_input']:,.2f} | {r['irr_low'] * 100.0:.2f}% | {r['irr_base'] * 100.0:.2f}% | "
                f"{r['irr_high'] * 100.0:.2f}% | `{swing_bps:,.0f}` |"
            )
        md = normalize_multiline_markdown("\n".join(lines))

        categories = [r["parameter"] for r in reversed(sorted_rows)]
        low_deltas = [round((r["irr_low"] - base_irr) * 100.0, 2) for r in reversed(sorted_rows)]
        high_deltas = [round((r["irr_high"] - base_irr) * 100.0, 2) for r in reversed(sorted_rows)]

        echarts = {
            "title": {
                "text": f"Brazil Power v13 Tornado IRR Sensitivity — {tech_label} ({technology_code})",
                "subtext": f"Base IRR: {base_irr * 100.0:.2f}% | Source: BigQuery Digital Twin",
            },
            "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
            "legend": {"data": ["-15% Input Shock (Δ IRR %)", "+15% Input Shock (Δ IRR %)"], "bottom": 0},
            "grid": {"left": "22%", "right": "8%", "top": "16%", "bottom": "14%"},
            "xAxis": {"type": "value", "name": "Δ IRR (% pts)"},
            "yAxis": {"type": "category", "data": categories},
            "series": [
                {"name": "-15% Input Shock (Δ IRR %)", "type": "bar", "data": low_deltas},
                {"name": "+15% Input Shock (Δ IRR %)", "type": "bar", "data": high_deltas},
            ],
        }
        return md, md, echarts

    @staticmethod
    def render_lcoe_outputs(
        years: list[int],
        lcoe_grid: list[list[float | None]],
    ) -> tuple[str, str, dict[str, Any]]:
        col_headers = ["Year (`Col A`)"] + [f"`Col {c}`: {lbl}" for c, _, lbl in OUTPUT3_COLS]
        align = [":---:"] + ["---:" for _ in OUTPUT3_COLS]

        def _rows_md(title: str, filter_years: set[int] | None) -> str:
            out = [f"# {title}", "", "| " + " | ".join(col_headers) + " |", "| " + " | ".join(align) + " |"]
            for idx, yr in enumerate(years):
                if filter_years is not None and yr not in filter_years:
                    continue
                vals = [f"`{yr}`"] + [
                    "-" if v is None else f"{v:,.2f}" for v in lcoe_grid[idx]
                ]
                out.append("| " + " | ".join(vals) + " |")
            return normalize_multiline_markdown("\n".join(out))

        milestones = {2024, 2025, 2030, 2035, 2040, 2046}
        inline_md = _rows_md("23-Year LCOE Horizon Milestones (`Output_3!B8:J31`, BRL/MWh)", milestones)
        full_md = _rows_md("Full 23-Year LCOE Horizon Digital Twin Replica: `Output_3!B8:J31` (BRL/MWh)", None)

        series = []
        for col_idx, (_, _, lbl) in enumerate(OUTPUT3_COLS):
            pts = [round(row[col_idx], 2) if row[col_idx] is not None else None for row in lcoe_grid]
            if any(p is not None for p in pts):
                series.append({"name": lbl, "type": "line", "smooth": True, "data": pts})

        echarts = {
            "title": {
                "text": "23-Year Multi-Technology LCOE Trajectory (2024–2046)",
                "subtext": "BRL/MWh | BigQuery Digital Twin Solver",
            },
            "tooltip": {"trigger": "axis"},
            "legend": {"bottom": 0},
            "xAxis": {"type": "category", "data": [str(y) for y in years]},
            "yAxis": {"type": "value", "name": "LCOE (BRL/MWh)"},
            "series": series,
        }
        return inline_md, full_md, echarts

    @staticmethod
    def render_dcf_outputs(
        technology_code: str,
        tech_label: str,
        summary: dict[str, float],
        annual_rows: list[dict[str, Any]],
        cvu_rows: list[dict[str, Any]] | None = None,
    ) -> tuple[str, str, dict[str, Any]]:
        header_block = [
            f"# 30-Year Project & Equity DCF — {tech_label} (`{technology_code}`)",
            "",
            "| Metric | Value | Unit |",
            "| :--- | ---: | :---: |",
            f"| **Installed Capacity** | {summary['capacity_mw']:,.1f} | MW |",
            f"| **Total CAPEX** | {summary['total_capex_m_brl']:,.2f} | M BRL |",
            f"| **Equilibrium / Base Tariff** | {summary['tariff_brl_mwh']:,.2f} | BRL/MWh |",
            f"| **Project IRR (Unlevered)** | {summary['project_irr'] * 100.0:.2f}% | % |",
            f"| **Equity IRR (Levered)** | {summary['equity_irr'] * 100.0:.2f}% | % |",
            f"| **Project NPV (@ Real WACC)** | {summary['project_npv_m_brl']:,.2f} | M BRL |",
            "",
        ]

        def _schedule_table(rows_subset: list[dict[str, Any]]) -> list[str]:
            tbl = [
                "| Year | Net Gen (GWh) | Revenue (M BRL) | Fuel + O&M (M BRL) | EBITDA (M BRL) | CAPEX (M BRL) | Tax (M BRL) | Project FCF (M BRL) | Equity FCF (M BRL) | Cum. NPV (M BRL) |",
                "| :---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
            for r in rows_subset:
                tbl.append(
                    f"| `{r['year']}` | {r['net_gen_gwh']:,.1f} | {r['revenue_m_brl']:,.2f} | "
                    f"{r['opex_m_brl']:,.2f} | {r['ebitda_m_brl']:,.2f} | {r['capex_m_brl']:,.2f} | "
                    f"{r['tax_m_brl']:,.2f} | {r['project_fcf_m_brl']:,.2f} | {r['equity_fcf_m_brl']:,.2f} | "
                    f"{r['cum_npv_m_brl']:,.2f} |"
                )
            return tbl

        milestone_years = {2024, 2025, 2026, 2028, 2030, 2035, 2040, 2045, 2050, 2053}
        inline_lines = header_block + ["### Milestone Cash-Flow Schedule (M BRL)", ""] + _schedule_table(
            [r for r in annual_rows if r["year"] in milestone_years]
        )
        full_lines = header_block + ["### Complete 30-Year Horizontal Cash-Flow Schedule (`2024–2053`, M BRL)", ""] + _schedule_table(
            annual_rows
        )

        if cvu_rows:
            cvu_tbl = [
                "",
                "### 10-Point Thermal CVU & Physical Guarantee Sweep (`CVU_GF`)",
                "",
                "| Dispatch Factor (%) | Variable Cost CVU (BRL/MWh) | Physical Guarantee (MWmed) | Required ICB Tariff (BRL/MWh) |",
                "| :---: | ---: | ---: | ---: |",
            ]
            for cr in cvu_rows:
                cvu_tbl.append(
                    f"| {cr['dispatch_pct'] * 100.0:.0f}% | {cr['cvu_brl_mwh']:,.2f} | "
                    f"{cr['gf_mwmed']:,.2f} | {cr['icb_brl_mwh']:,.2f} |"
                )
            inline_lines.extend(cvu_tbl)
            full_lines.extend(cvu_tbl)

        echarts = {
            "title": {
                "text": f"30-Year Project Free Cash Flow & Cumulative NPV — {tech_label}",
                "subtext": f"Project IRR: {summary['project_irr'] * 100.0:.2f}% | NPV: {summary['project_npv_m_brl']:,.1f} M BRL",
            },
            "tooltip": {"trigger": "axis"},
            "legend": {"data": ["Project FCF (M BRL)", "Cumulative NPV (M BRL)"], "bottom": 0},
            "xAxis": {"type": "category", "data": [str(r["year"]) for r in annual_rows]},
            "yAxis": {"type": "value", "name": "Million BRL"},
            "series": [
                {"name": "Project FCF (M BRL)", "type": "bar", "data": [round(r["project_fcf_m_brl"], 2) for r in annual_rows]},
                {"name": "Cumulative NPV (M BRL)", "type": "line", "smooth": True, "data": [round(r["cum_npv_m_brl"], 2) for r in annual_rows]},
            ],
        }
        return normalize_multiline_markdown("\n".join(inline_lines)), normalize_multiline_markdown("\n".join(full_lines)), echarts
