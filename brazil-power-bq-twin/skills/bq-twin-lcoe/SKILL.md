---
name: bq-twin-lcoe
description: Shortcut workflow for the 23-year (2024–2046) multi-technology LCOE horizon forecast on the isolated BigQuery Digital Twin (brazil-power-bq-twin-mcp). Prompts for scenario or BQML refresh choices, executes run_lcoe_horizon_forecast, renders the multi-series LCOE EChart, writes bq_twin_output3_lcoe_horizon.md, and offers 22-tab DB synthesis.
---

# BigQuery Digital Twin — 23-Year Multi-Technology LCOE Horizon (`/bq-twin-lcoe`)

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
1. If scenario assumptions or BQML refresh preferences are unspecified, prompt via `ask_question` (or your active user-question tool / numbered chat options).
2. Apply any requested overrides (`update_session_assumptions`) or BQML refresh (`run_bqml_timeseries_refresh`).
3. Call `run_lcoe_horizon_forecast` (`{}`).
4. Render the milestone `Output_3!B8:J31` table inline, display the LCOE horizon chart via `render_chart` (or write a self-contained interactive Apache ECharts `.html` file if `render_chart` is unavailable), and save the full 23-row replica to `bq_twin_output3_lcoe_horizon.md` via `write_to_file` (or your file-creation tool).
5. Offer 22-tab database-synthesized export via `export_full_22tab_workbook` (`{"export_format": "xlsx", "output_filename": "Brazil_v13_BQ_Twin_Export.xlsx"}`), downloading `/v1/exports/<output_filename>` to `~/Desktop/` when requested.
