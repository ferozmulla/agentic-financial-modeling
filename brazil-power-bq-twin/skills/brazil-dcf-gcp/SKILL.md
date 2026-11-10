---
name: brazil-dcf-gcp
description: Shortcut workflow for the 30-year (2024–2053) Project & Equity DCF cash-flow schedule and 10-point Thermal CVU/GF sweep on the isolated BigQuery Digital Twin (brazil-power-bq-twin-mcp). Collects target technology (_01_CF.._12_CF) and overrides, runs run_dcf_cashflow_analysis, renders the cash-flow EChart, saves the full 30-year schedule, and offers 22-tab DB synthesis.
---

# Brazil Power v13 (GCP) — 30-Year Project & Equity DCF (`/brazil-dcf-gcp`)

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
1. If target technology (`_01_CF.._12_CF`) is unspecified, prompt via `ask_question` (or your active user-question tool / numbered chat options).
2. Apply any requested overrides via `update_session_assumptions` (`{"overrides": {...}}`).
3. Call `run_dcf_cashflow_analysis` (`{"technology_code": "<tech>", "start_year": 2024, "end_year": 2053, "include_cvu_gf_sweep": true}`).
4. Render the valuation header and milestone schedule inline, display the cash-flow chart via `render_chart` (or write a self-contained interactive Apache ECharts `.html` file if `render_chart` is unavailable), and save the complete 30-year schedule to `bq_twin_dcf_30yr_<tech>.md` via `write_to_file` (or your file-creation tool).
5. Offer 22-tab database-synthesized export via `export_full_22tab_workbook` (`{"export_format": "xlsx", "output_filename": "Brazil_v13_BQ_Twin_Export.xlsx"}`), downloading `/v1/exports/<output_filename>` to `~/Desktop/` when requested.
