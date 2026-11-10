---
name: brazil-bqml-gcp
description: "Shortcut workflow for the BigQuery ML ARIMA_PLUS 23-year trajectory refresh on the isolated BigQuery Digital Twin (brazil_power_digital_twin.vw_lt_forecasts via brazil-power-bq-twin-mcp). Presents a 2-question card (1/2 Target Curves, 2/2 Session Application & Downstream Chain), executes run_bqml_timeseries_refresh, renders ECharts, and writes bq_twin_lt_trajectories.md."
---

# Brazil Power v13 (GCP) — `ARIMA_PLUS` 23-Year Trajectory Refresh (`/brazil-bqml-gcp`)

> [!IMPORTANT]
> **FAST-START RULE (ZERO PRE-CARD TOOL CALLS)**: When invoked without explicit curve selections in the prompt, your **very first tool call MUST be `ask_question`** using the 2-question JSON card below.

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
         "question": "Which 23-year BigQuery ML ARIMA_PLUS trajectory curves (2024–2046) should we refresh from vw_lt_forecasts?",
         "is_multi_select": true,
         "options": [
           "(Recommended) All 3 Long-Term Curves: CAPEX (LT Capex), FUEL (LT Fuel), and CF (LT CF)",
           "CAPEX Only — Capital Cost Learning Curves (LT Capex!B8:J30)",
           "FUEL Only — Thermal & Biomass Fuel Trajectories (LT Fuel!B8:J30)",
           "CF Only — Renewable & Thermal Capacity Factor Curves (LT CF!B8:J30)"
         ]
       },
       {
         "question": "Would you also like to stage any General!B5:N40 variable overrides or chain directly into the 23-Year LCOE Forecast?",
         "is_multi_select": false,
         "options": [
           "(Recommended) Apply refreshed BQML curves to session LT tabs with current General!B5:N40 assumptions",
           "Apply refreshed BQML curves AND chain immediately into 23-Year LCOE Horizon Forecast (Output_3!B8:J31)",
           "Preview BQML forecast curves only without modifying session LT tabs (apply_to_session_lt_tabs=false)"
         ]
       }
     ]
   }
   ```
2. **Step 2**: Stage any custom `General!B5:N40` overrides if typed via `update_session_assumptions`, then call `run_bqml_timeseries_refresh` (`{"curve_types": [...], "apply_to_session_lt_tabs": ...}`).
3. **Step 3**: Render the inline trajectory table, pass `ECharts Option JSON` to `render_chart`, and save `bq_twin_lt_trajectories.md` via `write_to_file` (`Overwrite=true`, `UserFacing=true`).
4. **Step 4**: Run `run_lcoe_horizon_forecast` if requested, and offer 22-tab synthesis via `export_full_22tab_workbook`.
