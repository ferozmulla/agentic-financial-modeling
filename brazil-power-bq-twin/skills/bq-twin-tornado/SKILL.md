---
name: bq-twin-tornado
description: Shortcut workflow for the 21-point IRR Tornado Sensitivity analysis on the isolated BigQuery Digital Twin (brazil-power-bq-twin-mcp). Prompts for target technology (_01_CF.._12_CF) and optional overrides via ask_question, runs run_tornado_sensitivity against comm-model-mod.brazil_power_digital_twin, renders the Tornado EChart inline via render_chart, saves the side-pane Artifact via write_to_file, and offers DB-synthesized 22-tab export.
---

# BigQuery Digital Twin — 21-Point Tornado IRR Sensitivity (`/bq-twin-tornado`)

1. If target technology or overrides are unspecified, call `ask_question` to select `_01_CF.._12_CF` and optional parameter overrides.
2. If overrides were provided, call `update_session_assumptions` on `brazil-power-bq-twin-mcp`.
3. Call `run_tornado_sensitivity` on `brazil-power-bq-twin-mcp`.
4. Render the inline Markdown table, call `render_chart` with `ECharts Option JSON`, and call `write_to_file` (`TargetFile="<artifact_dir>/bq_twin_tornado_<tech>.md"`, `Overwrite=true`, `UserFacing=true`) preserving physical `\n` newlines on every table row.
5. Offer 22-tab database-synthesized export via `export_full_22tab_workbook`.
