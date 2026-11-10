---
name: brazil-lcoe-gcp
description: "Shortcut workflow for the 23-year (2024-2046) multi-technology LCOE horizon forecast on the isolated BigQuery Digital Twin (brazil-power-bq-twin-mcp). Presents a 2-question card (1/2 Trajectory Curve Source, 2/2 Scenario Variable Overrides in General!B5:N40), executes run_lcoe_horizon_forecast, renders the LCOE EChart, writes bq_twin_output3_lcoe_horizon.md, and offers 22-tab DB synthesis."
---

# Brazil Power v13 (GCP) — 23-Year Multi-Technology LCOE Horizon (`/brazil-lcoe-gcp`)

> [!IMPORTANT]
> **FAST-START RULE (ZERO PRE-CARD TOOL CALLS)**: When invoked without explicit scenario/curve choices in the prompt, your **very first tool call MUST be `ask_question`** using the 2-question JSON card below.

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
1. **Step 1 (`ask_question` — Questions `1/2` & `2/2`)**: Unless already specified in the user's message, call `ask_question`:
   ```json
   {
     "questions": [
       {
         "question": "Which long-term trajectory curves should drive the 2024–2046 LCOE Horizon Forecast (Output_3!B8:J31)?",
         "is_multi_select": false,
         "options": [
           "(Recommended) Refresh LT Capex, LT Fuel, and LT CF from live BigQuery ML ARIMA_PLUS first, then solve LCOE",
           "Use current session LT Capex, LT Fuel, and LT CF Digital Twin trajectories as-is"
         ]
       },
       {
         "question": "Would you like to stage any scenario variable overrides in General!B5:N40 before solving LCOE (or use 'Something else' for custom overrides)?",
         "is_multi_select": false,
         "options": [
           "(Recommended) Keep current General!B5:N40 baseline / session assumptions",
           "High Gas Fuel & Fast SHP Build: Gas CCGT Fuel (General!C20) -> 6.50 USD/MMBtu, SHP Lead Time (General!H14) -> 2.0 yrs",
           "Higher Real WACC: Increase Real WACC (General!C34:N34) from 8.00% to 9.50%",
           "Reset session overrides in BigQuery dt_scenario_deltas to clean v13_baseline first"
         ]
       }
     ]
   }
   ```
2. **Step 2**: Apply any requested overrides (`update_session_assumptions`) and/or BQML refresh (`run_bqml_timeseries_refresh`).
3. **Step 3**: Call `run_lcoe_horizon_forecast` (`{}`).
4. **Step 4**: Output the milestone `Output_3!B8:J31` table inline, pass `ECharts Option JSON` to `render_chart`, and save the full 23-row replica to `bq_twin_output3_lcoe_horizon.md` via `write_to_file` (`Overwrite=true`, `UserFacing=true`).
5. **Step 5**: Offer 22-tab database-synthesized export via `export_full_22tab_workbook`.
