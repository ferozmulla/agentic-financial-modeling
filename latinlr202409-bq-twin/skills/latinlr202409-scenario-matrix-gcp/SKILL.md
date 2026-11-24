---
name: latinlr202409-scenario-matrix-gcp
description: "Direct shortcut workflow for Multi-Scenario Sensitivity Matrix on latinlr202409-bq-twin-mcp."
---

# Latinlr202409 — Scenario Sensitivity Matrix (`/latinlr202409-scenario-matrix-gcp`)

Use this skill when the analyst invokes `/latinlr202409-scenario-matrix-gcp` or asks directly for scenario comparison or multi-scenario sensitivities.

## Dual-Mode Backend Invocation (`latinlr202409-bq-twin-mcp` or Direct Cloud Run HTTPS)

If `latinlr202409-bq-twin-mcp` tools are in your active MCP tool list, call them directly with `session_id="cowork_latinlr202409_session"`. Otherwise invoke over HTTPS:
```bash
python3 -c '
import json, os, sys, urllib.request
url = os.getenv("LATINLR202409_MCP_URL", "https://latinlr202409-bq-twin-mcp-2wcxwkmdga-uc.a.run.app")
body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": sys.argv[1], "arguments": json.loads(sys.argv[2])}}).encode()
req = urllib.request.Request(f"{url.rstrip(\"/\")}/mcp", data=body, headers={"Content-Type": "application/json", "Mcp-Session-Id": sys.argv[3]}, method="POST")
resp = json.loads(urllib.request.urlopen(req, timeout=120).read().decode())
print(resp["result"]["content"][0]["text"])
' "run_latinlr202409_scenario_matrix" '{"target_year": 2035}' "cowork_latinlr202409_session"
```

## Workflow Steps

1. **Prompt via `ask_question`** (unless parameters are already specified):
   - Question `1/2`: Target horizon year for the scenario matrix (`(Recommended) 2035`, `2025`, `2030`, `2040`, `2050`).
   - Question `2/2`: Levers or driver shocks to sweep (`(Recommended) Default Price Ranges (Low/Base/High)`, `Widen Heavy Spatials Ranges`, `Squeeze Argentine Yields`).
2. **Execute**:
   - If overrides or a reset were selected, call `update_latinlr202409_session_overrides` first.
   - Call `run_latinlr202409_scenario_matrix` (`{"session_id": "cowork_latinlr202409_session", "target_year": 2035}`).
3. **Present**:
   - Render `echarts_option` inline via `render_chart` (when available) and highlight key numeric deltas vs. baseline.
   - Write `artifact_markdown` to `latinlr202409_scenario_matrix_results.md` via `write_to_file` (`UserFacing=true`, `RequestFeedback=false`).
   - Offer pure BigQuery-to-`.xlsx` export via `export_latinlr202409_workbook`.
