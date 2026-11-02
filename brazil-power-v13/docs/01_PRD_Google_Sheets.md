# Product Requirements Document (PRD): Enterprise Commodity Modeling — Google Sheets Modernization & Structural Governance Platform

| Document Metadata | Details |
| :--- | :--- |
| **Document ID** | `ENT-PRD-SHEETS-MOD-001` |
| **Version** | `1.0.0 (Google Sheets Native Architecture — Approved for Engineering Execution)` |
| **Status** | `APPROVED FOR ENGINEERING EXECUTION` |
| **Date** | October 29, 2026 |
| **Authors** | Principal Google Cloud Architect & Staff Quantitative Systems Engineer |
| **Target GCP Project & Region** | Parameterized via `var.project_id` / `GCP_PROJECT_ID` (Default Project: `comm-model-mod`, Region: `us-central1`, Zone: `us-central1-a`, BigQuery Location: `us-central1`) |
| **Universal GCP Resource Label** | `app = "sheets-commodity-mod"`, `project = "enterprise-commodity-modernization"`, `env = "mvp"`, `managed-by = "terraform"` |
| **Primary Frontend Layer** | **Google Sheets** + **Google Apps Script (`V8` Runtime)** + **Native Connected Sheets for BigQuery** |
| **Pilot Model Seed Baseline** | Regional Power Generation Techno-Economic Model (`2023-11-27-Brazil_TT_v13_RJEB.xlsm` — used strictly as the one-time seed source to populate the Golden Google Sheet and verify $\le 10^{-8}$ mathematical parity) |

---

## 1. Executive Summary & Vision

Enterprise Quantitative Commodity Research teams rely on complex, multi-sheet techno-economic financial models to produce long-term Levelized Cost of Electricity (LCOE) forecasts, dispatchable thermal generation curves, and multi-parameter sensitivity tables across power generation technologies. Historically, these models were trapped in single-user desktop files with iterative solver loops and zero automated structural auditability.

This Product Requirements Document (PRD) defines the end-to-end architecture, functional requirements, non-functional SLAs, and verification criteria for the **Enterprise Commodity Modeling — Google Sheets Modernization & Structural Governance Platform**, built natively on the **Google Workspace + Google Cloud Platform (GCP)** stack.

The platform uses **Google Sheets** as its lightweight, collaborative cloud-native frontend while delegating heavy mathematical optimization, machine learning forecasting, and structural governance to managed Google Cloud services across two tightly integrated pillars:

1. **Pillar A — Cloud-Native Quantitative Solver, Vertex AI & Native Connected Sheets for BigQuery:**
   - Replaces slow, single-threaded iterative solver loops across **12 power generation technology cash-flow sheets (`_01_CF` through `_12_CF`)** with a vectorized **Python (NumPy/SciPy)** numerical solver hosted on **Vertex AI / Gemini Agent Platform Custom Prediction Endpoints** and orchestrated via a **Cloud Run Solver & Governance Gateway**.
   - Preserves all **31 interactive macro button actions** on the `General` control sheet (`B42:N52` rendered as permanent styled native cells with 3D `OverGridImage` click overlays) and a custom `"Commodity Modeling"` menu in Google Sheets via **Google Apps Script (`UrlFetchApp` + `ScriptApp.getIdentityToken()`)**, executing single-sheet sensitivity sweeps in **$\le 800\text{ ms}$ (p95)** and the full 184-solve, 23-year, 8-technology LCOE forecast (`lcoe_exec`) in **$\le 2.0\text{ seconds}$ (p95)** at **$\le 10^{-8}$ relative numerical parity** against the legacy mathematical baseline.
   - Leverages **Native Connected Sheets for BigQuery** so analysts can refresh three dedicated, workbook-styled **BigQuery ML (`ML.FORECAST` with `ARIMA_PLUS`)** long-term trajectory sheets (**`LT_Capex_BQML`**, **`LT_Fuel_BQML`**, and **`LT_CF_BQML`**, combining `<=2025` historical actuals with `2026–2040` ML forecasts via a hidden `BQML_LT_Forecasts` `DataSourceTable` Extract and 1-click `Refresh BQML` buttons), invoke the **BigQuery ML Remote Function (`fn_solve_lcoe`)**, inspect the **BigQuery ML LCOE Surrogate Model (`BQML_LCOE_Surrogate` / `bqml_lcoe_surrogate_v1`)**, and review live governance dashboards (**`BQ_4Ws_Audit_Log`**) directly inside Google Sheets with zero manual CSV exports.

2. **Pillar B — Distributed Copy Governance, Self-Activating Silent `onEdit` & `onChange` Hooks, and Serverless BigQuery "4 Ws" Audit Log:**
   - Supports the real-world **Distributed Analyst Copy Workflow (`File -> Make a copy`)**, where Quantitative Analysts create personal copies of the central governed Google Sheet in their own Google Drive folders to run scenarios independently:
     - **Self-Activating Silent `onEdit` & `onChange` Triggers:** Because Google Drive strips installable triggers when a user clicks `File -> Make a copy`, the bound Apps Script (`invokeCloudSolver`) automatically self-installs both `onGovernedSheetEdit` (`onEdit`) and `onGovernedSheetChange` (`onChange`) triggers on any newly copied sheet the first time the analyst clicks any of the 31 solver buttons. All logging is **100% silent** (no popups, toasts, or cell notes interrupting the analyst).
     - **Three Governed Change Categories Streamed to BigQuery (`audit_events`):**
       1. **Formula Changes (`onEdit`):** Overwriting a `FORMULA_CELL` with a literal (`MANUAL_OVERRIDE`), modifying a formula (`FORMULA_MODIFIED`), or adding a new formula (`FORMULA_ADDED`).
       2. **Table Header & Label Changes (`onEdit`):** Modifying any `LABEL_OR_STATIC_CELL` text cell (e.g., changing a table header in `_01_CF!B2:H2` from `"Gas"` to `"Gasoline"` -> `HEADER_OR_LABEL_MODIFIED`), while ignoring routine numeric edits to `SCENARIO_INPUT_CELL`.
       3. **Spreadsheet Metadata & Structural Changes (`onChange`):** Inserting or deleting rows (`ROW_INSERTED`, `ROW_DELETED`), inserting or deleting columns (`COL_INSERTED`, `COL_DELETED`), and adding or deleting worksheets (`SHEET_ADDED`, `SHEET_DELETED`).
   - Persists an append-only **"4 Ws" Audit Log** (*What Element, What Change, Who & Which Local Spreadsheet Copy Name/URL, When*) in **BigQuery** (`sheets_commodity_mod_governance.audit_events`), directly queryable in Google Sheets via **Connected Sheets**.

---

## 2. Pilot Model Anatomical Baseline (Regional Power Generation Techno-Economic Model)

To guarantee 100% mathematical fidelity and structural completeness, the Google Sheets application is seeded directly from the authoritative **Regional Power Generation Techno-Economic Model** baseline (`2023-11-27-Brazil_TT_v13_RJEB.xlsm`, imported into Google Sheets via `scripts/seed_google_sheet_from_xlsm.py`). Every requirement in this PRD is anchored to the exact empirical inventory of that 22-sheet model:

### 2.1 Worksheet & Cell Inventory (`22` Visible Worksheets, `35,655` Populated Cells, `15,961` Baseline Formulas)

| Sheet Index | Sheet Name | Category / Role | Populated Cells | Baseline Formula Cells | Key Ranges & Functional Purpose |
| :-: | :--- | :--- | :-: | :-: | :--- |
| 1 | `Version Control` | Metadata | 92 | 0 | Manual change log table (`B4:E30`) recording historical author revisions |
| 2 | `General` | Master Control & Parameters | 3,100 | 62 | Master plant techno-economic table (`C5:N40`) for 12 technologies + **31 Interactive Solver Buttons** anchored in `B42:N52` |
| 3 | `Output_1` | Comparative Dashboard | 2,635 | 891 | Cross-technology LCOE, Capex, Efficiency, and Capacity Factor comparison tables |
| 4 | `Output_2` | Sensitivity Dashboard | 1,543 | 150 | Consolidated Tornado & 1D/2D sensitivity chart source tables |
| 5 | `Output_3` | 23-Year LCOE Forecast | 747 | 12 | Master 23-year LCOE trajectory table (`B9:J31`, years `2018`–`2040`) populated by `lcoe_exec` + run timestamp in `B3` |
| 6 | `_01_CF` | Utility Thermal Cash Flow | 2,756 | 1,264 | **Natural Gas Combined Cycle (CCGT — 500 MW)** 45-year discounted cash flow (`B20:AT63`), Tornado (`B6:G12`), CVU sweep (`B70:C79`), Thermal ICB (`row 81`) |
| 7 | `_02_CF` | Utility Renewable Cash Flow | 2,908 | 1,286 | **Biomass Sugarcane Bagasse Boiler (55 MW)** 45-year DCF + 2D BI LCOE matrix (`E70:N79`) |
| 8 | `_03_CF` | Utility Renewable Cash Flow | 2,520 | 1,208 | **Biomass Boiler Retrofit (55 MW)** 45-year DCF + Tornado (`E6:G12`) + CVU (`C70:C79`) |
| 9 | `_04_CF` | Utility Renewable Cash Flow | 2,899 | 1,285 | **Onshore Wind Turbine Class 6 (30 MW)** 45-year DCF + 2D BI LCOE matrix (`E70:N79`) |
| 10 | `_05_CF` | Utility Renewable Cash Flow | 3,164 | 1,357 | **Utility-Scale Solar PV (30 MW)** 45-year DCF + Capex vs CF (`G84:G93`) + 2D BI LCOE (`C99:L108`) + 12-yr Forecast (`U71:U82`) |
| 11 | `_06_CF` | Utility Renewable Cash Flow | 3,023 | 1,283 | **Small Hydro Power Plant — SHP (30 MW)** 45-year DCF + Price vs IRR (`B88:F97`) + 2D BI LCOE (`C105:L114`) |
| 12 | `_07_CF` | Utility Thermal Cash Flow | 2,553 | 1,213 | **Local Coal Circulating Fluidized Bed — CFBC (400 MW)** 45-year DCF + Thermal ICB (`row 81`) |
| 13 | `_08_CF` | Utility Thermal Cash Flow | 2,869 | 1,397 | **Imported Coal Pulverized — PC (400 MW)** 45-year DCF + Thermal ICB (`row 105`) |
| 14 | `_09_CF` | Utility Thermal Cash Flow | 2,606 | 1,264 | **Biomass Woodchip Fired Plant (50 MW)** 45-year DCF + Thermal ICB (`row 81`) |
| 15 | `_10_CF` | Utility Thermal Cash Flow | 2,519 | 1,208 | **LNG Combined Cycle — CCGT (500 MW)** 45-year DCF + Tornado (`E6:G12`) + CVU (`C70:C79`) |
| 16 | `_11_CF` | Distributed Gen Cash Flow | 1,111 | 589 | **Residential Solar PV Distributed Generation (5 kW)** 26-year net-metering cash flow (`B20:AA32`), 4-param Tornado (`E6:G9`) |
| 17 | `_12_CF` | Distributed Gen Cash Flow | 1,105 | 589 | **Commercial Solar PV Distributed Generation (50 kW)** 26-year net-metering cash flow (`B20:AA32`), 4-param Tornado (`E6:G9`) |
| 18 | `_CAPEX 01` | Supporting Engineering Table | 785 | 408 | Bottom-up EPC, equipment, civil works, and balance-of-plant Capex breakdown |
| 19 | `CVU_GF` | Thermal Dispatch Lookup | 1,159 | 56 | Variable Unit Cost (`CVU`) vs. Physical Guarantee (`Garantia Física - GF`) quadratic regression curves and `fator k` parameters |
| 20 | `LT Capex` | Long-Term Time-Series Input | 329 | 265 | 23-year technology Capex learning curves (`rows 8–30`, years `2018–2040`) — enhanced with **Connected Sheets for BigQuery ML (`ML.FORECAST`)** |
| 21 | `LT Fuel` | Long-Term Time-Series Input | 329 | 34 | 23-year fuel price trajectories (`rows 8–30`, years `2018–2040`) — enhanced with **Connected Sheets for BigQuery ML (`ML.FORECAST`)** |
| 22 | `LT CF` | Long-Term Time-Series Input | 303 | 7 | 23-year capacity factor trajectories (`rows 8–30`, years `2018–2040`) — enhanced with **Connected Sheets for BigQuery ML (`ML.FORECAST`)** |

*Note on Formula Representation:* In raw OpenXML (`xl/worksheets/sheet*.xml`), the baseline workbook contains `17,354` `<f>` tags (`15,961` active calculated formulas + `1,393` shared/array/ghost tags, including `10,654` shared formula cells across `430` `si` groups). When seeded into Google Sheets, all shared formulas are materialized as canonical cell formulas across all 22 tabs, and our ingestion engine supports both native Google Sheets JSON Grid exports and `.xlsx`/`.xlsm` OpenXML archives.

### 2.2 Complete Inventory of the 31 Interactive Solver Buttons (`General!B42:N52`) & 38 Ported Routines

All **31 interactive buttons** on `General` (plus the custom `"Commodity Modeling"` menu in Google Sheets) invoke the Cloud Run Solver Gateway (`POST /v1/solve/{macro_name}`). In addition, `Module2.lcoe_forecast`, `Module1.fator_i`, `rst_scenario`, and the 4 internal convergence routines are ported, totaling **38 active routines** (while cataloging the 3 broken legacy artifacts as technical debt):

1. **Master Multi-Year LCOE Trajectory (`lcoe_exec` — Button `General!B43` `"Forecast LCOE"`):**
   - Iterates across **23 forecast years (`count_yr = 1..23`, rows `8..30` of `LT Capex`, `LT Fuel`, `LT CF`)** and **8 technologies** in exact sequence:
     1. `_01_CF` (Gas CCGT, `price_frst = 500`, writes to `Output_3` Col `B`)
     2. `_02_CF` (Biomass Bagasse, `price_frst = 400`, writes to `Output_3` Col `C`)
     3. `_09_CF` (Biomass Woodchip, `price_frst = 500`, writes to `Output_3` Col `E`)
     4. `_04_CF` (Onshore Wind, `price_frst = 250`, writes to `Output_3` Col `F`)
     5. `_05_CF` (Solar PV, `price_frst = 350`, writes to `Output_3` Col `G`)
     6. `_08_CF` (Imported Coal, `price_frst = 500`, writes to `Output_3` Col `H`)
     7. `_06_CF` (Small Hydro SHP, `price_frst = 250`, writes to `Output_3` Col `I`)
     8. `_07_CF` (Local Coal, `price_frst = 500`, writes to `Output_3` Col `J`)
   - Total = **184 two-stage solves** (`iter_conv` to `8.0001%` IRR $\rightarrow$ `iter_refining` with `0.001` step to `12.00%` IRR $\pm 10^{-5}$).
   - **Thermal vs. Renewable Output Distinction (`FR-A04`):** For thermal dispatchable technologies (`_01_CF`, `_09_CF`, `_07_CF` at row `81`; `_08_CF` at row `105`), writes solved `price_lst` (`B16`) into `C81` (or `C105`), evaluates quadratic Physical Guarantee (`GF`) and `fator k`, and writes the resulting Cost-Benefit Index **`icb` (`I81` or `I105`)** into `Output_3`. For renewable technologies (`_02_CF`, `_04_CF`, `_05_CF`, `_06_CF`), writes `price_lst` (`B16`) directly into `Output_3`. Writes execution timestamp to `Output_3!B3`.

2. **12 Tornado Sensitivity Macros (`calcule_tir1` through `calcule_tir12` — Buttons `General!C42:N42`):**
   - **`calcule_tir1`..`calcule_tir10` (`_01_CF`..`_10_CF`):** 7 parameters (`rows 6..12`) $\times$ 3 columns (`B..D`: Low, Base, High) = **21 solves per macro**. Calls `rst_scenario` (`H6:H12 <- C6:C12`) before each solve, mutates `H[row]`, runs `iter_conv` (`8.0001%`) $\rightarrow$ `iter_refining` (`12.00%`, step `0.001`). **Thermal sheets (`1, 7, 8, 9, 10`) write `fxd_revenue = C16` to `E6:G12`; Renewable sheets (`2, 3, 4, 5, 6`) write `price_lst = B16` to `E6:G12`.**
   - **`calcule_tir11` & `calcule_tir12` (`_11_CF` & `_12_CF` Distributed Generation):** 4 parameters (`rows 6..9`) $\times$ 3 columns (`B..D`) = **12 solves per macro**. **Critical Legacy Quirk Preserved (`DEC-01`):** Runs Stage 1 `iter_conv` (`Goal:=0.080001` on `B18 = IRR(B32:AA32)`) **ONLY** and omits `iter_refining`, writing `price_lst` (`B16`) at `8.0001%` IRR into `E6:G9`.

3. **12 1D Fuel / CVU / Capex Sensitivity Sweep Macros (`calculo_cvu1` through `calculo_cvu12` — Buttons `General!C45:N45`):**
   - **`calculo_cvu1`..`calculo_cvu10` (`_01_CF`..`_10_CF`):** 10-point 1D sweep (`B70:B79` $\rightarrow$ `C70:C79`).
     - **Selective `rst_scenario` Quirk Preserved:** Calls `rst_scenario` at the start of each step **only** in `calculo_cvu1, 4, 5, 6, 10`; skips `rst_scenario` (commented out as `'rst_scenario` in legacy code) in `calculo_cvu2, 3, 7, 8, 9`, preserving prior `H6:H12` observer state.
     - **Mutated Observer Cell Quirk Preserved:** Writes `B70:B79` into `H7` (Fuel / CF) for `calculo_cvu1..4, 6..10`, but writes `B70:B79` into **`H6` (Capex)** for `calculo_cvu5` (`_05_CF` Solar PV).
   - **`calculo_cvu11` & `calculo_cvu12` (`_11_CF` & `_12_CF`):** Single-point solve (`1` solve each) calling `rst_scenario`, then `iter_conv_gd` (`12.001%`) $\rightarrow$ `iter_refining_gd` (`12.00%`, step `0.001`), writing `B16`.

4. **6 Specialized 1D & 2D Bivariate Sensitivity Matrix Macros:**
   - `calculo_capexvscf` (`General!G48` on `_05_CF`): 10 solves (`A84:A93` $\rightarrow$ `H6`, writes `G84:G93`).
   - `calculo_priceirr` (`General!H48` on `_06_CF`): 50 direct `IRR` formula evaluations without GoalSeek (`B87:F87` $\rightarrow$ `B16`, `A88:A97` $\rightarrow$ `H6`, writes `B18` into `B88:F97`).
   - `calculo_cvu2bi` (`General!D48` on `_02_CF!E70:N79`), `calculo_cvu4bi` (`General!F48` on `_04_CF!E70:N79`), `calculo_capexvscfbi` (`General!G52` on `_05_CF!C99:L108`), `calculo_priceirr_bi` (`General!H52` on `_06_CF!C105:L114`): **10 $\times$ 10 = 100 solves each**.

5. **2 Unbound Quantitative Routines Exposed via API & Custom Menu:**
   - `lcoe_forecast` (`Module2`): 12-year Solar PV LCOE forecast on `_05_CF!U71:U82` reading `LT Capex!F8:F19` and `LT CF!G8:G19` (`iter_conv_forecast` `8.0%` $\rightarrow$ `iter_conv_ref_forecast` step `0.01`, tolerance `0.0005`).
   - `fator_i` (`Module1`): 10-point dispatch (`F68=1`) vs. non-dispatch (`F68=0`) IRR convergence loop stepping `H68` (`c_fator_i`) by `0.001` and writing `G70:G79`.

6. **Cataloged Legacy Technical Debt Items (`DEC-02`):**
   - `3,400` defined names (`1,123` broken `#REF!` definitions = `33.0%`).
   - Broken subroutine `Sub calculo()` calling undefined `calcule_tir`.
   - Empty `Module4`.
   - Orphans in `lcoe_exec` referencing 5 previously deleted `LT *` worksheets (`LT Transmission`, `LT O&M`, `LT Financing`, `LT Efficiencies`, `LT CO2`).

---

## 3. Architectural Decisions (Google Sheets Native Pivot)

| Decision ID | Decision Topic | Selected Architectural Pattern | Rationale & Impact |
| :--- | :--- | :--- | :--- |
| **`DEC-01`** | **Solver Numerical Parity Mode** | **Strict Legacy Emulation Mode ($\le 10^{-8}$ relative error)** | Reproduces exact two-stage convergence (`iter_conv` + `iter_refining` on the discrete $P_0 \pm k \cdot 0.001$ price lattice) and all legacy macro quirks (`tir11/12` stopping at `8.0001%`, `cvu5` mutating `H6`, selective `rst_scenario`, thermal `fxd_revenue` vs. renewable `price_lst`) while using integer binary search over $k \in \mathbb{Z}$ to achieve sub-millisecond per-point solves. |
| **`DEC-02`** | **Legacy Scope & Debt Handling** | **Port 38 Active Routines + Automated Remediation Report** | Exposes all 31 button macros + `lcoe_forecast` + `fator_i` + 5 internal helpers on Cloud Run & Vertex AI, and catalogs all `1,123` `#REF!` named ranges and orphaned references in AlloyDB (`technical_debt_items`) and BigQuery. |
| **`DEC-03`** | **Cloud Solver Execution Engine** | **Hybrid Vertex AI Custom Prediction + BigQuery ML + Connected Sheets** | Interactive button clicks on Google Sheets call the Cloud Run Gateway $\rightarrow$ **Vertex AI Custom Prediction Endpoint** (with warm in-process Cloud Run fallback). Batch SQL sensitivity runs and time-series forecasting (`ML.FORECAST`) run in **BigQuery ML** and sync directly into Google Sheets via **Native Connected Sheets for BigQuery**. |
| **`DEC-04`** | **Distributed Copy Governance & Self-Activating Triggers** | **Self-Installing `onEdit` Hook + Silent Solver-Linked Checkpoint (`ensureGovernanceTriggers_` & `runSilentCheckpoint_`)** | Analysts work by making personal copies (`File -> Make a copy`) of the central Google Sheet in their own Google Drive, and will not manually click a "Commit Checkpoint" button. Because Google strips installable triggers on `File -> Make a copy`, `invokeCloudSolver` automatically self-installs the `onGovernedSheetEdit` (`onEdit`) trigger on any new copy upon the first solver button click and triggers a silent background `.xlsx` checkpoint diff against the canonical baseline. |
| **`DEC-05`** | **Ingestion Durability & Concurrency** | **GCS-First Immutable Snapshot + AlloyDB Advisory Lock + Pluggable Publisher** | Every version checkpoint writes the immutable `.xlsx`/JSON snapshot to **GCS first** before acquiring `pg_advisory_xact_lock(hashtext(spreadsheet_id))` in AlloyDB to compute `parent_version_id` and `version_seq_num` sequentially. |
| **`DEC-06`** | **Branding & Multi-Environment Portability** | **Generic Enterprise Commodity Modeling + Parameterized `GCP_PROJECT_ID`** | Zero organization-specific proprietary branding; parameterized `var.project_id` / `GCP_PROJECT_ID` with universal label `app = "sheets-commodity-mod"` and full `ENV=local` (Docker Compose) / `ENV=gcp` dual-mode support. |

---

## 4. User Personas & End-to-End Workflows

1. **`PER-01` — Quantitative Commodity Analyst (Distributed Personal Copy Workflow):**
   - Creates a **personal or scenario-specific copy (`File -> Make a copy`)** of the central master Google Sheet (`Regional Power Generation Techno-Economic Model — Brazil v13 (Governed)`) inside their own Google Drive (`My Drive` or team workspace folder).
   - Works identically to their familiar Excel workflow with **zero manual governance overhead**: edits scenario assumptions on `General` or `_01_CF`–`_12_CF`, refreshes BigQuery ML curves on `LT_Capex_BQML`, `LT_Fuel_BQML`, and `LT_CF_BQML`, and clicks any of the **31 3D native cell buttons (`OverGridImage` overlays)** on `General!B42:N52` to run sub-second cloud solves.
   - Behind the scenes, clicking any solver button in their personal copy automatically activates real-time `onEdit` and `onChange` governance monitoring on that copy, streaming silent 4-Ws audit events (including its local copy name, `spreadsheet_id`, and clickable Google Sheets URL) to BigQuery.
2. **`PER-02` — Model Risk & Governance Engineer:**
   - Monitors real-time `MANUAL_OVERRIDE` and `FORMULA_MODIFIED` events across **all distributed analyst copies** of the model—tracking not only *who* (`who_google_user`) made the change and *what* cell/formula changed, but also **which local spreadsheet copy (`workbook_id` / `workbook_name`) and Google Drive location (`who_spreadsheet_id`, `spreadsheet_url`, and `drive_location`)** the change occurred in.
3. **`PER-03` — Head of Commodity Research / Executive Approver:**
   - Reviews cross-technology LCOE trajectories (`Output_1`–`Output_3`), verifies whether numbers presented by an analyst came from the central master sheet or a specific personal Drive copy, and inspects the immutable `4-Ws` audit trail in BigQuery (`vw_audit_4w_summary`, `vw_manual_overrides`).

---

## 5. Detailed Functional Requirements

### 5.1 Pillar A — Cloud-Native Quantitative Solver, Vertex AI & Connected Sheets for BigQuery

- **`FR-A01` (Automated `.xlsm`-to-Google-Sheets Seeding & Fixture Extraction):**
  - Provide an automated CLI/script (`scripts/seed_google_sheet_from_xlsm.py`) that takes the baseline `.xlsm` file (`2023-11-27-Brazil_TT_v13_RJEB.xlsm`), extracts the golden parity fixture (`data/fixtures/brazil_tt_v13_baseline.json` containing all 854 baseline macro output cells), imports/creates the 22-sheet Google Spreadsheet via Google Drive/Sheets API, and provides the consolidated Apps Script (`apps_script/CombinedSheetScript.gs`) and button layout formatter (`scripts/configure_general_buttons.py`).
- **`FR-A02` (Vectorized Cash-Flow & IRR Engine Across All 12 Sheets):**
  - Replicate the exact 45-year utility cash-flow logic (`B20:AT63` on `_01_CF`–`_10_CF`) and 26-year Distributed Generation net-metering logic (`B20:AA32` on `_11_CF`–`_12_CF`) in IEEE 754 double-precision Python (`NumPy`/`SciPy`), matching spreadsheet `IRR()` to $\le 10^{-14}$.
- **`FR-A03` (Two-Stage Discrete Lattice Convergence Engine — `StrictLegacyVBAEmulator`):**
  - Replicate Stage 1 (`iter_conv` to `0.080001`, `iter_conv_gd` to `0.12001`, `iter_conv_forecast` to `0.08`) and Stage 2 discrete price-lattice stepping (`iter_refining` with $\Delta P = 0.001$ to `0.12` $\pm 10^{-5}$, `iter_conv_ref_forecast` with $\Delta P = 0.01$ to `0.08` $\pm 5 \times 10^{-4}$) using monotonic bracketed integer binary search over $k \in \mathbb{Z}_{\ge 1}$ so the terminal price $P_{k^*}$ is bit-for-bit identical to sequential stepping in $< 0.3\text{ ms}$ per solve.
- **`FR-A04` (Thermal Physical Guarantee `GF`, `fator k`, and `icb` Post-Solver Logic):**
  - For thermal sheets `_01_CF`, `_07_CF`, `_08_CF`, and `_09_CF`, evaluate row `81` (or row `105` on `_08_CF`) using the quadratic regression polynomials on `CVU_GF` and write `icb` (`I81` or `I105`) to `Output_3` during `lcoe_exec`.
- **`FR-A05` & `FR-A06` (Vertex AI Model Registry & Custom Prediction Container):**
  - Package the solver as a Vertex AI Custom Prediction container (`Dockerfile.vertex_solver` implementing `AIP_HEALTH_ROUTE=/health` and `AIP_PREDICT_ROUTE=/predict`), register it in **Vertex AI Model Registry** (`sheets-commodity-mod-lcoe-solver`), and support both dedicated Vertex AI Prediction Endpoints and warm in-process Cloud Run execution.
- **`FR-A07` (BigQuery ML Forecasting, Remote Function & Surrogate Model with Connected Sheets):**
  - Provision:
    1. **BigQuery ML Time-Series Forecasting (`bqml_lt_trajectories_forecast_v1`):** Trains an `ARIMA_PLUS` multi-series model on `<= 2025` historical actuals in `historical_lt_trajectories` (`445` empirical curve points across `LT_CAPEX`, `LT_FUEL`, and `LT_CF` for all 11 technology curves) and forecasts the 15-year `2026–2040` horizon via `ML.FORECAST`. Surfaced horizontally via `vw_connected_sheets_lt_forecasts` into a hidden Connected Sheets `DataSourceTable` Extract (`BQML_LT_Forecasts`) that dynamically populates three workbook-styled sheets—**`LT_Capex_BQML`**, **`LT_Fuel_BQML`**, and **`LT_CF_BQML`**—complete with soft-blue conditional formatting for `2026–2040` forecasted rows and 1-click **`Refresh BQML`** 3D buttons (`refreshBqmlForecasts()`).
    2. **BigQuery ML Remote Function (`fn_solve_lcoe`):** Invokes `/v1/bqml/solve` on the Cloud Run Gateway (`us-central1.sheets-mod-vertex-conn`) for parallel SQL scenario sweeps.
    3. **BigQuery ML Surrogate Model (`bqml_lcoe_surrogate_v1`):** Trained in BigQuery ML, registered in Vertex AI Model Registry (`sheets-commodity-mod-bqml-surrogate`), and surfaced directly into the **`BQML_LCOE_Surrogate`** Connected Sheet via `vw_bqml_lcoe_surrogate_predictions`.
- **`FR-A08` (Google Apps Script Solver Client, 3D Button Deck & Batch Sheet Write-Back):**
  - Provide Google Apps Script bindings (`apps_script/CombinedSheetScript.gs`) bound to all 31 permanent native cell buttons with 3D `OverGridImage` click overlays (`autoBindGeneralDrawingButtons()`) on `General!B42:N52` and the custom `"Commodity Modeling"` menu.
  - On click, reads `General!C5:N40`, `LT Capex!B8:J30`, `LT Fuel!B8:J30`, and `LT CF!B8:J30`, attaches `ScriptApp.getIdentityToken()` as an OIDC `Bearer` token alongside copy provenance headers, calls `POST /v1/solve/{macro_name}`, writes all returned `cell_updates`, and ensures `onEdit`/`onChange` governance triggers are installed on the active workbook copy.

### 5.2 Pillar B — Distributed Copy Governance, AST/DAG Lineage & Immutable "4 Ws" Audit

- **`FR-B01` (4-Role Deterministic Cell Semantic Classifier):**
  - Every populated cell in the 22-sheet Google Sheet (`35,655` baseline cells) is deterministically classified into exactly one of four mutually exclusive `CellSemanticRole` values:
    1. `FORMULA_CELL`: Any cell containing a formula (`=SUM(...)`, `=IRR(...)`, `=-(I$6*$H$6*C23)*$F$7`).
    2. `SOLVER_OUTPUT_CELL`: Non-formula cells written by any of the 38 solver routines (`_01_CF.._10_CF!E6:G12`, `_11_CF.._12_CF!E6:G9`, `_01_CF.._10_CF!C70:C79`, `_02_CF!E70:N79`, `_04_CF!E70:N79`, `_05_CF!G84:G93, C99:L108, U71:U82`, `_06_CF!B88:F97, C105:L114`, `Output_3!B9:J31, B3`, and `_01_CF, _07_CF, _09_CF!C81`, `_08_CF!C105`).
    3. `SCENARIO_INPUT_CELL`: Non-formula numeric input cells in designated assumption ranges (`General!C5:N40`, `_01_CF.._12_CF!B6:D12, H6:H12, B16, B70:B79`, `LT Capex`, `LT Fuel`, `LT CF` rows `8..30`, `_CAPEX 01`, `CVU_GF` numeric inputs).
    4. `LABEL_OR_STATIC_CELL`: All remaining text headers, unit labels, and metadata cells.
- **`FR-B02` (Canonical Formula Normalization & R1C1 Translation):**
  - Normalize every formula to both canonical A1 notation and relative **R1C1 notation (`r1c1_formula`)** with a SHA-256 `formula_hash`, expanding any shared formulas if ingested from `.xlsx`/`.xlsm` export bytes.
- **`FR-B03` (Cell-Level Precedent $\rightarrow$ Dependent DAG Builder):**
  - Parse every formula's cell, range, cross-sheet, and named-range references to construct the complete directed graph of `cell_dependency_edges` (`precedent_sheet, precedent_coord` $\rightarrow$ `dependent_sheet, dependent_coord`).
- **`FR-B04` (Named Range & Technical Debt Scanner):**
  - Extract all `3,400` named ranges, flag all `1,123` broken `#REF!` ranges, and catalog legacy technical debt items in `technical_debt_items`.
- **`FR-B05` (Zero-Touch Silent Audit Capture Across Personal Copies — Self-Installing `onEdit` & `onChange` Hooks):**
  - **Path 1 — Self-Installing Silent `onEdit` Hook (`onGovernedSheetEdit` -> `POST /v1/ingest/edit-event`):**
    - Automatically registered on the central sheet and on any personal copy (`File -> Make a copy`) via `installEditTrigger()` when the analyst clicks any solver button.
    - Suppresses events when a routine numeric edit occurs on a `SCENARIO_INPUT_CELL` or `SOLVER_OUTPUT_CELL`.
    - Silently streams a `CRITICAL` **`MANUAL_OVERRIDE`** `4-Ws` audit event to BigQuery when a cell classified as `FORMULA_CELL` (in the canonical seed baseline) is overwritten with a literal scalar (`new_formula == ""`), a `WARNING` **`FORMULA_MODIFIED`** / `INFO` **`FORMULA_ADDED`** event when a formula expression is altered or added, and a `WARNING` **`HEADER_OR_LABEL_MODIFIED`** event when any `LABEL_OR_STATIC_CELL` text cell (such as a table header in `_01_CF!B2:H2`) is changed.
  - **Path 2 — Self-Installing Silent `onChange` Metadata Hook (`onGovernedSheetChange` -> `POST /v1/ingest/edit-event`):**
    - Automatically registered alongside `onEdit` via `installEditTrigger()`.
    - Silently captures structural and metadata changes across worksheets (`INSERT_ROW` -> `ROW_INSERTED`, `REMOVE_ROW` -> `ROW_DELETED`, `INSERT_COLUMN` -> `COL_INSERTED`, `REMOVE_COLUMN` -> `COL_DELETED`, `INSERT_GRID` -> `SHEET_ADDED`, `REMOVE_GRID` -> `SHEET_DELETED`) and streams them directly to BigQuery (`sheets_commodity_mod_governance.audit_events`).
- **`FR-B06` & `FR-B07` (Noise-Free Structural Diff Engine & R1C1 Coordinate Shift Normalization):**
  - Routine value edits to `SCENARIO_INPUT_CELL` and solver writes to `SOLVER_OUTPUT_CELL` generate **zero (`0`) structural audit events**.
  - When a full `.xlsx` checkpoint is ingested via `/v1/ingest/checkpoint`, `shift_normalizer.py` aligns rows/columns via R1C1 signature vectors, emits **1** `ROW_INSERTED` (or `ROW_DELETED`) event, and suppresses false-positive `FORMULA_MODIFIED` alerts on all shifted downstream rows whose R1C1 relative formula is unchanged.
- **`FR-B08` (Serverless BigQuery "4 Ws" Audit Log, Connected Sheet View & Rollback Lineage):**
  - Every governed change across both the central sheet and all personal analyst copies is streamed to **BigQuery** (`sheets_commodity_mod_governance.audit_events`) with full copy provenance:
    - **1st W (`What Element`):** `workbook_id` (the **local spreadsheet copy name**, e.g., `"FHM Copy of Regional Power Generation Techno-Economic Model — Brazil v13 (Governed)"`), `what_element_coord` (`<Local_Copy_Name> -> _01_CF!B2`), & `what_semantic_role` (`FORMULA_CELL` or `LABEL_OR_STATIC_CELL`).
    - **2nd W (`What Change`):** `what_change_type` (`MANUAL_OVERRIDE`, `FORMULA_MODIFIED`, `FORMULA_ADDED`, `HEADER_OR_LABEL_MODIFIED`, `ROW_INSERTED`, `ROW_DELETED`, `COL_INSERTED`, `COL_DELETED`, `SHEET_ADDED`, `SHEET_DELETED`), `severity` (`CRITICAL`, `WARNING`, `INFO`), `before_state` JSON, and `after_state` JSON.
    - **3rd W (`Who & Where`):** `who_google_user` (`Session.getActiveUser().getEmail()`), `who_iam_principal`, `who_spreadsheet_id` (the unique Google Drive file ID of the local copy), and `who_client_platform` / `gcs_snapshot_uri` (surfaced as `copy_location_url`—the direct clickable Google Sheets URL of that live workbook or personal copy).
    - **4th W (`When`):** `when_event_utc` (ISO-8601 UTC timestamp, used for daily time-partitioning in BigQuery).
  - Expose BigQuery views (`vw_audit_4w_summary`, `vw_manual_overrides`) surfacing `copy_name`, `copy_location_url`, `who_google_user`, and before/after diffs directly to the **`BQ_4Ws_Audit_Log`** Connected Sheet, supporting both surgical single-cell rollback (restoring `before_formula` / `before_value`) and full-workbook point-in-time recovery (opening `copy_location_url` and matching `when_event_utc` in Google Sheets **File > Version history**).

---

## 6. Non-Functional Requirements (SLAs) & Infrastructure Guardrails

| Requirement ID | Category | Metric / Mandate | Target SLA / Verification Criteria |
| :--- | :--- | :--- | :--- |
| **`NFR-01`** | **Numerical Parity** | Relative floating-point error across all 854 baseline macro outputs | **$\le 10^{-8}$** ($0.000001\%$) verified against `brazil_tt_v13_baseline.json` |
| **`NFR-02`** | **Single-Sheet Solver Latency** | End-to-end latency for `calcule_tir1..12` (21 solves) & `calculo_cvu1..12` (10 solves) | **$\le 800\text{ ms}$ (p95)** at Cloud Run Gateway |
| **`NFR-03`** | **Full 184-Solve Forecast Latency** | End-to-end latency for `lcoe_exec` (23 yrs $\times$ 8 sheets = 184 solves) & 100-solve 2D sweeps | **$\le 2,000\text{ ms}$ (p95)** at Cloud Run Gateway |
| **`NFR-04`** | **Silent `onEdit`/`onChange` Hook Latency** | Non-blocking silent execution of Apps Script `onEdit`/`onChange` hooks + `/v1/ingest/edit-event` | **$\le 150\text{ ms}$** server processing time; zero UI popups or blocking in Google Sheets |
| **`NFR-05`** | **Audit Log Immutability** | Append-only governance log protection on `audit_events` | **100% Append-Only** streaming inserts to BigQuery `audit_events` (with database trigger enforcement on local SQL mirror) |
| **`NFR-06`** | **Checkpoint Ingestion SLA** | Full 22-sheet, 35,655-cell AST/DAG extraction + R1C1 diff | **$\le 5.0\text{ seconds}$ (p95)** |
| **`INFRA-01`** | **Target Region & Parameterized Project** | All GCP resources provisioned in `var.project_id` (`GCP_PROJECT_ID`) | Region **`us-central1`** (or configured region), BigQuery Location **`us-central1`** |
| **`INFRA-02`** | **Universal Resource Labeling** | Mandatory FinOps & resource governance labels on all label-capable resources | `app = "sheets-commodity-mod"`, `project = "enterprise-commodity-modernization"`, `env = var.environment`, `managed-by = "terraform"` |
| **`INFRA-03`** | **Zero Static Keys & OIDC Auth** | Service-to-service and Apps Script-to-Cloud Run authentication | `ScriptApp.getIdentityToken()` OIDC Bearer verification + background trigger identity headers + least-privilege IAM Service Accounts |
| **`INFRA-04`** | **Clean `terraform destroy` Lifecycle** | Zero-residue infrastructure tear-down | GCS `force_destroy = true`, BigQuery `delete_contents_on_destroy = true`, Vertex AI pre-destroy `undeploy-model` hook |
| **`INFRA-06`** | **Shared-Project Blast-Radius Isolation** | Safe coexistence in shared Google Cloud demo/sandbox projects | No `google_project` resource, `disable_on_destroy = false` on all APIs, additive-only `google_project_iam_member` |

---

## 7. Acceptance Test Matrix

| Test ID | Pillar / Scope | Description | Pass Criteria |
| :--- | :---: | :--- | :--- |
| **`TEST-A01`** | Pillar A | 12 Fuel/CVU sweep macros (`calculo_cvu1`–`calculo_cvu12`, 102 output cells + selective `rst_scenario` & `H6`/`H7` quirks) | Relative error $\le 10^{-8}$ across all 102 outputs; p95 latency $\le 800\text{ ms}$ |
| **`TEST-A02`** | Pillar A | 12 Tornado IRR macros (`calcule_tir1`–`calcule_tir12`, 234 output cells including thermal `C16` vs. renewable `B16` and `tir11/12` `8.0001%` Stage-1-only quirk) | Relative error $\le 10^{-8}$ across all 234 outputs; p95 latency $\le 800\text{ ms}$ |
| **`TEST-A03`** | Pillar A | 6 1D/2D sensitivity matrices (`calculo_capexvscf`, `calculo_priceirr`, 4 `*_bi` 100-solve grids = 460 cells) + `lcoe_forecast` (12 cells) + `fator_i` (10 cells) | Relative error $\le 10^{-8}$ across all 482 outputs; p95 latency $\le 2,000\text{ ms}$ |
| **`TEST-A04`** | Pillar A | Master 23-year, 8-technology `lcoe_exec` forecast (`184` cells on `Output_3!B9:J31` + thermal `icb` + timestamp `Output_3!B3`) | Relative error $\le 10^{-8}$ across all 184 cells; p95 latency $\le 2,000\text{ ms}$ |
| **`TEST-A05`** | Pillar A | Vertex AI Custom Prediction container (`/health` and `/predict` endpoints) | Returns valid `predictions` payload matching `SolveMacroResponse` |
| **`TEST-A06`** | Pillar A | BigQuery ML `ML.FORECAST`, Remote Function `fn_solve_lcoe`, and `bqml_lcoe_surrogate_v1` for Connected Sheets | SQL queries and Connected Sheets views return valid LCOE predictions and 23-year input forecasts |
| **`TEST-B01`** | Pillar B | Full 22-sheet, 35,655-cell AST/DAG extraction, 10,654 shared formula expansion, 3,400 named ranges (`1,123` `#REF!`), 31 macro bindings | 100% count match in $\le 5.0\text{ s}$ |
| **`TEST-B02`** | Pillar B | Noise suppression on `SCENARIO_INPUT_CELL` edits and `SOLVER_OUTPUT_CELL` writes | `0` structural `audit_events` emitted |
| **`TEST-B03`** | Pillar B | Undocumented `MANUAL_OVERRIDE` detection (`_01_CF!G23` formula `=-(I$6*$H$6*C23)*$F$7` overwritten with literal `1250000000` via silent `onEdit`) | Emits 1 `CRITICAL` `MANUAL_OVERRIDE` 4W event with `who_google_user` email, copy name/URL, before formula, after literal |
| **`TEST-B04`** | Pillar B | Formula modification detection (`_01_CF!I60` formula edited) | Emits 1 `WARNING` `FORMULA_MODIFIED` event |
| **`TEST-B05`** | Pillar B | Row insertion (`_01_CF` Row 30 inserted) with R1C1 coordinate shift normalization | Emits 1 `ROW_INSERTED` event; `0` false-positive `FORMULA_MODIFIED` events on shifted rows `31..109` |
| **`TEST-B06`** | Pillar B | Sheet visibility change (`CVU_GF` hidden) and named range repair | Emits `SHEET_VISIBILITY_CHANGED` and `NAMED_RANGE_MODIFIED` events |
| **`TEST-B07`** | Pillar B | Audit log immutability (`UPDATE` or `DELETE` on `audit_events`) | Rejected by database immutability trigger |
| **`TEST-B08`** | Pillar B | Personal copy silent tracking of Table Header/Label (`_01_CF!B2` `"Gas"` -> `"Gasoline"` -> `HEADER_OR_LABEL_MODIFIED`) and Metadata (`INSERT_ROW`, `INSERT_GRID`) | Emits `HEADER_OR_LABEL_MODIFIED`, `ROW_INSERTED`, and `SHEET_ADDED` with copy name & URL |

---

## 8. Version 2 (V2) Strategic Roadmap & Backlog

While the MVP establishes the deterministic quantitative solver, BigQuery ML Connected Sheets integration, and silent BigQuery `4-Ws` structural governance foundation, **Version 2 (V2)** includes the following strategic backlog items:

1. **Solver Run Telemetry & FinOps Observability (`solver_run_telemetry` — Parked for V2):**
   - Optional telemetry tracking solver execution frequency, p50/p95 latency SLAs, and active scenario modeling usage across copies in `sheets_commodity_mod_governance.solver_run_telemetry`.
2. **Automated Scenario & Assumption Research (`Precept` + `DataGemma`):**
   - Multi-step research agents ingest macroeconomic indicators (inflation/IPCA, FX curves, WACC), regulatory auction caps, and global fuel/EPC reports, cross-checking numerical claims via `DataGemma` and staging validated assumption tables in BigQuery for one-click refresh into Google Sheets (`LT Capex`, `LT Fuel`, `LT CF`, `General`).
3. **Natural-Language Scenario Co-Pilot in Google Sheets Workspace Sidebar:**
   - Analysts type plain-English requests in a Google Sheets side panel (e.g., *"Compare Gas CCGT vs. Onshore Wind LCOE under a +20% LNG shock and 10% WACC"*), and a Precept Orchestrator Agent automatically coordinates batch solves across Vertex AI and BigQuery ML and writes a structured comparison table back to the sheet.
4. **Intelligent Model Risk & Override Triage Agent:**
   - Triggered automatically whenever Pillar B logs a `CRITICAL` `MANUAL_OVERRIDE` or `FORMULA_MODIFIED` event in BigQuery. Traces the downstream blast radius across the Dependency DAG (`Output_1`–`Output_3`) and drafts a plain-English Model Risk Assessment for Research Directors.
5. **Automated Executive Commentary & Investment Memo Generation:**
   - Uses Precept's parallel `MapReduce` document writer to synthesize multi-technology LCOE outputs, Tornado sensitivities, and governance status into publication-ready Commodity Research Briefs in Google Docs/Slides with cell-level citations.

