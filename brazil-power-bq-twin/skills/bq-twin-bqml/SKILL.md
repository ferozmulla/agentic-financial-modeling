---
name: bq-twin-bqml
description: Shortcut workflow for the BigQuery ML ARIMA_PLUS 23-year trajectory refresh on the isolated BigQuery Digital Twin (brazil_power_digital_twin.vw_lt_forecasts via brazil-power-bq-twin-mcp). Collects curve selection via ask_question, executes run_bqml_timeseries_refresh, renders ECharts inline via render_chart, writes bq_twin_lt_trajectories.md via write_to_file, and chains into LCOE or 22-tab synthesis.
---

# BigQuery Digital Twin — `ARIMA_PLUS` 23-Year Trajectory Refresh (`/bq-twin-bqml`)

1. If curve selection (`CAPEX`, `FUEL`, `CF`) is unspecified, prompt via `ask_question`.
2. Call `run_bqml_timeseries_refresh` on `brazil-power-bq-twin-mcp` to query `comm-model-mod.brazil_power_digital_twin.vw_lt_forecasts` and append trajectory deltas to `dt_scenario_deltas`.
3. Render the inline trajectory summary, call `render_chart` with `ECharts Option JSON`, and write `<artifact_dir>/bq_twin_lt_trajectories.md` via `write_to_file` (`Overwrite=true`, `UserFacing=true`).
4. Offer chaining into `run_lcoe_horizon_forecast` or `export_full_22tab_workbook` on `brazil-power-bq-twin-mcp`.
