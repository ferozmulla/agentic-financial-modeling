---
name: latinlr202409-model-gcp
description: "End-to-end guided workflow for the 100% Excel-free BigQuery Digital Twin of Latinlr202409 Crude Model (latinlr202409_digital_twin via latinlr202409-bq-twin-mcp). Publishes latinlr202409_baseline_assumptions.md in the side-pane Artifact viewer first, presents Card 1 (Scope & Driver/Pinned Overrides), stages overrides to BigQuery dt_scenario_deltas + 4-Ws dt_audit_events, presents Card 2 (Quantitative Analysis Selection), renders ECharts + Artifacts, and synthesizes multi-tab .xlsx workbooks purely from BigQuery rows."
---

# Latinlr202409 — GCP BigQuery Digital Twin Orchestrator (`/latinlr202409-model-gcp`)

Use this skill whenever the analyst invokes `/latinlr202409-model-gcp` or asks to start, configure, or run an interactive modeling session backed by `latinlr202409_digital_twin`.

> [!CAUTION]
> **HARD GATE FOR TURN 1 — `write_to_file` MUST COMPLETE BEFORE `ask_question` (ZERO PRE-CARD TOOL CALLS)**:
> 1. **YOUR FIRST TOOL CALL MUST BE ONLY `write_to_file` (STEP 1)**: Do **NOT** call `get_latinlr202409_session_assumptions`, `run_command`, `find_by_name`, or `ask_question` in Step 1. Calling `write_to_file` alone with the verified baseline tables below opens `latinlr202409_baseline_assumptions.md` in the right-hand Artifact pane immediately.
> 2. **IMMEDIATELY PRESENT CARD 1 (`ask_question` WITH QUESTIONS `1/2` AND `2/2`) IN STEP 2**: As soon as `write_to_file` returns, call `ask_question` with **Question `1/2` = Domain Hub / Asset / Assay Focus** and **Question `2/2` = Driver Shocks, Regime Switches, or `#FDE68A` Pinned Overrides**. Do **NOT** ask which quantitative solver to run on Card 1 — that belongs on **Card 2 (Step 4)** after overrides are staged!

---

## Dual-Mode Backend Invocation (`latinlr202409-bq-twin-mcp` or Direct Cloud Run HTTPS)

1. **Mode A — Native MCP Toolset**: If `latinlr202409-bq-twin-mcp` tools (`get_latinlr202409_session_assumptions`, `update_latinlr202409_session_overrides`, `run_latinlr202409_equilibrium_solve`, `run_latinlr202409_scenario_matrix`, `run_latinlr202409_bqml_forecast_refresh`, `run_latinlr202409_domain_economics`, `export_latinlr202409_workbook`) are in your active MCP tool list, call them directly with a consistent `session_id` (e.g. `"cowork_latinlr202409_session"`).
2. **Mode B — Direct Cloud Run HTTPS Fallback**:
   ```bash
   python3 -c '
   import json, os, sys, urllib.request
   url = os.getenv("LATINLR202409_MCP_URL", "https://latinlr202409-bq-twin-mcp-2wcxwkmdga-uc.a.run.app")
   body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": sys.argv[1], "arguments": json.loads(sys.argv[2])}}).encode()
   req = urllib.request.Request(f"{url.rstrip(\"/\")}/mcp", data=body, headers={"Content-Type": "application/json", "Mcp-Session-Id": sys.argv[3]}, method="POST")
   resp = json.loads(urllib.request.urlopen(req, timeout=120).read().decode())
   print(resp["result"]["content"][0]["text"])
   ' "<tool_name>" '<json_args>' "cowork_latinlr202409_session"
   ```

---

## 6-Step Sequential Guided Workflow

### Step 1 (Mandatory Standalone First Tool Call): Publish `latinlr202409_baseline_assumptions.md` via `write_to_file`

Unless the analyst already specified exact overrides and a target analysis in their prompt, your **sole tool call in Step 1** MUST be `write_to_file`:
- `TargetFile`: `"<artifact_dir>/latinlr202409_baseline_assumptions.md"` *(keep the literal `<artifact_dir>/` prefix for Cowork's side-pane Artifact viewer — NEVER use a `/workspace/` sandbox path here!)*
- `Overwrite`: `true`
- `ArtifactMetadata`: `{"UserFacing": true, "RequestFeedback": false, "Summary": "Latinlr202409 Digital Twin Baseline (2024–2050)"}`
- `CodeContent`:

```markdown
# Latinlr202409 Crude Model — Digital Twin Snapshot (`latinlr202409_digital_twin`)

- **Active Session Overrides**: `0` cells (`0` pinned price/driver cells)

## 1. Key Benchmark Crude Input Prices (USD/bbl)
| Metric | Sheet!Row | Units | 2024 | 2025 | 2030 | 2035 | 2040 | 2045 | 2050 |
| :--- | :--- | :---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **Maya** | `Dashboard_Annual!B52` | USD/bbl | 67.98 | 61.81 | 66.58 | 65.48 | 64.50 | 62.50 | 59.92 |
| **Isthmus** | `Dashboard_Annual!B53` | USD/bbl | 75.65 | 67.03 | 73.26 | 72.10 | 71.13 | 69.21 | 66.84 |
| **Olmeca** | `Dashboard_Annual!B54` | USD/bbl | 79.72 | 71.35 | 76.95 | 75.92 | 75.21 | 73.69 | 71.95 |
| **Escalante** | `Dashboard_Annual!B55` | USD/bbl | 77.59 | 69.58 | 75.07 | 74.65 | 74.11 | 72.68 | 70.01 |
| **Medanito** | `Dashboard_Annual!B56` | USD/bbl | 77.91 | 67.94 | 76.14 | 75.77 | 75.73 | 74.45 | 72.43 |
| **Lula** | `Dashboard_Annual!B57` | USD/bbl | 82.28 | 71.92 | 76.84 | 75.30 | 74.38 | 71.83 | 69.04 |
| **Dated Brent** | `Dashboard_Annual!B65` | USD/bbl | 81.73 | 72.81 | 76.26 | 75.36 | 74.46 | 72.38 | 70.00 |

## 2. Regional Heavy/Medium Crude Discount Spread Spatials (USD/bbl)
| Metric | Sheet!Row | Units | 2024 | 2025 | 2030 | 2035 | 2040 | 2045 | 2050 |
| :--- | :--- | :---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **Marlim** | `Dashboard_Annual!B58` | USD/bbl | 70.19 | 63.79 | 67.93 | 66.74 | 65.70 | 63.69 | 61.20 |
| **Castilla Blend** | `Dashboard_Annual!B59` | USD/bbl | 72.14 | 64.82 | 67.74 | 67.27 | 66.37 | 64.85 | 62.73 |
| **Vasconia** | `Dashboard_Annual!B60` | USD/bbl | 73.93 | 67.30 | 71.80 | 70.73 | 69.80 | 67.80 | 65.50 |
| **Napo** | `Dashboard_Annual!B61` | USD/bbl | 65.90 | 60.86 | 65.00 | 63.81 | 62.76 | 60.73 | 58.16 |
| **Oriente** | `Dashboard_Annual!B62` | USD/bbl | 69.70 | 64.18 | 68.31 | 67.01 | 65.97 | 63.93 | 61.36 |
| **Merey** | `Dashboard_Annual!B63` | USD/bbl | 69.37 | 64.23 | 67.97 | 66.70 | 65.71 | 63.72 | 61.16 |
| **Liza** | `Dashboard_Annual!B64` | USD/bbl | 81.99 | 72.00 | 78.03 | 77.24 | 76.15 | 73.91 | 71.49 |
```

---

### Step 2 (Immediately After `write_to_file` Returns): Present Card 1 (`ask_question` — Questions `1/2` & `2/2`)

```json
{
  "questions": [
    {
      "question": "Which regional crude assay, asset node, or heavy oil discount segment would you like to focus on?",
      "is_multi_select": true,
      "options": [
        "(Recommended) Heavy Crudes (Maya, Castilla Blend, Merey)",
        "Medium/Light Crudes (Lula, Vasconia, Liza)",
        "Argentine Crudes (Escalante, Medanito)",
        "Ecuadorian Crudes (Oriente, Napo)"
      ]
    },
    {
      "question": "Which driver shocks, price regime switches, or #FDE68A Pinned Overrides would you like to stage in BigQuery?",
      "is_multi_select": true,
      "options": [
        "(Recommended) Keep current baseline crude price curve assumptions",
        "Dated Brent Supply Pinch (+15% flat Dated Brent price adjustment)",
        "Heavy Discount Blowout (Maya & Castilla Blend spreads widen by $5/bbl)",
        "Reset all active session overrides in BigQuery back to clean baseline"
      ]
    }
  ]
}
```

---

### Step 3: Stage Overrides in BigQuery & Refresh `latinlr202409_baseline_assumptions.md`

- If the analyst selected any override, shock, pin, or reset on Card 1, call `update_latinlr202409_session_overrides` with `session_id="cowork_latinlr202409_session"` and write the returned `artifact_markdown` back to `latinlr202409_baseline_assumptions.md` via `write_to_file`.

---

### Step 4: Present Card 2 (`ask_question` — Quantitative Analysis Selection)

```json
{
  "questions": [
    {
      "question": "Which quantitative analysis would you like to execute against `latinlr202409_digital_twin`?",
      "is_multi_select": true,
      "options": [
        "(Recommended) Multi-Pass Equilibrium & Margin Solve (`run_latinlr202409_equilibrium_solve`)",
        "Multi-Scenario Sensitivity Matrix (`run_latinlr202409_scenario_matrix`)",
        "BigQuery ML `ARIMA_PLUS` 2025–2050 Trajectory Refresh (`run_latinlr202409_bqml_forecast_refresh`)",
        "Refining Assay GPW & Netback Economics (`run_latinlr202409_domain_economics`)"
      ]
    }
  ]
}
```

---

### Step 5: Execute Analysis, Render Inline ECharts & Publish Side-Pane Markdown Artifact

1. Call the selected MCP tool(s) from Step 4.
2. Render the returned `echarts_option` inline via `render_chart` (when available) and summarize headline deltas vs. baseline in chat.
3. Publish the full `artifact_markdown` to `latinlr202409_analysis_results.md` via `write_to_file` (`UserFacing=true`, `RequestFeedback=false`).

---

### Step 6: Pure BigQuery-to-`.xlsx` Deliverable Synthesis

- Offer to export the full live-formula `.xlsx` deliverable via `export_latinlr202409_workbook` (synthesized 100% from BigQuery baseline + session deltas, with `#FDE68A` amber highlights on overridden cells).
