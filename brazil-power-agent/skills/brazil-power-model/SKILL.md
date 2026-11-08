---
name: brazil-power-model
description: Primary end-to-end guided workflow for the Brazil Power Generation Techno-Economic Model v13 (2023-11-27-Brazil_TT_v13_RJEB.xlsm). Collects scenario assumptions via interactive cards (ask_question), updates General!B5:N40 via brazil-power-mcp, runs Tornado IRR, BQML ARIMA_PLUS, 23-Year LCOE, 30-Year DCF, or Thermal CVU sweeps, renders exact Excel-layout tables + ECharts inline (render_chart) and wide tab replicas in side-pane Artifacts, and exports 100% faithful 22-tab .xlsx or Google Sheets workbooks.
---

# Brazil Energy Model (v13) — Master Interactive Modeling Workflow (`/brazil-power-model`)

Use this skill whenever the analyst invokes `/brazil-power-model` or asks to start, configure, or run an interactive Brazil Power Generation v13 modeling session in the Gemini App (`Chat App`).

This workflow encapsulates the complete 22-tab `2023-11-27-Brazil_TT_v13_RJEB.xlsm` workbook (`Version Control`, `General`, `Output_1`, `Output_2`, `Output_3`, `_01_CF` .. `_12_CF`, `_CAPEX 01`, `CVU_GF`, `LT Capex`, `LT Fuel`, `LT CF`) using the `brazil-power-mcp` MCP server, native interactive visual cards (`ask_question`), inline Apache ECharts (`render_chart` / `mcp_data-agent-kit_render_chart`), side-pane Markdown **Artifact** tables (`write_to_file`), and 1-click 22-tab `.xlsx` or Google Sheets export (`export_full_22tab_workbook`).

---

## Reference: 12 Technology Tabs & `General!B5:N40` Column Mapping

| Sheet Code | `General` Col | `Output_3` Col | Display Name | Fuel / Technology | Baseline Capacity (`Row 8`) | Baseline Capex (`Row 11`, R$/kW) | Lead Time (`Row 14`, yrs) | Capacity Factor (`Row 16`) | Fuel Cost (`Row 20`) | Real WACC (`Row 34`) |
| :--- | :---: | :---: | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **`_01_CF`** | `Col C` | `Col B` | **Gas CCGT** | Natural Gas CCGT | `500.0 MW` | `4,250.00` | `3.0` | `85.0%` | `4.50 R$/MMBtu` | `8.00%` |
| **`_02_CF`** | `Col D` | `Col C` | **Biomass CHP** | Sugarcane Bagasse Boiler | `50.0 MW` | `5,100.00` | `2.0` | `50.0%` | `0.00` | `8.00%` |
| **`_03_CF`** | `Col E` | `Col D` | **Biomass Retrofit** | Boiler Retrofit | `50.0 MW` | `2,800.00` | `2.0` | `45.0%` | `0.00` | `8.00%` |
| **`_04_CF`** | `Col F` | `Col F` | **Onshore Wind** | Wind WT Cl. 6 | `30.0 MW` | `5,100.00` | `2.0` | `45.0%` | `0.00` | `8.00%` |
| **`_05_CF`** | `Col G` | `Col G` | **Utility Solar PV** | Utility-Scale Solar PV | `30.0 MW` | `3,850.00` | `1.0` | `26.0%` | `0.00` | `8.00%` |
| **`_06_CF`** | `Col H` | `Col I` | **Small Hydro (SHP)** | Run-of-River SHP | `20.0 MW` | `7,500.00` | `3.0` | `55.0%` | `0.00` | `8.00%` |
| **`_07_CF`** | `Col I` | `Col J` | **Local Coal (CFBC)** | Domestic Coal CFBC | `350.0 MW` | `9,200.00` | `4.0` | `80.0%` | `3.20 US$/MMBtu` | `8.00%` |
| **`_08_CF`** | `Col J` | `Col H` | **Imported Coal (PC)** | Pulverized Coal PC | `600.0 MW` | `8,400.00` | `4.0` | `80.0%` | `4.10 US$/MMBtu` | `8.00%` |
| **`_09_CF`** | `Col K` | `Col E` | **Biomass Woodchip** | Dedicated Woodchip Thermal | `50.0 MW` | `5,600.00` | `2.0` | `75.0%` | `18.00 R$/MMBtu` | `8.00%` |
| **`_10_CF`** | `Col L` | — | **LNG CCGT** | Imported LNG CCGT | `500.0 MW` | `4,400.00` | `3.0` | `85.0%` | `8.50 US$/MMBtu` | `8.00%` |
| **`_11_CF`** | `Col M` | — | **DG Solar Residential** | Rooftop PV Residential | `5.0 kW` | `4,800.00` | `1.0` | `18.0%` | `0.00` | `8.00%` |
| **`_12_CF`** | `Col N` | — | **DG Solar Commercial** | Rooftop PV Commercial | `100.0 kW` | `4,100.00` | `1.0` | `19.5%` | `0.00` | `8.00%` |

---

## 4-Step Interactive Visual Card Workflow

### Step 1: Technology Group & Scenario Assumption Selection (`ask_question`)

1. If the analyst already provided explicit parameter overrides in natural language (e.g., *"Set Gas CCGT fuel cost to 6.50 R$/MMBtu and Small Hydro lead time to 2 years"*), proceed directly to **Step 2**.
2. Otherwise, first call `get_session_assumptions` on `brazil-power-mcp` to inspect current baseline and staged values from `General!B5:N40`.
3. Present a native interactive visual card via `ask_question` so the analyst can select technologies and scenario assumption changes without leaving chat:

```json
{
  "questions": [
    {
      "question": "Which Brazil Power v13 technology groups would you like to model or adjust in General!B5:N40?",
      "is_multi_select": true,
      "options": [
        "(Recommended) Core Dispatch & Renewables Basket: Gas CCGT (_01_CF Col C), Onshore Wind (_04_CF Col F), Utility Solar PV (_05_CF Col G), Small Hydro SHP (_06_CF Col H)",
        "Thermal & Coal Fleet: Gas CCGT (_01_CF Col C), Local Coal CFBC (_07_CF Col I), Imported Coal PC (_08_CF Col J), LNG CCGT (_10_CF Col L)",
        "Biomass Portfolio: Biomass CHP (_02_CF Col D), Biomass Retrofit (_03_CF Col E), Biomass Woodchip (_09_CF Col K)",
        "Distributed Generation Solar: DG Solar Residential (_11_CF Col M) & DG Solar Commercial (_12_CF Col N)",
        "All 12 Generation Technologies (_01_CF .. _12_CF across General!C5:N40)"
      ]
    },
    {
      "question": "Which scenario assumptions in General!B5:N40 would you like to apply (or use the write-in box for custom cell/parameter overrides)?",
      "is_multi_select": true,
      "options": [
        "(Recommended) Keep current General!B5:N40 baseline assumptions (Gas Fuel=4.50 R$/MMBtu, WACC=8.00%, SHP Lead Time=3.0 yrs)",
        "High Gas Fuel & Fast SHP Build: Gas CCGT Fuel (General!C20) 4.50 -> 6.50 R$/MMBtu (+44.4%), Small Hydro Lead Time (General!H14) 3.0 -> 2.0 yrs (-33.3%)",
        "Tighter Capital Cost & Higher WACC: Real WACC (General!C34:N34) 8.00% -> 9.50% (+150 bps), Solar PV Capex (General!G11) -10%",
        "Reset all staged session overrides back to the clean 2023-11-27-Brazil_TT_v13_RJEB.xlsm seed baseline"
      ]
    }
  ]
}
```

### Step 2: Update Session Assumptions & Render `General!B5:N40` Diff Preview

1. If the analyst selected or typed any parameter changes (or requested a baseline reset), call `update_session_assumptions` on `brazil-power-mcp` with `overrides` (accepts either semantic dictionaries such as `{"_01_CF": {"fuel_cost_r_per_mmbtu": 6.50}, "_06_CF": {"lead_time_years": 2.0}}` or exact Excel cell coordinates such as `{"General!C20": 6.50, "General!H14": 2.0}`).
2. Render the returned `inline_excel_table_md` directly in the chat response so the analyst sees the exact `General!B5:N40` rows, Excel coordinates, units, and `Baseline -> Current (Δ%)` deltas.
3. Write `full_artifact_table_md` (the complete 12-column `General!B5:N40` parameter grid covering `_01_CF.._12_CF`) to a side-pane **Artifact** (`brazil_v13_general_assumptions.md`) using `write_to_file` with `ArtifactMetadata(UserFacing=True, RequestFeedback=False, Summary="Complete 12-Technology General!B5:N40 Assumptions Matrix")`.

### Step 3: Interactive Analysis Selection Card (`ask_question`)

If the analyst has not yet specified which quantitative solver macro(s) to execute, present the **Analysis Selection Card** via `ask_question`:

```json
{
  "questions": [
    {
      "question": "Which Brazil Power v13 quantitative analysis workflows would you like to execute on the active session?",
      "is_multi_select": true,
      "options": [
        "(Recommended) Tornado IRR Sensitivity (calcule_tir1..12 -> _01_CF.._12_CF!A4:H12 & Output_1)",
        "23-Year Multi-Technology LCOE Horizon Forecast 2024–2046 (lcoe_exec -> Output_3!B8:J31, 184 binary-search solves + Thermal ICB)",
        "BigQuery ML ARIMA_PLUS 23-Year Time-Series Refresh (LT Capex!B8:J30, LT Fuel!B8:J30, LT CF!B8:J30)",
        "30-Year Project & Shareholder DCF Cash Flow Schedule 2024–2053 (_01_CF.._12_CF Rows 33–101 & Output_2)",
        "10-Point Thermal CVU & Physical Guarantee Sweep (calculo_cvu1..12 -> CVU_GF & _06_CF.._08_CF)"
      ]
    }
  ]
}
```

### Step 4: Dual Inline + Side-Pane Artifact Rendering & 22-Tab Workbook Export

For each selected analysis workflow, execute the corresponding `brazil-power-mcp` tool and adhere strictly to the **Dual Inline + Artifact Rendering Standard**:

1. **Tornado IRR Sensitivity** (`run_tornado_sensitivity`):
   - Render `inline_excel_table_md` (`_0N_CF!A4:H12` 21-point IRR sensitivity grid + `Output_1` summary) inline in chat.
   - Call `render_chart` (`mcp_data-agent-kit_render_chart`) with `echarts_spec` to render the horizontal Tornado bar chart inline.
   - Write `full_artifact_table_md` to a side-pane **Artifact** (`brazil_v13_tornado_output1.md`).
2. **23-Year Multi-Tech LCOE Forecast** (`run_lcoe_horizon_forecast`):
   - Render `inline_excel_table_md` (compact milestone table: `2024, 2025, 2030, 2035, 2040, 2046` across `Output_3!B8:J31`) inline in chat.
   - Call `render_chart` with `echarts_spec` to render the 23-year multi-technology LCOE trajectory line chart inline.
   - Write `full_artifact_table_md` (complete 23-row × 9-column `Output_3!B8:J31` replica covering `2024–2046`, including Legacy Quirk 7 blank `Col D` in `strict_legacy_vba` mode) to a side-pane **Artifact** (`brazil_v13_output3_lcoe_2024_2046.md`).
3. **BigQuery ML `ARIMA_PLUS` Time-Series Refresh** (`run_bqml_timeseries_refresh`):
   - Render `inline_excel_table_md` (milestone normalized index summary across `LT Capex!B8:J30`, `LT Fuel!B8:J30`, `LT CF!B8:J30`) inline in chat.
   - Call `render_chart` with `echarts_spec` to render the 23-year BQML trajectory chart inline.
   - Write `full_artifact_table_md` (full 23-row `LT Capex`, `LT Fuel`, and `LT CF` Excel replicas) to a side-pane **Artifact** (`brazil_v13_bqml_lt_curves.md`).
4. **30-Year Project & Shareholder DCF + Thermal CVU Sweep** (`run_dcf_cashflow_analysis`):
   - Render `inline_excel_table_md` (executive valuation header `_0N_CF!B2:H14` + milestone years `2024, 2025, 2026, 2027, 2028, 2030, 2035, 2040, 2045, 2050, 2053` + `CVU_GF` 10-point table when `include_cvu_gf_sweep=True`) inline in chat.
   - Call `render_chart` with `echarts_spec` (and `cvu_sweep_echarts_option` if a CVU sweep was run) to render the 30-year Free Cash Flow & Cumulative NPV stacked bar/line visual inline.
   - Write `full_artifact_table_md` (complete 30-column `Col K..Col AN` × Rows `33–101` horizontal `_0N_CF` DCF replica) to a side-pane **Artifact** (`brazil_v13_dcf_30yr_schedule.md`).
5. **1-Click 22-Tab `.xlsx` or Google Sheets Deliverable Export** (`export_full_22tab_workbook`):
   - At the conclusion of the analysis turn (or whenever requested), offer or invoke `export_full_22tab_workbook(export_format="xlsx" | "google_sheets" | "both")`.
   - Confirm that all 22 original worksheets (`Version Control`, `General`, `Output_1`, `Output_2`, `Output_3`, `_01_CF` .. `_12_CF`, `_CAPEX 01`, `CVU_GF`, `LT Capex`, `LT Fuel`, `LT CF`) are preserved with 100% of original Excel formulas, number formats, styles, and all staged overrides/solved outputs written to their exact cell coordinates, and provide the clickable `[filename.xlsx](file:///...)` link or live Google Sheets URL.
