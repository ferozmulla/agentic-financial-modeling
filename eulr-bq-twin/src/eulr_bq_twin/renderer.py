"""Markdown table formatters and Apache ECharts v5 JSON specs for EULR Gemini Agent workflows."""

from __future__ import annotations

from typing import Any


def _fmt(val: Any, digits: int = 2) -> str:
    if val is None:
        return "—"
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        return f"{val:,.{digits}f}"
    return str(val)


def render_assumptions_markdown(data: dict[str, Any]) -> dict[str, str]:
    """Render concise inline summary and full side-pane Artifact markdown for EULR baseline/session."""
    years: list[int] = data["years"]
    yr_hdr = " | ".join(str(y) for y in years)
    yr_sep = " | ".join("---:" for _ in years)

    lines_full: list[str] = [
        "# EULR European Refining & Product Equilibrium — Digital Twin Snapshot",
        "",
        f"- **EU ETS Carbon Toggle (`Carbon!A5`)**: `{data['carbon_switch_a5']}`",
        f"- **EU ETS Pass-Through Allocation (`Carbon!A6`)**: `{data['carbon_switch_a6']}`",
        f"- **Active Session Overrides**: `{data.get('active_override_count', 0)}` cells (`{data.get('active_pinned_count', 0)}` pinned price cells)",
        "",
        "## 1. European Refinery Yardstick Margins & EU ETS Pass-Through (`$/bbl`)",
        f"| Metric | Sheet!Row | Units | {yr_hdr} |",
        f"| :--- | :--- | :---: | {yr_sep} |",
    ]
    for m in data["margins"]:
        vals = " | ".join(_fmt(m["values"].get(y), 2) for y in years)
        lines_full.append(f"| **{m['metric']}** | `{m['coord']}` | {m['units']} | {vals} |")

    lines_full.extend(
        [
            "",
            "## 2. Benchmark Crude Slate (`$/bbl`)",
            f"| Crude Grade | Sheet!Row | Units | {yr_hdr} |",
            f"| :--- | :--- | :---: | {yr_sep} |",
        ]
    )
    for c in data["crudes"]:
        vals = " | ".join(_fmt(c["values"].get(y), 2) for y in years)
        lines_full.append(f"| {c['grade']} | `{c['coord']}` | {c['units']} | {vals} |")

    lines_full.extend(
        [
            "",
            "## 3. Northwest Europe (`NWE Cif` — ARA) Refined Product Prices (`$/mt`)",
            f"| Product | Sheet!Row | Units | {yr_hdr} |",
            f"| :--- | :--- | :---: | {yr_sep} |",
        ]
    )
    for p in data["nwe_cif"]:
        vals = " | ".join(_fmt(p["values"].get(y), 2) for y in years)
        lines_full.append(f"| {p['product']} | `{p['coord']}` | {p['units']} | {vals} |")

    lines_full.extend(
        [
            "",
            "## 4. Mediterranean (`MED Cif` — Lavera/Augusta) Refined Product Prices (`$/mt`)",
            f"| Product | Sheet!Row | Units | {yr_hdr} |",
            f"| :--- | :--- | :---: | {yr_sep} |",
        ]
    )
    for p in data["med_cif"]:
        vals = " | ".join(_fmt(p["values"].get(y), 2) for y in years)
        lines_full.append(f"| {p['product']} | `{p['coord']}` | {p['units']} | {vals} |")

    lines_full.extend(
        [
            "",
            "## 5. FOB Netbacks & IMO Marine Bunker Fuels (`$/mt`)",
            f"| Series | Sheet!Row | Units | {yr_hdr} |",
            f"| :--- | :--- | :---: | {yr_sep} |",
        ]
    )
    for p in data["fob_and_imo"]:
        vals = " | ".join(_fmt(p["values"].get(y), 2) for y in years)
        lines_full.append(f"| {p['product']} | `{p['coord']}` | {p['units']} | {vals} |")

    # Compact inline preview (2024, 2025, 2030, 2040, 2050)
    short_yrs = [2024, 2025, 2030, 2040, 2050]
    s_hdr = " | ".join(str(y) for y in short_yrs)
    s_sep = " | ".join("---:" for _ in short_yrs)
    inline_lines = [
        f"| Benchmark Series | Units | {s_hdr} |",
        f"| :--- | :---: | {s_sep} |",
    ]
    for item, label_key in [
        (data["margins"][0], "metric"),
        (data["margins"][2], "metric"),
        (data["margins"][6], "metric"),
        (data["crudes"][0], "grade"),
        (data["nwe_cif"][4], "product"),
        (data["nwe_cif"][2], "product"),
        (data["med_cif"][4], "product"),
        (data["fob_and_imo"][5], "product"),
    ]:
        v_str = " | ".join(_fmt(item["values"].get(y), 2) for y in short_yrs)
        inline_lines.append(f"| **{item[label_key]}** | {item['units']} | {v_str} |")

    return {
        "inline_summary_markdown": "\n".join(inline_lines),
        "full_artifact_markdown": "\n".join(lines_full),
    }


def render_equilibrium_outputs(solve_res: dict[str, Any]) -> dict[str, Any]:
    """Render Markdown + ECharts v5 JSON for the 10-pass NWE/MED equilibrium solve."""
    ms = solve_res["milestone_snapshot"]
    tables = render_assumptions_markdown(ms)
    years = [str(y) for y in ms["years"]]

    nwe_diesel = [ms["nwe_cif"][4]["values"].get(y) for y in ms["years"]]
    med_diesel = [ms["med_cif"][4]["values"].get(y) for y in ms["years"]]
    nwe_gaso = [ms["nwe_cif"][2]["values"].get(y) for y in ms["years"]]
    imo_vlsfo = [ms["fob_and_imo"][5]["values"].get(y) for y in ms["years"]]
    fcc_margin = [ms["margins"][0]["values"].get(y) for y in ms["years"]]

    echart = {
        "title": {
            "text": "European Equilibrium Refined Product Trajectory & NWE FCC Margin (2024–2050)",
            "left": "center",
            "textStyle": {"fontSize": 14},
        },
        "tooltip": {"trigger": "axis"},
        "legend": {"bottom": 0},
        "grid": {"left": "7%", "right": "8%", "top": 48, "bottom": 52},
        "xAxis": {"type": "category", "data": years},
        "yAxis": [
            {"type": "value", "name": "Product Price ($/mt)"},
            {"type": "value", "name": "FCC Margin ($/bbl)", "position": "right"},
        ],
        "series": [
            {"name": "NWE Diesel EN590 ($/mt)", "type": "line", "smooth": True, "data": nwe_diesel, "itemStyle": {"color": "#1a73e8"}},
            {"name": "MED Diesel EN590 ($/mt)", "type": "line", "smooth": True, "data": med_diesel, "lineStyle": {"type": "dashed"}, "itemStyle": {"color": "#34a853"}},
            {"name": "NWE Euro Gasoline ($/mt)", "type": "line", "smooth": True, "data": nwe_gaso, "itemStyle": {"color": "#fbbc04"}},
            {"name": "IMO 0.5% VLSFO ($/mt)", "type": "line", "smooth": True, "data": imo_vlsfo, "itemStyle": {"color": "#5f6368"}},
            {"name": "NWE FCC Margin ($/bbl)", "type": "bar", "yAxisIndex": 1, "barMaxWidth": 24, "data": fcc_margin, "itemStyle": {"color": "#ea4335", "opacity": 0.65}},
        ],
    }

    conv_rows = " | ".join(
        f"P{i+1}: `{v:.4f}`" for i, v in enumerate(solve_res["convergence_history"])
    )
    diag = solve_res["checks_diagnostics"]
    header_md = (
        f"**10-Pass Equilibrium Converged**: `{solve_res['converged']}` | "
        f"**Final Step Residual**: `{solve_res['final_max_delta_usd_mt']:.6f} $/mt` | "
        f"**Compute**: `{solve_res['compute_ms']} ms` | "
        f"**Checks Rules Flagged**: `{diag['flagged_count']} / {diag['evaluated_formula_cells']}`\n\n"
        f"**Per-Pass Residual (`$/mt`)**: {conv_rows}\n\n"
    )
    return {
        "inline_markdown": header_md + tables["inline_summary_markdown"],
        "artifact_markdown": header_md + tables["full_artifact_markdown"],
        "echarts_option": echart,
    }


def render_scenario_matrix_outputs(matrix_res: dict[str, Any]) -> dict[str, Any]:
    """Render 6-case EU ETS Carbon, Margin Stress & Global Peer Sync comparison table + EChart."""
    yr = matrix_res["target_year"]
    cases = matrix_res["cases"]

    lines = [
        f"### EULR 6-Way Margin, EU ETS Carbon & Global Peer Sync Matrix (`{yr}`)",
        "",
        "| Scenario Case | FCC Margin (`$/bbl`) | ETS Erosion (`$/bbl`) | NWE Diesel (`$/mt`) | MED Diesel (`$/mt`) | NWE Gasoline (`$/mt`) | IMO 0.5% VLSFO (`$/mt`) | ULSD–GO Spread (`$/mt`) |",
        "| :--- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for c in cases:
        lines.append(
            f"| **{c['case_label']}** | {_fmt(c['fcc_margin_usd_bbl'], 2)} | {_fmt(c['ets_erosion_usd_bbl'], 2)} | "
            f"{_fmt(c['nwe_diesel_cif_usd_mt'], 2)} | {_fmt(c['med_diesel_cif_usd_mt'], 2)} | "
            f"{_fmt(c['nwe_euro_gasoline_usd_mt'], 2)} | {_fmt(c['imo_vlsfo_05_usd_mt'], 2)} | "
            f"{_fmt(c['ulsd_gasoil_spread_usd_mt'], 2)} |"
        )

    short_labels = [c["case_label"].split("(")[0].strip() for c in cases]
    echart = {
        "title": {
            "text": f"EULR {yr} Product Slate & FCC Margin Across EU ETS & Peer-Sync Scenarios",
            "left": "center",
            "textStyle": {"fontSize": 13.5},
        },
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
        "legend": {"bottom": 0},
        "grid": {"left": "7%", "right": "8%", "top": 48, "bottom": 64},
        "xAxis": {"type": "category", "data": short_labels, "axisLabel": {"interval": 0, "rotate": 12}},
        "yAxis": [
            {"type": "value", "name": "Product Price ($/mt)", "min": 350},
            {"type": "value", "name": "FCC Margin ($/bbl)", "position": "right"},
        ],
        "series": [
            {"name": "NWE Diesel EN590 ($/mt)", "type": "bar", "data": [c["nwe_diesel_cif_usd_mt"] for c in cases], "itemStyle": {"color": "#1a73e8"}},
            {"name": "NWE Euro Gasoline ($/mt)", "type": "bar", "data": [c["nwe_euro_gasoline_usd_mt"] for c in cases], "itemStyle": {"color": "#34a853"}},
            {"name": "IMO 0.5% VLSFO ($/mt)", "type": "bar", "data": [c["imo_vlsfo_05_usd_mt"] for c in cases], "itemStyle": {"color": "#5f6368"}},
            {"name": "FCC Margin ($/bbl)", "type": "line", "yAxisIndex": 1, "symbolSize": 8, "data": [c["fcc_margin_usd_bbl"] for c in cases], "itemStyle": {"color": "#ea4335"}},
        ],
    }
    md = "\n".join(lines)
    return {"inline_markdown": md, "artifact_markdown": md, "echarts_option": echart}


def render_bqml_outputs(bqml_res: dict[str, Any]) -> dict[str, Any]:
    """Render BigQuery ML ARIMA_PLUS forecast tables (2024 actual + 2025..2050 forecasts) + EChart."""
    milestone_yrs = [2020, 2024, 2025, 2030, 2035, 2040, 2045, 2050]
    m_hdr = " | ".join(f"{y}{' (Act)' if y <= 2024 else ' (BQML)'}" for y in milestone_yrs)
    m_sep = " | ".join("---:" for _ in milestone_yrs)

    inline_lines = [
        "### BigQuery ML `ARIMA_PLUS` Driver Trajectories (`1990–2024` Actuals -> `2025–2050` Forecast)",
        "",
        f"| Domain | Series | Target Row | Units | {m_hdr} |",
        f"| :--- | :--- | :--- | :---: | {m_sep} |",
    ]
    for s in bqml_res["series"]:
        vals: list[str] = []
        for yr in milestone_yrs:
            v = s["actuals"].get(yr) if yr <= 2024 else s["forecasts"].get(yr)
            vals.append(_fmt(v, 2))
        inline_lines.append(
            f"| `{s['domain_group']}` | **{s['series_label']}** | `{s['target_sheet']}!R{s['target_row']}` | {s['units']} | {' | '.join(vals)} |"
        )

    # Full 2024..2050 artifact table
    all_fc_yrs = list(range(2024, 2051))
    full_lines = [
        "# BigQuery ML `ARIMA_PLUS` Complete 2024–2050 Trajectory Matrix",
        "",
        inline_lines[2],
        inline_lines[3],
        *inline_lines[4:],
        "",
        "## Annual Forecast Grid (`2024` Actual + `2025–2050` `ARIMA_PLUS` Mean)",
        "| Series ID | Units | " + " | ".join(str(y) for y in all_fc_yrs) + " |",
        "| :--- | :---: | " + " | ".join("---:" for _ in all_fc_yrs) + " |",
    ]
    for s in bqml_res["series"]:
        r_vals = [
            _fmt(s["actuals"].get(2024) if y == 2024 else s["forecasts"].get(y), 2)
            for y in all_fc_yrs
        ]
        full_lines.append(f"| `{s['series_id']}` | {s['units']} | {' | '.join(r_vals)} |")

    # Plot Crudes if available, else first domain's series across 2015..2050
    chart_yrs = list(range(2015, 2051))
    crude_series = [s for s in bqml_res["series"] if s["domain_group"] == "CRUDES"] or bqml_res["series"][:4]
    palette = ["#1a73e8", "#ea4335", "#34a853", "#fbbc04", "#9334e6"]
    echart_series = []
    for idx, s in enumerate(crude_series[:5]):
        pts = [
            s["actuals"].get(y) if y <= 2024 else s["forecasts"].get(y)
            for y in chart_yrs
        ]
        echart_series.append(
            {
                "name": s["series_label"],
                "type": "line",
                "smooth": True,
                "data": pts,
                "itemStyle": {"color": palette[idx % len(palette)]},
            }
        )

    echart = {
        "title": {
            "text": "BigQuery ML ARIMA_PLUS Historical (2015–2024) & Forecast (2025–2050) Trajectories",
            "left": "center",
            "textStyle": {"fontSize": 14},
        },
        "tooltip": {"trigger": "axis"},
        "legend": {"bottom": 0},
        "grid": {"left": "7%", "right": "5%", "top": 48, "bottom": 56},
        "xAxis": {"type": "category", "data": [str(y) for y in chart_yrs]},
        "yAxis": {"type": "value", "name": crude_series[0]["units"] if crude_series else "Value"},
        "series": echart_series,
    }
    return {
        "inline_markdown": "\n".join(inline_lines),
        "artifact_markdown": "\n".join(full_lines),
        "echarts_option": echart,
    }


def render_hck_economics_outputs(hck_res: dict[str, Any]) -> dict[str, Any]:
    """Render Hydrocracker IRR sensitivity, Naphtha/Diesel revamp & ULSD-Gasoil parity tables + EChart."""
    rev = hck_res["hck_naphtha_revamp"]
    sweep = hck_res["hck_irr_sensitivity_sweep"]
    ulsd = hck_res["ulsd_gasoil_spread_economics"]

    lines = [
        "### European Hydrocracker (`200 kb/d`) IRR & Distillate Spread Economics",
        "",
        f"- **Initial Capex (`2015 NWE HCK IRR!I25`)**: `${_fmt(hck_res['initial_capex_musd'], 2)}M` | **Base Sour HCK Uplift**: `${_fmt(hck_res['base_net_hck_uplift_usd_bbl'], 2)}/bbl` | **Discount Rate (WACC)**: `{hck_res['discount_rate_wacc']*100:.1f}%`",
        f"- **HCK Naphtha vs. Diesel Mode (`HCK naphtha revamp`)**: Max Naphtha VM = `${_fmt(rev['hck_vm_max_naphtha_usd_bbl'], 2)}/bbl` | Max Diesel VM = `${_fmt(rev['hck_vm_max_diesel_usd_bbl'], 2)}/bbl` | Revamp Capex = `${_fmt(rev['incremental_capex_musd'], 1)}M`",
        "",
        "#### 1. 9-Point Sour Hydrocracker Conversion Margin Sensitivity (`2015 NWE HCK IRR`)",
        "| Margin Shock (`$/bbl`) | Net HCK Uplift (`$/bbl`) | Annual EBITDA (`$M/yr`) | Project IRR (`%`) | Project NPV @ WACC (`$M`) |",
        "| ---: | ---: | ---: | ---: | ---: |",
    ]
    for r in sweep:
        lines.append(
            f"| `{r['margin_delta_usd_bbl']:+.1f}` | {_fmt(r['net_hck_uplift_usd_bbl'], 2)} | "
            f"{_fmt(r['annual_ebitda_musd'], 1)} | **{_fmt(r['project_irr_pct'], 2)}%** | "
            f"{_fmt(r['npv_musd_at_wacc'], 1)} |"
        )

    lines.extend(
        [
            "",
            "#### 2. ULSD 10ppm vs. 0.1%S Gasoil Cost-Coverage Thresholds (`ULSD-GO_spread_econs`, `$/mt`)",
            "| Year | Variable Cost Parity | Cash Cost Parity | 40-Yr Replacement Parity | Model 10ppm–GO Spread | USGC ULSD Spread |",
            "| :---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for u in ulsd:
        lines.append(
            f"| **{u['year']}** | {_fmt(u['var_cost_parity_usd_mt'], 2)} | {_fmt(u['cash_cost_parity_usd_mt'], 2)} | "
            f"{_fmt(u['full_40yr_replacement_usd_mt'], 2)} | {_fmt(u['model_10ppm_vs_gasoil_usd_mt'], 2)} | "
            f"{_fmt(u['usgc_spread_usd_mt'], 2)} |"
        )

    echart = {
        "title": {
            "text": "200 kb/d NWE Hydrocracker Project IRR (%) & NPV ($M) vs. Conversion Margin Shock",
            "left": "center",
            "textStyle": {"fontSize": 13.5},
        },
        "tooltip": {"trigger": "axis"},
        "legend": {"bottom": 0},
        "grid": {"left": "7%", "right": "8%", "top": 48, "bottom": 50},
        "xAxis": {
            "type": "category",
            "name": "Margin Shock ($/bbl)",
            "data": [f"{r['margin_delta_usd_bbl']:+.1f} $/bbl" for r in sweep],
        },
        "yAxis": [
            {"type": "value", "name": "Project IRR (%)"},
            {"type": "value", "name": "Project NPV ($M)", "position": "right"},
        ],
        "series": [
            {"name": "Project IRR (%)", "type": "line", "smooth": True, "symbolSize": 8, "data": [r["project_irr_pct"] for r in sweep], "itemStyle": {"color": "#1a73e8"}},
            {"name": "NPV @ WACC ($M)", "type": "bar", "yAxisIndex": 1, "barMaxWidth": 28, "data": [r["npv_musd_at_wacc"] for r in sweep], "itemStyle": {"color": "#0f9d58", "opacity": 0.7}},
        ],
    }
    md = "\n".join(lines)
    return {"inline_markdown": md, "artifact_markdown": md, "echarts_option": echart}
