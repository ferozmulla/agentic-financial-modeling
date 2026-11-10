---
name: bq-twin-power-model
description: End-to-end guided workflow for the 100% Excel-free BigQuery Digital Twin of the Brazil Power Generation Model v13 (comm-model-mod.brazil_power_digital_twin via brazil-power-bq-twin-mcp). Step 1: FIRST calls write_to_file alone to publish bq_twin_general_assumptions.md in the side-pane Artifact viewer BEFORE asking questions. Step 2: Calls ask_question to collect scenario overrides and target analyses, executes Tornado IRR, BQML ARIMA_PLUS, 23-Year LCOE, or 30-Year DCF on brazil-power-bq-twin-mcp, renders ECharts inline via render_chart, and synthesizes 22-tab .xlsx or Google Sheets deliverables purely from BigQuery rows.
---

# Brazil Power v13 — BigQuery Digital Twin Orchestrator (`/bq-twin-power-model`)

> [!CAUTION]
> **HARD GATE FOR TURN 1 — `write_to_file` MUST COMPLETE BEFORE `ask_question`**:
> 1. **Step 1 (Standalone First Tool Call)**: Call `get_session_assumptions` on `brazil-power-bq-twin-mcp` and write the returned `Full Multi-Line Artifact Markdown Replica` via `write_to_file` (`TargetFile="<artifact_dir>/bq_twin_general_assumptions.md"`, `Overwrite=true`, `ArtifactMetadata={"UserFacing": true, "RequestFeedback": false, "Summary": "BigQuery Digital Twin: General!B5:N40"}`) BEFORE calling `ask_question`.
> 2. **Step 2 (`ask_question`)**: Immediately after `write_to_file` returns, present `ask_question` asking which technologies (`_01_CF.._12_CF`), assumption overrides, and quantitative workflows (`Tornado IRR`, `BQML ARIMA_PLUS Refresh`, `23-Year LCOE Horizon`, `30-Year DCF`) to run against `comm-model-mod.brazil_power_digital_twin`.

## Execution Rules
1. Stage any user parameter overrides via `update_session_assumptions` on `brazil-power-bq-twin-mcp` (persisting sparse deltas to `dt_scenario_deltas` and 4-Ws rows to `dt_audit_events`).
2. Execute the selected quantitative tools (`run_tornado_sensitivity`, `run_bqml_timeseries_refresh`, `run_lcoe_horizon_forecast`, `run_dcf_cashflow_analysis`) on `brazil-power-bq-twin-mcp`.
3. Render `Inline Markdown Table` in chat, pass `ECharts Option JSON` to `render_chart`, and save `Full Multi-Line Artifact Markdown Replica` to `<artifact_dir>/<Side-Pane Artifact Filename>` via `write_to_file` (preserving physical `\n` newlines after every row).
4. Offer 22-tab deliverable synthesis via `export_full_22tab_workbook` on `brazil-power-bq-twin-mcp` (`xlsx`, `google_sheets`, or `both` — synthesized 100% from BigQuery Digital Twin tables with zero template Excel files).
