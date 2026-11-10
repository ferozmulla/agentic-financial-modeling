---
name: eulr-scenario-matrix-gcp
description: "Direct shortcut workflow for the EULR 6-Way European Refining Margin, EU ETS Carbon Pass-Through (Cost+Allocation, Variable Cost Only, Carbon Off), and Live 3-Peer Upstream Sync (Uslr/Felr/Tankerlr) Scenario Matrix on eulr-refining-mcp."
---

# EULR 6-Way EU ETS Carbon, Margin Stress & Peer-Sync Matrix (`/eulr-scenario-matrix-gcp`)

Use this skill when the analyst invokes `/eulr-scenario-matrix-gcp` or asks to compare EU ETS carbon pass-through regimes, refinery margin shocks, and upstream global peer sync across European product prices.

## Backend Invocation (`eulr-refining-mcp` or Direct Cloud Run HTTPS)
If `eulr-refining-mcp` MCP tools are in your active tool list, call them directly (`session_id="cowork_eulr_session"`). Otherwise (e.g. macOS Gemini Desktop App), invoke tools over HTTPS:
```bash
python3 -c '
import json, sys, urllib.request
body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": sys.argv[1], "arguments": json.loads(sys.argv[2])}}).encode()
req = urllib.request.Request("https://eulr-bq-twin-mcp-2wcxwkmdga-uc.a.run.app/mcp", data=body, headers={"Content-Type": "application/json", "Mcp-Session-Id": sys.argv[3]}, method="POST")
resp = json.loads(urllib.request.urlopen(req, timeout=120).read().decode())
print(resp["result"]["content"][0]["text"])
' "<tool_name>" '<json_args>' "cowork_eulr_session"
```

## Workflow Steps
1. **Prompt via `ask_question`** (unless `target_year` is already specified):
   - Question `1/2`: Which horizon milestone year to evaluate (`(Recommended) 2035 — EU CBAM Free-Allowance Phase-Out Active`, `2025 — Near-Term Prompt Year`, `2030 — Mid-Term Transition`, `2040 — Deep Decarbonization`, `2050 — Long-Run Horizon`).
   - Question `2/2`: Optional session driver or pinned price override before running the 6-way sweep (`(Recommended) Run on current session / baseline assumptions`, `Pin 2025 NWE EN590 Diesel (NWE Cif!AU122) = $750.00/mt`, `Reset session to LR202409 baseline first`).
2. **Execute**:
   - Apply any requested session override via `update_eulr_session_overrides`, then call `run_eulr_scenario_matrix` (`{"session_id": "cowork_eulr_session", "target_year": <year>}`).
3. **Present**:
   - Render `echarts_option` inline via `render_chart` (if available).
   - Write `artifact_markdown` to `eulr_scenario_matrix.md` via `write_to_file` (`UserFacing=true`, `RequestFeedback=false`) and highlight the dollar impact of EU ETS erosion and `Uslr`/`Felr`/`Tankerlr` peer sync.
   - Offer 18-tab `.xlsx` synthesis via `export_eulr_workbook`.
