---
name: eulr-equilibrium-gcp
description: "Direct shortcut workflow for the EULR 10-Pass Gauss-Seidel Circular Equilibrium Solver, #FDE68A Pinned Price Overrides, 3-Peer (Uslr/Felr/Tankerlr) Upstream Sync, and 180-rule Checks diagnostics on eulr-refining-mcp (comm-model-mod.eulr_digital_twin)."
---

# EULR 10-Pass Circular Equilibrium & Pinned Price Solver (`/eulr-equilibrium-gcp`)

Use this skill when the analyst invokes `/eulr-equilibrium-gcp` or asks to solve European NWE/MED CIF & FOB refined product prices, pin a product price (e.g. `NWE Cif!AU122`), or sync upstream `Uslr`/`Felr`/`Tankerlr` peer inputs.

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
1. **Prompt via `ask_question`** (unless parameters are already specified):
   - Question `1/2`: Upstream & EU ETS Mode (`(Recommended) Baseline Cached + EU ETS Cost & Allocation`, `Sync Live 3-Peer Models (Uslr + Felr + Tankerlr — 1,104 updated cells)`, `Switch EU ETS Carbon Off`).
   - Question `2/2`: Optional Pinned Price or Margin Shock (`(Recommended) No pinned override`, `Pin 2025 NWE EN590 Diesel (NWE Cif!AU122) = $750.00/mt`, `Apply +$1.50/bbl FCC Margin Shock`).
2. **Execute**:
   - If persistent overrides or pins were chosen, call `update_eulr_session_overrides` (`{"session_id": "cowork_eulr_session", "eu_ets_mode": ..., "driver_overrides": ..., "pinned_price_overrides": ...}`), then call `run_eulr_equilibrium_solve` (`{"session_id": "cowork_eulr_session", "upstream_mode": ...}`).
3. **Present**:
   - Render `echarts_option` inline via `render_chart` (if available) and summarize key NWE/MED CIF & FOB equilibrium spreads.
   - Write `artifact_markdown` to `eulr_equilibrium_results.md` via `write_to_file` (`UserFacing=true`, `RequestFeedback=false`).
   - Offer 18-tab (or 19-tab `+UPLOAD`) `.xlsx` export via `export_eulr_workbook` (`download_url` can be fetched to `~/Desktop/` if requested).
