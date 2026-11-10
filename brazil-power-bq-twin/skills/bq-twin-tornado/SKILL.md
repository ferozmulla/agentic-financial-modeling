---
name: bq-twin-tornado
description: Shortcut workflow for the 21-point IRR Tornado Sensitivity analysis on the isolated BigQuery Digital Twin (brazil-power-bq-twin-mcp). Prompts for target technology (_01_CF.._12_CF) and optional overrides, runs run_tornado_sensitivity against comm-model-mod.brazil_power_digital_twin, renders the Tornado EChart, saves the side-pane Artifact, and offers DB-synthesized 22-tab export.
---

# BigQuery Digital Twin — 21-Point Tornado IRR Sensitivity (`/bq-twin-tornado`)

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
1. If target technology (`_01_CF.._12_CF` or `ALL`) or overrides are unspecified, prompt the user via `ask_question` (or your active user-question tool / numbered chat options).
2. If overrides were provided, call `update_session_assumptions` (`{"overrides": {...}}`).
3. Call `run_tornado_sensitivity` (`{"technology_code": "<tech_or_ALL>"}`).
4. Render the inline Markdown table, display the Tornado chart via `render_chart` (or write a self-contained interactive Apache ECharts `.html` file if `render_chart` is unavailable), and save `bq_twin_tornado_<tech>.md` via `write_to_file` (or your file-creation tool) preserving physical `\n` newlines on every row.
5. Offer 22-tab database-synthesized export via `export_full_22tab_workbook` (`{"export_format": "xlsx", "output_filename": "Brazil_v13_BQ_Twin_Export.xlsx"}`), downloading `/v1/exports/<output_filename>` to `~/Desktop/` when requested.
