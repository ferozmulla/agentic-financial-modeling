# Product Requirements Document (PRD): European Long-Range Crude & Refined Products Price & Margin Model (`Eulr202409.xlsx`) — Google Sheets & Google Cloud Edition

| Metadata | Details |
| :--- | :--- |
| **Document Version** | 2.0 (Validated Architecture Aligned with `brazil-power-v13` Serverless & 3D In-Sheet UX Pattern) |
| **Target Workbook** | `Eulr/seed/Eulr202409.xlsx` (European Long-Range Crude Oil & Refined Products Price & Refinery Margin Model) |
| **Frontend Target** | **Google Sheets** (`24` Tabs: `17` Model Tabs + `7` BQML / Connected Sheets / Scenario Tabs) + **Google Apps Script (`V8` Runtime)** + **3D `OverGridImage` Action Buttons** |
| **Backend & AI Target** | **GCP Project `comm-model-mod` (`us-central1`)** — **Cloud Run** (`eulr-equilibrium-gateway`), **BigQuery & BigQuery ML (`ARIMA_PLUS` + Crack-Spread Surrogate)**, **Vertex AI (`gemini-3.8-flash` + Model Registry + Custom Prediction Toggle)**, **Cloud Storage (`gs://comm-model-mod-eulr-snapshots`)** |

---

## 0. Plain-English Glossary of Domain & Technical Terms

### Commodity Pricing & Refinery Economics Terms
* **CIF (`Cost, Insurance, and Freight`) vs. FOB (`Free on Board`):**
  * **CIF (`NWE Cif`, `MED Cif`):** Landed price of a crude oil or refined product cargo delivered to Northwest Europe (`NWE`, ARA — Amsterdam-Rotterdam-Antwerp) or the Mediterranean (`MED`, Augusta/Lavera), including marine tanker freight and insurance.
  * **FOB (`NWE Fob`, `MED Fob`):** Cargo price at the origin refinery gate or export terminal (`CIF` minus marine freight and port handling when Europe is net-short, or vice versa when net-long).
* **Refinery Process Yardsticks (`FCC`, `HSK`, `HCK`, `Coking`):** Standardized benchmark refinery configurations used to value crudes and set marginal product prices:
  * **FCC (`Fluid Catalytic Cracking`):** Upgrades vacuum gasoil (`VGO`) into gasoline and middle distillates (`KeyInputs!A15:A29`).
  * **HSK (`Hydroskimming`):** Topping + reforming configuration (`Incremental FCC/HSK ROCE` on `KeyInputs`).
  * **HCK (`Hydrocracking`):** Deep-conversion unit cracking heavy gasoils into ultra-low-sulfur diesel (`ULSD`), jet fuel, or naphtha (`HCK naphtha revamp`, `2015 NWE HCK IRR`).
  * **Coking:** Thermally cracks vacuum residue into lighter distillates and petcoke (`Coking ICRF`).
* **Crack Spread & Gross Product Worth (`GPW`):** Economic margin (`$/bbl`) between weighted-average product value (`SUMPRODUCT(Yield_Vector, Product_Price_Vector)` on `NWE Cif` and `MED Cif`) and delivered crude cost plus variable operating and carbon compliance costs (`Op_Cost`, `Carbon`).
* **Import / Export Parity Switch:** Switches regional pricing between **Import Parity** (`Origin FOB + Freight`) and **Export Parity** (`Destination CIF - Freight`), driven by upstream supply/demand balance workbooks (`NWEDF202409.xlsx`, `MedDF202409.xlsx`).
* **EU ETS Carbon Pass-Through (`Carbon` sheet):** European Union Emissions Trading System compliance cost (`€/tCO2e` converted to `$/bbl`) above free allowances, controlled by interactive dropdown toggles in `Carbon!A5:A6`.
* **IMO Marine Bunker Fuels (`IMOfuels` sheet):** `0.1%S MGO`, `0.5%S VLSFO`, and `3.5%S HSFO` marine bunker blends whose prices depend on refined product spreads (`NWE Cif`, `MED Cif`) and feed back into marine tanker freight rates (`Freight`).

### Technical & Cloud Architecture Terms
* **Iterative Circular Equilibrium (`iterate="1"`, `iterateCount="10"`):** `Eulr202409.xlsx` contains intentional bidirectional cross-sheet feedback loops across `13` coupled calculation sheets (`357,708` formulas $\times 10$ passes = `3.57M` evaluations per run).
* **Ahead-of-Time (AOT) Vectorized Row Compilation (`357,708` Cells $\rightarrow$ `8,028` Equations):** Normalizing formulas into row-relative `R1C1` signatures compresses `357,708` cell formulas across `45–58` time columns (`1982–2050+`) into `8,028` row-level NumPy equations compiled into deterministic Python sheet evaluators (`< 150 ms` for all 10 passes on Cloud Run).
* **Hybrid Google Sheets Formula Split:** Keeps acyclic formulas (`KeyInputs` margin step-downs and internal cross-sheet formulas, `Yields` sum checks, `Info`, and `Checks` arbitrage diagnostics) **live and inspectable in Google Sheets**, while offloading the 10-pass circular pricing sheets, `6,745` `{=CSE}` array formulas, and `83,928` downstream `UPLOAD`/`Links out` staging formulas to Cloud Run and BigQuery.
* **3D `OverGridImage` Execution Deck:** Native styled cells on `KeyInputs!B2:N5` (and `Refresh BQML` cells on the BQML tabs) overlaid with programmatic 3D bevel PNG images assigned directly to Apps Script functions—eliminating fragile HTML5 sidebars or manual floating Drawings.
* **Pinned Trader Price Override Mask (`override_mask`):** When an analyst types a manual price into a calculated pricing sheet (`NWE Cif`, `MED Cif`, `NWE Fob`, `MED Fob`, `Crudes`, `IMOfuels`), `onGovernedSheetEdit` applies a subtle `#FEF3C7` amber fill (zero popups or hover notes), stores the coordinate in that spreadsheet's isolated Cloud Storage override mask (`gs://comm-model-mod-eulr-snapshots/overrides/{spreadsheet_id}.json`), and logs a `PINNED_PRICE_OVERRIDE` event to BigQuery so subsequent 10-pass solves hold that cell fixed until reverted with one click.

---

## 1. Executive Summary & Three Calculation Tiers

### Functional Purpose
`Eulr202409.xlsx` serves as the long-range valuation and refinery margin equilibrium model for the European oil and refined-products market (`1990–2050+`), pricing benchmark crude grades (`Dated Brent`, `Urals`, `Es Sider`, `Arab Light`, `Ekofisk`) and refined products (`LPG`, `Naphtha`, `Gasoline`, `Jet/Kero`, `EN590 Diesel`, `Gasoil`, `LSFO`, `HSFO`, `IMO Bunkers`) across **Northwest Europe (`NWE`)** and the **Mediterranean (`MED`)** on both **CIF** and **FOB** bases.

### Three Calculation Tiers (Consistent Across Platform Workbooks)
1. **Live Spreadsheet Formula Tier (`KeyInputs`, `Yields`, `Info`, `Checks`):**
   Retains acyclic, non-external spreadsheet formulas natively in Google Sheets (`~6,000+` live formulas, including `KeyInputs` refinery margin step-downs like `BA14 = BB14-0.25`, `Yields` `100%` column totals, and `Checks` cross-hub arbitrage rules), giving analysts transparent, editable in-sheet formulas with zero browser circular-loop lag.
2. **Cloud-Solver Equilibrium Tier (`KeyInputs!B2:N5` 3D Buttons $\rightarrow$ Cloud Run 10-Pass Vectorized Engine):**
   Executes all `8,028` compiled R1C1 row equations and `6,745` `{=CSE}` array formulas across 10 Gauss-Seidel passes in `< 150 ms` (`<= 1e-8` parity with desktop Excel), returning compact delta `Sheets.Values.batchUpdate` payloads in `< 2.0 seconds` while honoring active `#FEF3C7` Pinned Price Overrides.
3. **Time-Series ML & Generative AI Tier (`BigQuery ML` + `Vertex AI`):**
   - **3 Breakout `ARIMA_PLUS` Forecast Tabs (`Macro_BQML`, `Crudes_BQML`, `Freight_BQML`):** Train on `<= 2024` historical actuals to generate `2025–2050` statistical trajectories with 1-click 3D `Refresh BQML` buttons.
   - **Vertex AI Model Registry Surrogate:** Registers a `BQML` NWE/MED refinery crack-spread surrogate (`eulr-sheets-mod-margin-surrogate`) in Vertex AI Model Registry alongside an optional Vertex Custom Prediction container toggle (`ENABLE_VERTEX_REMOTE_PREDICT`).
   - **Vertex AI `gemini-3.8-flash` Attribution:** Generates executive cross-hub margin & arbitrage attribution directly on `Scenario_Comparison` after 4-way sweeps and populates `why_ai_summary` in `BQ_4Ws_Audit_Log`.

---

## 2. Empirical Anatomy & Target Tab Disposition (`24` Tabs Total)

### 2.1 Verified Workbook Telemetry (`Eulr202409.xlsx`)

| Metric | Verified Value in `Eulr202409.xlsx` | Architectural Disposition in `comm-model-mod` (`us-central1`) |
| :--- | :--- | :--- |
| **File Format & Size** | `9.16 MB` OpenXML `.xlsx` (`0` VBA macros) | Read-only baseline seed in `Eulr/seed/Eulr202409.xlsx`. |
| **Worksheet Count** | `20` (`19` visible + `1` `veryHidden` `shooju_addin`) | Retire `shooju_addin`; offload `UPLOAD` & `Links out` to BigQuery (`17` core tabs + `7` cloud/BQML tabs = **`24` Google Sheets tabs**). |
| **Grid Footprint** | `604,453` `<c>` cells (`2,236,876` bounding-box cells) | `22.4%` of Google Sheets' `10M`-cell limit (`> 7.7M` cells free headroom). |
| **Formula Footprint** | `357,708` formulas (`8,028` R1C1 row patterns, `6,745` `{=CSE}`) | Keep acyclic non-external formulas live on `KeyInputs`, `Yields`, `Info`, `Checks`; AOT-compile circular & `{=CSE}` equations on Cloud Run. |
| **Iterative Loop (`calcPr`)** | `iterate="1"`, `iterateCount="10"` | 10-pass Gauss-Seidel loop over `13` coupled sheets (including `ULSD-GO_spread_econs` inside the loop before `KeyInputs`). |
| **External SharePoint Links** | `13` active upstream workbooks (`14,162` formula cells, `0` missing `<v>`) | Seeded into `eulr_commodity_mod_governance.upstream_external_series` with full SharePoint URL/sheet/cell lineage + live `.xlsx` peer sync (`Uslr`, `Felr`, `Tankerlr`). |

### 2.2 Complete 24-Tab Google Sheets Layout

| Category | Tabs (`Count`) | Behavior in Google Sheets |
| :--- | :--- | :--- |
| **1. Live-Formula & Control Tabs** | `KeyInputs`, `Carbon`, `Yields`, `Info` (`4`) | `KeyInputs!B2:N5` hosts the **5-button 3D Execution Deck**; `KeyInputs`, `Yields`, and `Info` keep live acyclic formulas; `Carbon!A5:A6` hosts EU ETS dropdown switches while its circular body updates via Cloud Run. |
| **2. Cloud-Solved Equilibrium & Diagnostic Tabs** | `Input`, `Freight`, `Crudes`, `ULSD-GO_spread_econs`, `Op_Cost`, `NWE Cif`, `MED Cif`, `NWE Fob`, `MED Fob`, `IMOfuels`, `HCK naphtha revamp`, `2015 NWE HCK IRR`, `Checks` (`13`) | Updated via fast delta `Sheets.Values.batchUpdate` (`Checks` retains live non-external arbitrage formulas); manual price edits on pricing tabs highlight in `#FEF3C7` and pin across all 10 passes. |
| **3. Breakout BQML Forecast Tabs** | `Macro_BQML`, `Crudes_BQML`, `Freight_BQML` (`3`) | Horizontal `1990–2050` sheets (`<= 2024` actuals + `2025–2050` `ARIMA_PLUS` forecast), each with a 1-click 3D `Refresh BQML` button. |
| **4. Connected Sheets & Scenario Tabs** | `Upstream_Links_BQ`, `UPLOAD_BQ`, `BQ_4Ws_Audit_Log`, `Scenario_Comparison` (`4`) | Native Connected Sheets (`insertSheetWithDataSourceTable` + `setRawQuery`) for upstream links, `1,273` `UPLOAD` series, and `4-Ws` audit history; `Scenario_Comparison` renders the 4-way (`Base/Sens` $\times$ `Carbon`) matrix + `gemini-3.8-flash` attribution narrative. |

---

## 3. Detailed Functional Requirements

### 3.1 Pillar A: 10-Pass Vectorized Solver, SharePoint Portability & ML/AI

| Req ID | Requirement Title | Specification |
| :--- | :--- | :--- |
| **`FR-EULR-01`** | **10-Pass Vectorized Circular Equilibrium Solver** | Evaluate `Yields`, then run 10 Gauss-Seidel passes over `Input -> Freight -> Crudes -> ULSD-GO_spread_econs -> KeyInputs -> Op_Cost -> Carbon -> NWE Cif -> MED Cif -> NWE Fob -> MED Fob -> IMOfuels -> Links out`, followed by `HCK naphtha revamp`, `2015 NWE HCK IRR`, `Checks`, and `UPLOAD` (`<= 1e-8` baseline parity). |
| **`FR-EULR-02`** | **Vectorized `{=CSE}` Array & IRR Compilation** | Compile all `6,740` `Op_Cost` lookahead interpolation `{=CSE}` formulas and `5` `2015 NWE HCK IRR` formulas into vectorized NumPy operations. |
| **`FR-EULR-03`** | **SharePoint-Portable Upstream Link Hub & Peer `.xlsx` Sync** | Preserve exact `(sharepoint_url, external_workbook, source_sheet, source_cell_a1)` metadata in `upstream_external_series`, classify links into `ACTIVE_PEER_MODEL`, `SHARED_REFERENCE_DB`, and `FROZEN_LEGACY_PATH` (parameterized by `vintage`, e.g., `202409`), seed baseline `<v>` values for `<= 1e-8` parity, and support 1-click **Sync Upstream Peer Workbooks** reading updated cells from `Uslr202409.xlsx`, `Felr202409.xlsx`, and `Tankerlr202409.xlsx` in Argolis (swappable to SharePoint Graph in S&P). |
| **`FR-EULR-04`** | **3D `OverGridImage` Execution Deck (`KeyInputs!B2:N5`)** | Programmatically render 5 styled 3D bevel cell buttons on `KeyInputs!B2:N5` (mirrored in the `Commodity Modeling — EULR` menu): *Solve 10-Pass Equilibrium*, *Run 4-Way Scenario & Carbon Matrix*, *Sync Upstream Peer Workbooks*, *Revert Pinned Overrides*, and *Publish UPLOAD & Links Out*. |
| **`FR-EULR-05`** | **Parallel 4-Way Scenario & EU ETS Carbon Sweep** | Concurrently solve all 4 combinations (`Base/Sensitivity` $\times$ `EU ETS Carbon Off/On`) on Cloud Run and populate `Scenario_Comparison` with crack-spread and product price deltas plus a `gemini-3.8-flash` executive attribution summary. |
| **`FR-EULR-06`** | **3 Breakout BQML Tabs & Vertex AI Surrogate** | Deploy `ARIMA_PLUS` models backing `Macro_BQML`, `Crudes_BQML`, and `Freight_BQML` (each with a 3D `Refresh BQML` button), plus a `LINEAR_REG` / `BOOSTED_TREE_REGRESSOR` NWE/MED crack-spread surrogate registered in **Vertex AI Model Registry** (`eulr-sheets-mod-margin-surrogate`). |
| **`FR-EULR-07`** | **Zero-Formula `UPLOAD` (`1,273` Series) & `Links out` (`234` Series) Publishing** | Materialize `UPLOAD` (all 37 metadata columns `A:AK` + annual series `1990–2050`) and `Links out` directly into BigQuery (`eulr_upload_series`, `eulr_links_out`), surfaced via `UPLOAD_BQ` Connected Sheet and retiring `shooju_addin`. |

### 3.2 Pillar B: Silent Distributed `4-Ws` Governance, Pinned Overrides & Rollback

| Req ID | Requirement Title | Specification |
| :--- | :--- | :--- |
| **`FR-EULR-08`** | **Subtle `#FEF3C7` Pinned Trader Price Overrides (No Popups/Notes)** | Manual numeric edits on pricing sheets (`Crudes`, `NWE Cif`, `MED Cif`, `NWE Fob`, `MED Fob`, `IMOfuels`) apply a `#FEF3C7` amber background (zero popups or hover notes), persist per `spreadsheet_id` in GCS (`override_mask`), hold pinned across all 10 passes, and revert cleanly in 1 click via **Revert Pinned Overrides**. |
| **`FR-EULR-09`** | **Silent Distributed `4-Ws` Governance (`onEdit` + `onChange`)** | Self-install `onGovernedSheetEdit` and `onGovernedSheetChange` on both the central sheet and personal `File -> Make a copy` workbooks; suppress routine switch tweaks (`KeyInputs!AT10:BT10`, `Carbon!A5:A6`) while streaming formula changes (`MANUAL_OVERRIDE`), label renames (`HEADER_OR_LABEL_MODIFIED`), structural edits (`ROW_INSERTED`, `SHEET_ADDED`), `PINNED_PRICE_OVERRIDE`, and `SOLVER_RUN` events (enriched with `gemini-3.8-flash` `why_ai_summary`) to `BQ_4Ws_Audit_Log`. |
| **`FR-EULR-10`** | **Three-Tier Rollback & Arbitrage Diagnostics** | Support (1) 1-click Pinned Override reversion, (2) surgical single-cell rollback via `before_formula` / `before_value` in `audit_events`, and (3) full-workbook point-in-time recovery via `copy_location_url` + `when_event_utc` in Google Sheets **File > Version history**; evaluate all `180` `Checks` parity rules on every solve. |

---

## 4. Non-Functional Requirements (NFRs)

* **`NFR-EULR-01` (10-Pass Numerical Parity):** Max relative error $\le 10^{-8}$ across all `19` active sheets (`1990–2050+` columns) against `Eulr202409.xlsx` cached `<v>` baseline values.
* **`NFR-EULR-02` (Compute & Delta Sync Latency):** `< 250 ms` p95 Cloud Run 10-pass compute; `< 2.0 seconds` p95 end-to-end Google Sheets round-trip via delta `Sheets.Values.batchUpdate`.
* **`NFR-EULR-03` (100% Serverless & Isolated GCP Footprint):** Deployed in `comm-model-mod` (`us-central1`, Gemini in `global`/`us`) with `app = "eulr-sheets-mod"`, zero idle AlloyDB instances, and zero impact on `brazil-power-v13`.
