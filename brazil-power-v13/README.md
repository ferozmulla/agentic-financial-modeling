# Commodity Modeling Sheets Platform — Brazil Power Generation Techno-Economic Model (`v13`)

Enterprise modernization of the **Regional Power Generation Techno-Economic Model — Brazil (`2023-11-27-Brazil_TT_v13_RJEB.xlsm`)** onto **Google Sheets**, **Cloud Run**, **BigQuery / BigQuery ML**, and **Vertex AI**.

All **22 core worksheets**, **35,655 active cells**, **15,961 live spreadsheet formulas**, and **3,400 named ranges** run natively in Google Sheets, paired with a vectorized Python solver on Cloud Run (`<= 1e-8` numerical parity across all **854** legacy VBA macro outputs), three live-refreshable BigQuery ML (`ARIMA_PLUS`) forecast tabs, and zero-friction **4-Ws (`Who`, `What`, `When`, `Why`)** governance across both the central workbook and distributed analyst copies.

---

## 1. Functional Purpose & Three Calculation Tiers

### Functional Purpose
This workbook serves as the regional techno-economic valuation and dispatch benchmarking model for the **Brazilian power sector (`2018–2040`)**, comparing **12 utility-scale and distributed generation technologies** (Gas CCGT/OCGT, Biomass, Biogas, Onshore Wind, Utility & Distributed Solar PV, Small Hydro PCH, and Coal) on an apples-to-apples financial basis. Energy analysts and commercial teams use it to evaluate **20-to-30-year project cashflows**, **Brazilian tax regimes** (*Lucro Real* vs. *Lucro Presumido*, PIS/COFINS, ICMS), **financing structures** (BNDES / market debt), and **regulated auction competitiveness** (`LCOE` and `CVU` dispatch merit order).

### Three Calculation Tiers
1. **Spreadsheet Formula-Based Calculations (`15,961` live Google Sheets formulas):**
   Compute year-by-year project financial statements across `_01_CF`–`_12_CF`, `_CAPEX 01`, `CVU_GF`, and `Output_1`–`Output_3`—including capital expenditure schedules, depreciation, debt service, Brazilian corporate/revenue taxes, net free cashflows to equity/firm, **NPV**, **Equity/Project IRR**, and **Variable Unit Generation Cost (`CVU`)**—updating instantaneously as analysts test assumptions.
2. **Macro / Cloud-Solver Calculations (`31` interactive 3D buttons on `General!B42:N52` -> Cloud Run Python Engine):**
   Replace slow, single-threaded Excel VBA `GoalSeek` loops with vectorized **Secant + Brent** root-finding (`src/solver/`) to solve **break-even tariffs (`LCOE`)** at target hurdle rates (`lcoe_exec`), **23-year forward LCOE curves** (`lcoe_forecast`), **regulated `Fator-i` calibration** (`fator_i`), **Tornado IRR sensitivities** (`calcule_tir1`–`12`), and **1D/2D Capex/Fuel/Capacity-Factor risk matrices** (`854` parity-verified outputs in ~1–4 seconds).
3. **Time-Series ML Calculations (`BigQuery ML ARIMA_PLUS` -> `LT_Capex_BQML`, `LT_Fuel_BQML`, `LT_CF_BQML`):**
   Learn historical cost and performance trends (`<= 2025` empirical actuals across `445` data points from `LT Capex`, `LT Fuel`, and `LT CF`) in BigQuery ML (`bqml_lt_trajectories_forecast_v1`) to generate **data-driven `2026–2040` forward trajectories and 95% confidence bounds** for capital cost learning curves (`R$/kW`), thermal/biomass fuel cost paths, and renewable capacity factors (`%`), alongside a Vertex AI-registered `LINEAR_REG` LCOE surrogate (`BQML_LCOE_Surrogate`).

---

## 2. Live Hosted Resources (`comm-model-mod`, `us-central1`)

| Layer | Resource Identifier / URL | Notes |
| :--- | :--- | :--- |
| **GCP Project & Region** | `comm-model-mod` (`1024543888590`) / `us-central1` | BigQuery in `us-central1`; Gemini endpoint in `us` |
| **Central Governed Google Sheet** | `1apbos5xVpK4yBLiRFxQqAEyPVNkkYQ2ZvgAASibYYJI` | *Regional Power Generation Techno-Economic Model — Brazil v13 (Governed)* (`22` core tabs + `5` BQML / Connected Sheets tabs) |
| **Cloud Run FastAPI Gateway** | `https://sheets-commodity-mod-gateway-1024543888590.us-central1.run.app` | Hosts `/v1/sheets/solve`, `/v1/bqml/solve`, `/v1/ingest/edit-event`, and `/v1/ingest/checkpoint` |
| **Cloud Storage Snapshot Bucket** | `gs://comm-model-mod-sheets-mod-snapshots` | Immutable versioned workbook checkpoint storage (`us-central1`) |
| **BigQuery Governance Dataset** | `comm-model-mod:sheets_commodity_mod_governance` | Tables: `audit_events`, `historical_lt_trajectories`, `solver_training_grid`, `solver_run_telemetry` |
| **BigQuery ML Models** | `bqml_lt_trajectories_forecast_v1` (`ARIMA_PLUS`), `bqml_lcoe_surrogate_v1` (`LINEAR_REG`) | Registered in Vertex AI Model Registry (`sheets-commodity-mod-bqml-surrogate`) |
| **Connected Sheets Tabs** | `LT_Capex_BQML`, `LT_Fuel_BQML`, `LT_CF_BQML`, `BQML_LCOE_Surrogate`, `BQ_4Ws_Audit_Log` | `LT_*_BQML` include 1-click `Refresh BQML` 3D buttons; `BQ_4Ws_Audit_Log` & `BQML_LCOE_Surrogate` use native Connected Sheets (`DATA_SOURCE`) |

---

## 3. Silent Distributed `4-Ws` Governance & Rollback

- **Distributed Copy Lineage (`File -> Make a copy`):** Analysts can work directly in the central Google Sheet or create personal copies in Google Drive. `CombinedSheetScript.gs` travels automatically with every copy and self-installs `onGovernedSheetEdit` (`onEdit`) and `onGovernedSheetChange` (`onChange`) triggers on first solver execution (`installEditTrigger`).
- **Noise-Suppressed AST Classification (`src/parser/` & `src/diff/`):** Routine numeric tweaks on `SCENARIO_INPUT_CELL` coordinates are suppressed (`0` alert fatigue), whereas formula overrides (`MANUAL_OVERRIDE`), header/label renames (`HEADER_OR_LABEL_MODIFIED`), structural row/column shifts (`ROW_INSERTED`, `SHEET_ADDED`), and solver runs (`SOLVER_RUN`) stream silently to `sheets_commodity_mod_governance.audit_events` (`vw_audit_4w_summary`).
- **Two-Tier Rollback & Version Recovery:**
  1. **Surgical Cell/Formula Rollback:** Every cell/formula audit row stores exact `before_formula` and `before_value` snapshots in BigQuery so individual overrides can be restored without disturbing subsequent work.
  2. **Full-Workbook Point-in-Time Recovery:** Each audit row records `copy_location_url` (`gcs_snapshot_uri`) and `when_event_utc`, allowing model owners to open the exact central or analyst Google Sheet and restore the revision immediately preceding `when_event_utc` via **File > Version history > See version history**.

---

## 4. Sub-Project Structure (`brazil-power-v13/`)

```text
brazil-power-v13/
├── README.md                                     # Workbook overview, live resources & quickstart
├── Makefile                                      # Setup, lint, test, local API, and Terraform targets
├── pyproject.toml / requirements.txt             # Python 3.11+ package & dependency definitions
├── seed/
│   └── 2023-11-27-Brazil_TT_v13_RJEB.xlsm        # Read-only legacy Excel/VBA baseline workbook
├── data/fixtures/
│   └── brazil_tt_v13_baseline.json               # Extracted 854 macro parity fixtures & static tables
├── apps_script/
│   ├── CombinedSheetScript.gs                    # Unified container-bound Apps Script deployed to Google Sheets
│   ├── Menu.gs                                   # Custom menu, 3D OverGridImage overlays & BQML tab setup
│   ├── SolverClient.gs                           # Cloud Run solver bridge & distributed trigger installer
│   ├── AuditHooks.gs                             # Silent onEdit + onChange 4-Ws governance hooks
│   └── appsscript.json                           # Apps Script V8 manifest (Sheets, BigQuery, Drive)
├── src/
│   ├── api/                                      # FastAPI Cloud Run gateway (/v1/sheets/solve, /v1/ingest/*)
│   ├── solver/                                   # Vectorized NumPy/SciPy LCOE, IRR, CVU & Fator-i engine
│   ├── parser/                                   # OpenXML & Sheets AST/DAG builder + 4-role classifier
│   ├── diff/                                     # R1C1 structural shift normalizer & formula differ
│   ├── ingestion/                                # Real-time edit classifier & checkpoint pipeline
│   ├── bqml/                                     # BigQuery ML forecast & remote-function helpers
│   ├── vertex/                                   # Vertex AI custom job launcher & Gemini 2.5 explainer
│   └── db/                                       # Dual-mode AlloyDB / SQLite + BigQuery repositories
├── sql/bigquery/
│   ├── 001_dataset_and_tables.sql                # audit_events, trajectories, training grid & telemetry DDL
│   ├── 002_governance_views.sql                  # vw_audit_4w_summary, vw_manual_overrides, SLA views
│   └── 003_bqml_forecasts_remote_fn_and_surrogate.sql # ARIMA_PLUS, pivoted forecast view & LCOE surrogate
├── scripts/
│   ├── seed_google_sheet_from_xlsm.py            # Converts seed .xlsm to native Google Sheet & verifies 22 tabs
│   ├── configure_general_buttons.py              # Styles General!B42:N52 31-button deck & pushes Apps Script
│   └── deploy_bqml_and_vertex.py                 # Seeds 445 empirical LT rows, trains BQML & verifies views
├── infra/terraform/                              # Isolated GCP IaC (Cloud Run, BigQuery, AlloyDB, Vertex AI)
├── tests/                                        # Unit, 854-cell solver parity, AST/DAG, E2E & Terraform tests
└── docs/
    ├── 01_PRD_Google_Sheets.md                   # Product Requirements Document
    ├── 02_Design_Document_Google_Sheets.md       # System Architecture & Technical Design
    ├── 03_Implementation_Plan_Google_Sheets.md   # Implementation Plan & Module Specifications
    ├── 04_Antigravity_Handoff_Context.md         # Workbook Forensics & Handoff Context
    ├── 05_Execution_Prompts_Google_Sheets.md     # Reproducible Engineering Prompts
    └── 06_Live_Demo_Runbook_Google_Sheets.md     # 5-Minute Executive & Leadership Demo Runbook
```

---

## 5. Quickstart & Verification (Run inside `brazil-power-v13/`)

```bash
# 1. Create or update the shared virtualenv and install dependencies
make setup

# 2. Run Ruff static analysis across src/, tests/, and scripts/
make lint

# 3. Run full unit, 854-output numerical parity, AST/DAG governance, E2E, and Terraform test suite
make test

# 4. Run local FastAPI gateway (ENV=local)
make run-local

# 5. Re-verify or redeploy BigQuery ML models & views against GCP (comm-model-mod / us-central1)
PYTHONPATH=. ../.venv/bin/python scripts/deploy_bqml_and_vertex.py
```
