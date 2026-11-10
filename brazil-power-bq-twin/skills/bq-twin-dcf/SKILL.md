---
name: bq-twin-dcf
description: Shortcut workflow for the 30-year (2024–2053) Project & Equity DCF cash-flow schedule and 10-point Thermal CVU/GF sweep on the isolated BigQuery Digital Twin (brazil-power-bq-twin-mcp). Collects target technology (_01_CF.._12_CF) and overrides via ask_question, runs run_dcf_cashflow_analysis, renders the cash-flow EChart inline via render_chart, saves the full 30-year schedule via write_to_file, and offers 22-tab DB synthesis.
---

# BigQuery Digital Twin — 30-Year Project & Equity DCF (`/bq-twin-dcf`)

1. If target technology (`_01_CF.._12_CF`) is unspecified, prompt via `ask_question`.
2. Apply any requested overrides via `update_session_assumptions` on `brazil-power-bq-twin-mcp`.
3. Call `run_dcf_cashflow_analysis` on `brazil-power-bq-twin-mcp`.
4. Render the valuation header and milestone schedule inline, pass `ECharts Option JSON` to `render_chart`, and save the complete 30-year schedule to `<artifact_dir>/bq_twin_dcf_30yr_<tech>.md` via `write_to_file` (`Overwrite=true`, `UserFacing=true`).
5. Offer 22-tab database-synthesized export via `export_full_22tab_workbook`.
