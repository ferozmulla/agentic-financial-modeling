# Antigravity Session Initialization Prompt: `Eulr202409.xlsx` Modernization (`comm-model-mod` / `us-central1`)

## Workspace Layout Checklist

1. Seed & Peer Reference Workbooks (strictly read-only):
   - `Eulr/seed/Eulr202409.xlsx` — European Long-Range Crude & Refined Products Model (`20` sheets, `604,453` `<c>` cells, `357,708` formulas $\rightarrow$ `8,028` R1C1 row equations, `iterateCount=10`)
   - `Eulr/references/*.xlsx` (gitignored) — Peer regional models (`Uslr202409.xlsx`, `Felr202409.xlsx`, `Tankerlr202409.xlsx`, etc.) used for live upstream peer sync testing
2. Validated Specification & Design Documents in `Eulr/docs/`:
   - [`01_PRD_Eulr_Google_Sheets.md`](./01_PRD_Eulr_Google_Sheets.md)
   - [`02_Design_Document_Eulr_Google_Sheets.md`](./02_Design_Document_Eulr_Google_Sheets.md)
   - [`03_Implementation_Plan_Eulr_Google_Sheets.md`](./03_Implementation_Plan_Eulr_Google_Sheets.md)
   - [`04_Antigravity_Handoff_Context_Eulr.md`](./04_Antigravity_Handoff_Context_Eulr.md)
   - [`06_Pilot_Workbooks_Demo_Scripts_Google_Sheets.md`](./06_Pilot_Workbooks_Demo_Scripts_Google_Sheets.md)

---

## Core Validated Architecture Mandates

1. **Isolated Serverless GCP Stack (`comm-model-mod` / `us-central1`, `app = "eulr-sheets-mod"`):**
   - Keep `brazil-power-v13/` untouched. Deploy Cloud Run (`eulr-equilibrium-gateway`), BigQuery (`eulr_commodity_mod_governance`), Cloud Storage (`gs://comm-model-mod-eulr-snapshots`), and Vertex AI (`gemini-3.8-flash` + Model Registry surrogate `eulr-sheets-mod-margin-surrogate` + optional Custom Prediction toggle) with zero AlloyDB dependency.
2. **AOT 10-Pass Vectorized Equilibrium Engine (`<= 1e-8` Parity) + Delta `Values.batchUpdate`:**
   - Transpile all `8,028` R1C1 row equations + `6,745` `{=CSE}` formulas into vectorized NumPy sheet evaluators, placing `ULSD-GO_spread_econs` inside the 10-pass Gauss-Seidel loop right before `KeyInputs`, and write compact delta A1 ranges in `< 2.0s` while keeping acyclic non-external formulas live on `KeyInputs`, `Yields`, `Info`, and `Checks`.
3. **SharePoint-Portable Upstream Link Registry + 3 Breakout BQML Tabs + Silent Distributed Governance:**
   - Preserve full SharePoint coordinate lineage in `upstream_external_series` (`eulr_baseline_cached`, `peer_xlsx`, and `sharepoint_graph` modes) with `ACTIVE_PEER_MODEL` / `SHARED_REFERENCE_DB` / `FROZEN_LEGACY_PATH` tags.
   - Render the 5-button **3D `OverGridImage` Execution Deck** at `KeyInputs!B2:N5`, 3 breakout BQML tabs (`Macro_BQML`, `Crudes_BQML`, `Freight_BQML`) with 3D `Refresh BQML` buttons, 3 Connected Sheets (`Upstream_Links_BQ`, `UPLOAD_BQ`, `BQ_4Ws_Audit_Log`), `Scenario_Comparison` (`gemini-3.8-flash` attribution), and `#FEF3C7` Pinned Trader Price Overrides stored per `spreadsheet_id` in GCS.
