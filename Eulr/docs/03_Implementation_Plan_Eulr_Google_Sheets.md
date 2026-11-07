# Phased Implementation Plan & Verification Runbook: `Eulr202409.xlsx` on Google Sheets & Google Cloud

| Metadata | Details |
| :--- | :--- |
| **Document Version** | 2.0 (Validated Serverless & 3D In-Sheet UX Track — `comm-model-mod` / `us-central1`) |
| **Target Pilot Workbook** | `Eulr/seed/Eulr202409.xlsx` (`20` Sheets, `604,453` `<c>` Cells, `357,708` Formulas $\rightarrow$ `8,028` Vectorized Row Equations, `iterateCount=10`) |
| **Companion Documents** | [`01_PRD_Eulr_Google_Sheets.md`](./01_PRD_Eulr_Google_Sheets.md), [`02_Design_Document_Eulr_Google_Sheets.md`](./02_Design_Document_Eulr_Google_Sheets.md), [`04_Antigravity_Handoff_Context_Eulr.md`](./04_Antigravity_Handoff_Context_Eulr.md), [`06_Pilot_Workbooks_Demo_Scripts_Google_Sheets.md`](./06_Pilot_Workbooks_Demo_Scripts_Google_Sheets.md) |
| **Target GCP Resources** | Project: `comm-model-mod` (`us-central1`, `app = "eulr-sheets-mod"`) \| Cloud Run: `eulr-equilibrium-gateway` \| BigQuery: `eulr_commodity_mod_governance` \| GCS: `gs://comm-model-mod-eulr-snapshots` \| Vertex AI: `gemini-3.8-flash` + Model Registry (`eulr-sheets-mod-margin-surrogate`) |

---

## 1. Guiding Engineering Principles for the `Eulr202409.xlsx` Build

1. **SharePoint-Portable Upstream Link Registry (`UPSTREAM_SOURCE_MODE`) & Zero `shooju_addin` Dependency:**
   All `14,162` external formula cells across the `13` active upstream workbooks (`NWEDF202409.xlsx`, `Uslr202409.xlsx`, `MedDF202409.xlsx`, `Felr202409.xlsx`, `Tankerlr202409.xlsx`, etc.) carry valid cached `<v>` values inside `Eulr202409.xlsx`. Phase 1 extracts 100% of these cached values along with their full SharePoint URL, workbook, sheet, and cell coordinates into `eulr_commodity_mod_governance.upstream_external_series` (supporting `eulr_baseline_cached` for exact $\le 10^{-8}$ parity, `peer_xlsx` for live ingestion of the `1,104` updated cells in `Uslr202409.xlsx`, `Felr202409.xlsx`, and `Tankerlr202409.xlsx`, and `sharepoint_graph` for S&P tenant deployment).
2. **AOT-Compiled `8,028` Row-Level Vectorized Equations (`< 150 ms` for 10 Passes):**
   Instead of evaluating `357,708` individual cells one by one, Phase 2 groups formulas by their normalized `R1C1` row signature (`8,028` unique row patterns + `6,745` `{=CSE}` array formulas) and compiles them into vectorized NumPy operations that evaluate across all time columns (`1982–2050+`) while preserving exact cross-sheet column offsets (`Carbon` aligns `2024` at Column `P` vs. Column `AT` on `KeyInputs` and `NWE Cif`).
3. **Exact 10-Pass Gauss-Seidel Circular Convergence (`iterateCount=10` Across 13 Coupled Sheets):**
   Phase 2 implements the verified 10-pass sheet-order fixed-point loop—evaluating `ULSD-GO_spread_econs` **inside** each pass right before `KeyInputs`:
   `Input -> Freight -> Crudes -> ULSD-GO_spread_econs -> KeyInputs -> Op_Cost -> Carbon -> NWE Cif -> MED Cif -> NWE Fob -> MED Fob -> IMOfuels -> Links out`
   and verifies $\le 10^{-8}$ numerical parity against the cached `<v>` values in `Eulr202409.xlsx`.
4. **24-Tab Hybrid Google Sheets Workbench, 3D `OverGridImage` Deck & 100% Serverless Governance:**
   - Keeps acyclic, non-external formulas (`KeyInputs`, `Yields`, `Info`, `Checks`) live and inspectable in Google Sheets while updating circular pricing tabs via compact delta `Sheets.Values.batchUpdate` (`< 2.0s` round-trip).
   - Places the 5-button **3D `OverGridImage` Execution Deck** at `KeyInputs!B2:N5` and 1-click 3D `Refresh BQML` buttons on `Macro_BQML`, `Crudes_BQML`, and `Freight_BQML`.
   - Eliminates always-on AlloyDB/Cloud SQL instances: active `#FEF3C7` Pinned Trader Price Overrides are stored per `spreadsheet_id` in Cloud Storage (`gs://comm-model-mod-eulr-snapshots/overrides/{spreadsheet_id}.json`), while immutable `4-Ws` audit and override history stream to BigQuery (`audit_events`, `cell_overrides_history`) enriched by Vertex AI `gemini-3.8-flash`.

---

## 2. Target Project Directory Layout (`Eulr/`)

```text
Eulr/
├── .env.example
├── Dockerfile.gateway               # Cloud Run image for eulr-equilibrium-gateway
├── Dockerfile.vertex_solver         # Optional Vertex AI Custom Prediction container
├── Makefile                         # lint, test, extract, deploy, push-sheets targets
├── pyproject.toml                   # Python 3.11+, FastAPI, NumPy, Pydantic, Ruff, Pytest
├── requirements.txt
├── seed/
│   └── Eulr202409.xlsx              # Read-only baseline workbook (9.16 MB, 20 sheets)
├── references/                      # Read-only peer workbooks (Uslr, Felr, Tankerlr, etc.)
├── infra/
│   ├── main.tf                      # GCP provider,GCS bucket, BigQuery dataset & tables, Cloud Run, IAM
│   ├── variables.tf                 # project_id="comm-model-mod", region="us-central1", app="eulr-sheets-mod"
│   └── outputs.tf
├── sql/
│   ├── 01_governance_tables_and_views.sql
│   └── 02_bqml_models.sql           # ARIMA_PLUS driver models + crack-spread surrogate
├── src/
│   ├── __init__.py
│   ├── core/
│   │   └── config.py                # Environment settings, GCP resource names, UPSTREAM_SOURCE_MODE
│   ├── schemas/
│   │   └── models.py                # Pydantic request/response schemas for solver, audit, and BQML
│   ├── parser/
│   │   ├── openxml_extractor.py     # Streaming iterparse extractor for 20 sheets, 604,453 cells & 14,162 external links
│   │   ├── r1c1_catalog.py          # Normalizes 357,708 formulas into 8,028 R1C1 row equations & classifies cells
│   │   └── upstream_link_hub.py     # 3-tier external link classifier + eulr_baseline_cached / peer_xlsx / sharepoint_graph sync
│   ├── solver/
│   │   ├── cse_rewriter.py          # Vectorized NumPy helpers for 6,740 Op_Cost {=CSE} & 5 IRR formulas
│   │   ├── equilibrium_engine.py    # 10-pass Gauss-Seidel solver across 13 circular sheets + #FEF3C7 Pinned Override mask
│   │   ├── scenario_matrix.py       # Parallel 4-way (Base/Sens x EU ETS Carbon Off/On) sweep + Checks validator
│   │   └── upload_publisher.py      # Unpivots 1,273 UPLOAD series & 234 Links out series for BigQuery
│   ├── diff/
│   │   └── ast_differ.py            # R1C1 coordinate-shift normalizer & semantic 4-Ws event classifier
│   ├── bqml/
│   │   └── forecaster.py            # ARIMA_PLUS trajectories (Macro_BQML, Crudes_BQML, Freight_BQML) & crack-spread surrogate
│   ├── vertex/
│   │   └── explainer.py             # Vertex AI gemini-3.8-flash margin attribution & 4-Ws why_ai_summary generator
│   ├── storage/
│   │   └── repository.py            # Dual-mode (GCS/BigQuery + local SQLite/JSON offline) persistence for snapshots & overrides
│   └── api/
│       └── main.py                  # FastAPI gateway (/v1/eulr/solve, /v1/eulr/scenario-matrix, /v1/eulr/sync-upstream, /v1/eulr/override/revert, /v1/eulr/publish, /v1/ingest/edit-event, /healthz)
├── apps_script/
│   ├── appsscript.json              # V8 runtime manifest & OAuth scopes
│   └── CombinedSheetScript.gs       # Menu, 3D button handlers, delta batchUpdate client & silent onGovernedSheetEdit/Change
├── scripts/
│   └── push_sheets_live.py          # Builds & populates the 24-tab Google Sheet + 3D OverGridImage buttons + Connected Sheets
└── tests/
    ├── test_parser_and_links.py     # TEST-B01 (OpenXML/R1C1 extraction) & TEST-A05 (14,162 links + 1,104 peer xlsx deltas)
    ├── test_equilibrium_solver.py   # TEST-A01 (<= 1e-8 parity), TEST-A02 (10-pass convergence), TEST-A03 (ULSD-GO coupling), TEST-A04 (#FEF3C7 overrides)
    ├── test_audit_and_bqml.py       # TEST-A06 (BQML & surrogate), TEST-B02..B08 (4-Ws audit, R1C1 shift immunity, 3-tier rollback)
    ├── test_api_gateway.py          # TEST-E2E-01 (FastAPI endpoints & payload contracts)
    └── test_infra_compliance.py     # TEST-INFRA-01..06 (Terraform labels, serverless isolation, zero hardcoded secrets)
```

---

## 3. Step-by-Step Implementation Phases (`Phases 1–5`)

### Phase 1: Project Scaffolding, Streaming OpenXML Extractor & SharePoint-Portable Upstream Link Hub
**Objective:** Scaffold `Eulr/` and extract all `20` worksheets (`604,453` `<c>` cells, `357,708` formulas $\rightarrow$ `8,028` R1C1 row patterns) and `14,162` external link cells from `Eulr202409.xlsx`.
1. Create `Eulr/pyproject.toml`, `Eulr/Makefile`, `Eulr/requirements.txt`, and link `Eulr/seed/Eulr202409.xlsx` and `Eulr/references/*.xlsx`.
2. Implement `src/parser/openxml_extractor.py` and `src/parser/r1c1_catalog.py`:
   - Use streaming `xml.etree.ElementTree.iterparse` to extract values, formulas, shared-formula masters/slaves, `{=CSE}` array bounds, and defined names (`2,303` total, pruning/flagging the `281` legacy `#REF!` names and retiring `shooju_addin`).
   - Compress `357,708` formulas into `8,028` row-level R1C1 patterns and classify cells (`LIVE_SHEET_FORMULA`, `EQUILIBRIUM_SOLVED`, `UPSTREAM_EXTERNAL_LINK`, `SCENARIO_SWITCH`, `STATIC_METADATA`).
3. Implement `src/parser/upstream_link_hub.py`:
   - Map all `14,162` external formula cells (`[14]`–`[26]`) with full `(sharepoint_url, external_workbook_name, source_sheet, source_cell_a1, vintage_tag='202409', link_health_tier)` provenance.
   - Support `eulr_baseline_cached` (`100%` cached `<v>` seed for exact parity) and `peer_xlsx` (live extraction of the `971` updated cells from `Uslr202409.xlsx`, `106` from `Felr202409.xlsx`, and `27` from `Tankerlr202409.xlsx`).
4. **Verification Gate:** Pass `pytest tests/test_parser_and_links.py` (`TEST-B01`, `TEST-A05`).

### Phase 2: Vectorized 10-Pass Gauss-Seidel Equilibrium Engine, `{=CSE}` Rewriter & `#FEF3C7` Pinned Overrides
**Objective:** Implement the 10-pass circular equilibrium solver in `src/solver/` and verify $\le 10^{-8}$ numerical parity against `Eulr202409.xlsx`.
1. Implement `src/solver/cse_rewriter.py`:
   - Vectorize the `6,740` `{=CSE}` forward-interpolation formulas on `Op_Cost` and `5` `IRR` formulas on `2015 NWE HCK IRR`.
   - Isolate the `280` pre-1990 error sentinels (`#DIV/0!`, `#REF!`, `#VALUE!`, `#N/A`) using IEEE-754 `NaN` + error masks so `1990–2050+` columns evaluate cleanly.
2. Implement `src/solver/equilibrium_engine.py`:
   - Execute pre-loop acyclic sheets (`Info`, `Yields`), followed by **10 Gauss-Seidel passes** over the `13` circularly coupled sheets in exact order:
     `Input -> Freight -> Crudes -> ULSD-GO_spread_econs -> KeyInputs -> Op_Cost -> Carbon -> NWE Cif -> MED Cif -> NWE Fob -> MED Fob -> IMOfuels -> Links out`
     and post-loop sheets (`HCK naphtha revamp`, `2015 NWE HCK IRR`, `Checks`, `UPLOAD`).
   - Re-assert per-spreadsheet `#FEF3C7` **Pinned Trader Price Overrides** (`override_mask`) immediately after each sheet evaluation inside each pass, and support 1-click reversion to $\le 10^{-12}$ of baseline.
3. Implement `src/solver/scenario_matrix.py` and `src/solver/upload_publisher.py`:
   - Parallel 4-way (`Base/Sensitivity` $\times$ `EU ETS Carbon Off/On`) sweep, `180`-row `Checks` arbitrage diagnostics, and unpivoted `UPLOAD` (`1,273` series) / `Links out` (`234` series) staging.
4. **Verification Gate:** Pass `pytest tests/test_equilibrium_solver.py` (`TEST-A01` $\le 10^{-8}$ parity, `TEST-A02` 10-pass convergence, `TEST-A03` `ULSD-GO_spread_econs` bidirectional coupling, `TEST-A04` Pinned Override propagation & reversion).

### Phase 3: Silent Distributed `4-Ws` Governance, R1C1 Row-Shift Normalizer, BQML Forecaster & `gemini-3.8-flash` Explainer
**Objective:** Implement AST/R1C1 diffing, 3-tier rollback persistence, BQML `ARIMA_PLUS` driver trajectories, and Vertex AI `gemini-3.8-flash` attribution.
1. Implement `src/diff/ast_differ.py` and `src/storage/repository.py`:
   - Normalize formulas into R1C1 before diffing so row/column insertions emit a single structural event (`ROW_INSERTED` / `ROW_DELETED`) with zero false-positive formula alerts on shifted rows.
   - Classify `PINNED_PRICE_OVERRIDE`, `MANUAL_OVERRIDE`, `HEADER_OR_LABEL_MODIFIED`, `STRUCTURAL_CHANGE`, and `SOLVER_RUN` while suppressing routine switch toggles and convergence output updates.
   - Persist per-spreadsheet override masks (`overrides/{spreadsheet_id}.json` in GCS / local fallback) and `4-Ws` audit history (`audit_events`, `cell_overrides_history`).
2. Implement `src/bqml/forecaster.py` and `src/vertex/explainer.py`:
   - Generate `1990–2050` trajectories (`<= 2024` actuals + `2025–2050` `ARIMA_PLUS` forecast with confidence intervals) for `Macro_BQML`, `Crudes_BQML`, and `Freight_BQML`, plus the NWE/MED crack-spread surrogate (`eulr-sheets-mod-margin-surrogate`).
   - Generate `gemini-3.8-flash` executive margin attribution narratives and `why_ai_summary` audit explanations with deterministic fallback when offline.
3. **Verification Gate:** Pass `pytest tests/test_audit_and_bqml.py` (`TEST-A06`, `TEST-B02`..`TEST-B08`).

### Phase 4: FastAPI Cloud Run Gateway (`eulr-equilibrium-gateway`) & Bound Apps Script (`CombinedSheetScript.gs`)
**Objective:** Expose the REST API endpoints and build the Google Sheets V8 client with the 5-button 3D `OverGridImage` Execution Deck.
1. Implement `src/api/main.py`:
   - `POST /v1/eulr/solve`: Runs the 10-pass equilibrium solver with live sheet switches (`KeyInputs`, `Carbon!A5:A6`, `Yields`) and `spreadsheet_id` override mask; returns compact delta A1 ranges.
   - `POST /v1/eulr/scenario-matrix`: Runs the 4-way (`Base/Sens` $\times$ `Carbon Off/On`) sweep and returns `Scenario_Comparison` grid + `gemini-3.8-flash` narrative.
   - `POST /v1/eulr/sync-upstream`: Switches between `eulr_baseline_cached` and `peer_xlsx` (`Uslr`, `Felr`, `Tankerlr`), returning updated link counts and re-converged deltas.
   - `POST /v1/eulr/override/revert`: Clears `overrides/{spreadsheet_id}.json` (or specific cell) and returns restored baseline values.
   - `POST /v1/eulr/publish`: Publishes `1,273` `UPLOAD` series and `234` `Links out` series to BigQuery.
   - `POST /v1/eulr/bqml/refresh`: Returns refreshed `Macro_BQML`, `Crudes_BQML`, or `Freight_BQML` matrices.
   - `POST /v1/ingest/edit-event`: Silent `4-Ws` edit/override ingestion and surgical rollback lookup.
   - `GET /healthz`: Readiness and baseline graph checksum probe.
2. Implement `apps_script/CombinedSheetScript.gs` and `scripts/push_sheets_live.py`:
   - 5-button 3D `OverGridImage` deck at `KeyInputs!B2:N5` + 3D `Refresh BQML` buttons on `Macro_BQML`, `Crudes_BQML`, and `Freight_BQML`.
   - Silent `onGovernedSheetEdit` applying `#FEF3C7` amber background on pricing sheets with zero popups/notes.
3. **Verification Gate:** Pass `pytest tests/test_api_gateway.py` (`TEST-E2E-01`).

### Phase 5: Terraform IaC (`comm-model-mod` / `us-central1`), Cloud Run Deployment & 24-Tab Google Sheets Live Push
**Objective:** Validate Terraform compliance, deploy `eulr-equilibrium-gateway` to Cloud Run, provision BigQuery tables/models in `eulr_commodity_mod_governance`, and push the live 24-tab Google Sheet.
1. Author `infra/main.tf`, `infra/variables.tf`, `infra/outputs.tf`, and `sql/*.sql` with mandatory labels (`env = "dev"`, `app = "eulr-sheets-mod"`, `owner = "quant-platform"`, `cost-center = "commodities-r-and-d"`).
2. Pass `pytest tests/test_infra_compliance.py` (`TEST-INFRA-01`..`06`) and `ruff check .`.
3. Deploy `eulr-equilibrium-gateway` to Cloud Run (`comm-model-mod` / `us-central1`), seed `eulr_commodity_mod_governance` and `gs://comm-model-mod-eulr-snapshots`, and execute `scripts/push_sheets_live.py` to populate the 24-tab Google Sheet.

---

## 4. Verification & Acceptance Runbook

```bash
# 1. Run full automated test suite (OpenXML/R1C1 extraction, 10-pass <= 1e-8 parity, peer xlsx sync, #FEF3C7 overrides, 4-Ws audit, FastAPI, Terraform compliance)
cd Eulr && pytest -v

# 2. Run linter and formatting check
cd Eulr && ruff check .
```

| Verification Check | Target Acceptance Threshold |
| :--- | :--- |
| **External Link Seed Completeness (`14,162` cells)** | `100.0%` of active external link cells populated with valid numeric values and SharePoint coordinates (`1,104` live peer updates detected across `Uslr`, `Felr`, `Tankerlr`) |
| **10-Pass Equilibrium Numerical Parity (`357,708` cells)** | Max relative error $\le 10^{-8}$ across all `19` active sheets (`1990–2050+` columns) against `Eulr202409.xlsx` cached `<v>` values |
| **Cloud Run 10-Pass Compute Latency** | `< 250 ms` (p95) for 10 full Gauss-Seidel passes across all `8,028` vectorized row equations |
| **Google Sheets End-to-End Round-Trip Latency** | `< 2.0 seconds` from clicking *"Solve 10-Pass Equilibrium"* (`KeyInputs!B4`) to delta `Sheets.Values.batchUpdate` completion |
| **Pinned Override Restoration Accuracy** | Reverting a `#FEF3C7` pinned override (`NWE Cif!AU122`) restores the exact baseline equilibrium across all coupled sheets to within $\le 10^{-12}$ |
