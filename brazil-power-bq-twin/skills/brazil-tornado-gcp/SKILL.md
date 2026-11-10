---
name: brazil-tornado-gcp
description: Shortcut workflow for the 21-point IRR Tornado Sensitivity analysis on the isolated BigQuery Digital Twin (brazil-power-bq-twin-mcp). Presents a 2-question card (1/2 Target Technology, 2/2 Scenario Variable Overrides in General!B5:N40), runs run_tornado_sensitivity against comm-model-mod.brazil_power_digital_twin, renders the Tornado EChart, saves the side-pane Artifact, and offers DB-synthesized 22-tab export.
---

# Brazil Power v13 (GCP) — 21-Point Tornado IRR Sensitivity (`/brazil-tornado-gcp`)

> [!IMPORTANT]
> **FAST-START RULE (ZERO PRE-CARD TOOL CALLS)**: When invoked without explicit technology + override choices in the prompt, your **very first tool call MUST be `ask_question`** using the 2-question JSON card below (`1/2` Target Technology, `2/2` Scenario Variable Overrides).

## Backend Invocation (`brazil-power-bq-twin-mcp` or Direct Cloud Run HTTPS)
If `brazil-power-bq-twin-mcp` MCP tools are in your active tool list, call them directly. Otherwise, invoke tools over HTTPS (`session_id="cowork_twin_session"`):
```bash
python3 -c '
import json, sys, urllib.request
body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": sys.argv[1], "arguments": json.loads(sys.argv[2])}}).encode()
req = urllib.request.Request("https://brazil-power-bq-twin-mcp-1024543888590.us-central1.run.app/mcp?session_id=" + sys.argv[3], data=body, headers={"Content-Type": "application/json"}, method="POST")
resp = json.loads(urllib.request.urlopen(req, timeout=60).read().decode())
print(resp["result"]["content"][0]["text"])
' "<tool_name>" '<json_args>' "cowork_twin_session"
```

## Workflow Steps
1. **Step 1 (`ask_question` — Questions `1/2` & `2/2`)**: Unless both technology and override choices were already specified in the user's message, call `ask_question`:
   ```json
   {
     "questions": [
       {
         "question": "Which technology tab (_01_CF .. _12_CF or ALL) should we run the 21-point IRR Tornado Sensitivity on?",
         "is_multi_select": false,
         "options": [
           "(Recommended) _01_CF — Gas CCGT (Col C: Capex=3,814 BRL/kW, Fuel=4.50 USD/MMBtu, CF=50.0%, WACC=8.00%)",
           "_06_CF — Small Hydro SHP (Col H: Capex=6,500 BRL/kW, Lead Time=3.0 yrs, CF=57.0%, WACC=8.00%)",
           "_04_CF — Onshore Wind (Col F: Capex=4,900 BRL/kW, Lead Time=3.0 yrs, CF=52.0%, WACC=8.00%)",
           "_05_CF — Utility Solar PV (Col G: Capex=5,000 BRL/kW, Lead Time=1.0 yr, CF=34.0%, WACC=8.00%)",
           "ALL — Execute Tornado sensitivity across all 12 technology tabs (_01_CF.._12_CF)"
         ]
       },
       {
         "question": "Would you like to stage any scenario variable overrides in General!B5:N40 before solving (or use 'Something else' for custom overrides)?",
         "is_multi_select": false,
         "options": [
           "(Recommended) Run with current session / baseline assumptions in General!B5:N40",
           "Bump Gas CCGT Fuel Cost (General!C20) to 6.50 USD/MMBtu and Small Hydro Lead Time (General!H14) to 2.0 yrs",
           "Increase Real WACC (General!C34:N34) by +150 bps to 9.50%",
           "Reset session overrides in BigQuery dt_scenario_deltas to clean v13_baseline before running"
         ]
       }
     ]
   }
   ```
2. **Step 2**: If overrides or a reset were selected, call `update_session_assumptions` (`{"overrides": {...}, "reset_to_baseline": ...}`).
3. **Step 3**: Call `run_tornado_sensitivity` (`{"technology_code": "<tech_or_ALL>"}`).
4. **Step 4**: Output the `Inline Markdown Table`, pass `ECharts Option JSON` to `render_chart` (or write an interactive ECharts `.html` artifact if unavailable), and save `bq_twin_tornado_<tech>.md` via `write_to_file` (`Overwrite=true`, `UserFacing=true`) preserving physical `\n` newlines on every row.
5. **Step 5**: Offer 22-tab database-synthesized export via `export_full_22tab_workbook` (`{"export_format": "xlsx", "output_filename": "Brazil_v13_BQ_Twin_Export.xlsx"}`).
