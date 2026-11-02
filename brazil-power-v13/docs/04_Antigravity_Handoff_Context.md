# Antigravity Session Handoff Context: Enterprise Commodity Modeling — Google Sheets Modernization & Structural Governance Platform

| Handoff Metadata | Details |
| :--- | :--- |
| **Document ID** | `ENT-HANDOFF-CONTEXT-004` |
| **Companion Documents** | `docs/01_PRD_Google_Sheets.md`, `docs/02_Design_Document_Google_Sheets.md`, `docs/03_Implementation_Plan_Google_Sheets.md`, `docs/06_Live_Demo_Runbook_Google_Sheets.md`, `docs/GCP_System_Architecture_Diagram_Google_Sheets.png` (`.svg`) |
| **Seed Baseline Workbook** | `2023-11-27-Brazil_TT_v13_RJEB.xlsm` (Used strictly as read-only seed source to populate Google Sheets and verify $\le 10^{-8}$ numerical parity) |
| **Frontend Architecture** | **Google Sheets** + **Google Apps Script (`V8` Runtime)** + **Native Connected Sheets for BigQuery** |
| **Backend & Data Stack** | **Cloud Run** (FastAPI Gateway) + **Vertex AI Prediction & Model Registry** + **BigQuery & BigQuery ML** + **Cloud Storage (GCS)** |
| **Target GCP Region & Labels** | Parameterized `GCP_PROJECT_ID` (`comm-model-mod`), Region `us-central1` (`us-central1-a`), Universal Label `app = "sheets-commodity-mod"` |

---

## 1. Purpose of This Handoff Context Document

This document transfers **100% of the domain, mathematical, structural, and architectural knowledge** extracted during the analysis, engineering, and live Google Sheets modernization of the Brazil Power Generation Techno-Economic Model.

By reading this document (alongside `01_PRD_Google_Sheets.md`, `02_Design_Document_Google_Sheets.md`, `03_Implementation_Plan_Google_Sheets.md`, and `06_Live_Demo_Runbook_Google_Sheets.md`), any engineer or AI agent has immediate access to:
1. The exact cell-by-cell anatomy of the 22-sheet, 35,655-cell **Regional Power Generation Techno-Economic Model** (`2023-11-27-Brazil_TT_v13_RJEB.xlsm`).
2. Every mathematical formula, cash-flow row equation, thermal dispatch polynomial, and legacy solver quirk across all **38 ported quantitative routines** (`31` interactive 3D cell buttons on `General!B42:N52` + `7` unbound/helper routines) required to pass the **$\le 10^{-8}$ relative numerical parity gate (`NFR-01`)** across all **854 baseline output cells**.
3. The complete **Google Sheets + Google Cloud** architecture, including **Google Apps Script (`CombinedSheetScript.gs`, `Menu.gs`, `SolverClient.gs`, `AuditHooks.gs`)**, **Native Connected Sheets for BigQuery (`LT_Capex_BQML`, `LT_Fuel_BQML`, `LT_CF_BQML`, `BQML_LCOE_Surrogate`, `BQ_4Ws_Audit_Log`, `fn_solve_lcoe`)**, and **Silent Distributed Copy Governance (`onGovernedSheetEdit` & `onGovernedSheetChange` -> BigQuery `audit_events`)**.

---

## 2. Complete Empirical Anatomy of the Pilot Model (`2023-11-27-Brazil_TT_v13_RJEB.xlsm`)

### 2.1 High-Level Structural Metrics
- **Core Model Worksheets:** `22` (`0` hidden sheets in seed baseline), augmented in the live governed Google Sheet with 5 Connected Sheets / BigQuery ML tabs (`LT_Capex_BQML`, `LT_Fuel_BQML`, `LT_CF_BQML`, `BQML_LCOE_Surrogate`, `BQ_4Ws_Audit_Log`, plus hidden backing Extract `BQML_LT_Forecasts`).
- **Total Populated Cells:** `35,655` across the 22 core sheets.
- **Total Baseline Formula Cells:** `15,961` active calculated formulas (`17,354` raw `<f>` XML tags in OpenXML, including `10,654` shared formula cells across `430` `si` groups).
- **Total Defined Names (Named Ranges):** `3,400` total (`2,277` valid + `1,123` broken `#REF!` definitions = `33.0%` broken named ranges cataloged as technical debt).
- **Interactive 3D Solver Buttons:** `31` native styled button cells with 3D `OverGridImage` click overlays on `General!B42:N52` bound to solver macros via `autoBindGeneralDrawingButtons()`.

### 2.2 Master Parameter & Control Sheet (`General`)
- **Master Techno-Economic Parameter Grid (`General!C5:N40`):**
  - Each column (`C` through `N`) defines the baseline engineering and financial parameters for one of the **12 Power Generation Technologies** (`_01_CF` through `_12_CF`):
    - **Col `C` (`_01_CF`):** Natural Gas Combined Cycle (`CCGT`, 500 MW) — Thermal Dispatchable
    - **Col `D` (`_02_CF`):** Biomass Sugarcane Bagasse Boiler (55 MW) — Renewable
    - **Col `E` (`_03_CF`):** Biomass Boiler Retrofit (55 MW) — Renewable
    - **Col `F` (`_04_CF`):** Onshore Wind Turbine Class 6 (30 MW) — Renewable
    - **Col `G` (`_05_CF`):** Utility-Scale Solar PV (30 MW) — Renewable
    - **Col `H` (`_06_CF`):** Small Hydro Power Plant (`SHP`, 30 MW) — Renewable
    - **Col `I` (`_07_CF`):** Local Coal Circulating Fluidized Bed (`CFBC`, 400 MW) — Thermal Dispatchable
    - **Col `J` (`_08_CF`):** Imported Coal Pulverized (`PC`, 400 MW) — Thermal Dispatchable
    - **Col `K` (`_09_CF`):** Biomass Woodchip Fired Plant (50 MW) — Thermal Dispatchable
    - **Col `L` (`_10_CF`):** LNG Combined Cycle (`CCGT`, 500 MW) — Thermal Dispatchable
    - **Col `M` (`_11_CF`):** Residential Solar PV Distributed Generation (`DG`, 5 kW) — Net Metering
    - **Col `N` (`_12_CF`):** Commercial Solar PV Distributed Generation (`DG`, 50 kW) — Net Metering
  - Rows `5` through `40` on `General` hold: Installed Capacity (MW), Net Capacity, Capex (`R$/kW` or `R$/W`), Fuel Cost, Plant Efficiency (%), Heat Rate (`MMBtu/MWh`), Annual Degradation (%), Scheduled/Forced Outage Availability, Baseline Capacity Factor (%), Fixed O&M, Variable O&M, Debt Share (%), Real Interest Rate (%), Loan Tenor (years), Construction Drawdown Schedule (5 years: `-4` to `0`), Tax Rates (`IRPJ/CSLL`, `PIS/COFINS`, `ICMS`), Depreciation Rate, and Economic Life (`20` to `35` years).
- **Interactive 3D Button Matrix (`General!B42:N52`):**
  - **Cell `B43`:** `"Forecast LCOE"` $\rightarrow$ `lcoe_exec` (23-year `2018–2040` $\times$ 8-technology master forecast = 184 solves).
  - **Row `42` (`C42:N42`):** `"Tornado 1"` through `"Tornado 12"` $\rightarrow$ `calcule_tir1` through `calcule_tir12`.
  - **Row `45` (`C45:N45`):** `"Fuel/CVU1"` through `"Fuel/CVU12"` $\rightarrow$ `calculo_cvu1` through `calculo_cvu12`.
  - **Rows `48` & `52` (`D48, F48, G48, H48, G52, H52`):**
    - `D48` (`"BI LCOE"` on Biomass `_02_CF`) $\rightarrow$ `calculo_cvu2bi`
    - `F48` (`"BI LCOE"` on Wind `_04_CF`) $\rightarrow$ `calculo_cvu4bi`
    - `G48` (`"Capex vs IRR"` on Solar `_05_CF`) $\rightarrow$ `calculo_capexvscf`
    - `H48` (`"Price vs IRR"` on Hydro `_06_CF`) $\rightarrow$ `calculo_priceirr`
    - `G52` (`"BI LCOE"` on Solar `_05_CF`) $\rightarrow$ `calculo_capexvscfbi`
    - `H52` (`"BI LCOE"` on Hydro `_06_CF`) $\rightarrow$ `calculo_priceirr_bi`

### 2.3 Anatomy of the 10 Utility-Scale Cash-Flow Sheets (`_01_CF` through `_10_CF`)
Each utility-scale sheet (`_01_CF`..`_10_CF`) shares a standardized layout with critical technology-specific equations:
1. **Top Scenario & Tornado Block (`Rows 6..12`, `Cols B..H`):**
   - `B6:D12`: 7-parameter Tornado sensitivity input matrix (`Col B` = Low, `Col C` = Baseline Reference, `Col D` = High):
     - `Row 6`: Capex (`R$/kW` or multiplier)
     - `Row 7`: Fuel Cost (`CVU` input) or Capacity Factor (for Renewables)
     - `Row 8`: Efficiency / Heat Rate / Secondary CF
     - `Row 9`: O&M Cost
     - `Row 10`: Debt Share (%)
     - `Row 11`: Real Interest Rate (%)
     - `Row 12`: Economic Life (Years, e.g., `20`, `25`, `30`)
   - `E6:G12`: **Tornado Solver Output Matrix (`SOLVER_OUTPUT_CELL`, 21 cells)** populated by `calcule_tir1..10`.
   - `H6:H12`: **Active Scenario Observer Vector (`SCENARIO_INPUT_CELL`)**. All downstream cash-flow formulas on the sheet read from `H6:H12`! Calling `rst_scenario` copies `C6:C12` into `H6:H12`.
2. **Core Solver Target & Decision Cells (`Rows 16..18`):**
   - **`B16` (`price_lst`):** The solved Electricity Price (`R$/MWh`) — mutated by Stage 1 `GoalSeek` and Stage 2 discrete stepping.
   - **`C16` (`fxd_revenue`):** Fixed Annual Revenue (`R$ MM/yr` or `R$/MWh` equivalent) calculated by formula from `B16`, net capacity, and capacity factor.
   - **`B18` (`tir`):** Project Internal Rate of Return (`=IRR(B63:AT63)`), which must converge to the target IRR (`12.00%` $\pm 10^{-5}$).
3. **45-Year Discounted Cash-Flow Grid (`B20:AT63`):**
   - **Columns `B` through `F` (`5` columns):** Construction years `-4, -3, -2, -1, 0` (multi-year Capex drawdown schedule).
   - **Columns `G` through `AT` (`40` columns):** Operating years `1` through `40` (gated dynamically by `IF(year <= $H$12, ..., 0)`).
   - **Rows `20` through `63`:** Gross Generation, Gross Revenue (driven by `$B$16`), Revenue Taxes (`PIS/COFINS`, `ICMS`), Net Revenue, Fuel Cost (driven by `$H$7`), Fixed & Variable O&M, Sector Charges (`P&D`, `TFSEE`, `CFURH`), EBITDA, Depreciation, Debt Service (Interest & Principal Amortization over tenor), Corporate Income Taxes (`IRPJ` 25% + `CSLL` 9%), Working Capital, Capex (`Row 23`, e.g., `_01_CF!G23` has `=-(I$6*$H$6*C23)*$F$7`), and **Free Cash Flow to Equity/Project in `Row 63` (`B63:AT63`)**.
4. **1D & 2D Sensitivity Blocks (`Rows 68..114`):**
   - `B70:B79` (10 input points) $\rightarrow$ `C70:C79` (10 solved `B16` outputs written by `calculo_cvu1..10`).
   - `F68` (Dispatch mode flag `0` or `1`), `H68` (`c_fator_i`), `G70:G79` (10 outputs written by `fator_i`).
   - **Thermal Physical Guarantee (`GF`) & `ICB` Row (`Row 81` on `_01_CF`, `_07_CF`, `_09_CF`; `Row 105` on `_08_CF`):**
     - `C81` (or `C105` on `_08_CF`): Receives the solved `B16` price during `lcoe_exec`.
     - `D81..H81` (or `D105..H105`): Evaluates Variable Unit Cost (`CVU`), looks up the quadratic regression coefficients on `CVU_GF` to compute Physical Guarantee (`GF`), and computes `fator k`.
     - **`I81` (or `I105` on `_08_CF`):** The resulting Cost-Benefit Index (`icb`), which `lcoe_exec` writes into `Output_3`!

### 2.4 Anatomy of the 2 Distributed Generation Cash-Flow Sheets (`_11_CF` & `_12_CF`)
- Represent behind-the-meter **Residential Solar PV (5 kW, `_11_CF`)** and **Commercial Solar PV (50 kW, `_12_CF`)** under net-metering tariff rules:
  - **4-Parameter Tornado Table (`B6:D9` inputs $\rightarrow$ `E6:G9` outputs, `H6:H9` active observer):** Only 4 rows (`Rows 6..9`: Capex, Capacity Factor, Tariff, O&M) $\times$ 3 columns = **12 cells**.
  - **26-Year Cash-Flow Horizon (`B20:AA32`):** Column `B` is Year `0` upfront Capex; Columns `C:AA` are Operating Years `1..25` (including annual solar panel degradation and inverter replacement Capex in Year `13`).
  - **Net Cash Flow Row (`Row 32`):** `B18 = IRR(B32:AA32)`.

---

## 3. The 7 Critical Legacy Mathematical Quirks (Mandatory for $\le 10^{-8}$ Parity)

Any engineer or AI agent implementing the Python solver (`src/solver/`) **must** preserve these 7 empirical behaviors discovered in the legacy VBA code (`Module1`, `Module2`, `Module3`):

1. **Quirk 1 — Two-Stage Discrete Lattice Stopping Point (`iter_conv` + `iter_refining`):**
   - Stage 1 (`iter_conv`) runs `GoalSeek` to `0.080001` (or `0.12001` in `iter_conv_gd`, or `0.08` in `iter_conv_forecast`), establishing a starting price $P_0$.
   - Stage 2 (`iter_refining`) steps $P_k = P_0 + s \cdot k \cdot \Delta P$ (where $\Delta P = 0.001$ and $s = \text{sign}(\text{IRR}_{\text{target}} - \text{IRR}(P_0))$) and terminates at the **first integer step $k^*$** where $|\text{IRR}_{\text{target}} - \text{IRR}(P_{k^*})| \le 10^{-5}$ (`0.00001`).
   - Because stopping as soon as the trajectory enters the $\pm 10^{-5}$ band leaves `IRR` at roughly `0.11999001` (when stepping up) rather than `0.12000000`, our solver uses **bracketed integer binary search over $k \in \mathbb{Z}_{\ge 1}$** to find that exact entry integer $k^*$ in $\le 14$ steps ($< 0.3\text{ ms}$).

2. **Quirk 2 — Thermal vs. Renewable Tornado Output Variable (`calcule_tir1..10`):**
   - In `Module1`, after `iter_refining` finishes each of the 21 Tornado solves:
     - **Thermal macros (`calcule_tir1`, `calcule_tir7`, `calcule_tir8`, `calcule_tir9`, `calcule_tir10`)** write **`fxd_revenue` (`C16`)** into `E6:G12`.
     - **Renewable macros (`calcule_tir2`, `calcule_tir3`, `calcule_tir4`, `calcule_tir5`, `calcule_tir6`)** write **`price_lst` (`B16`)** into `E6:G12`.

3. **Quirk 3 — Distributed Generation Tornado (`calcule_tir11` & `calcule_tir12`) Stops at Stage 1 (`8.0001%` IRR):**
   - In `Module1`, `calcule_tir11` (`_11_CF`) and `calcule_tir12` (`_12_CF`) call `iter_conv` (`Goal:=0.080001`) and **never call `iter_refining`**. Thus, `E6:G9` on `_11_CF` and `_12_CF` contain the **8.0001% IRR** breakeven prices! (By contrast, `calculo_cvu11` and `calculo_cvu12` call `iter_conv_gd` $\rightarrow$ `iter_refining_gd` to `12.00%` IRR).

4. **Quirk 4 — Selective `rst_scenario` Execution in `calculo_cvu1..10`:**
   - In `Module1`, `rst_scenario` (`H6:H12 <- C6:C12`) is called before each loop iteration in **`calculo_cvu1, 4, 5, 6, 10`**, but is **commented out (`'rst_scenario`) in `calculo_cvu2, 3, 7, 8, 9`**. Therefore, `calculo_cvu2, 3, 7, 8, 9` retain whatever values were left in `H6, H8:H12` from prior state (or baseline `H6:H12`).

5. **Quirk 5 — `calculo_cvu5` Mutates `H6` (Capex) Instead of `H7` (Fuel/CF):**
   - While `calculo_cvu1..4` and `calculo_cvu6..10` copy the 10-point sweep vector `B70:B79` into `H7`, **`calculo_cvu5` (on `_05_CF` Solar PV) copies `B70:B79` into `H6` (Capex)**.

6. **Quirk 6 — Thermal `lcoe_exec` Row `81` vs. Row `105` (`_08_CF`) `ICB` Extraction:**
   - During `lcoe_exec`, for thermal sheets `_01_CF`, `_07_CF`, and `_09_CF`, the solved `B16` is written to **`C81`** and the resulting `icb` is read from **`I81`**. However, on **`_08_CF` (Imported Coal)**, the table is shifted down by 24 rows: solved `B16` is written to **`C105`** and `icb` is read from **`I105`**.

7. **Quirk 7 — `lcoe_exec` Technology Ordering & LT Sheet Column Mappings:**
   - `lcoe_exec` loops `count_yr = 1..23` (corresponding to rows `8..30` of `LT Capex`, `LT Fuel`, `LT CF`) and processes the 8 technologies in this exact order:
     - Tech 1 (`_01_CF` Gas CCGT): `H6 <- LT Capex Col B`, `H7 <- LT Fuel Col B`, `H8 <- LT CF Col B`, `price_frst = 500`, writes `icb` (`I81`) to `Output_3` Col `B` (`B9:B31`).
     - Tech 2 (`_02_CF` Biomass): `H6 <- LT Capex Col C`, `H7 <- LT Fuel Col C`, `H8 <- LT CF Col C`, `price_frst = 400`, writes `B16` to `Output_3` Col `C` (`C9:C31`). *(Note: `Output_3` Col `D` is skipped/blank in `lcoe_exec`!)*
     - Tech 3 (`_09_CF` Woodchip): `H6 <- LT Capex Col E`, `H7 <- LT Fuel Col E`, `H8 <- LT CF Col E`, `price_frst = 500`, writes `icb` (`I81`) to `Output_3` Col `E` (`E9:E31`).
     - Tech 4 (`_04_CF` Wind): `H6 <- LT Capex Col F`, `H7 <- LT CF Col F`, `price_frst = 250`, writes `B16` to `Output_3` Col `F` (`F9:F31`).
     - Tech 5 (`_05_CF` Solar PV): `H6 <- LT Capex Col G`, `H7 <- LT CF Col G`, `price_frst = 350`, writes `B16` to `Output_3` Col `G` (`G9:G31`).
     - Tech 6 (`_08_CF` Imported Coal): `H6 <- LT Capex Col H`, `H7 <- LT Fuel Col H`, `H8 <- LT CF Col H`, `price_frst = 500`, writes `icb` (`I105`) to `Output_3` Col `H` (`H9:H31`).
     - Tech 7 (`_06_CF` Small Hydro): `H6 <- LT Capex Col I`, `H7 <- LT CF Col I`, `price_frst = 250`, writes `B16` to `Output_3` Col `I` (`I9:I31`).
     - Tech 8 (`_07_CF` Local Coal): `H6 <- LT Capex Col J`, `H7 <- LT Fuel Col J`, `H8 <- LT CF Col J`, `price_frst = 500`, writes `icb` (`I81`) to `Output_3` Col `J` (`J9:J31`).

---

## 4. Summary of the Finalized Google Sheets + Google Cloud Solution Architecture

1. **Google Sheets Light Frontend (`apps_script/CombinedSheetScript.gs` + `scripts/`):**
   - `scripts/seed_google_sheet_from_xlsm.py` and `scripts/configure_general_buttons.py` import `2023-11-27-Brazil_TT_v13_RJEB.xlsm` into Google Drive/Sheets (`1apbos5xVpK4yBLiRFxQqAEyPVNkkYQ2ZvgAASibYYJI`) and style the 31 button slots on `General!B42:N52`.
   - **Pillar A Solver Execution (`invokeCloudSolver`):** `autoBindGeneralDrawingButtons()` places 3D `OverGridImage` PNG click overlays (`getButton3dOverlayBlob_()`) on all 31 native button cells. Clicking any button or menu item invokes `POST /v1/solve/{macro_name}` on Cloud Run (`sheets-commodity-mod-gateway` in `us-central1`), writes `cell_updates` back to the sheet, and calls `installEditTrigger(ss)` to ensure governance triggers are active on any `File -> Make a copy` spreadsheet.
   - **Native Connected Sheets for BigQuery (`setupBigQueryConnectedSheets` & `refreshBqmlForecasts`):** Creates a hidden Connected Sheets `DataSourceTable` Extract (`BQML_LT_Forecasts` via `insertSheetWithDataSourceTable` + `setRawQuery`) that powers live `=FILTER(...)` formulas on three workbook-styled tabs—**`LT_Capex_BQML`**, **`LT_Fuel_BQML`**, and **`LT_CF_BQML`** (`<=2025` actuals + soft-blue `2026–2040` `ARIMA_PLUS` forecasts, with 1-click **`Refresh BQML`** 3D buttons)—alongside **`BQML_LCOE_Surrogate`** (`vw_bqml_lcoe_surrogate_predictions`) and **`BQ_4Ws_Audit_Log`** (`vw_audit_4w_summary`).
2. **Pillar B Silent Distributed Copy Governance (`onGovernedSheetEdit` & `onGovernedSheetChange` -> Cloud Run -> BigQuery):**
   - **Silent Real-Time Hooks (`POST /v1/ingest/edit-event`):** Streams formula overrides (`MANUAL_OVERRIDE`), formula modifications (`FORMULA_MODIFIED`), header/label changes (`HEADER_OR_LABEL_MODIFIED`), and structural sheet/row/column mutations (`ROW_INSERTED`/`DELETED`, `COL_INSERTED`/`DELETED`, `SHEET_ADDED`/`DELETED`) to BigQuery (`comm-model-mod.sheets_commodity_mod_governance.audit_events`) with user email, copy name, and `copy_location_url`, while suppressing routine `SCENARIO_INPUT_CELL` edits.
   - **Rollback & Recovery:** Pairing `before_formula` / `before_value` with `copy_location_url` and `when_event_utc` enables both surgical single-cell formula restoration and full-workbook point-in-time recovery via Google Sheets **File > Version history**.

