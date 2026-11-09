---
name: brazil-power-model
description: Primary end-to-end guided workflow for the Brazil Power Generation Techno-Economic Model v13 (2023-11-27-Brazil_TT_v13_RJEB.xlsm). Step 1: FIRST calls write_to_file alone to publish brazil_v13_general_assumptions.md (General!B5:N40) in the side-pane Artifact viewer BEFORE asking any questions. Step 2: AFTER write_to_file returns, calls ask_question to collect scenario assumptions, updates General!B5:N40 via brazil-power-mcp, runs Tornado IRR, BQML ARIMA_PLUS, 23-Year LCOE, 30-Year DCF, or Thermal CVU sweeps, renders exact Excel-layout tables + ECharts inline (render_chart) and wide tab replicas in side-pane Artifacts, and exports 100% faithful 22-tab .xlsx or Google Sheets workbooks.
---

# Brazil Energy Model (v13) — Master Interactive Modeling Workflow (`/brazil-power-model`)

Use this skill whenever the analyst invokes `/brazil-power-model` or asks to start, configure, or run an interactive Brazil Power Generation v13 modeling session in the Gemini App (`Chat App`).

> [!CAUTION]
> **HARD GATE FOR TURN 1 — `write_to_file` MUST COMPLETE BEFORE `ask_question`**:
> 1. **YOUR FIRST TOOL CALL MUST BE ONLY `write_to_file` (STEP 1)**: When the session starts, your very first response **MUST contain ONLY ONE tool call**: `write_to_file` (`TargetFile="<artifact_dir>/brazil_v13_general_assumptions.md"`, `Overwrite=true`, `ArtifactMetadata={"UserFacing": true, "RequestFeedback": false, "Summary": "Full 12-Technology Excel Tab Replica: General!B5:N40"}`) using the 34-row `General!B5:N40` Markdown table in **Step 1** below.
> 2. **NEVER CALL `ask_question` IN YOUR FIRST TOOL-CALL RESPONSE**: Do **NOT** call `ask_question` on the first tool-call step, do **NOT** emit `write_to_file` and `ask_question` in the same tool-call batch, and do **NOT** call `ask_question` while `brazil_v13_general_assumptions.md` has not yet been written.
> 3. **AUTOMATIC CONTINUATION TO STEP 2 (`ask_question`)**: Because `RequestFeedback` is `false`, `write_to_file` executes in `<0.1s`, immediately opens `brazil_v13_general_assumptions.md` in the right-hand `Files` / Artifact pane, and returns `"Created file..."` back to you automatically without waiting for user input. **As soon as you receive the `write_to_file` tool response**, immediately execute **Step 2 (`ask_question`)** so Question `1/2` appears alongside the open `brazil_v13_general_assumptions.md` artifact.
> 4. **ZERO PRE-CARD TOOL CALLS TO SHELL/MCP/FILESYSTEM BEFORE STEP 2**: Do **NOT** call `run_command`, `get_session_assumptions`, `find_by_name`, `grep_search`, or `list_dir` before Step 2 — only call `write_to_file` in Step 1.

---

## 6-Step Sequential Interactive Visual Card Workflow

### Step 1 (Mandatory Standalone First Tool Call): Publish `brazil_v13_general_assumptions.md` via `write_to_file`

Unless the analyst already provided explicit parameter overrides in natural language in their first message (in which case go to **Step 3**), your **sole tool call in Step 1** MUST be `write_to_file` (do **not** call `ask_question` yet — wait for `write_to_file` to return first):

- `TargetFile`: `"<artifact_dir>/brazil_v13_general_assumptions.md"`
- `Overwrite`: `true`
- `Description`: `"Publish upfront Brazil Power v13 General!B5:N40 34-row x 12-technology baseline assumptions grid"`
- `ArtifactMetadata`: `{"UserFacing": true, "RequestFeedback": false, "Summary": "Full 12-Technology Excel Tab Replica: General!B5:N40 (Rows 5-40 across _01_CF through _12_CF)"}`
- `CodeContent` (preserve every physical newline `\n` at the end of every table row):

```markdown
# Full 12-Technology Excel Tab Replica: `General!B5:N40`

| Row | Parameter (`General!B`) | Unit | Col C: Gas CCGT (`_01_CF`) | Col D: Biomass CHP (`_02_CF`) | Col E: Biomass Retrofit (`_03_CF`) | Col F: Onshore Wind (`_04_CF`) | Col G: Utility Solar PV (`_05_CF`) | Col H: Small Hydro (SHP) (`_06_CF`) | Col I: Local Coal (CFBC) (`_07_CF`) | Col J: Imported Coal (PC) (`_08_CF`) | Col K: Biomass Woodchip (`_09_CF`) | Col L: LNG CCGT (`_10_CF`) | Col M: DG Solar Residential (`_11_CF`) | Col N: DG Solar Commercial (`_12_CF`) |
| :---: | :--- | :---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `5` | **Fuel** | text | Gas | Biomass | Biomass Retrofit | Wind | Solar | SHP | Local Coal (CFBC) | Imported Coal (PC) | Biomass | LNG-fired | Solar | Solar |
| `6` | **Label** | sheet_id | 01_CF | 02_CF | 03_CF | 04_CF | 05_CF | 06_CF | 07_CF | 08_CF | 09_CF | 10_CF | 11_CF | 12_CF |
| `7` | **Technology** | type | CCGT | Boiler | Boiler | WT Cl. 6 | PV | Hydro | CFBC | PC | Woodchip | CCGT | PV - Residential | PV - Commercial |
| `8` | **Capacity (MW or kW where indicated)** | MW / kW | 500.0 | 55.0 | 55.0 | 30.0 | 30.0 | 30.0 | 400.0 | 400.0 | 50.0 | 500.0 | 5.0 | 50.0 |
| `9` | **Net capacity (MW)** | MW | 485.00 | 53.62 | 53.62 | 29.40 | 29.70 | 29.25 | 390.00 | 390.00 | 48.75 | 485.00 | 5.00 | 50.00 |
| `10` | **General losses (%)** | % | 3.0% | 2.5% | 2.5% | 2.0% | 1.0% | 2.5% | 2.5% | 2.5% | 2.5% | 3.0% | 0.0% | 0.0% |
| `11` | **Base capital cost (BRL/kW)** | BRL/kW | 3,814.35 | 3,100.00 | 2,800.00 | 4,900.00 | 5,000.00 | 6,500.00 | 6,800.00 | 6,400.00 | 4,600.00 | 2,850.00 | 7,500.00 | 6,900.00 |
| `12` | **Lower capital cost (BRL/kW)** | BRL/kW | 2,500.00 | 3,050.00 | 2,750.00 | 4,650.00 | 4,700.00 | 6,100.00 | 6,300.00 | 6,100.00 | 4,000.00 | 2,500.00 | 7,400.00 | 6,800.00 |
| `13` | **Upper capital cost (BRL/kW)** | BRL/kW | 3,050.00 | 3,650.00 | 3,650.00 | 5,500.00 | 5,600.00 | 7,250.00 | 7,350.00 | 7,100.00 | 4,950.00 | 3,050.00 | 8,800.00 | 7,900.00 |
| `14` | **Construction lead time (yrs)** | yrs | 5.0 | 3.0 | 3.0 | 3.0 | 1.0 | 3.0 | 5.0 | 5.0 | 3.0 | 5.0 | 1.0 | 1.0 |
| `15` | **Plant economic life (yrs)** | yrs | 30.0 | 25.0 | 25.0 | 25.0 | 25.0 | 30.0 | 30.0 | 30.0 | 30.0 | 30.0 | 25.0 | 25.0 |
| `16` | **Capacity factor** | ratio / % | 50.0% | 40.0% | 40.0% | 52.0% | 34.0% | 57.0% | 50.0% | 0.0% | 0.0% | 0.0% | 22.0% | 22.0% |
| `17` | **Heat rate** | Btu/kWh | 6,600 | 2 | 2 | 0 | 0 | 0 | 1 | 0 | 1 | 6,600 | 0 | 0 |
| `18` | **Availability (MWmed)** | MWmed | 460.75 | 51.48 | 51.48 | 28.22 | 37.04 | 28.08 | 343.20 | 351.00 | 46.31 | 460.75 | 4.05 | 40.50 |
| `19` | **Fuel cost unit** | unit | (USD/MMBtu) | (BRL/ton) | (BRL/ton) | - | - | - | (BRL/metric ton) | (BRL/metric ton) | (BRL/ton) | (USD/MMBtu) | - | - |
| `20` | **Fuel cost** | USD/MMBtu or BRL/MMBtu | 4.50 | 35.00 | 35.00 | - | - | - | 65.00 | 326.17 | 80.00 | 7.00 | - | - |
| `23` | **Fixed O&M costs (BRL/kW-yr)** | BRL/kW-yr | 69.00 | 29.00 | 29.00 | 76.00 | 30.00 | 48.50 | 80.00 | 72.00 | 29.00 | 69.00 | 47.67 | 42.90 |
| `24` | **Variable O&M costs (BRL/MWh)** | BRL/MWh | 12.00 | 20.90 | 20.90 | 0.00 | 0.00 | 2.30 | 12.70 | 9.60 | 20.90 | 12.00 | 0.00 | 0.00 |
| `25` | **Operation insurance (% yr)** | %/yr | 0.50% | 0.30% | 0.30% | 0.30% | 0.30% | 0.30% | 0.30% | 0.30% | 0.30% | 0.50% | 0.20% | 0.20% |
| `26` | **Warranty insurance (% yr)** | %/yr | 0.50% | 0.50% | 0.50% | 0.30% | 0.30% | 0.30% | 0.40% | 0.40% | 0.40% | 0.50% | 0.50% | 0.50% |
| `27` | **Transmission cost (BRL/kWh.month)** | BRL/kW.mo | 5.50 | 4.50 | 4.50 | 3.50 | 3.50 | 4.50 | 5.00 | 5.00 | 4.50 | 5.50 | 0.00 | 0.00 |
| `28` | **Administration cost (%)** | % | 2.00% | 1.50% | 1.50% | 0.50% | 0.00% | 0.50% | 1.00% | 1.00% | 2.00% | 2.00% | 0.00% | 0.00% |
| `29` | **Rental** | % | 1.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 0.00% | 1.00% | 0.00% | 0.00% |
| `30` | **Water (USD/MWh)** | USD/MWh | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| `32` | **Equity** | share | 30.0% | 30.0% | 20.0% | 25.0% | 20.0% | 20.0% | 40.0% | 40.0% | 40.0% | 30.0% | 100.0% | 100.0% |
| `33` | **Debt** | share | 70.0% | 70.0% | 80.0% | 75.0% | 80.0% | 80.0% | 60.0% | 60.0% | 60.0% | 70.0% | 0.0% | 0.0% |
| `34` | **Interest Rate** | real WACC % | 8.00% | 8.00% | 8.00% | 8.00% | 8.00% | 8.00% | 8.00% | 8.00% | 8.00% | 8.00% | 8.00% | 8.00% |
| `35` | **Credit Period** | yrs | 14.0 | 16.0 | 16.0 | 16.0 | 20.0 | 16.0 | 14.0 | 14.0 | 20.0 | 14.0 | 14.0 | 14.0 |
| `36` | **IRR** | target % | 10.00% | 10.00% | 10.00% | 10.00% | 10.00% | 10.00% | 10.00% | 10.00% | 10.00% | 10.00% | 10.00% | 10.00% |
| `38` | **Income tax** | % | 34.0% | 34.0% | 34.0% | 34.0% | 34.0% | 34.0% | 34.0% | 34.0% | 34.0% | 34.0% | 0.0% | 0.0% |
| `39` | **Projected inflation** | % | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% | 0.0% |
| `40` | **Exchange rate (BRL/USD)** | BRL/USD | 3.70 | 3.70 | 3.70 | 3.70 | 3.70 | 3.70 | 3.70 | 3.70 | 3.70 | 3.70 | 3.70 | 3.70 |
```

---

### Step 2 (Immediately After `write_to_file` Returns): Present Card 1 (`ask_question` — Questions `1/2` & `2/2`)

As soon as `write_to_file` from **Step 1** returns its confirmation (so `brazil_v13_general_assumptions.md` is now visible in the right-hand `Files` / Artifact pane), immediately call `ask_question` with **both** Card 1 questions in a single call:

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
        "(Recommended) Keep current General!B5:N40 baseline assumptions (Gas Fuel=4.50 BRL/MMBtu, WACC=8.00%, SHP Lead Time=3.0 yrs)",
        "High Gas Fuel & Fast SHP Build: Gas CCGT Fuel (General!C20) 4.50 -> 6.50 BRL/MMBtu (+44.4%), Small Hydro Lead Time (General!H14) 3.0 -> 2.0 yrs (-33.3%)",
        "Tighter Capital Cost & Higher WACC: Real WACC (General!C34:N34) 8.00% -> 9.50% (+150 bps), Solar PV Capex (General!G11) -10%",
        "Reset all staged session overrides back to the clean 2023-11-27-Brazil_TT_v13_RJEB.xlsm seed baseline"
      ]
    }
  ]
}
```

---

### Step 3: Apply Any Assumption Overrides & Refresh `brazil_v13_general_assumptions.md`

1. If the analyst selected `"Keep current General!B5:N40 baseline assumptions"`, make **zero** MCP tool calls in Step 3 (`brazil_v13_general_assumptions.md` is already open in the right-hand pane from Step 1) and proceed immediately to **Step 4** (Card 2).
2. If the analyst selected or typed any parameter changes (or requested a baseline reset):
   - Call `update_session_assumptions` on `brazil-power-mcp` with `overrides` (accepts either semantic dictionaries such as `{"_01_CF": {"fuel_cost_r_per_mmbtu": 6.50}, "_06_CF": {"lead_time_years": 2.0}}` or exact Excel cell coordinates such as `{"General!C20": 6.50, "General!H14": 2.0}`).
   - Refresh `<artifact_dir>/brazil_v13_general_assumptions.md` via `write_to_file` (`Overwrite=true`, `UserFacing=true`, `RequestFeedback=false`) using the returned multi-line `Full Multi-Line Artifact Markdown Replica` from `update_session_assumptions` (preserving a real physical newline `\n` after every single `| ... |` table row — **NEVER** collapse rows onto one line with `| |`).
   - Once `write_to_file` returns, proceed immediately to **Step 4** (Card 2).

---

### Step 4: Card 2 — Interactive Quantitative Analysis Selection Card (`ask_question`)

Immediately present the **Analysis Selection Card** via `ask_question`:

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

---

### Step 5: Dual Inline + Pre-Saved Side-Pane Artifact Rendering & 22-Tab Workbook Export

> [!TIP]
> **FAST EXECUTION & MULTI-LINE TABLE ARTIFACT RULE**:
> - Call the `brazil-power-mcp` MCP tool directly via `call_mcp_tool`.
> - **PRE-RESOLVED FAST CLI COMMAND (if `call_mcp_tool` is unavailable in Step 3 or Step 5)**: Run directly without searching the filesystem:
>   `REPO="${HOME}/Documents/commodity-modeling-sheets-platform"; [ -d "$REPO" ] || REPO="/Users/ferozmulla/Desktop/smart-coder/commodity-modeling-sheets-platform"; PY="$REPO/.venv-linux/bin/python"; [ -x "$PY" ] || PY="$REPO/.venv/bin/python"; PYTHONPATH="$REPO/brazil-power-agent/src:$REPO/brazil-power-v13" "$PY" -m brazil_power_agent.mcp_server --call <tool_name> --args '<json_args>' --compact-llm --artifact-dir "<artifact_dir>"`
> - Every `brazil-power-mcp` tool outputs **real multi-line Markdown tables** (with physical `\n` line breaks after every `| ... |` row) and pre-saves the full Excel replica to `artifact_file_path` (`artifact_file_uri`).
> - When calling `write_to_file` (`TargetFile=artifact_file_path`, `UserFacing=true`) to open the side-pane **Artifact** tab, you **MUST preserve the exact multi-line Markdown formatting with a real newline (`\n`) at the end of every single `| ... |` table row** — **NEVER** collapse multiple rows onto one line separated by `| |`.

For each selected analysis workflow, execute the corresponding `brazil-power-mcp` tool and adhere strictly to the **Dual Inline + Artifact Rendering Standard**:

1. **Tornado IRR Sensitivity** (`run_tornado_sensitivity`):
   - Render `inline_markdown` (`inline_excel_table_md`: `_0N_CF!A4:H12` 21-point IRR sensitivity grid + `Output_1` summary) inline in chat.
   - Call `render_chart` (`mcp_data-agent-kit_render_chart`) with `echarts_option` (`echarts_spec`) to render the horizontal Tornado bar chart inline.
   - Open/link the side-pane **Artifact** at `artifact_file_path` (`artifact_file_uri`), preserving every row newline (`\n`) in the Markdown table.
2. **23-Year Multi-Tech LCOE Forecast** (`run_lcoe_horizon_forecast`):
   - Render `inline_markdown` (`inline_excel_table_md`: compact milestone table `2024, 2025, 2030, 2035, 2040, 2046` across `Output_3!B8:J31`) inline in chat.
   - Call `render_chart` with `echarts_option` (`echarts_spec`) to render the 23-year multi-technology LCOE trajectory line chart inline.
   - Open/link the 23-row × 9-column `Output_3!B8:J31` **Artifact** at `artifact_file_path` (`artifact_file_uri`), preserving every row newline (`\n`).
3. **BigQuery ML `ARIMA_PLUS` Time-Series Refresh** (`run_bqml_timeseries_refresh`):
   - Render `inline_markdown` (`inline_excel_table_md`: milestone normalized index summary across `LT Capex!B8:J30`, `LT Fuel!B8:J30`, `LT CF!B8:J30`) inline in chat.
   - Call `render_chart` with `echarts_option` (`echarts_spec`) to render the 23-year BQML trajectory chart inline.
   - Open/link the 23-row `LT Capex`, `LT Fuel`, and `LT CF` **Artifact** at `artifact_file_path` (`artifact_file_uri`), preserving every row newline (`\n`).
4. **30-Year Project & Shareholder DCF + Thermal CVU Sweep** (`run_dcf_cashflow_analysis`):
   - Render `inline_markdown` (`inline_excel_table_md`: executive valuation header `_0N_CF!B2:H14` + milestone years `2024, 2025, 2026, 2027, 2028, 2030, 2035, 2040, 2045, 2050, 2053` + `CVU_GF` 10-point table when `include_cvu_gf_sweep=True`) inline in chat.
   - Call `render_chart` with `echarts_option` (`echarts_spec`, and `cvu_sweep_echarts_option` if a CVU sweep was run) to render the 30-year Free Cash Flow & Cumulative NPV stacked bar/line visual inline.
   - Open/link the 30-column `Col K..Col AN` × Rows `33–101` horizontal `_0N_CF` DCF **Artifact** at `artifact_file_path` (`artifact_file_uri`), preserving every row newline (`\n`).
5. **1-Click 22-Tab `.xlsx` or Google Sheets Deliverable Export** (`export_full_22tab_workbook`):
   - At the conclusion of the analysis turn (or whenever requested), offer or invoke `export_full_22tab_workbook(export_format="xlsx" | "google_sheets" | "both")`.
   - Confirm that all 22 original worksheets (`Version Control`, `General`, `Output_1`, `Output_2`, `Output_3`, `_01_CF` .. `_12_CF`, `_CAPEX 01`, `CVU_GF`, `LT Capex`, `LT Fuel`, `LT CF`) are preserved with 100% of original Excel formulas, number formats, styles, and all staged overrides/solved outputs written to their exact cell coordinates, and provide the clickable `[filename.xlsx](file:///...)` link or live Google Sheets URL.
