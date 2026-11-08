---
name: brazil-bqml
description: Direct shortcut workflow for the Brazil Power v13 BigQuery ML ARIMA_PLUS 23-year time-series forecast refresh (LT Capex!B8:J30, LT Fuel!B8:J30, LT CF!B8:J30). Prompts for target curve selection via ask_question, executes run_bqml_timeseries_refresh on brazil-power-mcp, renders milestone index matrices and ECharts trajectory fan/line visuals inline via render_chart, writes full 23-year LT tab replicas to a side-pane Artifact, and chains into run_lcoe_horizon_forecast or 22-tab export.
---

# Brazil Energy Model (v13) — BigQuery ML `ARIMA_PLUS` Time-Series Forecast Shortcut (`/brazil-bqml`)

Use this skill whenever the analyst invokes `/brazil-bqml` or asks to query, refresh, or inspect the BigQuery ML `ARIMA_PLUS` long-term time-series trajectories (`2024–2046`) that drive `LT Capex!B8:J30`, `LT Fuel!B8:J30`, and `LT CF!B8:J30` in the Brazil Power v13 model (`2023-11-27-Brazil_TT_v13_RJEB.xlsm`).

---

## Excel Coordinate Architecture (`LT Capex`, `LT Fuel`, `LT CF` -> `General!B5:N40` & `Output_3!B8:J31`)

In the 22-tab Brazil Power v13 workbook, the three Connected Sheets tabs **`LT Capex`**, **`LT Fuel`**, and **`LT CF`** store normalized 23-year trajectory multipliers (`2024 = 1.0000` at `Row 8` through `2046` at `Row 30`) across columns `Col B` .. `Col J` (mapping to `_01_CF` .. `_12_CF` and feeding `General!B5:N40`, `Output_1`, and `Output_3!B8:J31`):

| Worksheet Tab | Cell Range (`2024–2046`) | BigQuery ML Governance Source View | Normalized Base (`2024`, `Row 8`) | Downstream Impact on `Output_3!B8:J31` (`lcoe_exec`) |
| :--- | :--- | :--- | :---: | :--- |
| **`LT Capex`** | `LT Capex!B8:J30` (`A8:A30` = Years `2024..2046`) | `comm-model-mod.sheets_commodity_mod_governance.vw_connected_sheets_lt_forecasts` (`curve_type = 'CAPEX'`) | `1.0000` | Multiplies `General!C11:N11` (`Base capital cost R$/kW`) for each vintage year `t` |
| **`LT Fuel`** | `LT Fuel!B8:J30` (`A8:A30` = Years `2024..2046`) | `comm-model-mod.sheets_commodity_mod_governance.vw_connected_sheets_lt_forecasts` (`curve_type = 'FUEL'`) | `1.0000` | Multiplies `General!C20:N20` (`Fuel cost`) for thermal tabs `_01_CF, _07_CF, _08_CF, _09_CF, _10_CF` |
| **`LT CF`** | `LT CF!B8:J30` (`A8:A30` = Years `2024..2046`) | `comm-model-mod.sheets_commodity_mod_governance.vw_connected_sheets_lt_forecasts` (`curve_type = 'CF'`) | `1.0000` | Multiplies `General!C16:N16` (`Capacity factor`) for wind, solar, hydro, and biomass technologies |

*(Note: When running offline or without active BigQuery credentials, `run_bqml_timeseries_refresh` automatically falls back to the deterministic local `ARIMA_PLUS` snapshot extracted from the v13 seed &BQML surrogate fixture.)*

---

## Step-by-Step Execution Workflow

> [!IMPORTANT]
> **FAST-START LATENCY RULE (ZERO PRE-CARD TOOL CALLS)**:
> When the analyst invokes `/brazil-bqml` without specifying which curves to refresh, your **VERY FIRST AND ONLY tool call on Turn 1 MUST be `ask_question`**. Do **NOT** call `get_session_assumptions`, do **NOT** search the filesystem (`find_by_name`, `grep_search`, `list_dir`, `view_file`), and do **NOT** run shell commands before presenting the `ask_question` card below.

### Step 1: Interactive Curve Selection & LCOE Chaining Card (`ask_question`)

If the analyst invokes `/brazil-bqml` without specifying which curves to refresh, immediately call `ask_question` on Turn 1 to display the curve selection card:

```json
{
  "questions": [
    {
      "question": "Which BigQuery ML ARIMA_PLUS long-term trajectory tabs (2024–2046) would you like to refresh into the active session?",
      "is_multi_select": true,
      "options": [
        "(Recommended) All 3 Long-Term Forecast Tabs: LT Capex!B8:J30, LT Fuel!B8:J30, and LT CF!B8:J30",
        "LT Capex!B8:J30 — Specific Capital Cost Learning Curves (Solar PV -38%, Onshore Wind -22% by 2046)",
        "LT Fuel!B8:J30 — Thermal Fuel Commodity Trajectories (Natural Gas CCGT, Coal CFBC/PC, Biomass Woodchip)",
        "LT CF!B8:J30 — Capacity Factor & Hub-Height / Tracker Efficiency Curves"
      ]
    },
    {
      "question": "After injecting the refreshed ARIMA_PLUS trajectories into LT Capex / LT Fuel / LT CF, should we immediately re-solve the 23-Year LCOE Horizon (Output_3!B8:J31)?",
      "is_multi_select": false,
      "options": [
        "(Recommended) Yes — Refresh LT tabs and immediately run run_lcoe_horizon_forecast (Output_3!B8:J31)",
        "Only refresh and inspect the LT Capex / LT Fuel / LT CF trajectory tables and ECharts visual for now"
      ]
    }
  ]
}
```

### Step 2: Execute `run_bqml_timeseries_refresh` on `brazil-power-mcp`

1. Call `run_bqml_timeseries_refresh(curve_types=..., apply_to_session_lt_tabs=True)` on `brazil-power-mcp`. *(If `brazil-power-mcp` is not in your active MCP tool list, do NOT search the filesystem; invoke `mcp_server.py --call run_bqml_timeseries_refresh --args '<json>' --compact-llm` directly.)*
2. Note the returned `source` (`bigquery_live` or `offline_arima_plus_snapshot`) and number of updated cells across `LT Capex!B8:J30`, `LT Fuel!B8:J30`, and `LT CF!B8:J30`.

### Step 3: Dual Inline (Summary Table + ECharts) & Pre-Saved 23-Row Side-Pane Artifact

1. **Inline Excel Summary Table**: Render `inline_markdown` (`inline_excel_table_md`) directly in chat, showing milestone normalized index multipliers (`2024 = 1.0000`, `2025`, `2030`, `2035`, `2040`, `2046`) and `2024 -> 2046 Δ (%)` across `Col B (CCGT)` .. `Col J (Coal CFBC)`.
2. **Inline ECharts Trajectory Chart**: Call `render_chart` (`mcp_data-agent-kit_render_chart`) with the returned `echarts_option` (`echarts_spec`) to display the 23-year normalized `ARIMA_PLUS` curves inline.
3. **Pre-Saved 23-Year `LT Capex / LT Fuel / LT CF` Side-Pane Artifact**: `run_bqml_timeseries_refresh` automatically writes the multi-line `full_artifact_table_md` directly into your active conversation brain folder at `artifact_file_path` (`artifact_file_uri`) in `<1 ms` and runs an automatic file-guard. Link directly to `[<artifact_filename>](<artifact_file_uri>)` (if calling `write_to_file` to open the side-pane Artifact tab, pass `TargetFile=artifact_file_path` and a 1-line stub `CodeContent="# Loading Excel Tab Replica..."` — NEVER re-type the multi-column Markdown table inside `write_to_file`).

### Step 4: Optional Immediate Chain to `run_lcoe_horizon_forecast` & 22-Tab Export

1. If the analyst selected immediate LCOE re-solving, call `run_lcoe_horizon_forecast` to propagate the updated `LT Capex`, `LT Fuel`, and `LT CF` trajectories into `Output_3!B8:J31`, and render the updated LCOE table and chart.
2. Offer 1-click export of the complete 22-tab workbook via `export_full_22tab_workbook(export_format="xlsx" | "google_sheets" | "both")`.
