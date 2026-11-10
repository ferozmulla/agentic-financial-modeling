---
name: bq-twin-power-model
description: End-to-end guided workflow for the 100% Excel-free BigQuery Digital Twin of the Brazil Power Generation Model v13 (comm-model-mod.brazil_power_digital_twin via brazil-power-bq-twin-mcp). Publishes bq_twin_general_assumptions.md in the side-pane Artifact viewer, prompts for scenario overrides and target analyses, executes Tornado IRR, BQML ARIMA_PLUS, 23-Year LCOE, or 30-Year DCF against BigQuery, renders interactive ECharts, and synthesizes 22-tab .xlsx or Google Sheets deliverables purely from BigQuery rows.
---

# Brazil Power v13 — BigQuery Digital Twin Orchestrator (`/bq-twin-power-model`)

## Dual-Mode Backend Invocation (`brazil-power-bq-twin-mcp` or Direct Cloud Run HTTPS)

1. **Mode A — Native MCP Toolset**: If `brazil-power-bq-twin-mcp` tools are directly available in your active MCP tool list, call them natively.
2. **Mode B — Direct Cloud Run HTTPS Fallback (GMac Gemini Enterprise Desktop App / Zero `Apps` Connector Needed)**:
   If `brazil-power-bq-twin-mcp` is NOT in your active MCP tool list, invoke any of the 7 tools over HTTPS against the live Cloud Run endpoint using Python 3 stdlib in your bash/command tool (pick a stable `session_id` for the conversation, e.g. `gmac_twin_session`):
   ```bash
   python3 -c '
   import json, sys, urllib.request
   body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": sys.argv[1], "arguments": json.loads(sys.argv[2])}}).encode()
   req = urllib.request.Request("https://brazil-power-bq-twin-mcp-1024543888590.us-central1.run.app/mcp?session_id=" + sys.argv[3], data=body, headers={"Content-Type": "application/json"}, method="POST")
   resp = json.loads(urllib.request.urlopen(req, timeout=60).read().decode())
   print(resp["result"]["content"][0]["text"])
   ' "<tool_name>" '<json_args>' "gmac_twin_session"
   ```

### Available 7 Tools & Exact JSON Arguments
- `get_session_assumptions`: `{}` or `{"technologies": ["_01_CF", "_06_CF"]}`
- `update_session_assumptions`: `{"overrides": {"_06_CF": {"fuel_cost": 5.25}, "General!D10": 0.025}, "reset_to_baseline": false}`
- `run_tornado_sensitivity`: `{"technology_code": "_06_CF"}` (`"_01_CF"`..`"_12_CF"` or `"ALL"`)
- `run_bqml_timeseries_refresh`: `{"curve_types": ["CAPEX", "FUEL", "CF"], "apply_to_session_lt_tabs": true}`
- `run_lcoe_horizon_forecast`: `{}`
- `run_dcf_cashflow_analysis`: `{"technology_code": "_06_CF", "start_year": 2024, "end_year": 2053, "include_cvu_gf_sweep": true}`
- `export_full_22tab_workbook`: `{"export_format": "xlsx", "output_filename": "Brazil_v13_BQ_Twin_Export.xlsx"}` (`"xlsx"`, `"google_sheets"`, or `"both"`)
  - When exporting `.xlsx`, download the synthesized 22-tab workbook directly from `https://brazil-power-bq-twin-mcp-1024543888590.us-central1.run.app/v1/exports/<output_filename>` to `~/Desktop/<output_filename>` (and/or the current workspace folder) via `curl -sSL`.

---

## Cross-Client UI & Artifact Rules

> [!CAUTION]
> **TURN 1 SEQUENCE — PUBLISH ASSUMPTIONS ARTIFACT FIRST, THEN ASK SCENARIO QUESTIONS**:
> 1. **Step 1 (Publish Baseline Assumptions Artifact)**: Call `get_session_assumptions` (`{}`) and save the returned `Full Multi-Line Artifact Markdown Replica` to `bq_twin_general_assumptions.md` using `write_to_file` (or your active file-writing / artifact creation tool) preserving physical `\n` newlines on every table row.
> 2. **Step 2 (Interactive Scenario Prompt)**: Present an interactive question card via `ask_question` (or your active user-question tool; if unavailable, present concise numbered options in chat and pause for the user's reply) asking:
>    - Which technology (`_01_CF` Onshore Wind, `_02_CF` Sugarcane Biomass, `_05_CF` Utility Solar PV, `_06_CF` Natural Gas CCGT, `_07_CF` Coal PC, `_09_CF` Small Hydro, `_11_CF` BESS, `_12_CF` Green H2, or `ALL`) and any assumption overrides to stage.
>    - Which quantitative workflows to run (`21-Point Tornado IRR`, `BigQuery ML ARIMA_PLUS Refresh`, `23-Year LCOE Horizon`, `30-Year DCF & CVU/GF Sweep`).

## Execution Steps After User Selection
1. Stage any requested assumption overrides via `update_session_assumptions` (persists sparse deltas to `comm-model-mod.brazil_power_digital_twin.dt_scenario_deltas` and 4-Ws audit rows to `dt_audit_events`).
2. Run the selected quantitative tools (`run_tornado_sensitivity`, `run_bqml_timeseries_refresh`, `run_lcoe_horizon_forecast`, `run_dcf_cashflow_analysis`).
3. Display the `Inline Markdown Table` in chat, save the `Full Multi-Line Artifact Markdown Replica` as a `.md` file via `write_to_file` (or your file-creation tool), and render the `ECharts Option JSON` chart via `render_chart` (or if `render_chart` is not in your toolset, write a self-contained interactive Apache ECharts `.html` file loading `https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js` so it renders interactively in the artifact pane).
4. Offer 22-tab deliverable synthesis via `export_full_22tab_workbook` (`xlsx`, `google_sheets`, or `both` — synthesized 100% from BigQuery Digital Twin tables with zero template Excel files) and save `.xlsx` exports to `~/Desktop/` if running locally.
