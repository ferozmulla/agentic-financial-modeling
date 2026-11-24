---
name: latinlr202409-bqml-gcp
description: "Direct shortcut workflow for BigQuery ML ARIMA_PLUS Forecast Refresh on latinlr202409-bq-twin-mcp."
---

# Latinlr202409 — BigQuery ML Forecast Refresh (`/latinlr202409-bqml-gcp`)

Use this skill when the analyst invokes `/latinlr202409-bqml-gcp` or asks directly to refresh statistical forecasts or query the ARIMA_PLUS model.

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
' "run_latinlr202409_bqml_forecast_refresh" '{"apply_to_session": true}' "cowork_latinlr202409_session"
```

## Workflow Steps

1. **Prompt via `ask_question`** (unless parameters are already specified):
   - Question `1/2`: Apply forecasts as the active session price curve? (`(Recommended) Yes, apply and update session`, `No, view forecast only`).
   - Question `2/2`: Confidence interval for upper/lower bounds (`(Recommended) 90% Confidence`, `95% Confidence`, `80% Confidence`).
2. **Execute**:
   - Call `run_latinlr202409_bqml_forecast_refresh` (`{"session_id": "cowork_latinlr202409_session", "apply_to_session": true}`).
3. **Present**:
   - Render `echarts_option` inline via `render_chart` (when available) and highlight key statistical forecast paths.
   - Write `artifact_markdown` to `latinlr202409_bqml_results.md` via `write_to_file` (`UserFacing=true`, `RequestFeedback=false`).
   - Offer pure BigQuery-to-`.xlsx` export via `export_latinlr202409_workbook`.
