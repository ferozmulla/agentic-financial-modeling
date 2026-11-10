---
name: bq-twin-lcoe
description: Shortcut workflow for the 23-year (2024–2046) multi-technology LCOE horizon forecast on the isolated BigQuery Digital Twin (brazil-power-bq-twin-mcp). Prompts for scenario or BQML refresh choices via ask_question, executes run_lcoe_horizon_forecast, renders the multi-series LCOE EChart inline via render_chart, writes bq_twin_output3_lcoe_horizon.md via write_to_file, and offers 22-tab DB synthesis.
---

# BigQuery Digital Twin — 23-Year Multi-Technology LCOE Horizon (`/bq-twin-lcoe`)

1. If scenario assumptions or BQML refresh preferences are unspecified, prompt via `ask_question`.
2. Apply any requested overrides (`update_session_assumptions`) or BQML refresh (`run_bqml_timeseries_refresh`) on `brazil-power-bq-twin-mcp`.
3. Call `run_lcoe_horizon_forecast` on `brazil-power-bq-twin-mcp`.
4. Render the milestone `Output_3!B8:J31` table inline, pass `ECharts Option JSON` to `render_chart`, and save the full 23-row replica to `<artifact_dir>/bq_twin_output3_lcoe_horizon.md` via `write_to_file` (`Overwrite=true`, `UserFacing=true`).
5. Offer 22-tab database-synthesized export via `export_full_22tab_workbook`.
