"""Excel-Layout Markdown Table and Apache ECharts V5 Specification Renderer for Brazil Power v13."""

from __future__ import annotations

from typing import Any


TECH_SPECS: dict[str, dict[str, Any]] = {
    "_01_CF": {
        "index": 1,
        "code": "_01_CF",
        "general_col": "C",
        "general_col_idx": 0,
        "fuel": "Gas",
        "tech": "CCGT",
        "display_name": "Gas CCGT",
        "output3_col": "B",
        "output3_header": "CCGT",
        "is_thermal": True,
        "is_dg": False,
    },
    "_02_CF": {
        "index": 2,
        "code": "_02_CF",
        "general_col": "D",
        "general_col_idx": 1,
        "fuel": "Biomass",
        "tech": "Boiler",
        "display_name": "Biomass CHP",
        "output3_col": "C",
        "output3_header": "Bio (CHP)",
        "is_thermal": False,
        "is_dg": False,
    },
    "_03_CF": {
        "index": 3,
        "code": "_03_CF",
        "general_col": "E",
        "general_col_idx": 2,
        "fuel": "Biomass Retrofit",
        "tech": "Boiler",
        "display_name": "Biomass Retrofit",
        "output3_col": "D",
        "output3_header": "Bio (retro)",
        "is_thermal": False,
        "is_dg": False,
    },
    "_04_CF": {
        "index": 4,
        "code": "_04_CF",
        "general_col": "F",
        "general_col_idx": 3,
        "fuel": "Wind",
        "tech": "WT Cl. 6",
        "display_name": "Onshore Wind",
        "output3_col": "F",
        "output3_header": "Wind",
        "is_thermal": False,
        "is_dg": False,
    },
    "_05_CF": {
        "index": 5,
        "code": "_05_CF",
        "general_col": "G",
        "general_col_idx": 4,
        "fuel": "Solar",
        "tech": "PV",
        "display_name": "Utility Solar PV",
        "output3_col": "G",
        "output3_header": "Solar",
        "is_thermal": False,
        "is_dg": False,
    },
    "_06_CF": {
        "index": 6,
        "code": "_06_CF",
        "general_col": "H",
        "general_col_idx": 5,
        "fuel": "SHP",
        "tech": "Hydro",
        "display_name": "Small Hydro (SHP)",
        "output3_col": "I",
        "output3_header": "SHP",
        "is_thermal": False,
        "is_dg": False,
    },
    "_07_CF": {
        "index": 7,
        "code": "_07_CF",
        "general_col": "I",
        "general_col_idx": 6,
        "fuel": "Local Coal (CFBC)",
        "tech": "CFBC",
        "display_name": "Local Coal (CFBC)",
        "output3_col": "J",
        "output3_header": "Coal (CFBC)",
        "is_thermal": True,
        "is_dg": False,
    },
    "_08_CF": {
        "index": 8,
        "code": "_08_CF",
        "general_col": "J",
        "general_col_idx": 7,
        "fuel": "Imported Coal (PC)",
        "tech": "PC",
        "display_name": "Imported Coal (PC)",
        "output3_col": "H",
        "output3_header": "Coal (PC)",
        "is_thermal": True,
        "is_dg": False,
    },
    "_09_CF": {
        "index": 9,
        "code": "_09_CF",
        "general_col": "K",
        "general_col_idx": 8,
        "fuel": "Biomass",
        "tech": "Woodchip",
        "display_name": "Biomass Woodchip",
        "output3_col": "E",
        "output3_header": "Bio (WC)",
        "is_thermal": True,
        "is_dg": False,
    },
    "_10_CF": {
        "index": 10,
        "code": "_10_CF",
        "general_col": "L",
        "general_col_idx": 9,
        "fuel": "LNG-fired",
        "tech": "CCGT",
        "display_name": "LNG CCGT",
        "output3_col": None,
        "output3_header": "LNG CCGT",
        "is_thermal": True,
        "is_dg": False,
    },
    "_11_CF": {
        "index": 11,
        "code": "_11_CF",
        "general_col": "M",
        "general_col_idx": 10,
        "fuel": "Solar",
        "tech": "PV - Residential",
        "display_name": "DG Solar Residential",
        "output3_col": None,
        "output3_header": "DG PV Res",
        "is_thermal": False,
        "is_dg": True,
    },
    "_12_CF": {
        "index": 12,
        "code": "_12_CF",
        "general_col": "N",
        "general_col_idx": 11,
        "fuel": "Solar",
        "tech": "PV - Commercial",
        "display_name": "DG Solar Commercial",
        "output3_col": None,
        "output3_header": "DG PV Comm",
        "is_thermal": False,
        "is_dg": True,
    },
}


GENERAL_ROW_CATALOG: list[dict[str, Any]] = [
    {"row": 5, "label": "Fuel", "unit": "text", "fmt": "text"},
    {"row": 6, "label": "Label", "unit": "sheet_id", "fmt": "text"},
    {"row": 7, "label": "Technology", "unit": "type", "fmt": "text"},
    {"row": 8, "label": "Capacity (MW or kW where indicated)", "unit": "MW / kW", "fmt": "num1"},
    {"row": 9, "label": "Net capacity (MW)", "unit": "MW", "fmt": "num2"},
    {"row": 10, "label": "General losses (%)", "unit": "%", "fmt": "pct1"},
    {"row": 11, "label": "Base capital cost (BRL/kW)", "unit": "BRL/kW", "fmt": "num2"},
    {"row": 12, "label": "Lower capital cost (BRL/kW)", "unit": "BRL/kW", "fmt": "num2"},
    {"row": 13, "label": "Upper capital cost (BRL/kW)", "unit": "BRL/kW", "fmt": "num2"},
    {"row": 14, "label": "Construction lead time (yrs)", "unit": "yrs", "fmt": "num1"},
    {"row": 15, "label": "Plant economic life (yrs)", "unit": "yrs", "fmt": "num1"},
    {"row": 16, "label": "Capacity factor", "unit": "ratio / %", "fmt": "pct1"},
    {"row": 17, "label": "Heat rate", "unit": "Btu/kWh", "fmt": "num0"},
    {"row": 18, "label": "Availability (MWmed)", "unit": "MWmed", "fmt": "num2"},
    {"row": 19, "label": "Fuel cost unit", "unit": "unit", "fmt": "text"},
    {"row": 20, "label": "Fuel cost", "unit": "USD/MMBtu or BRL/MMBtu", "fmt": "num2"},
    {"row": 23, "label": "Fixed O&M costs (BRL/kW-yr)", "unit": "BRL/kW-yr", "fmt": "num2"},
    {"row": 24, "label": "Variable O&M costs (BRL/MWh)", "unit": "BRL/MWh", "fmt": "num2"},
    {"row": 25, "label": "Operation insurance (% yr)", "unit": "%/yr", "fmt": "pct2"},
    {"row": 26, "label": "Warranty insurance (% yr)", "unit": "%/yr", "fmt": "pct2"},
    {"row": 27, "label": "Transmission cost (BRL/kWh.month)", "unit": "BRL/kW.mo", "fmt": "num2"},
    {"row": 28, "label": "Administration cost (%)", "unit": "%", "fmt": "pct2"},
    {"row": 29, "label": "Rental", "unit": "%", "fmt": "pct2"},
    {"row": 30, "label": "Water (USD/MWh)", "unit": "USD/MWh", "fmt": "num2"},
    {"row": 32, "label": "Equity", "unit": "share", "fmt": "pct1"},
    {"row": 33, "label": "Debt", "unit": "share", "fmt": "pct1"},
    {"row": 34, "label": "Interest Rate", "unit": "real WACC %", "fmt": "pct2"},
    {"row": 35, "label": "Credit Period", "unit": "yrs", "fmt": "num1"},
    {"row": 36, "label": "IRR", "unit": "target %", "fmt": "pct2"},
    {"row": 38, "label": "Income tax", "unit": "%", "fmt": "pct1"},
    {"row": 39, "label": "Projected inflation", "unit": "%", "fmt": "pct1"},
    {"row": 40, "label": "Exchange rate (BRL/USD)", "unit": "BRL/USD", "fmt": "num2"},
]

GENERAL_ROW_BY_NUM: dict[int, dict[str, Any]] = {item["row"]: item for item in GENERAL_ROW_CATALOG}


OUTPUT3_COLUMNS: list[dict[str, Any]] = [
    {"col_letter": "B", "col_idx": 0, "header": "CCGT", "tech_code": "_01_CF"},
    {"col_letter": "C", "col_idx": 1, "header": "Bio (CHP)", "tech_code": "_02_CF"},
    {"col_letter": "D", "col_idx": 2, "header": "Bio (retro)", "tech_code": "_03_CF"},
    {"col_letter": "E", "col_idx": 3, "header": "Bio (WC)", "tech_code": "_09_CF"},
    {"col_letter": "F", "col_idx": 4, "header": "Wind", "tech_code": "_04_CF"},
    {"col_letter": "G", "col_idx": 5, "header": "Solar", "tech_code": "_05_CF"},
    {"col_letter": "H", "col_idx": 6, "header": "Coal (PC)", "tech_code": "_08_CF"},
    {"col_letter": "I", "col_idx": 7, "header": "SHP", "tech_code": "_06_CF"},
    {"col_letter": "J", "col_idx": 8, "header": "Coal (CFBC)", "tech_code": "_07_CF"},
]


def normalize_markdown_table(md_text: str) -> str:
    """Ensure Markdown tables have zero LaTeX '$' collisions and preserve newline breaks between rows."""
    if not md_text:
        return ""
    cleaned = md_text.replace("US$", "USD").replace("R$", "BRL")
    out_lines: list[str] = []
    for raw_line in cleaned.splitlines():
        if "| ---" in raw_line and "| |" in raw_line:
            expanded = raw_line.replace("| |", "|\n|").replace("||", "|\n|")
            for sub in expanded.splitlines():
                out_lines.append(sub)
        else:
            out_lines.append(raw_line)
    return "\n".join(out_lines) + ("\n" if cleaned.endswith("\n") else "")


def format_excel_value(val: Any, fmt: str = "num2") -> str:
    """Format a spreadsheet cell value using exact Excel display conventions."""
    if val is None or val == "":
        return "-"
    if isinstance(val, str):
        return val.replace("US$", "USD").replace("R$", "BRL")
    if not isinstance(val, (int, float)):
        return str(val).replace("US$", "USD").replace("R$", "BRL")
    fval = float(val)
    if fmt == "pct1":
        return f"{fval * 100.0:.1f}%"
    if fmt == "pct2":
        return f"{fval * 100.0:.2f}%"
    if fmt == "num0":
        return f"{fval:,.0f}"
    if fmt == "num1":
        return f"{fval:,.1f}"
    return f"{fval:,.2f}"


class ExcelLayoutRenderer:
    """Renders exact Excel-coordinate Markdown tables and Apache ECharts V5 specifications."""

    @staticmethod
    def render_general_assumptions_tables(
        general_grid: list[list[Any]],
        baseline_grid: list[list[Any]],
        technologies: list[str] | None = None,
        active_overrides: dict[str, Any] | None = None,
    ) -> tuple[str, str]:
        """Render inline slice and full 12-technology General!B5:N40 Markdown tables."""
        active_overrides = active_overrides or {}
        all_tech_codes = list(TECH_SPECS.keys())
        selected_codes = (
            [c if c.startswith("_") else f"_{c}" for c in technologies]
            if technologies
            else ["_01_CF", "_04_CF", "_05_CF", "_06_CF"]
        )
        selected_codes = [c for c in selected_codes if c in TECH_SPECS] or all_tech_codes[:4]

        def _cell_display(row_num: int, tech_code: str, fmt: str) -> str:
            spec = TECH_SPECS[tech_code]
            col_letter = spec["general_col"]
            col_idx = spec["general_col_idx"]
            r_idx = row_num - 5
            coord_key = f"General!{col_letter}{row_num}"
            cur_val = (
                general_grid[r_idx][col_idx]
                if 0 <= r_idx < len(general_grid) and col_idx < len(general_grid[r_idx])
                else None
            )
            base_val = (
                baseline_grid[r_idx][col_idx]
                if 0 <= r_idx < len(baseline_grid) and col_idx < len(baseline_grid[r_idx])
                else None
            )
            cur_str = format_excel_value(cur_val, fmt)
            if coord_key in active_overrides and isinstance(cur_val, (int, float)):
                if isinstance(base_val, (int, float)) and abs(float(base_val)) > 1e-12:
                    dpct = ((float(cur_val) - float(base_val)) / abs(float(base_val))) * 100.0
                    base_str = format_excel_value(base_val, fmt)
                    return f"**{cur_str}** *(was {base_str}, {dpct:+.1f}%)* [`{coord_key}`]"
                return f"**{cur_str}** *(override)* [`{coord_key}`]"
            return f"{cur_str} (`{coord_key}`)" if row_num in (11, 14, 16, 20, 23, 24, 34) else cur_str

        # 1. Inline compact table for requested technologies
        inline_headers = [
            "Row",
            "Parameter (`General!B5:B40`)",
            "Unit",
            *[
                f"Col {TECH_SPECS[tc]['general_col']}: {TECH_SPECS[tc]['display_name']} (`{tc}`)"
                for tc in selected_codes
            ],
        ]
        inline_lines = [
            "### Excel Tab Replica: `General` (`General!B5:N40` Scenario Assumptions)",
            "",
            "| " + " | ".join(inline_headers) + " |",
            "| :---: | :--- | :---: | " + " | ".join(["---:"] * len(selected_codes)) + " |",
        ]
        for row_meta in GENERAL_ROW_CATALOG:
            r_num = row_meta["row"]
            fmt = row_meta["fmt"]
            cells = [_cell_display(r_num, tc, fmt) for tc in selected_codes]
            inline_lines.append(
                f"| `{r_num}` | **{row_meta['label']}** (`General!B{r_num}`) | {row_meta['unit']} | "
                + " | ".join(cells)
                + " |"
            )
        inline_md = "\n".join(inline_lines)

        # 2. Full 12-technology table for side-pane Artifact
        full_headers = [
            "Row",
            "Parameter (`General!B`)",
            "Unit",
            *[
                f"Col {TECH_SPECS[tc]['general_col']}: {TECH_SPECS[tc]['display_name']} (`{tc}`)"
                for tc in all_tech_codes
            ],
        ]
        full_lines = [
            "# Full 12-Technology Excel Tab Replica: `General!B5:N40`",
            "",
            "| " + " | ".join(full_headers) + " |",
            "| :---: | :--- | :---: | " + " | ".join(["---:"] * len(all_tech_codes)) + " |",
        ]
        for row_meta in GENERAL_ROW_CATALOG:
            r_num = row_meta["row"]
            fmt = row_meta["fmt"]
            cells = []
            for tc in all_tech_codes:
                spec = TECH_SPECS[tc]
                col_idx = spec["general_col_idx"]
                col_letter = spec["general_col"]
                r_idx = r_num - 5
                cur_val = (
                    general_grid[r_idx][col_idx]
                    if 0 <= r_idx < len(general_grid) and col_idx < len(general_grid[r_idx])
                    else None
                )
                coord_key = f"General!{col_letter}{r_num}"
                val_str = format_excel_value(cur_val, fmt)
                if coord_key in active_overrides:
                    val_str = f"**{val_str}** (`{coord_key}`)"
                cells.append(val_str)
            full_lines.append(
                f"| `{r_num}` | **{row_meta['label']}** | {row_meta['unit']} | "
                + " | ".join(cells)
                + " |"
            )
        full_md = "\n".join(full_lines)
        return normalize_markdown_table(inline_md), normalize_markdown_table(full_md)

    @staticmethod
    def render_assumptions_diff_table(changes: list[dict[str, Any]]) -> str:
        """Render exact Excel cell diff table for staged scenario overrides."""
        if not changes:
            return "### Scenario Assumptions Diff (`General` / `LT`)\n\n_No active overrides (all cells at seed baseline)._"

        lines = [
            "### Staged Scenario Assumption Overrides (`General!C5:N40` & `LT` Tabs)",
            "",
            "| Excel Cell Coord | Technology | Parameter Name | Unit | Seed Baseline | Staged Current | Δ Change |",
            "| :--- | :--- | :--- | :--- | ---: | ---: | ---: |",
        ]
        for ch in changes:
            b_val = ch.get("baseline_value")
            c_val = ch.get("current_value")
            b_str = f"{float(b_val):.2f}" if isinstance(b_val, (int, float)) else str(b_val or "-")
            c_str = f"{float(c_val):.2f}" if isinstance(c_val, (int, float)) else str(c_val or "-")
            dpct = ch.get("delta_pct")
            d_str = f"{dpct:+.2f}%" if isinstance(dpct, (int, float)) else "override"
            lines.append(
                f"| `{ch['cell_coord']}` | `{ch.get('technology_code', '-')}` ({ch.get('technology_label', '-')}) "
                f"| **{ch.get('parameter', ch['cell_coord'])}** | {ch.get('unit', '-')} "
                f"| {b_str} | **{c_str}** | `{d_str}` |"
            )
        return normalize_markdown_table("\n".join(lines))

    @staticmethod
    def render_tornado_table(
        technology_code: str,
        tornado_rows: list[dict[str, Any]],
        output_var: str,
        baseline_output: float,
    ) -> str:
        """Render exact replica of _0N_CF!A4:H12 Tornado IRR Sensitivity table and Output_1 summary."""
        spec = TECH_SPECS.get(technology_code, TECH_SPECS["_06_CF"])
        unit_label = "Fixed Revenue (BRL/yr, `C16`)" if spec["is_thermal"] else "Solved LCOE Tariff (BRL/MWh, `B16`)"
        lines = [
            f"### Excel Tab Replica: `{technology_code}!A4:H12` & `Output_1` — Tornado IRR Sensitivity (`{spec['display_name']}`)",
            f"- **Target Worksheet**: `{technology_code}` (`Fuel: {spec['fuel']}`, `Technology: {spec['tech']}`)",
            f"- **Macro Executed**: `calcule_tir{spec['index']}` (`Output Variable: {output_var}` — {unit_label})",
            "",
            f"| Row | Parameter (`{technology_code}!A6:A12`) | Input -15% (`Col B`) | Base Input (`Col C`) | Input +15% (`Col D`) | Output -15% (`Col E`) | Base Output (`Col F`) | Output +15% (`Col G`) | Active Scenario (`Col H`) | Spread (Δ Output) |",
            "| :---: | :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
        for r in tornado_rows:
            row_num = r["row_num"]
            lines.append(
                f"| `{row_num}` | **{r['parameter']}** (`{technology_code}!A{row_num}`) "
                f"| {r['in_low']:.3f} (`B{row_num}`) | {r['in_base']:.3f} (`C{row_num}`) | {r['in_high']:.3f} (`D{row_num}`) "
                f"| **{r['out_low']:,.2f}** (`E{row_num}`) | {r['out_base']:,.2f} (`F{row_num}`) | **{r['out_high']:,.2f}** (`G{row_num}`) "
                f"| {r['active_h']:.3f} (`H{row_num}`) | `{r['spread']:,.2f}` |"
            )
        return normalize_markdown_table("\n".join(lines))

    @staticmethod
    def build_tornado_echarts(
        technology_code: str,
        tornado_rows: list[dict[str, Any]],
        output_var: str,
        baseline_output: float,
    ) -> dict[str, Any]:
        """Build Apache ECharts V5 horizontal Tornado bar specification for render_chart."""
        spec = TECH_SPECS.get(technology_code, TECH_SPECS["_06_CF"])
        sorted_rows = sorted(tornado_rows, key=lambda x: abs(float(x["spread"])))
        categories = [f"{r['parameter']} (Row {r['row_num']})" for r in sorted_rows]
        low_deltas = [round(float(r["out_low"]) - float(r["out_base"]), 2) for r in sorted_rows]
        high_deltas = [round(float(r["out_high"]) - float(r["out_base"]), 2) for r in sorted_rows]
        unit_str = "R$/yr (C16)" if spec["is_thermal"] else "R$/MWh (B16)"

        return {
            "title": {
                "text": f"Tornado Sensitivity — {technology_code} ({spec['display_name']})",
                "subtext": f"Base Case = {baseline_output:,.2f} {unit_str} | ±15% Parameter Perturbation",
                "left": "center",
            },
            "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
            "legend": {"data": ["-15% Input Perturbation (Col E)", "+15% Input Perturbation (Col G)"], "bottom": 0},
            "grid": {"left": "18%", "right": "8%", "top": "16%", "bottom": "14%", "containLabel": True},
            "xAxis": {
                "type": "value",
                "name": f"Δ {unit_str} vs Base (Col F)",
            },
            "yAxis": {
                "type": "category",
                "data": categories,
            },
            "series": [
                {
                    "name": "-15% Input Perturbation (Col E)",
                    "type": "bar",
                    "stack": "tornado",
                    "data": low_deltas,
                    "itemStyle": {"color": "#2563eb"},
                },
                {
                    "name": "+15% Input Perturbation (Col G)",
                    "type": "bar",
                    "stack": "tornado",
                    "data": high_deltas,
                    "itemStyle": {"color": "#dc2626"},
                },
            ],
        }

    @staticmethod
    def render_lcoe_output3_tables(
        output_grid: list[list[Any]],
        timestamp_b3: str,
        thermal_icb_diagnostics: dict[str, Any] | None = None,
    ) -> tuple[str, str]:
        """Render compact inline summary and full 23-year Output_3!B9:J31 Excel-layout Markdown tables."""
        col_headers = [
            "Row (`Output_3`)",
            "Horizon Year (`Col A`)",
            *[f"Col {c['col_letter']} (`{c['tech_code']}` {c['header']})" for c in OUTPUT3_COLUMNS],
        ]

        def _format_row(yr_idx: int) -> str:
            excel_row = 9 + yr_idx
            horizon_yr = 2024 + yr_idx
            seed_yr = 2018 + yr_idx
            row_vals = output_grid[yr_idx] if yr_idx < len(output_grid) else [None] * 9
            formatted_cells: list[str] = []
            for c_meta in OUTPUT3_COLUMNS:
                c_idx = c_meta["col_idx"]
                c_let = c_meta["col_letter"]
                v = row_vals[c_idx] if c_idx < len(row_vals) else None
                if isinstance(v, (int, float)):
                    formatted_cells.append(f"{float(v):,.2f} (`{c_let}{excel_row}`)")
                else:
                    formatted_cells.append(f"- (`{c_let}{excel_row}` skipped)")
            return (
                f"| `Row {excel_row}` | **{horizon_yr}** *(seed {seed_yr})* | "
                + " | ".join(formatted_cells)
                + " |"
            )

        # Inline table shows milestone rows (2024, 2025, 2026, 2028, 2030, 2035, 2040, 2045, 2046)
        milestone_indices = [0, 1, 2, 4, 6, 11, 16, 21, 22]
        inline_lines = [
            "### Excel Tab Replica: `Output_3!B9:J31` — 23-Year Multi-Technology LCOE & Thermal ICB Forecast (`R$/MWh`)",
            f"- **Timestamp Cell (`Output_3!B3`)**: `{timestamp_b3}`",
            "- **Legacy Quirk 7 Preserved**: `Output_3!D9:D31` (`_03_CF Bio (retro)`) is intentionally left blank per VBA `lcoe_exec`.",
            "",
            "| " + " | ".join(col_headers) + " |",
            "| " + " | ".join(["---"] * len(col_headers)) + " |",
            *[_format_row(idx) for idx in milestone_indices if idx < len(output_grid)],
        ]
        inline_md = "\n".join(inline_lines)

        # Full 23-row table (2024..2046 / Rows 9..31)
        full_lines = [
            "# Full Excel Tab Replica: `Output_3!B9:J31` (23-Year Horizon `2024–2046` / Seed `2018–2040`, in `R$/MWh`)",
            f"- **`Output_3!B3`**: `{timestamp_b3}`",
            "",
            "| " + " | ".join(col_headers) + " |",
            "| " + " | ".join(["---"] * len(col_headers)) + " |",
            *[_format_row(idx) for idx in range(len(output_grid))],
        ]
        if thermal_icb_diagnostics:
            full_lines.extend(
                [
                    "",
                    "### Thermal ICB & Physical Guarantee Diagnostics (`Row 81` / `_08_CF Row 105`)",
                    "",
                    "| Sheet | ICB Row | Solved Tariff Coord | ICB Output Coord | Terminal ICB (`R$/MWh`) |",
                    "| :--- | :---: | :--- | :--- | ---: |",
                ]
            )
            for sname, d in thermal_icb_diagnostics.items():
                full_lines.append(
                    f"| `{sname}` | `{d['icb_row']}` | `{d['c_coord']}` | `{d['i_coord']}` | **{float(d['icb_value']):,.2f}** |"
                )
        full_md = "\n".join(full_lines)
        return normalize_markdown_table(inline_md), normalize_markdown_table(full_md)

    @staticmethod
    def build_lcoe_horizon_echarts(output_grid: list[list[Any]]) -> dict[str, Any]:
        """Build Apache ECharts V5 multi-series 23-year LCOE trajectory chart specification."""
        years = [str(2024 + idx) for idx in range(len(output_grid))]
        series: list[dict[str, Any]] = []
        for c_meta in OUTPUT3_COLUMNS:
            if c_meta["col_letter"] == "D":
                continue
            c_idx = c_meta["col_idx"]
            data_pts = [
                round(float(output_grid[yr_idx][c_idx]), 2)
                if yr_idx < len(output_grid)
                and c_idx < len(output_grid[yr_idx])
                and isinstance(output_grid[yr_idx][c_idx], (int, float))
                else None
                for yr_idx in range(len(output_grid))
            ]
            series.append(
                {
                    "name": f"{c_meta['header']} ({c_meta['tech_code']} Col {c_meta['col_letter']})",
                    "type": "line",
                    "smooth": True,
                    "data": data_pts,
                }
            )
        return {
            "title": {
                "text": "23-Year Multi-Technology LCOE & Thermal ICB Forecast (Output_3!B9:J31)",
                "subtext": "Solved Real LCOE Trajectories across 2024–2046 (R$/MWh)",
                "left": "center",
            },
            "tooltip": {"trigger": "axis"},
            "legend": {"bottom": 0, "type": "scroll"},
            "grid": {"left": "6%", "right": "5%", "top": "16%", "bottom": "16%", "containLabel": True},
            "xAxis": {"type": "category", "name": "Year", "data": years},
            "yAxis": {"type": "value", "name": "LCOE / ICB (R$/MWh)"},
            "series": series,
        }

    @staticmethod
    def render_bqml_lt_tables(
        lt_grids: dict[str, list[list[Any]]],
        curve_types: list[str],
    ) -> tuple[str, str]:
        """Render Excel-layout tables for LT Capex!B8:J30, LT Fuel!B8:J30, and LT CF!B8:J30."""
        tab_map = {
            "CAPEX": ("LT Capex", "BRL/kW", "lt_capex_b8_j30"),
            "FUEL": ("LT Fuel", "Index / Multiplier", "lt_fuel_b8_j30"),
            "CF": ("LT CF", "Capacity Factor Ratio", "lt_cf_b8_j30"),
        }
        headers = [
            "Row",
            "Year (`Col A`)",
            *[f"Col {c['col_letter']} (`{c['tech_code']}` {c['header']})" for c in OUTPUT3_COLUMNS],
        ]

        inline_sections: list[str] = [
            "### BigQuery ML `ARIMA_PLUS` Time-Series Refresh (`LT Capex`, `LT Fuel`, `LT CF` — `B8:J30`)",
            "- **Source View**: `comm-model-mod.sheets_commodity_mod_governance.vw_connected_sheets_lt_forecasts`",
        ]
        full_sections: list[str] = [
            "# Full Excel Tab Replicas: `LT Capex!B8:J30`, `LT Fuel!B8:J30`, `LT CF!B8:J30` (`2024–2046`)",
        ]

        for ctype in curve_types:
            key_up = ctype.upper().replace("LT_", "")
            if key_up not in tab_map:
                continue
            tab_name, unit_desc, grid_key = tab_map[key_up]
            grid = lt_grids.get(grid_key, [])

            def _fmt_lt_row(yr_idx: int, tname: str = tab_name) -> str:
                excel_row = 8 + yr_idx
                horizon_yr = 2024 + yr_idx
                row_vals = grid[yr_idx] if yr_idx < len(grid) else [None] * 9
                cells = []
                for c_meta in OUTPUT3_COLUMNS:
                    c_idx = c_meta["col_idx"]
                    c_let = c_meta["col_letter"]
                    v = row_vals[c_idx] if c_idx < len(row_vals) else None
                    if isinstance(v, (int, float)):
                        cells.append(f"{float(v):,.3f} (`{c_let}{excel_row}`)")
                    else:
                        cells.append("-")
                return f"| `Row {excel_row}` | **{horizon_yr}** | " + " | ".join(cells) + " |"

            sample_idxs = [0, 2, 6, 12, 17, 22]
            inline_sections.extend(
                [
                    "",
                    f"#### Tab `{tab_name}!B8:J30` ({unit_desc})",
                    "| " + " | ".join(headers) + " |",
                    "| " + " | ".join(["---"] * len(headers)) + " |",
                    *[_fmt_lt_row(i) for i in sample_idxs if i < len(grid)],
                ]
            )
            full_sections.extend(
                [
                    "",
                    f"## Tab `{tab_name}!B8:J30` ({unit_desc})",
                    "| " + " | ".join(headers) + " |",
                    "| " + " | ".join(["---"] * len(headers)) + " |",
                    *[_fmt_lt_row(i) for i in range(len(grid))],
                ]
            )

        return normalize_markdown_table("\n".join(inline_sections)), normalize_markdown_table("\n".join(full_sections))

    @staticmethod
    def build_bqml_echarts(
        lt_grids: dict[str, list[list[Any]]],
    ) -> dict[str, Any]:
        """Build Apache ECharts V5 trajectory and 95% confidence band spec for LT Capex."""
        capex_grid = lt_grids.get("lt_capex_b8_j30", [])
        years = [str(2024 + i) for i in range(len(capex_grid))]
        featured = [
            ("CCGT (_01_CF Col B)", 0),
            ("Wind (_04_CF Col F)", 4),
            ("Solar PV (_05_CF Col G)", 5),
            ("Small Hydro (_06_CF Col I)", 7),
        ]
        series: list[dict[str, Any]] = []
        for label, c_idx in featured:
            pts = [
                round(float(capex_grid[yr][c_idx]), 2)
                if yr < len(capex_grid)
                and c_idx < len(capex_grid[yr])
                and isinstance(capex_grid[yr][c_idx], (int, float))
                else None
                for yr in range(len(capex_grid))
            ]
            series.append({"name": label, "type": "line", "smooth": True, "data": pts})
        return {
            "title": {
                "text": "BigQuery ML ARIMA_PLUS Long-Term CAPEX Trajectories (LT Capex!B8:J30)",
                "subtext": "Real CAPEX Forecast 2024–2046 (R$/kW)",
                "left": "center",
            },
            "tooltip": {"trigger": "axis"},
            "legend": {"bottom": 0},
            "grid": {"left": "7%", "right": "5%", "top": "16%", "bottom": "15%", "containLabel": True},
            "xAxis": {"type": "category", "data": years, "name": "Year"},
            "yAxis": {"type": "value", "name": "Real CAPEX (R$/kW)"},
            "series": series,
        }

    @staticmethod
    def render_dcf_tables(
        technology_code: str,
        summary_metrics: dict[str, Any],
        years: list[int],
        col_letters: list[str],
        statement_rows: list[dict[str, Any]],
    ) -> tuple[str, str]:
        """Render executive summary + milestone table inline, and full 30-year DCF schedule for Artifact."""
        spec = TECH_SPECS.get(technology_code, TECH_SPECS["_01_CF"])

        # Milestone years for inline preview: 2024..2028, 2030, 2035, 2040, 2045, 2050, 2053
        milestone_set = {years[0], years[1], years[2], years[3], 2030, 2035, 2040, 2045, 2050, years[-1]}
        m_indices = [i for i, y in enumerate(years) if y in milestone_set]

        inline_lines = [
            f"### Excel Tab Replica: `{technology_code}` & `Output_2` — 30-Year Project DCF & Shareholder Cash Flow (`{spec['display_name']}`)",
            "",
            "#### Executive Valuation & Parameter Header Block (`" + technology_code + "!A2:H18`)",
            "| Excel Coord | Metric / Parameter | Value | Unit |",
            "| :--- | :--- | ---: | :--- |",
            f"| `General!{spec['general_col']}8` | **Installed Capacity** | {summary_metrics['capacity_mw']:,.2f} | MW |",
            f"| `{technology_code}!C6` | **Specific CAPEX** | {summary_metrics['capex_r_per_kw']:,.2f} | BRL/kW |",
            f"| `General!{spec['general_col']}14` | **Construction Lead Time** | {summary_metrics['lead_time_yrs']:.1f} | years |",
            f"| `General!{spec['general_col']}15` | **Economic Operational Life** | {summary_metrics['economic_life_yrs']:.1f} | years |",
            f"| `{technology_code}!C7` | **Capacity Factor / Fuel Input** | {summary_metrics['h7_input']:,.3f} | unit |",
            f"| `{technology_code}!C11` | **Real WACC / Financing Rate** | {summary_metrics['wacc_rate'] * 100.0:.2f}% | %/yr |",
            f"| `{technology_code}!B16` | **Solved Break-Even Tariff (LCOE)** | **{summary_metrics['lcoe_b16']:,.2f}** | BRL/MWh |",
            f"| `{technology_code}!B17` | **Annual Net Generation** | {summary_metrics['generation_b17']:,.1f} | MWh/yr |",
            f"| `{technology_code}!B18` | **Shareholder / Project IRR (`TIR`)** | **{summary_metrics['irr_b18'] * 100.0:.2f}%** | % |",
            f"| `{technology_code}!NPV` | **Net Present Value @ Real WACC** | **{summary_metrics['npv_at_wacc']:,.2f}** | BRL |",
            f"| `{technology_code}!Payback` | **Discounted Payback Period** | {summary_metrics['payback_yrs']:.1f} | years |",
            "",
            f"#### Milestone Years Preview (`{technology_code}!Row 19..63`, `{years[0]}–{years[-1]}`)",
            "| Row | Line Item (`Col A`) | "
            + " | ".join([f"{years[i]} (`Col {col_letters[i]}`)" for i in m_indices])
            + " |",
            "| :---: | :--- | " + " | ".join(["---:"] * len(m_indices)) + " |",
        ]
        for srow in statement_rows:
            r_num = srow["row_num"]
            label = srow["label"]
            vals = srow["values"]
            cell_strs = [f"{float(vals[i]):,.0f}" for i in m_indices]
            inline_lines.append(
                f"| `{r_num}` | **{label}** (`{technology_code}!A{r_num}`) | " + " | ".join(cell_strs) + " |"
            )
        inline_md = "\n".join(inline_lines)

        # Full 30-year horizontal table for Side-Pane Artifact
        full_lines = [
            f"# Complete 30-Year DCF Cash Flow Schedule: `{technology_code}` (`{spec['display_name']}`, `{years[0]}–{years[-1]}`)",
            f"- **Solved LCOE (`{technology_code}!B16`)**: `{summary_metrics['lcoe_b16']:,.2f} BRL/MWh` | **IRR (`{technology_code}!B18`)**: `{summary_metrics['irr_b18'] * 100.0:.2f}%` | **NPV @ WACC**: `BRL {summary_metrics['npv_at_wacc']:,.2f}`",
            "",
            "| Row | Line Item (`" + technology_code + "!Col A`) | "
            + " | ".join([f"{years[i]} (`Col {col_letters[i]}`)" for i in range(len(years))])
            + " |",
            "| :---: | :--- | " + " | ".join(["---:"] * len(years)) + " |",
        ]
        for srow in statement_rows:
            r_num = srow["row_num"]
            label = srow["label"]
            vals = srow["values"]
            cell_strs = [f"{float(v):,.0f}" for v in vals]
            full_lines.append(
                f"| `{r_num}` | **{label}** (`{technology_code}!A{r_num}`) | " + " | ".join(cell_strs) + " |"
            )
        full_md = "\n".join(full_lines)
        return normalize_markdown_table(inline_md), normalize_markdown_table(full_md)

    @staticmethod
    def build_dcf_echarts(
        technology_code: str,
        years: list[int],
        shareholder_cf: list[float],
        cumulative_dcf: list[float],
        ebitda_series: list[float],
    ) -> dict[str, Any]:
        """Build Apache ECharts V5 30-year DCF cash-flow & cumulative discounted NPV chart specification."""
        spec = TECH_SPECS.get(technology_code, TECH_SPECS["_01_CF"])
        yr_labels = [str(y) for y in years]
        return {
            "title": {
                "text": f"30-Year DCF Cash Flow & Cumulative NPV Profile — {technology_code} ({spec['display_name']})",
                "subtext": f"Horizon {years[0]}–{years[-1]} (R$ Millions)",
                "left": "center",
            },
            "tooltip": {"trigger": "axis"},
            "legend": {
                "data": [
                    "Annual Shareholder Cash Flow (Row 63, R$M)",
                    "Annual EBITDA (Row 51, R$M)",
                    "Cumulative Discounted Cash Flow (R$M)",
                ],
                "bottom": 0,
            },
            "grid": {"left": "7%", "right": "6%", "top": "16%", "bottom": "15%", "containLabel": True},
            "xAxis": {"type": "category", "data": yr_labels, "name": "Year"},
            "yAxis": {"type": "value", "name": "R$ Millions"},
            "series": [
                {
                    "name": "Annual Shareholder Cash Flow (Row 63, R$M)",
                    "type": "bar",
                    "data": [round(v / 1.0e6, 3) for v in shareholder_cf],
                    "itemStyle": {"color": "#0284c7"},
                },
                {
                    "name": "Annual EBITDA (Row 51, R$M)",
                    "type": "bar",
                    "data": [round(v / 1.0e6, 3) for v in ebitda_series],
                    "itemStyle": {"color": "#10b981"},
                },
                {
                    "name": "Cumulative Discounted Cash Flow (R$M)",
                    "type": "line",
                    "smooth": True,
                    "data": [round(v / 1.0e6, 3) for v in cumulative_dcf],
                    "itemStyle": {"color": "#f59e0b"},
                },
            ],
        }

    @staticmethod
    def render_cvu_sweep_tables(
        technology_code: str,
        sweep_rows: list[dict[str, Any]],
        mutated_cell: str,
    ) -> tuple[str, str]:
        """Render 10-point CVU / Physical Guarantee / ICB sweep table (_0N_CF!B70:I79 & CVU_GF)."""
        spec = TECH_SPECS.get(technology_code, TECH_SPECS["_01_CF"])
        lines = [
            f"### Excel Tab Replica: `{technology_code}!B70:I79` & `CVU_GF` — 1D CVU & Physical Guarantee Sweep (`{spec['display_name']}`)",
            f"- **Macro Executed**: `calculo_cvu{spec['index']}` (`Mutated Observer Cell: {technology_code}!{mutated_cell}`)",
            "",
            f"| Row | Sweep Input (`{technology_code}!Col B`) | Solved Tariff (`{technology_code}!Col C`, BRL/MWh) | Fixed Revenue (`Col D`, BRL/yr) | Variable Unit Cost `CVU` (`Col E`, BRL/MWh) | Physical Guarantee `GF` (`Col F`, MWmed) | Dispatch Factor `fator_k` (`Col H`) | Cost-Benefit Index `ICB` (`Col I`, BRL/MWh) |",
            "| :---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
        for r in sweep_rows:
            rnum = r["row_num"]
            lines.append(
                f"| `{rnum}` | {r['sweep_input']:,.3f} (`B{rnum}`) "
                f"| **{r['solved_price']:,.2f}** (`C{rnum}`) "
                f"| {r['fxd_rev']:,.0f} (`D{rnum}`) "
                f"| {r['cvu']:,.2f} (`E{rnum}`) "
                f"| **{r['gf_mw']:,.2f}** (`F{rnum}`) "
                f"| {r['fator_k']:.4f} (`H{rnum}`) "
                f"| **{r['icb']:,.2f}** (`I{rnum}`) |"
            )
        md = normalize_markdown_table("\n".join(lines))
        return md, md

    @staticmethod
    def build_cvu_sweep_echarts(
        technology_code: str,
        sweep_rows: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Build Apache ECharts V5 dual-metric chart for CVU Sweep & Physical Guarantee (GF)."""
        spec = TECH_SPECS.get(technology_code, TECH_SPECS["_01_CF"])
        x_vals = [f"{r['sweep_input']:.2f} (B{r['row_num']})" for r in sweep_rows]
        return {
            "title": {
                "text": f"CVU & Physical Guarantee Sweep — {technology_code} ({spec['display_name']})",
                "subtext": f"Macro calculo_cvu{spec['index']} ({technology_code}!B70:I79 & CVU_GF)",
                "left": "center",
            },
            "tooltip": {"trigger": "axis"},
            "legend": {
                "data": ["Solved LCOE Tariff (Col C, R$/MWh)", "Cost-Benefit Index ICB (Col I, R$/MWh)", "Physical Guarantee GF (Col F, MWmed)"],
                "bottom": 0,
            },
            "grid": {"left": "7%", "right": "7%", "top": "16%", "bottom": "15%", "containLabel": True},
            "xAxis": {"type": "category", "data": x_vals, "name": "Sweep Input (Col B)"},
            "yAxis": [
                {"type": "value", "name": "Tariff / ICB (R$/MWh)"},
                {"type": "value", "name": "Physical Guarantee GF (MWmed)"},
            ],
            "series": [
                {
                    "name": "Solved LCOE Tariff (Col C, R$/MWh)",
                    "type": "line",
                    "smooth": True,
                    "data": [round(float(r["solved_price"]), 2) for r in sweep_rows],
                },
                {
                    "name": "Cost-Benefit Index ICB (Col I, R$/MWh)",
                    "type": "line",
                    "smooth": True,
                    "data": [round(float(r["icb"]), 2) for r in sweep_rows],
                },
                {
                    "name": "Physical Guarantee GF (Col F, MWmed)",
                    "type": "bar",
                    "yAxisIndex": 1,
                    "data": [round(float(r["gf_mw"]), 2) for r in sweep_rows],
                },
            ],
        }
