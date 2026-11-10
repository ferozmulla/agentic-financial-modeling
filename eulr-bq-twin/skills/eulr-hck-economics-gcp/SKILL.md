---
name: eulr-hck-economics-gcp
description: "Direct shortcut workflow for the EULR 200 kb/d Sour Hydrocracker Project IRR & NPV 9-point sensitivity (2015 NWE HCK IRR), Naphtha vs. Diesel mode revamp (HCK naphtha revamp), and ULSD 10ppm vs. 0.1%S Gasoil cost-coverage thresholds (ULSD-GO_spread_econs) on eulr-refining-mcp."
---

# EULR Hydrocracker Project IRR & Distillate Spread Economics (`/eulr-hck-economics-gcp`)

Use this skill when the analyst invokes `/eulr-hck-economics-gcp` or asks to evaluate European hydrocracker conversion investment returns (`2015 NWE HCK IRR`), Naphtha vs. Diesel mode revamp (`HCK naphtha revamp`), or ULSD–Gasoil desulfurization cost-coverage spreads (`ULSD-GO_spread_econs`).

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
1. **Prompt via `ask_question`** (unless WACC is already specified):
   - Question `1/2`: Which real discount rate (`discount_rate_wacc`) to apply for the `200 kb/d` Hydrocracker NPV calculation (`(Recommended) 10.0% Real WACC (0.10)`, `8.0% Real WACC (0.08)`, `12.0% Hurdle Rate (0.12)`).
   - Question `2/2`: Optional refining margin or EU ETS override before evaluating HCK conversion economics (`(Recommended) Evaluate on current session / baseline assumptions`, `Apply +$1.50/bbl FCC Margin Shock`, `Switch EU ETS Carbon Off`).
2. **Execute**:
   - Apply any requested session override via `update_eulr_session_overrides`, then call `run_eulr_hck_and_ulsd_economics` (`{"session_id": "cowork_eulr_session", "discount_rate_wacc": <wacc>}`).
3. **Present**:
   - Render `echarts_option` inline via `render_chart` (if available).
   - Write `artifact_markdown` to `eulr_hck_and_ulsd_economics.md` via `write_to_file` (`UserFacing=true`, `RequestFeedback=false`).
   - Offer 18-tab `.xlsx` synthesis via `export_eulr_workbook`.
