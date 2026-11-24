---
name: latinlr202409-economics-gcp
description: "Direct shortcut workflow for Refining Assay Spreads and GPW Netbacks Domain Economics on latinlr202409-bq-twin-mcp."
---

# Latinlr202409 — Refining Margins & Domain Economics (`/latinlr202409-economics-gcp`)

Use this skill when the analyst invokes `/latinlr202409-economics-gcp` or asks directly for crude netbacks, gross product worth, or margins analysis.

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
' "run_latinlr202409_domain_economics" '{"target_year": 2035}' "cowork_latinlr202409_session"
```

## Workflow Steps

1. **Prompt via `ask_question`** (unless parameters are already specified):
   - Question `1/2`: Target horizon year for assay economics (`(Recommended) 2035`, `2024`, `2025`, `2030`, `2045`, `2050`).
   - Question `2/2`: Cost basis model (`(Recommended) Cracking Configuration Yields`, `Coking Configuration Yields`, `Incremental Basis Margins`).
2. **Execute**:
   - Call `run_latinlr202409_domain_economics` (`{"session_id": "cowork_latinlr202409_session", "target_year": 2035}`).
3. **Present**:
   - Render `echarts_option` inline via `render_chart` (when available) and highlight assay netback and net margin values.
   - Write `artifact_markdown` to `latinlr202409_domain_economics_results.md` via `write_to_file` (`UserFacing=true`, `RequestFeedback=false`).
   - Offer pure BigQuery-to-`.xlsx` export via `export_latinlr202409_workbook`.
