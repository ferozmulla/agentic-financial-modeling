---
name: brazil-bqml-gcp
description: Shortcut workflow for the BigQuery ML ARIMA_PLUS 23-year trajectory refresh on the isolated BigQuery Digital Twin (brazil_power_digital_twin.vw_lt_forecasts via brazil-power-bq-twin-mcp). Collects curve selection, executes run_bqml_timeseries_refresh, renders ECharts, writes bq_twin_lt_trajectories.md, and chains into LCOE or 22-tab synthesis.
---

# Brazil Power v13 (GCP) — `ARIMA_PLUS` 23-Year Trajectory Refresh (`/brazil-bqml-gcp`)

## Backend Invocation (`brazil-power-bq-twin-mcp` or Direct Cloud Run HTTPS)
If `brazil-power-bq-twin-mcp` MCP tools are in your active tool list, call them directly. Otherwise, invoke tools over HTTPS on the live Cloud Run service (`session_id="gmac_twin_session"`):
```bash
python3 -c '
import json, sys, urllib.request
body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": sys.argv[1], "arguments": json.loads(sys.argv[2])}}).encode()
req = urllib.request.Request("https://brazil-power-bq-twin-mcp-1024543888590.us-central1.run.app/mcp?session_id=" + sys.argv[3], data=body, headers={"Content-Type": "application/json"}, method="POST")
resp = json.loads(urllib.request.urlopen(req, timeout=60).read().decode())
print(resp["result"]["content"][0]["text"])
' "<tool_name>" '<json_args>' "gmac_twin_session"
```

## Workflow Steps
1. If curve selection (`CAPEX`, `FUEL`, `CF`) is unspecified, prompt via `ask_question` (or your active user-question tool / numbered chat options).
2. Call `run_bqml_timeseries_refresh` (`{"curve_types": ["CAPEX", "FUEL", "CF"], "apply_to_session_lt_tabs": true}`) to query `comm-model-mod.brazil_power_digital_twin.vw_lt_forecasts` and append trajectory deltas to `dt_scenario_deltas`.
3. Render the inline trajectory summary, display the trajectory chart via `render_chart` (or write a self-contained interactive Apache ECharts `.html` file if `render_chart` is unavailable), and save `bq_twin_lt_trajectories.md` via `write_to_file` (or your file-creation tool).
4. Offer chaining into `run_lcoe_horizon_forecast` (`{}`) or `export_full_22tab_workbook` (`{"export_format": "xlsx", "output_filename": "Brazil_v13_BQ_Twin_Export.xlsx"}`), downloading `/v1/exports/<output_filename>` to `~/Desktop/` when requested.
