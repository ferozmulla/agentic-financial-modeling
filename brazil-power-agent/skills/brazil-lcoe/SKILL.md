---
name: brazil-lcoe
description: Direct shortcut workflow for the Brazil Power v13 23-Year Multi-Technology LCOE Horizon Forecast (2024–2046, 184 binary-search LCOE solves + Thermal ICB dispatch on Output_3!B8:J31). Collects scenario or BQML curve choices via ask_question, executes run_lcoe_horizon_forecast on brazil-power-mcp, renders the milestone Output_3 table and multi-series EChart inline via render_chart, writes the complete 23-row Output_3!B8:J31 replica to a side-pane Artifact, and offers 22-tab .xlsx or Google Sheets export.
---

# Brazil Energy Model (v13) — 23-Year Multi-Technology LCOE Forecast Shortcut (`/brazil-lcoe`)

Use this skill whenever the analyst invokes `/brazil-lcoe` or asks to compute or inspect the 23-year (`2024–2046`) Multi-Technology Levelized Cost of Electricity (LCOE) trajectory across `Output_3!B8:J31` (`lcoe_exec`).

---

## Excel Coordinate Architecture (`Output_3!B8:J31`, `General!B5:N40`, `LT Capex/Fuel/CF`)

The `lcoe_exec` macro iterates over each forecast year `t ∈ [2024..2046]` (`Output_3!B3` active year counter), scales each technology's specific Capex, Fuel Cost, and Capacity Factor by the normalized trajectories in `LT Capex!B8:J30`, `LT Fuel!B8:J30`, and `LT CF!B8:J30` relative to `General!B5:N40`, solves the breakeven tariff (`R$/MWh`) where Project NPV = 0 across `_01_CF.._12_CF`, and writes the 23-row × 9-column matrix into **`Output_3!B8:J31`** (`Output_1` and `Output_2` hold point-in-time comparisons):

| `Output_3` Column | Header Cell (`Row 8`) | Technology Sheet | Technology Description | Solver / Parity Behavior (`Rows 9..31`, Years `2024..2046`) |
| :---: | :--- | :---: | :--- | :--- |
| **`Col A`** | `Output_3!A8` (`Year`) | — | Forecast Horizon Year | `A9 = 2024` .. `A31 = 2046` (23 annual rows) |
| **`Col B`** | `Output_3!B8` (`CCGT`) | `_01_CF` | Natural Gas CCGT (`General!Col C`) | Thermal ICB / Breakeven LCOE solve (`R$/MWh`) |
| **`Col C`** | `Output_3!C8` (`Bio (CHP)`) | `_02_CF` | Biomass Sugarcane Bagasse CHP (`General!Col D`) | 2-Stage Discrete Lattice Binary Search LCOE (`R$/MWh`) |
| **`Col D`** | `Output_3!D8` (`Bio (retro)`) | `_03_CF` | Biomass Boiler Retrofit (`General!Col E`) | **Legacy Quirk 7**: Blank (`-`) in `strict_legacy_vba`; solved in `modern_corrected` |
| **`Col E`** | `Output_3!E8` (`Bio (WC)`) | `_09_CF` | Biomass Woodchip Thermal (`General!Col K`) | Thermal ICB / Breakeven LCOE solve (`R$/MWh`) |
| **`Col F`** | `Output_3!F8` (`Wind`) | `_04_CF` | Onshore Wind WT Cl. 6 (`General!Col F`) | 2-Stage Discrete Lattice Binary Search LCOE (`R$/MWh`) |
| **`Col G`** | `Output_3!G8` (`Solar`) | `_05_CF` | Utility-Scale Solar PV (`General!Col G`) | 2-Stage Discrete Lattice Binary Search LCOE (`R$/MWh`) |
| **`Col H`** | `Output_3!H8` (`Coal (PC)`) | `_08_CF` | Imported Pulverized Coal PC (`General!Col J`) | Thermal ICB (`_08_CF!G2`) dispatch solve (`R$/MWh`) |
| **`Col I`** | `Output_3!I8` (`SHP`) | `_06_CF` | Small Hydro Run-of-River SHP (`General!Col H`) | 2-Stage Discrete Lattice Binary Search LCOE (`R$/MWh`) |
| **`Col J`** | `Output_3!J8` (`Coal (CFBC)`) | `_07_CF` | Domestic Local Coal CFBC (`General!Col I`) | Thermal ICB (`_07_CF!G2`) dispatch solve (`R$/MWh`) |

---

## Step-by-Step Execution Workflow

> [!IMPORTANT]
> **FAST-START LATENCY RULE (ZERO PRE-CARD TOOL CALLS)**:
> When the analyst invokes `/brazil-lcoe` without specifying parameters, your **VERY FIRST AND ONLY tool call on Turn 1 MUST be `ask_question`**. Do **NOT** call `get_session_assumptions`, do **NOT** search the filesystem (`find_by_name`, `grep_search`, `list_dir`, `view_file`), and do **NOT** run shell commands before presenting the `ask_question` card below.

### Step 1: Interactive Assumption & Parity Mode Card (`ask_question`)

If the analyst invokes `/brazil-lcoe` without specifying parameters, immediately call `ask_question` on Turn 1 to present a quick configuration card:

```json
{
  "questions": [
    {
      "question": "How would you like to configure the 23-Year Multi-Technology LCOE Horizon run (Output_3!B8:J31, 2024–2046)?",
      "is_multi_select": false,
      "options": [
        "(Recommended) Strict Legacy VBA Parity (strict_legacy_vba — 100% bit-exact match with 2023-11-27-Brazil_TT_v13_RJEB.xlsm including Quirk 7 on Output_3!D9:D31)",
        "Refresh BigQuery ML ARIMA_PLUS Long-Term Curves (LT Capex, LT Fuel, LT CF) first, then run 23-Year LCOE Forecast",
        "Modern Corrected Mode (modern_corrected — populates Output_3!D9:D31 Biomass Retrofit alongside all 8 other technologies)"
      ]
    },
    {
      "question": "Would you like to stage any General!B5:N40 assumption changes before solving the 184 LCOE horizon points?",
      "is_multi_select": false,
      "options": [
        "(Recommended) Use current session assumptions in General!B5:N40",
        "High Gas Fuel & Fast SHP Scenario: Gas CCGT Fuel (General!C20) = 6.50 R$/MMBtu, SHP Lead Time (General!H14) = 2.0 yrs",
        "Higher Cost of Capital Scenario: Real WACC (General!C34:N34) = 9.50%",
        "Reset session to clean 2023-11-27-Brazil_TT_v13_RJEB.xlsm seed baseline"
      ]
    }
  ]
}
```

### Step 2: Apply Any Prerequisite Updates & Call `run_lcoe_horizon_forecast`

1. If the analyst chose to modify `General!B5:N40` assumptions, call `update_session_assumptions` on `brazil-power-mcp` first.
2. If the analyst chose to refresh the BigQuery ML `ARIMA_PLUS` curves first, call `run_bqml_timeseries_refresh` on `brazil-power-mcp`.
3. Call `run_lcoe_horizon_forecast(parity_mode=...)` on `brazil-power-mcp`. *(If `brazil-power-mcp` is not in your active MCP tool list, do NOT search the filesystem; invoke `mcp_server.py --call run_lcoe_horizon_forecast --args '<json>' --compact-llm` directly.)*

### Step 3: Dual Inline (`Output_3` Milestone Table + ECharts) & Pre-Saved 23-Row Side-Pane Artifact

1. **Compact Inline Milestone Table**: Render `inline_markdown` (`inline_excel_table_md`) directly in the chat response, showing the 5-year milestone rows (`2024 (Row 9)`, `2025 (Row 10)`, `2030 (Row 15)`, `2035 (Row 20)`, `2040 (Row 25)`, `2046 (Row 31)`) across all 9 columns (`Col B CCGT` .. `Col J Coal CFBC`) in `R$/MWh` with `2024 -> 2046 Δ (R$/MWh)` and `Δ (%)`.
2. **Inline Multi-Series Trajectory Chart**: Call `render_chart` (`mcp_data-agent-kit_render_chart`) with the returned `echarts_option` (`echarts_spec`) to plot the 23-year (`2024–2046`) LCOE trajectories across technologies.
3. **Pre-Saved 23-Row `Output_3!B8:J31` Side-Pane Artifact**: `run_lcoe_horizon_forecast` automatically writes the multi-line `full_artifact_table_md` directly into your active conversation brain folder at `artifact_file_path` (`artifact_file_uri`) in `<1 ms` and runs an automatic file-guard. Link directly to `[<artifact_filename>](<artifact_file_uri>)` (if calling `write_to_file` to open the side-pane Artifact tab, pass `TargetFile=artifact_file_path` and a 1-line stub `CodeContent="# Loading Excel Tab Replica..."` — NEVER re-type the multi-column Markdown table inside `write_to_file`).

### Step 4: Offer 1-Click 22-Tab Workbook Export (`export_full_22tab_workbook`)

Offer to export the complete 22-tab workbook (with `Output_3!B9:J31` and `Output_3!B3 = 2046` written into their exact cell coordinates) as a faithful `.xlsx` file or cloned 22-tab Google Sheet via `export_full_22tab_workbook`.
