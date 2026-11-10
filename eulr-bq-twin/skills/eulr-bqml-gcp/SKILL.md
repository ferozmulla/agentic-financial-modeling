---
name: eulr-bqml-gcp
description: Direct shortcut workflow for the EULR BigQuery ML ARIMA_PLUS 2025–2050 Time-Series Forecast Refresh across Macro, Benchmark Crudes (Dated Brent, Urals, Azeri, Arab Light, Es Sider), and Clean/Dirty Tanker Freight on eulr-refining-mcp.
---

# EULR BigQuery ML `ARIMA_PLUS` Driver Forecast Refresh (`/eulr-bqml-gcp`)

Use this skill when the analyst invokes `/eulr-bqml-gcp` or asks to forecast crude oil, macro/FX, or marine tanker freight trajectories (`2025–2050`) using BigQuery ML `ARIMA_PLUS` (`bqml_eulr_macro`, `bqml_eulr_crudes`, `bqml_eulr_freight`).

1. **Prompt via `ask_question`** (unless target domains are specified):
   - Question 1: Which `ARIMA_PLUS` driver domains to refresh (`(Recommended) All 3 Domains: CRUDES + FREIGHT + MACRO`, `CRUDES Only (Dated Brent, Urals, Azeri, Arab Light, Es Sider)`, `FREIGHT Only (VLCC, Aframax, LR2 & MR Clean/Dirty Tankers)`, `MACRO Only (Inflation, CE Plant Cost Index & EUR/USD)`).
   - Question 2: Whether to inject the `2025–2050` `ARIMA_PLUS` curves into active session drivers and re-solve 10-pass European equilibrium (`(Recommended) Yes — apply to session & re-solve NWE/MED equilibrium`, `Preview BQML trajectories only without modifying session`).
2. **Execute**:
   - Call `run_eulr_bqml_forecast_refresh` on `eulr-refining-mcp`.
3. **Present**:
   - Render `echarts_option` inline via `render_chart`.
   - Write the full `2024–2050` forecast matrix (`artifact_markdown`) to `eulr_bqml_trajectories.md` via `write_to_file` (`UserFacing=true`, `RequestFeedback=false`).
   - Offer 18-tab `.xlsx` synthesis via `export_eulr_workbook`.
