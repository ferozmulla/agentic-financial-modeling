# Engineering Implementation Plan: Enterprise Commodity Modeling — Google Sheets Modernization & Structural Governance Platform

| Document Metadata | Details |
| :--- | :--- |
| **Document ID** | `ENT-IMP-SHEETS-MOD-003` |
| **Related PRD & Design Doc** | `docs/01_PRD_Google_Sheets.md` (`ENT-PRD-SHEETS-MOD-001`), `docs/02_Design_Document_Google_Sheets.md` (`ENT-SDD-SHEETS-MOD-002`) |
| **Version** | `1.0.0 (Execution-Ready Engineering Blueprint — Google Sheets Native Stack)` |
| **Date** | October 29, 2026 |
| **Authors** | Principal Google Cloud Architect & Staff Quantitative Systems Engineer |
| **Target GCP Project & Region** | Parameterized via `var.project_id` / `GCP_PROJECT_ID` (Default Project: `comm-model-mod`, Region: `us-central1`, Zone: `us-central1-a`, BigQuery Location: `us-central1`) |
| **Universal GCP Resource Label** | `app = "sheets-commodity-mod"`, `project = "enterprise-commodity-modernization"`, `env = "mvp"`, `managed-by = "terraform"` |
| **Seed Baseline Input (Read-Only)** | `2023-11-27-Brazil_TT_v13_RJEB.xlsm` (Seeded into Google Sheets via `scripts/seed_google_sheet_from_xlsm.py` and used for $\le 10^{-8}$ parity verification) |
| **Frontend Layer** | **Google Sheets** + **Google Apps Script (`apps_script/*.gs`)** + **Native Connected Sheets for BigQuery** |

---

## 1. Complete Repository Directory Tree

The engineering implementation follows a clean, modular Python 3.11+, Google Apps Script (`V8`), and Terraform directory architecture supporting both **Local Developer / CI Mode (`ENV=local`)** and **Google Cloud Production Mode (`ENV=gcp` in region `us-central1`)**:

```text
commodity-modeling-sheets-platform/
├── README.md                                           # Executive & Engineering Repository Overview
├── docs/
│   ├── 01_PRD_Google_Sheets.md                         # Approved Product Requirements Document (Google Sheets Native)
│   ├── 02_Design_Document_Google_Sheets.md             # System Design Document (Google Sheets Native)
│   ├── 03_Implementation_Plan_Google_Sheets.md         # This File-by-File Engineering Blueprint
│   ├── 04_Antigravity_Handoff_Context.md               # Complete Context & Domain Handoff Document
│   └── 06_Live_Demo_Runbook_Google_Sheets.md           # Executive Talk Track & 5-Minute Live Demo Runbook
├── seed/
│   └── 2023-11-27-Brazil_TT_v13_RJEB.xlsm              # Read-Only Baseline Seed Workbook (22 sheets, 35,655 cells)
├── apps_script/
│   ├── appsscript.json                                 # Apps Script V8 manifest & OAuth scopes (spreadsheets, external_request, bigquery, drive)
│   ├── CombinedSheetScript.gs                          # Unified bound script: 31 3D button deck + Connected Sheets BQML tabs + solver client + silent 4-Ws governance
│   ├── Menu.gs                                         # Custom "Commodity Modeling" menu, 3D button overlays & setupBigQueryConnectedSheets / refreshBqmlForecasts
│   ├── SolverClient.gs                                 # Solver client: batch read + POST /v1/solve + batch write-back + installEditTrigger
│   └── AuditHooks.gs                                   # Distributed copy Pillar B hooks: installEditTrigger + silent onGovernedSheetEdit & onGovernedSheetChange
├── scripts/
│   ├── seed_google_sheet_from_xlsm.py                  # Automated Drive/Sheets API importer + Apps Script binder + Connected Sheets setup
│   ├── configure_general_buttons.py                    # Formats 31 button cells, spacer rows & row grouping on General!B42:N52
│   ├── deploy_bqml_and_vertex.py                       # Seeds 445 empirical LT rows & deploys BQML ARIMA_PLUS forecast, fn_solve_lcoe & Vertex AI surrogate
│   └── setup_apps_script_triggers.py                   # Configures installable onEdit & onChange triggers via Apps Script API
├── pyproject.toml                                      # Python package metadata, pytest, ruff, mypy config
├── requirements.txt                                    # Pinned production Python dependencies
├── requirements-dev.txt                                # Pinned test, linting & local development dependencies
├── .env.example                                        # Template environment variables for ENV=local and ENV=gcp
├── .gitignore                                          # Git ignore rules for data/, .venv/, .terraform/, etc.
├── .dockerignore                                       # Docker build context exclusions
├── Makefile                                            # Developer & CI automation targets (lint, test, seed-sheet, gcp, destroy)
├── Dockerfile.gateway                                  # Cloud Run Solver & Governance Gateway container image
├── Dockerfile.vertex_solver                            # Vertex AI Custom Prediction container image (AIP_* contract)
├── docker-compose.yml                                  # Local dev stack: Gateway + Vertex Solver
├── migrations/
│   ├── 001_initial_alloydb_schema.sql                  # Optional relational schema DDL
│   └── 002_audit_immutability_trigger.sql              # NFR-05 append-only trigger
├── sql/
│   └── bigquery/
│       ├── 001_dataset_and_tables.sql                  # BigQuery partitioned/clustered audit_events & LT input tables (solver_run_telemetry in V2 backlog)
│       ├── 002_governance_views.sql                    # Connected Sheets views: vw_audit_4w_summary (with copy_name & copy_location_url), vw_manual_overrides
│       └── 003_bqml_forecasts_remote_fn_and_surrogate.sql # ML.FORECAST (ARIMA_PLUS), fn_solve_lcoe Remote Function & bqml_lcoe_surrogate_v1
├── src/
│   ├── __init__.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py                                   # Pydantic Settings (ENV=local|gcp, GCP_PROJECT_ID, us-central1, BigQuery dataset)
│   │   ├── logging.py                                  # Structured JSON logging with GCP trace & spreadsheet correlation
│   │   └── security.py                                 # Google Apps Script OIDC Bearer & X-Local-Principal verification (GCP)
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── solver.py                                   # Solver API & Vertex AI instances/predictions Pydantic schemas
│   │   ├── ast_dag.py                                  # CellSemanticRole enum, AST cell, DAG edge, NamedRange, Debt schemas
│   │   └── audit.py                                    # ChangeType (including HEADER_OR_LABEL_MODIFIED, ROW_INSERTED, etc.), Severity, 4W AuditEventRecord
│   ├── solver/
│   │   ├── __init__.py
│   │   ├── workbook_context.py                         # Extracts & caches static baseline params from General, CVU_GF, LT *
│   │   ├── cashflow_model.py                           # Vectorized IEEE 754 cash-flow, IRR & thermal ICB polynomial engine
│   │   ├── convergence.py                              # StrictLegacyVBAEmulator: Stage 1 GoalSeek + Stage 2 lattice search
│   │   └── macros/
│   │       ├── __init__.py
│   │       ├── registry.py                             # Dispatcher mapping all 38 ported routines to solver implementations
│   │       ├── tornado_irr.py                          # calcule_tir1..12 (including tir11/12 Stage-1-only 8.0001% quirk)
│   │       ├── cvu_sweeps.py                           # calculo_cvu1..12 (including selective rst_scenario & gd routines)
│   │       ├── sensitivity_1d_2d.py                    # calculo_capexvscf, calculo_priceirr & 4 100-solve 2D *_bi sweeps
│   │       └── forecasts_and_dispatch.py               # lcoe_exec (184 solves), lcoe_forecast, fator_i, rst_scenario
│   ├── vertex/
│   │   ├── __init__.py
│   │   ├── predictor_server.py                         # FastAPI server implementing AIP_HEALTH_ROUTE & AIP_PREDICT_ROUTE
│   │   └── registry_client.py                          # Registers model & parity evaluation artifact in Vertex AI Registry
│   ├── bqml/
│   │   ├── __init__.py
│   │   ├── remote_function_handler.py                  # BigQuery Remote Function JSON request/response batch handler
│   │   └── surrogate_trainer.py                        # Generates sweep grid & trains/evaluates bqml_lcoe_surrogate_v1 + LT forecasts
│   ├── parser/
│   │   ├── __init__.py
│   │   ├── openxml_extractor.py                        # Streams Google Sheets .xlsx export / .xlsm ZIP XML parts & button bindings
│   │   ├── sheets_grid_extractor.py                    # Parses native Google Sheets API includeGridData JSON payloads
│   │   ├── formula_normalizer.py                       # Expands shared formulas to canonical A1 + R1C1 + SHA-256
│   │   ├── dag_builder.py                              # Tokenizes formulas into precedent -> dependent DAG edges
│   │   ├── semantic_classifier.py                      # Deterministic 4-role classifier (FR-B01 precedence rules)
│   │   └── technical_debt_scanner.py                   # Extracts 1,123 #REF! names, broken macros & orphaned LT * references
│   ├── diff/
│   │   ├── __init__.py
│   │   ├── shift_normalizer.py                         # FR-B07 row/col alignment & R1C1 relative formula shift filter
│   │   └── structural_differ.py                        # FR-B06 state machine emitting 4W AuditEventRecords & MANUAL_OVERRIDE
│   ├── storage/
│   │   ├── __init__.py
│   │   └── snapshot_store.py                           # GCSSnapshotStore (ENV=gcp) & LocalFilesystemSnapshotStore (ENV=local)
│   ├── db/
│   │   ├── __init__.py
│   │   ├── session.py                                  # Async SQLAlchemy engine helper
│   │   ├── models.py                                   # SQLAlchemy 2.0 ORM models
│   │   ├── repositories.py                             # Repository helpers
│   │   └── bigquery_sink.py                            # Primary serverless BigQuery 4-Ws audit sink (audit_events) or local JSONL
│   ├── ingestion/
│   │   ├── __init__.py
│   │   ├── publisher.py                                # DEC-05 EventPublisher interface (InProcess MVP + PubSub V2 hooks)
│   │   ├── realtime_edit_handler.py                    # Processes real-time onEdit & onChange events (< 150ms) with seed-baseline lookup
│   │   └── checkpoint_pipeline.py                      # Orchestrates GCS-first snapshot -> AST/DAG -> Diff (with seed fallback) -> BigQuery Audit
│   ├── api/
│   │   ├── __init__.py
│   │   ├── main.py                                     # Unified Cloud Run FastAPI application factory & lifespan hooks
│   │   └── routes/
│   │       ├── __init__.py
│   │       ├── solve.py                                # POST /v1/solve/{macro_name} & POST /v1/bqml/solve
│   │       ├── ingest.py                               # POST /v1/ingest/edit-event & POST /v1/ingest/checkpoint
│   │       ├── governance.py                           # GET /v1/workbooks/... versions, diff, dag, audit-log, lineage, debt
│   │       └── health.py                               # GET /health & GET /v1/health/deep
│   └── cli/
│       ├── __init__.py
│       ├── extract_baseline_fixtures.py                # Extracts golden parity fixtures from 2023-11-27-Brazil_TT_v13_RJEB.xlsm
│       ├── ingest_checkpoint_cli.py                    # CLI uploader simulating Google Sheets Checkpoint & onEdit events
│       └── run_solver_cli.py                           # CLI runner to execute any of the 38 macros & print parity report
├── infra/
│   └── terraform/
│       ├── providers.tf                                # Google & Google-Beta providers (var.project_id, us-central1)
│       ├── variables.tf                                # Root input variables (project_id, region = "us-central1", zone = "us-central1-a")
│       ├── locals.tf                                   # Mandatory local.common_labels (app = "sheets-commodity-mod")
│       ├── main.tf                                     # Root module composition + disable_on_destroy=false API safety
│       ├── outputs.tf                                  # Cloud Run URL, Vertex Endpoint ID, GCS URIs, BigQuery Dataset ID
│       ├── terraform.tfvars.example                    # Example tfvars for target Google Cloud project
│       └── modules/
│           ├── networking/                             # Isolated sheets-mod-vpc + Private Services Access + VPC Connector
│           ├── iam/                                    # 4 SAs + additive-only google_project_iam_member bindings
│           ├── storage/                                # 2 versioned buckets, force_destroy=true
│           ├── bigquery/                               # Dataset, audit_events table, connection, BQML models & Connected Sheets views
│           └── vertex_ai_and_cloud_run/                # Artifact Registry, Model, Endpoint + undeploy hook, Cloud Run Gateway
└── tests/
    ├── conftest.py                                     # PyTest fixtures for baseline .xlsm, local DB, GCS mock, AsyncClient
    ├── unit/
    │   ├── test_cashflow_and_irr.py                    # Tier 2 Unit: Cash-flow vectors, IRR & 2-stage discrete lattice convergence
    │   └── test_parser_and_normalizer.py               # Tier 2 Unit: Shared formula expansion, R1C1 conversion, 4-role classifier
    ├── integration/
    │   ├── test_solver_parity.py                       # Tier 3 Integration: TEST-A01..A04 (854 outputs verified to <= 1e-8)
    │   └── test_ast_dag_and_audit.py                   # Tier 3 Integration: TEST-B01..B08 (35,655 cells, formula override, header edit, row insert)
    ├── e2e/
    │   └── test_google_sheets_analyst_journey.py       # Tier 4 E2E: Simulates Google Sheets analyst workflow
    └── infra/
        └── test_terraform_governance.py                # Tier 1/3 IaC: TEST-INFRA-01..06
```

---

## 2. Subsystem Engineering Specifications

### 2.1 Google Sheets Frontend Layer, Distributed Copy Governance & Seeding Automation (`apps_script/` & `scripts/`)

#### 1. `scripts/seed_google_sheet_from_xlsm.py` & `scripts/configure_general_buttons.py`
- **Purpose:** Seeding and formatting utilities that read the baseline workbook (`seed/2023-11-27-Brazil_TT_v13_RJEB.xlsm`) **strictly read-only** and provision the cloud-enabled central Google Sheet in Google Drive (`1apbos5xVpK4yBLiRFxQqAEyPVNkkYQ2ZvgAASibYYJI`):
  1. Uploads `2023-11-27-Brazil_TT_v13_RJEB.xlsm` to Google Drive with `mimeType = "application/vnd.google-apps.spreadsheet"`, automatically converting all 22 worksheets, `35,655` cells, `15,961` formulas, `3,400` named ranges, formatting, and charts into a native Google Sheet (`Regional Power Generation Techno-Economic Model — Brazil v13 (Governed)`).
  2. Verifies via the Google Sheets API (`spreadsheets.get`) that all 22 tabs (`Version Control`, `General`, `Output_1`–`Output_3`, `_01_CF`–`_12_CF`, `_CAPEX 01`, `CVU_GF`, `LT Capex`, `LT Fuel`, `LT CF`) are present and intact.
  3. Formats the 31 solver button slots on `General!B42:N52` (`configure_general_buttons.py`) and binds `apps_script/CombinedSheetScript.gs` (`Menu.gs` + `SolverClient.gs` + `AuditHooks.gs`) so that `autoBindGeneralDrawingButtons()` snaps native 3D bevel `OverGridImage` PNG overlays (`getButton3dOverlayBlob_()`) onto all 31 solver cells, while `setupBigQueryConnectedSheets()` creates the 5 live BigQuery Connected Sheets / BQML tabs (`LT_Capex_BQML`, `LT_Fuel_BQML`, `LT_CF_BQML` with 3D `Refresh BQML` buttons, `BQML_LCOE_Surrogate`, and `BQ_4Ws_Audit_Log`).
  4. **Distributed Analyst Copy Support (`File -> Make a copy`):** When analysts create personal copies of the central Google Sheet in their own Google Drive (`My Drive` or shared folders), all worksheets, the 31 3D cell buttons, and `CombinedSheetScript.gs` carry over automatically. On the first solver button click in any personal copy (or when running `installEditTrigger`), `installEditTrigger(ss)` self-installs both `onGovernedSheetEdit` (`onEdit`) and `onGovernedSheetChange` (`onChange`) on that copy to stream silent 4-Ws audit events (including the copy's title and Google Drive URL) to BigQuery.

#### 2. `apps_script/appsscript.json`
```json
{
  "timeZone": "America/Sao_Paulo",
  "dependencies": {
    "enabledAdvancedServices": [
      {
        "userSymbol": "Sheets",
        "serviceId": "sheets",
        "version": "v4"
      },
      {
        "userSymbol": "BigQuery",
        "serviceId": "bigquery",
        "version": "v2"
      },
      {
        "userSymbol": "Drive",
        "serviceId": "drive",
        "version": "v3"
      }
    ]
  },
  "exceptionLogging": "STACKDRIVER",
  "runtimeVersion": "V8",
  "oauthScopes": [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/script.external_request",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/bigquery.readonly",
    "openid"
  ]
}
```

#### 3. `apps_script/Menu.gs` (Included in `apps_script/CombinedSheetScript.gs`)
```javascript
/**
 * Creates the custom "Commodity Modeling" menu in Google Sheets on open.
 * Exposes all 31 solver routines, live BQML forecast refresh, and admin controls.
 */
function onOpen(e) {
  var ui = SpreadsheetApp.getUi();
  ui.createMenu("Commodity Modeling")
    .addItem("Run Full LCOE & Dispatch Suite (lcoe_exec)", "lcoe_exec")
    .addItem("Run Multi-Decade LCOE Forecast (lcoe_forecast)", "lcoe_forecast")
    .addItem("Run Fator-i Calibration (fator_i)", "fator_i")
    .addSeparator()
    .addSubMenu(ui.createMenu("Tornado IRR Solvers (calcule_tir 1..12)")
      .addItem("Tech 01 — Gas CCGT (calcule_tir1)", "calcule_tir1")
      .addItem("Tech 02 — Biomass (calcule_tir2)", "calcule_tir2")
      .addItem("Tech 03 — Biogas (calcule_tir3)", "calcule_tir3")
      .addItem("Tech 04 — Wind Onshore (calcule_tir4)", "calcule_tir4")
      .addItem("Tech 05 — Solar Utility (calcule_tir5)", "calcule_tir5")
      .addItem("Tech 06 — Small Hydro PCH (calcule_tir6)", "calcule_tir6")
      .addItem("Tech 07 — Local Coal (calcule_tir7)", "calcule_tir7")
      .addItem("Tech 08 — Imported Coal (calcule_tir8)", "calcule_tir8")
      .addItem("Tech 09 — Woodchip (calcule_tir9)", "calcule_tir9")
      .addItem("Tech 10 — Gas OCGT (calcule_tir10)", "calcule_tir10")
      .addItem("Tech 11 — Solar DG Res (calcule_tir11)", "calcule_tir11")
      .addItem("Tech 12 — Solar DG Comm (calcule_tir12)", "calcule_tir12"))
    .addSubMenu(ui.createMenu("CVU Sweep Solvers (calculo_cvu 1..12)")
      .addItem("Tech 01 CVU (calculo_cvu1)", "calculo_cvu1")
      .addItem("Tech 02 CVU (calculo_cvu2)", "calculo_cvu2")
      .addItem("Tech 03 CVU (calculo_cvu3)", "calculo_cvu3")
      .addItem("Tech 04 CVU (calculo_cvu4)", "calculo_cvu4")
      .addItem("Tech 05 CVU (calculo_cvu5)", "calculo_cvu5")
      .addItem("Tech 06 CVU (calculo_cvu6)", "calculo_cvu6")
      .addItem("Tech 07 CVU (calculo_cvu7)", "calculo_cvu7")
      .addItem("Tech 08 CVU (calculo_cvu8)", "calculo_cvu8")
      .addItem("Tech 09 CVU (calculo_cvu9)", "calculo_cvu9")
      .addItem("Tech 10 CVU (calculo_cvu10)", "calculo_cvu10")
      .addItem("Tech 11 CVU (calculo_cvu11)", "calculo_cvu11")
      .addItem("Tech 12 CVU (calculo_cvu12)", "calculo_cvu12"))
    .addSubMenu(ui.createMenu("1D & 2D Sensitivity Matrices")
      .addItem("Biomass 2D BI LCOE (calculo_cvu2bi)", "calculo_cvu2bi")
      .addItem("Wind 2D BI LCOE (calculo_cvu4bi)", "calculo_cvu4bi")
      .addItem("Solar 1D Capex vs IRR (calculo_capexvscf)", "calculo_capexvscf")
      .addItem("Hydro 1D Price vs IRR (calculo_priceirr)", "calculo_priceirr")
      .addItem("Solar 2D BI LCOE (calculo_capexvscfbi)", "calculo_capexvscfbi")
      .addItem("Hydro 2D BI LCOE (calculo_priceirr_bi)", "calculo_priceirr_bi"))
    .addSeparator()
    .addItem("Refresh BQML Time-Series Forecasts (LT_Capex / LT_Fuel / LT_CF)", "refreshBqmlForecasts")
    .addSeparator()
    .addSubMenu(ui.createMenu("Admin Controls")
      .addItem("Enable 4-Ws Governance Audit Triggers (Edit + Change)", "installEditTrigger")
      .addItem("Auto-Bind, Snap & Size 3D Cell Buttons", "autoBindGeneralDrawingButtons")
      .addItem("Toggle Freeze Button Deck (Row 52 / Row 5)", "toggleFreezeButtonDeck")
      .addItem("Provision BigQuery ML & Connected Sheets Tabs", "setupBigQueryConnectedSheets"))
    .addToUi();
}
```

#### 4. `apps_script/SolverClient.gs` (Included in `apps_script/CombinedSheetScript.gs`)
```javascript
/**
 * Executes any of the quantitative solver macros on the Cloud Run + Vertex AI backend,
 * writes cell_updates back to Google Sheets, and automatically ensures both
 * onEdit (onGovernedSheetEdit) and onChange (onGovernedSheetChange) triggers are installed
 * on this spreadsheet copy via installEditTrigger(ss).
 */
function invokeCloudSolver(macroName) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var spreadsheetId = ss.getId();
  var userEmail = Session.getActiveUser().getEmail() || "admin@ferozmulla.altostrat.com";
  var copyLocation = getSpreadsheetLocation_(ss);

  ss.toast("Executing quantitative routine: " + macroName + " ...", "Vertex AI Solver", 5);

  var payload = {
    workbook_id: ss.getName(),
    spreadsheet_id: spreadsheetId,
    caller_google_user: userEmail,
    parity_mode: "strict_legacy_vba",
    general_overrides: {
      general_c5_n40: readRangeValuesSafe_(ss, "General", "C5:N40"),
      lt_capex_b8_j30: readRangeValuesSafe_(ss, "LT Capex", "B8:J30"),
      lt_fuel_b8_j30: readRangeValuesSafe_(ss, "LT Fuel", "B8:J30"),
      lt_cf_b8_j30: readRangeValuesSafe_(ss, "LT CF", "B8:J30")
    }
  };

  var url = getGatewayBaseUrl_() + "/v1/solve/" + encodeURIComponent(macroName);
  var response = UrlFetchApp.fetch(url, {
    method: "post",
    contentType: "application/json",
    headers: {
      Authorization: "Bearer " + ScriptApp.getIdentityToken(),
      "X-Local-Principal": userEmail,
      "X-Client-Platform": copyLocation
    },
    payload: JSON.stringify(payload),
    muteHttpExceptions: true
  });

  var statusCode = response.getResponseCode();
  if (statusCode < 200 || statusCode >= 300) {
    throw new Error("Solver Gateway returned HTTP " + statusCode + ": " + response.getContentText());
  }

  var result = JSON.parse(response.getContentText());
  var updates = result.cell_updates || [];
  for (var i = 0; i < updates.length; i++) {
    var u = updates[i];
    var targetSheet = ss.getSheetByName(u.sheet);
    if (targetSheet && u.values && u.values.length > 0) {
      targetSheet.getRange(u.range).setValues(u.values);
    }
  }

  SpreadsheetApp.flush();
  ss.toast(
    "Completed " + macroName + " (" + result.solve_count + " solves in " + Math.round(result.execution_time_ms) + " ms)",
    "Vertex AI Solver",
    4
  );

  // Self-install onEdit & onChange governance triggers on this copy (if not already installed)
  installEditTrigger(ss);

  return result;
}
```

#### 5. `apps_script/AuditHooks.gs` (Included in `apps_script/CombinedSheetScript.gs`)
```javascript
/**
 * Returns the local spreadsheet copy's title, ID, and direct Google Drive/Sheets URL
 * using only built-in SpreadsheetApp methods (requiring zero extra DriveApp OAuth scopes).
 */
function getSpreadsheetLocation_(ss) {
  var sheetObj = ss || SpreadsheetApp.getActiveSpreadsheet();
  return "Google Drive Copy (" + sheetObj.getName() + " | ID: " + sheetObj.getId() + ") | " + sheetObj.getUrl();
}

/**
 * Public function visible in the Apps Script toolbar dropdown and "Commodity Modeling" menu.
 * Installs both the installable onEdit trigger (onGovernedSheetEdit) and
 * installable onChange trigger (onGovernedSheetChange) on the central sheet
 * and any personal copy created via "File -> Make a copy" (detected via ss.getId()).
 */
function installEditTrigger(ss) {
  try {
    var sheetObj = (ss && typeof ss.getId === "function") ? ss : SpreadsheetApp.getActiveSpreadsheet();
    var currentId = sheetObj.getId();
    var props = PropertiesService.getScriptProperties();
    if (props.getProperty("GOVERNED_TRIGGERS_V2_ID") === currentId) {
      return;
    }

    var triggers = ScriptApp.getProjectTriggers();
    var hasEditTrigger = false;
    var hasChangeTrigger = false;
    for (var i = 0; i < triggers.length; i++) {
      var fn = triggers[i].getHandlerFunction();
      if (fn === "onGovernedSheetEdit") {
        hasEditTrigger = true;
      } else if (fn === "onGovernedSheetChange") {
        hasChangeTrigger = true;
      }
    }

    if (!hasEditTrigger) {
      ScriptApp.newTrigger("onGovernedSheetEdit")
        .forSpreadsheet(sheetObj)
        .onEdit()
        .create();
    }
    if (!hasChangeTrigger) {
      ScriptApp.newTrigger("onGovernedSheetChange")
        .forSpreadsheet(sheetObj)
        .onChange()
        .create();
    }
    props.setProperty("GOVERNED_TRIGGERS_V2_ID", currentId);
  } catch (err) {
    // Non-blocking so solver execution never fails if trigger creation is restricted
  }
}

/**
 * Silent onEdit governance hook: tracks formula changes (MANUAL_OVERRIDE, FORMULA_MODIFIED, FORMULA_ADDED)
 * and table header / label changes (HEADER_OR_LABEL_MODIFIED on LABEL_OR_STATIC_CELL) while ignoring
 * routine scenario input tweaks. Runs 100% silently with zero popups or cell notes.
 */
function onGovernedSheetEdit(e) {
  if (!e || !e.range) {
    return;
  }
  var sheet = e.range.getSheet();
  var ss = e.source || SpreadsheetApp.getActiveSpreadsheet();
  var cellCoord = e.range.getA1Notation();
  var formula = e.range.getFormula();
  var userEmail = Session.getActiveUser().getEmail() || "admin@ferozmulla.altostrat.com";
  var eventUtc = new Date().toISOString();
  var copyLocation = getSpreadsheetLocation_(ss);

  var payload = {
    spreadsheet_id: ss.getId(),
    workbook_name: ss.getName(),
    spreadsheet_url: ss.getUrl(),
    sheet_name: sheet.getName(),
    cell_coord: cellCoord,
    row_num: e.range.getRow(),
    col_num: e.range.getColumn(),
    old_value: e.oldValue !== undefined ? String(e.oldValue) : null,
    new_value: e.value !== undefined ? String(e.value) : null,
    new_formula: formula ? formula : null,
    who_google_user: userEmail,
    when_event_utc: eventUtc
  };

  var url = getGatewayBaseUrl_() + "/v1/ingest/edit-event";
  UrlFetchApp.fetch(url, {
    method: "post",
    contentType: "application/json",
    headers: {
      Authorization: "Bearer " + ScriptApp.getIdentityToken(),
      "X-Local-Principal": userEmail,
      "X-Client-Platform": copyLocation
    },
    payload: JSON.stringify(payload),
    muteHttpExceptions: true
  });
}

/**
 * Silent onChange governance hook: tracks spreadsheet metadata & structural mutations
 * (INSERT_ROW, REMOVE_ROW, INSERT_COLUMN, REMOVE_COLUMN, INSERT_GRID, REMOVE_GRID)
 * and streams them silently to BigQuery.
 */
function onGovernedSheetChange(e) {
  if (!e || !e.changeType) {
    return;
  }
  var trackedTypes = {
    INSERT_ROW: true,
    REMOVE_ROW: true,
    INSERT_COLUMN: true,
    REMOVE_COLUMN: true,
    INSERT_GRID: true,
    REMOVE_GRID: true
  };
  if (!trackedTypes[e.changeType]) {
    return;
  }

  var ss = e.source || SpreadsheetApp.getActiveSpreadsheet();
  var activeSheet = ss.getActiveSheet();
  var activeRange = ss.getActiveRange();
  var sheetName = activeSheet ? activeSheet.getName() : "Workbook";
  var cellCoord = activeRange ? activeRange.getA1Notation() : "A1";
  var rowNum = activeRange ? activeRange.getRow() : 1;
  var colNum = activeRange ? activeRange.getColumn() : 1;
  var userEmail = Session.getActiveUser().getEmail() || "admin@ferozmulla.altostrat.com";
  var eventUtc = new Date().toISOString();
  var copyLocation = getSpreadsheetLocation_(ss);

  var payload = {
    spreadsheet_id: ss.getId(),
    workbook_name: ss.getName(),
    spreadsheet_url: ss.getUrl(),
    sheet_name: sheetName,
    cell_coord: cellCoord,
    row_num: rowNum,
    col_num: colNum,
    old_value: null,
    new_value: e.changeType + " on " + sheetName + " (" + cellCoord + ")",
    new_formula: null,
    structural_change_type: e.changeType,
    who_google_user: userEmail,
    when_event_utc: eventUtc
  };

  var url = getGatewayBaseUrl_() + "/v1/ingest/edit-event";
  UrlFetchApp.fetch(url, {
    method: "post",
    contentType: "application/json",
    headers: {
      Authorization: "Bearer " + ScriptApp.getIdentityToken(),
      "X-Local-Principal": userEmail,
      "X-Client-Platform": copyLocation
    },
    payload: JSON.stringify(payload),
    muteHttpExceptions: true
  });
}
```

---

### 2.2 Cloud Run FastAPI Gateway Endpoints (`src/api/routes/`)

1. **`POST /v1/solve/{macro_name}` (`src/api/routes/solve.py`):**
   - Validates the caller's Google OIDC token (`verify_caller_identity`) or verified Apps Script `X-Local-Principal` header.
   - Clones the pre-warmed `WorkbookSolverContext` with any `general_overrides` and `sheet_inputs` passed from Google Sheets.
   - Dispatches to the **Vertex AI Custom Prediction Endpoint (`sheets-commodity-mod-solver-ep`)** when `enable_vertex_remote_predict=True`, or executes in-process via `MacroExecutionRegistry.execute(macro_name, context)` as an automatic zero-downtime fallback.
   - Returns `SolveMacroResponse` (`cell_updates` formatted for Google Sheets range updates). *(Note: `solver_run_telemetry` logging is parked in the V2 backlog per user direction.)*

2. **`POST /v1/bqml/solve` (`src/api/routes/solve.py`):**
   - Implements the BigQuery Remote Function protocol (`{"calls": [[macro_name, payload_json], ...]}` $\rightarrow$ `{"replies": [...]}`) so SQL queries inside BigQuery and Connected Sheets can invoke `fn_solve_lcoe` at scale.

3. **`POST /v1/ingest/edit-event` (`src/api/routes/ingest.py` & `src/ingestion/realtime_edit_handler.py`):**
   - Receives real-time `onEdit` and `onChange` payloads from `CombinedSheetScript.gs` / `AuditHooks.gs` across both the central sheet and personal copies (`File -> Make a copy`), capturing `who_google_user`, the **local spreadsheet copy name (`workbook_name` / `workbook_id`)**, and the **local copy's Google Drive URL (`spreadsheet_url` $\rightarrow$ `gcs_snapshot_uri` and `X-Client-Platform` $\rightarrow$ `who_client_platform`)**.
   - Looks up the cell's baseline/latest `semantic_role` and `canonical_formula` from the cached canonical seed baseline (`_get_seed_baseline_cell_map()` from `seed/2023-11-27-Brazil_TT_v13_RJEB.xlsm`).
   - **Category 3 (Structural / Metadata Changes via `onChange`):** Maps `INSERT_ROW`, `REMOVE_ROW`, `INSERT_COLUMN`, `REMOVE_COLUMN`, `INSERT_GRID`, and `REMOVE_GRID` to `ROW_INSERTED`, `ROW_DELETED`, `COL_INSERTED`, `COL_DELETED`, `SHEET_ADDED`, and `SHEET_DELETED` (`WARNING`) and streams to BigQuery (`audit_events`).
   - **Rule 1 (Routine Scenario Input Noise Suppression):** If `semantic_role in ('SCENARIO_INPUT_CELL', 'SOLVER_OUTPUT_CELL')` and `new_formula is None`, returns `{"status": "SUPPRESSED", "change_type": None}` (`0` audit events).
   - **Category 2 (`HEADER_OR_LABEL_MODIFIED`):** If `semantic_role == 'LABEL_OR_STATIC_CELL'` and `new_formula is None` (e.g., changing a table header in `_01_CF!B2` from `"Gas"` to `"Petrol"`), logs a `WARNING` `HEADER_OR_LABEL_MODIFIED` `AuditEventRecord` in BigQuery (`audit_events`).
   - **Category 1 (`MANUAL_OVERRIDE` / `FORMULA_MODIFIED` / `FORMULA_ADDED`):** If `semantic_role == 'FORMULA_CELL'` and `new_formula is None`, logs a `CRITICAL` `MANUAL_OVERRIDE` `AuditEventRecord` in BigQuery; if a formula is modified or added, logs `FORMULA_MODIFIED` (`WARNING`) or `FORMULA_ADDED` (`INFO`).

4. **`POST /v1/ingest/checkpoint` (`src/api/routes/ingest.py` & `src/ingestion/checkpoint_pipeline.py`):**
   - Executes the GCS-first checkpoint pipeline (`DEC-05`), automatically diffing against the canonical seed baseline (`_get_seed_baseline_graph()`) on the first checkpoint of any newly created personal copy (`File -> Make a copy`) and streaming `4-Ws` `audit_events` to BigQuery (`comm-model-mod.sheets_commodity_mod_governance.audit_events`).

---

### 2.3 BigQuery & BigQuery ML DDL for Native Connected Sheets (`sql/bigquery/`)

#### `sql/bigquery/003_bqml_forecasts_remote_fn_and_surrogate.sql`
```sql
-- 1. BigQuery ML Time-Series Forecasting Model for Long-Term Capex, Fuel & Capacity Factor Curves
-- Trained on <= 2025 Historical Actuals to forecast the 15-Year Horizon (2026..2040) matching the workbook
CREATE OR REPLACE MODEL `sheets_commodity_mod_governance.bqml_lt_trajectories_forecast_v1`
OPTIONS (
  model_type = 'ARIMA_PLUS',
  time_series_timestamp_col = 'forecast_year_date',
  time_series_data_col = 'trajectory_value',
  time_series_id_col = ['curve_family', 'technology_code'],
  auto_arima = TRUE,
  data_frequency = 'YEARLY'
) AS
SELECT
  forecast_year_date,
  curve_family,       -- 'LT_CAPEX', 'LT_FUEL', or 'LT_CF'
  technology_code,    -- 'CCGT', 'Bio_CHP', 'Bio_retro', 'Bio_WC', 'Wind', 'Solar', 'Coal_PC', 'SHP', 'Coal_CFBC', 'GDPV_RES', 'GDPV_COM'
  trajectory_value
FROM `sheets_commodity_mod_governance.historical_lt_trajectories`
WHERE EXTRACT(YEAR FROM forecast_year_date) <= 2025;

-- Connected Sheets Live View for Pivoted 2018-2040 Trajectories (Actuals <=2025 + BQML Forecast 2026-2040)
CREATE OR REPLACE VIEW `sheets_commodity_mod_governance.vw_connected_sheets_lt_forecasts` AS
WITH combined_series AS (
  SELECT
    curve_family,
    technology_code,
    EXTRACT(YEAR FROM forecast_year_date) AS yr,
    'Historical Actual (<=2025)' AS data_source,
    trajectory_value AS val
  FROM `sheets_commodity_mod_governance.historical_lt_trajectories`
  WHERE EXTRACT(YEAR FROM forecast_year_date) <= 2025

  UNION ALL

  SELECT
    curve_family,
    technology_code,
    EXTRACT(YEAR FROM forecast_timestamp) AS yr,
    'BQML ARIMA_PLUS Forecast (2026-2040)' AS data_source,
    forecast_value AS val
  FROM ML.FORECAST(
    MODEL `sheets_commodity_mod_governance.bqml_lt_trajectories_forecast_v1`,
    STRUCT(15 AS horizon, 0.95 AS confidence_level)
  )
)
SELECT
  CASE curve_family
    WHEN 'LT_CAPEX' THEN '1. LT Capex (R$/kW)'
    WHEN 'LT_FUEL'  THEN '2. LT Fuel (R$/kW)'
    WHEN 'LT_CF'    THEN '3. LT Capacity Factor (%)'
    ELSE curve_family
  END AS curve_sheet,
  yr AS Yr,
  data_source AS Data_Source,
  ROUND(MAX(IF(technology_code = 'CCGT',      val, NULL)), 2) AS CCGT,
  ROUND(MAX(IF(technology_code = 'Bio_CHP',   val, NULL)), 2) AS Bio_CHP,
  ROUND(MAX(IF(technology_code = 'Bio_retro', val, NULL)), 2) AS Bio_retro,
  ROUND(MAX(IF(technology_code = 'Bio_WC',    val, NULL)), 2) AS Bio_WC,
  ROUND(MAX(IF(technology_code = 'Wind',      IF(curve_family = 'LT_CF', val * 100.0, val), NULL)), 2) AS Wind,
  ROUND(MAX(IF(technology_code = 'Solar',     IF(curve_family = 'LT_CF', val * 100.0, val), NULL)), 2) AS Solar,
  ROUND(MAX(IF(technology_code = 'Coal_PC',   val, NULL)), 2) AS Coal_PC,
  ROUND(MAX(IF(technology_code = 'SHP',       val, NULL)), 2) AS SHP,
  ROUND(MAX(IF(technology_code = 'Coal_CFBC', val, NULL)), 2) AS Coal_CFBC,
  ROUND(MAX(IF(technology_code = 'GDPV_RES',  val, NULL)), 2) AS GDPV_RES,
  ROUND(MAX(IF(technology_code = 'GDPV_COM',  val, NULL)), 2) AS GDPV_COM
FROM combined_series
GROUP BY curve_family, yr, data_source
ORDER BY curve_sheet, Yr;

-- 2. BigQuery Remote Function invoking the Cloud Run / Vertex AI Vectorized Solver in us-central1
CREATE OR REPLACE FUNCTION `sheets_commodity_mod_governance.fn_solve_lcoe`(
  macro_name STRING,
  payload_json JSON
) RETURNS JSON
REMOTE WITH CONNECTION `us-central1.sheets-mod-vertex-conn`
OPTIONS (
  endpoint = '${CLOUD_RUN_GATEWAY_URL}/v1/bqml/solve',
  max_batching_rows = 25
);

-- 3. BigQuery ML LCOE Surrogate Model registered in Vertex AI Model Registry
CREATE OR REPLACE MODEL `sheets_commodity_mod_governance.bqml_lcoe_surrogate_v1`
OPTIONS (
  model_type = 'LINEAR_REG',
  input_label_cols = ['solved_lcoe'],
  model_registry = 'vertex_ai',
  vertex_ai_model_id = 'sheets-commodity-mod-bqml-surrogate',
  vertex_ai_model_version_aliases = ['mvp-surrogate']
) AS
SELECT
  technology_code,
  capex_multiplier,
  fuel_cost_multiplier,
  capacity_factor_multiplier,
  wacc_rate,
  economic_life_yrs,
  solved_lcoe
FROM `sheets_commodity_mod_governance.solver_training_grid`;

-- Connected Sheets Live View for BQML LCOE Surrogate Predictions vs Exact Solver
CREATE OR REPLACE VIEW `sheets_commodity_mod_governance.vw_bqml_lcoe_surrogate_predictions` AS
SELECT
  technology_code,
  capex_multiplier,
  fuel_cost_multiplier,
  capacity_factor_multiplier,
  wacc_rate,
  economic_life_yrs,
  ROUND(solved_lcoe, 4) AS exact_solver_lcoe,
  ROUND(predicted_solved_lcoe, 4) AS bqml_predicted_lcoe,
  ROUND(predicted_solved_lcoe - solved_lcoe, 4) AS residual_diff
FROM ML.PREDICT(
  MODEL `sheets_commodity_mod_governance.bqml_lcoe_surrogate_v1`,
  TABLE `sheets_commodity_mod_governance.solver_training_grid`
)
ORDER BY technology_code, capex_multiplier, fuel_cost_multiplier, capacity_factor_multiplier, wacc_rate;
```

---

## 3. Execution Order & Verification Checklist

1. **Phase 1 — Foundation & Fixture Extraction:**
   - Initialize repository structure (`pyproject.toml`, `requirements.txt`, `.env.example`, `Makefile`, `docker-compose.yml`).
   - Run `python -m src.cli.extract_baseline_fixtures` against `seed/2023-11-27-Brazil_TT_v13_RJEB.xlsm` to generate `data/fixtures/brazil_tt_v13_baseline.json` (854 cached baseline macro outputs + static tables).
2. **Phase 2 — Pillar A Quantitative Solver (`src/solver/`, `src/vertex/`, `src/bqml/`):**
   - Implement `workbook_context.py`, `cashflow_model.py`, `convergence.py` (`StrictLegacyVBAEmulator`), and all 38 routines in `src/solver/macros/`.
   - Run `pytest tests/unit/test_cashflow_and_irr.py tests/integration/test_solver_parity.py` and verify **100% pass at $\le 10^{-8}$ relative error across all 854 outputs (`TEST-A01`–`TEST-A04`)**.
3. **Phase 3 — Pillar B AST/DAG Parser, R1C1 Shift Differ & Hybrid Ingestion (`src/parser/`, `src/diff/`, `src/db/`, `src/ingestion/`):**
   - Apply `migrations/001_initial_alloydb_schema.sql` and `migrations/002_audit_immutability_trigger.sql`.
   - Implement `openxml_extractor.py`, `sheets_grid_extractor.py`, `formula_normalizer.py`, `dag_builder.py`, `semantic_classifier.py`, `shift_normalizer.py`, `structural_differ.py`, `realtime_edit_handler.py`, and `checkpoint_pipeline.py`.
   - Run `pytest tests/unit/test_parser_and_normalizer.py tests/integration/test_ast_dag_and_audit.py` (`TEST-B01`–`TEST-B07`).
4. **Phase 4 — Google Sheets Seeding, Apps Script, BigQuery ML & E2E Analyst Journey (`apps_script/`, `scripts/`, `tests/e2e/`):**
   - Run `pytest tests/e2e/test_google_sheets_analyst_journey.py` (`TEST-E2E-01`) and `pytest tests/infra/test_terraform_governance.py` (`TEST-INFRA-01`–`06`).
   - In GCP environment (`comm-model-mod`, `us-central1`): run `make tf-apply`, `python scripts/seed_google_sheet_from_xlsm.py --project-id comm-model-mod`, `python scripts/configure_general_buttons.py`, and `python scripts/deploy_bqml_and_vertex.py` to provision the central Google Sheet, 3D cell buttons, and live BigQuery ML Connected Sheets tabs (`LT_Capex_BQML`, `LT_Fuel_BQML`, `LT_CF_BQML`, `BQML_LCOE_Surrogate`, and `BQ_4Ws_Audit_Log`).

