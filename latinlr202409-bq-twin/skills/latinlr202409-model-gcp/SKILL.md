---
name: latinlr202409-model-gcp
description: "Guided Gemini Agent workflow for querying the isolated Latin America Refining Equilibrium BigQuery Digital Twin (`comm-model-mod.latinlr202409_digital_twin`), running Gross Product Worth (GPW) & circular equilibrium scenarios across 13 Latin American crudes, forecasting trajectories with BigQuery ML `ARIMA_PLUS`, and synthesizing path-safe `.xlsx` workbooks via `latinlr202409-bq-twin-mcp`."
---

# Latin America Refining Digital Twin (`latinlr202409-model-gcp`)

Use this skill whenever a user asks about the **Latin America Long-Term Refining Model (`Latinlr202409.xlsx`)**, Latin American crude assays (`Escalante`, `Medanito`, `Lula`, `Marlim`, `Castilla Blend`, `Vasconia`, `Napo`, `Oriente`, `Liza`, `Unity Gold`, `Olmeca`, `Merey`, `Mesa_30`), FCC/coking yields (`Yields`), or regional refining margins (`Dashboard_Annual`, `Dashboard_Month`).

## MCP Tools (`latinlr202409-bq-twin-mcp`)
1. `get_latinlr202409_model_summary`: Inspect workbook metadata, active sheets, and the 13 Latin American crude assays.
2. `run_latinlr202409_equilibrium_scenario`: Execute deterministic circular equilibrium and Gross Product Worth (`GPW`) simulations with optional `Sheet!Coord` overrides and 4-Ws audit logging.
3. `export_latinlr202409_xlsx`: Synthesize a clean `.xlsx` workbook directly from the BigQuery Digital Twin snapshot.
