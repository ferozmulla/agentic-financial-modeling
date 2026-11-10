---
name: brazil-dcf-gcp
description: Shortcut workflow for the 30-year (2024–2053) Project & Equity DCF cash-flow schedule and 10-point Thermal CVU/GF sweep on the isolated BigQuery Digital Twin (brazil-power-bq-twin-mcp). Presents a 2-question card (1/2 Target Technology, 2/2 Scenario Variable Overrides in General!B5:N40), runs run_dcf_cashflow_analysis, renders the cash-flow EChart, saves the full 30-year schedule, and offers 22-tab DB synthesis.
---

# Brazil Power v13 (GCP) — 30-Year Project & Equity DCF (`/brazil-dcf-gcp`)

> [!IMPORTANT]
> **FAST-START RULE (ZERO PRE-CARD TOOL CALLS)**: When invoked without explicit technology + override choices in the prompt, your **very first tool call MUST be `ask_question`** using the 2-question JSON card below (`1/2` Target Technology, `2/2` Scenario Variable Overrides).

## Backend Invocation (`brazil-power-bq-twin-mcp` or Direct Cloud Run HTTPS)
If `brazil-power-bq-twin-mcp` MCP tools are in your active tool list, call them directly. Otherwise, invoke tools over HTTPS (`session_id="cowork_twin_session"`):
```bash
python3 -c '
import json, sys, urllib.request
body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": sys.argv[1], "arguments": json.loads(sys.argv[2])}}).encode()
req = urllib.request.Request("https://brazil-power-bq-twin-mcp-1024543888590.us-central1.run.app/mcp?session_id=" + sys.argv[3], data=body, headers={"Content-Type": "application/json"}, method="POST")
resp = json.loads(urllib.request.urlopen(req, timeout=60).read().decode())
print(resp["result"]["content"][0]["text"])
' "<tool_name>" '<json_args>' "cowork_twin_session"
```

## Workflow Steps
1. **Step 1 (`ask_question` — Questions `1/2` & `2/2`)**: Unless both technology and override choices were already specified in the user's message, call `ask_question`:
   ```json
   {
     "questions": [
       {
         "question": "Which technology tab (_01_CF .. _12_CF) should we run the 30-Year Project & Equity DCF schedule (2024–2053) on?",
         "is_multi_select": false,
         "options": [
           "(Recommended) _01_CF — Gas CCGT + 10-Point Thermal CVU/GF Sweep (500 MW, Capex=3,814 BRL/kW, Fuel=4.50 USD/MMBtu)",
           "_04_CF — Onshore Wind (30 MW, Capex=4,900 BRL/kW, CF=52.0%, Equity=25% / Debt=75%)",
           "_05_CF — Utility Solar PV (30 MW, Capex=5,000 BRL/kW, CF=34.0%, Equity=20% / Debt=80%)",
           "_06_CF — Small Hydro SHP (30 MW, Capex=6,500 BRL/kW, CF=57.0%, Economic Life=30 yrs)",
           "_07_CF — Local Coal CFBC + 10-Point Thermal CVU/GF Sweep (400 MW, Capex=6,800 BRL/kW)"
         ]
       },
       {
         "question": "Would you like to stage any scenario variable overrides in General!B5:N40 before running the 30-year DCF (or use 'Something else' for custom overrides)?",
         "is_multi_select": false,
         "options": [
           "(Recommended) Run with current session / baseline assumptions in General!B5:N40",
           "Bump Gas CCGT Fuel Cost (General!C20) to 6.50 USD/MMBtu",
           "Higher Leverage & Higher WACC: Debt Share -> 80% / Equity Share -> 20%, Real WACC -> 9.50%",
           "Reset session overrides in BigQuery dt_scenario_deltas to clean v13_baseline before running"
         ]
       }
     ]
   }
   ```
2. **Step 2**: Apply any requested overrides via `update_session_assumptions` (`{"overrides": {...}, "reset_to_baseline": ...}`).
3. **Step 3**: Call `run_dcf_cashflow_analysis` (`{"technology_code": "<tech>", "start_year": 2024, "end_year": 2053, "include_cvu_gf_sweep": true}`).
4. **Step 4**: Output the valuation header and milestone schedule inline, pass `ECharts Option JSON` to `render_chart`, and save the complete 30-year schedule to `bq_twin_dcf_30yr_<tech>.md` via `write_to_file` (`Overwrite=true`, `UserFacing=true`).
5. **Step 5**: Offer 22-tab database-synthesized export via `export_full_22tab_workbook`.
