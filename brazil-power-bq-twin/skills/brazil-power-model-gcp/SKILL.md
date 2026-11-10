---
name: brazil-power-model-gcp
description: End-to-end guided workflow for the 100% Excel-free BigQuery Digital Twin of the Brazil Power Generation Model v13 (comm-model-mod.brazil_power_digital_twin via brazil-power-bq-twin-mcp). Step 1: FIRST calls write_to_file alone to publish bq_twin_general_assumptions.md in the side-pane Artifact viewer BEFORE asking questions. Step 2: Presents Card 1 (Question 1/2 Technology Selection & Question 2/2 Scenario Variable Overrides). Step 3: Stages overrides to BigQuery dt_scenario_deltas and refreshes the Artifact. Step 4: Presents Card 2 (Quantitative Analysis Selection), renders ECharts + Artifacts, and synthesizes 22-tab .xlsx or Google Sheets deliverables purely from BigQuery rows.
---

# Brazil Power v13 — GCP BigQuery Digital Twin Orchestrator (`/brazil-power-model-gcp`)

Use this skill whenever the analyst invokes `/brazil-power-model-gcp` or asks to start, configure, or run an interactive Brazil Power Generation v13 modeling session backed by the BigQuery Digital Twin (`comm-model-mod.brazil_power_digital_twin`).

> [!CAUTION]
> **HARD GATE FOR TURN 1 — `write_to_file` MUST COMPLETE BEFORE `ask_question` (ZERO PRE-CARD TOOL CALLS)**:
> 1. **YOUR FIRST TOOL CALL MUST BE ONLY `write_to_file` (STEP 1)**: Do **NOT** call `get_session_assumptions`, `run_command`, `find_by_name`, `grep_search`, or `ask_question` in Step 1. Calling `write_to_file` alone with the 34-row `General!B5:N40` table below completes in `<0.1s` and opens `bq_twin_general_assumptions.md` in the right-hand `Files` / Artifact pane immediately.
> 2. **IMMEDIATELY PRESENT CARD 1 (`ask_question` WITH QUESTIONS `1/2` AND `2/2`) IN STEP 2**: As soon as `write_to_file` returns, call `ask_question` with the exact two-question Card 1 schema (**Question `1/2` = Technology selection**, **Question `2/2` = Scenario variable overrides in `General!B5:N40`**). Do **NOT** ask which quantitative analysis to run on Card 1 — that belongs on **Card 2 (Step 4)** after overrides are staged!

---

## Dual-Mode Backend Invocation (`brazil-power-bq-twin-mcp` or Direct Cloud Run HTTPS)

1. **Mode A — Native MCP Toolset**: If `brazil-power-bq-twin-mcp` tools are in your active MCP tool list, call them directly.
2. **Mode B — Direct Cloud Run HTTPS Fallback (when `brazil-power-bq-twin-mcp` is not in your MCP tool list)**:
   Invoke any of the 7 tools over HTTPS against the live Cloud Run endpoint using Python 3 stdlib (keep a stable `session_id` across the conversation, e.g. `cowork_twin_session`):
   ```bash
   python3 -c '
   import json, sys, urllib.request
   body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": sys.argv[1], "arguments": json.loads(sys.argv[2])}}).encode()
   req = urllib.request.Request("https://brazil-power-bq-twin-mcp-1024543888590.us-central1.run.app/mcp?session_id=" + sys.argv[3], data=body, headers={"Content-Type": "application/json"}, method="POST")
   resp = json.loads(urllib.request.urlopen(req, timeout=60).read().decode())
   print(resp["result"]["content"][0]["text"])
   ' "<tool_name>" '<json_args>' "cowork_twin_session"
   ```

---

## 6-Step Sequential Interactive Visual Card Workflow

### Step 1 (Mandatory Standalone First Tool Call): Publish `bq_twin_general_assumptions.md` via `write_to_file`

Unless the analyst already specified explicit parameter overrides and a target analysis in their prompt, your **sole tool call in Step 1** MUST be `write_to_file` (or your active file-writing tool):
- `TargetFile`: `"<artifact_dir>/bq_twin_general_assumptions.md"` (or `"bq_twin_general_assumptions.md"` in workspace)
- `Overwrite`: `true`
- `Description`: `"Publish upfront BigQuery Digital Twin General!B5:N40 34-row x 12-technology baseline assumptions grid"`
- `ArtifactMetadata`: `{"UserFacing": true, "RequestFeedback": false, "Summary": "BigQuery Digital Twin Replica: General!B5:N40 (_01_CF through _12_CF)"}`
- `CodeContent` (preserve every physical newline `\n` at the end of every table row):

```markdown
# BigQuery Digital Twin Baseline Replica: `General!B5:N40` (`comm-model-mod.brazil_power_digital_twin`)

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

As soon as `write_to_file` from **Step 1** returns, call `ask_question` with **both** Card 1 questions (**`1/2` Technology Selection** and **`2/2` Scenario Variable Overrides**):

```json
{
  "questions": [
    {
      "question": "Which Brazil Power v13 generation technology or portfolio basket in General!B5:N40 would you like to model or adjust?",
      "is_multi_select": true,
      "options": [
        "(Recommended) _01_CF: Gas CCGT (Col C: 500 MW, Capex 3,814 BRL/kW, CF 50%, Gas Fuel 4.50 USD/MMBtu)",
        "_04_CF: Onshore Wind (Col F: 30 MW, Capex 4,900 BRL/kW, CF 52%, Lead Time 3 yrs)",
        "_05_CF: Utility Solar PV (Col G: 30 MW, Capex 5,000 BRL/kW, CF 34%, Lead Time 1 yr)",
        "_06_CF: Small Hydro SHP (Col H: 30 MW, Capex 6,500 BRL/kW, CF 57%, Lead Time 3 yrs)",
        "Core Basket / All 12 Technologies (_01_CF .. _12_CF across General!C5:N40)"
      ]
    },
    {
      "question": "Which scenario variable overrides in General!B5:N40 would you like to stage in BigQuery dt_scenario_deltas (or use 'Something else' to type any custom cell/parameter override)?",
      "is_multi_select": true,
      "options": [
        "(Recommended) Keep current General!B5:N40 baseline assumptions (Gas Fuel=4.50 USD/MMBtu, Real WACC=8.00%, SHP Lead Time=3.0 yrs)",
        "High Gas Fuel & Fast SHP Build: Gas CCGT Fuel (General!C20) 4.50 -> 6.50 USD/MMBtu (+44.4%), Small Hydro Lead Time (General!H14) 3.0 -> 2.0 yrs",
        "Higher Financing Cost & Lower Solar Capex: Real WACC (General!C34:N34) 8.00% -> 9.50% (+150 bps), Utility Solar PV Capex (General!G11) 5,000 -> 4,500 BRL/kW",
        "Reset all staged session overrides in BigQuery dt_scenario_deltas back to clean v13_baseline"
      ]
    }
  ]
}
```

---

### Step 3: Apply Any Assumption Overrides to BigQuery & Refresh `bq_twin_general_assumptions.md`

1. If the analyst selected `"Keep current General!B5:N40 baseline assumptions"`, make **zero** MCP tool calls in Step 3 (`bq_twin_general_assumptions.md` is already open in the right-hand pane from Step 1) and proceed immediately to **Step 4 (Card 2)**.
2. If the analyst selected or typed any variable overrides (or requested a baseline reset):
   - Call `update_session_assumptions` on `brazil-power-bq-twin-mcp` (accepts semantic keys such as `{"overrides": {"_01_CF": {"fuel_cost": 6.50}, "_06_CF": {"lead_time": 2.0}}, "reset_to_baseline": false}` or cell coordinates such as `{"overrides": {"General!C20": 6.50, "General!H14": 2.0}}`; note percentage cells like `wacc` / `General!C34` take decimals like `0.095`).
   - Refresh `bq_twin_general_assumptions.md` via `write_to_file` (`Overwrite=true`, `UserFacing=true`, `RequestFeedback=false`) using the returned multi-line `Full Multi-Line Artifact Markdown Replica` (preserving physical `\n` newlines on every table row).
   - Immediately proceed to **Step 4 (Card 2)**.

---

### Step 4: Present Card 2 — Quantitative Analysis Selection Card (`ask_question`)

Present **Card 2** via `ask_question` so the analyst chooses which quantitative workflows to run on the configured scenario:

```json
{
  "questions": [
    {
      "question": "Which quantitative analysis workflows would you like to execute against the BigQuery Digital Twin?",
      "is_multi_select": true,
      "options": [
        "(Recommended) 21-Point Tornado IRR Sensitivity (run_tornado_sensitivity -> _01_CF.._12_CF!A4:H12 & Output_1)",
        "23-Year Multi-Technology LCOE Horizon Forecast 2024–2046 (run_lcoe_horizon_forecast -> Output_3!B8:J31)",
        "BigQuery ML ARIMA_PLUS 23-Year Trajectory Refresh (run_bqml_timeseries_refresh -> LT Capex, LT Fuel, LT CF)",
        "30-Year Project & Equity DCF Schedule 2024–2053 + Thermal CVU/GF Sweep (run_dcf_cashflow_analysis)"
      ]
    }
  ]
}
```

---

### Step 5: Execute Selected Solvers, Render Charts (`render_chart`), & Save Side-Pane Artifacts

For each selected workflow on `brazil-power-bq-twin-mcp`:
1. **Tool Arguments**:
   - `run_tornado_sensitivity`: `{"technology_code": "<_01_CF.._12_CF or ALL>"}`
   - `run_bqml_timeseries_refresh`: `{"curve_types": ["CAPEX", "FUEL", "CF"], "apply_to_session_lt_tabs": true}`
   - `run_lcoe_horizon_forecast`: `{}`
   - `run_dcf_cashflow_analysis`: `{"technology_code": "<_01_CF.._12_CF>", "start_year": 2024, "end_year": 2053, "include_cvu_gf_sweep": true}`
2. **Inline Summary + Chart + Side-Pane Artifact**:
   - Output the returned `Inline Markdown Table` in chat.
   - Pass the returned `ECharts Option JSON` to `render_chart` (or if `render_chart` is unavailable in your client, write a self-contained interactive Apache ECharts `.html` file loading `https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js`).
   - Save the returned `Full Multi-Line Artifact Markdown Replica` to `<artifact_dir>/<Side-Pane Artifact Filename>` via `write_to_file` (`Overwrite=true`, `UserFacing=true`, `RequestFeedback=false`), preserving physical `\n` newlines on every row.

---

### Step 6: Present Card 3 — 22-Tab Workbook Synthesis (`export_full_22tab_workbook`)

After presenting the analytical outputs, offer 22-tab deliverable synthesis via `ask_question`:
- `export_full_22tab_workbook`: `{"export_format": "xlsx", "output_filename": "Brazil_v13_BQ_Twin_Export.xlsx"}` (`"xlsx"`, `"google_sheets"`, or `"both"` — synthesized 100% from BigQuery Digital Twin rows, styles, merged borders, sheet views, and formulas with zero template Excel files).
- When `.xlsx` is generated, provide the clickable `Cloud .xlsx Download URL` (`https://brazil-power-bq-twin-mcp-1024543888590.us-central1.run.app/v1/exports/<output_filename>`) and, if shell access is available, also download a local copy for convenience.
