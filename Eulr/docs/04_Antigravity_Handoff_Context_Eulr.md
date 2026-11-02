# Antigravity Handoff & Empirical Workbook Forensics: European Long-Range Crude & Refined Products Model (`Eulr202409.xlsx`)

| Handoff Metadata | Details |
| :--- | :--- |
| **Document ID** | `ENT-HANDOFF-CONTEXT-EULR-004B` (v2.0 — Verified Against `Eulr202409.xlsx` & `LR202409` Peer Workbooks) |
| **Companion Documents** | [`01_PRD_Eulr_Google_Sheets.md`](./01_PRD_Eulr_Google_Sheets.md), [`02_Design_Document_Eulr_Google_Sheets.md`](./02_Design_Document_Eulr_Google_Sheets.md), [`03_Implementation_Plan_Eulr_Google_Sheets.md`](./03_Implementation_Plan_Eulr_Google_Sheets.md), [`06_Pilot_Workbooks_Demo_Scripts_Google_Sheets.md`](./06_Pilot_Workbooks_Demo_Scripts_Google_Sheets.md) |
| **Seed & Reference Files** | Seed: `Eulr/seed/Eulr202409.xlsx` (read-only) \| Peer References (`Eulr/references/`, gitignored): `Uslr202409.xlsx`, `Felr202409.xlsx`, `Tankerlr202409.xlsx`, `Canlr202409.xlsx`, `Callr202409.xlsx`, `Latinlr202409.xlsx`, `LAMLR202409.xlsx` |
| **Frontend Architecture** | **Google Sheets (`24` Tabs)** + **Bound Apps Script (`V8`)** + **3D `OverGridImage` Buttons (`KeyInputs!B2:N5`)** + **Native Connected Sheets (`insertSheetWithDataSourceTable`)** |
| **Backend & AI Stack** | **GCP Project `comm-model-mod` (`us-central1`)** — **Cloud Run** (`eulr-equilibrium-gateway`) + **BigQuery & BigQuery ML (`eulr_commodity_mod_governance`)** + **Vertex AI (`gemini-3.8-flash` + Model Registry + Custom Prediction Toggle)** + **Cloud Storage (`gs://comm-model-mod-eulr-snapshots`)** |

---

## 1. Empirical Anatomy Verified Directly Against `Eulr202409.xlsx`

* **File Format & Size:** OpenXML `.xlsx` (`9.16 MB`, `0` VBA macros).
* **Worksheets & Bounding Box:** `20` worksheets (`19` visible + `1` `veryHidden` `shooju_addin` `A1:B1` retired). Total XML `<c>` elements: `604,453` (`438,412` value/formula cells). Total rectangular bounding-box cells across all 20 sheets: **`2,236,876` cells** (`22.4%` of Google Sheets' `10,000,000`-cell limit).
* **Formulas & R1C1 Vectorization:** `357,708` formula cells (`168,965` explicit/master `<f>` tags + `188,743` shared slave cells; `6,745` `{=CSE}` array formulas), compressing horizontally across time columns into **`8,028` unique R1C1 row equations**.
* **Excel Iterative Settings (`xl/workbook.xml` `<calcPr>`):** `iterate="1"`, `iterateCount="10"`, `calcId="191029"`.
* **Function Catalog (Zero Exotic Add-Ins):** `IF`, `COLUMN`, `ISNUMBER`, `MIN`, `MAX`, `SUMPRODUCT`, `SUM`, `OFFSET`, `AVERAGE`, `OR`, `VLOOKUP`, `AND`, `ISERROR`, `HLOOKUP`, `TREND`, `TRANSPOSE`, `IRR`, `CONCATENATE`, `DATE`, `YEAR`, `ROUND`, `ROUNDDOWN`, `LEFT`.
* **External Workbook Links (`0` Missing `<v>` Values):** `13` active external workbooks referenced across `14,162` formula cells, **100% of which carry valid cached `<v>` values** inside `Eulr202409.xlsx`.

---

## 2. Four Critical Empirical Discoveries From Our XML & Peer-Workbook Audit

1. **`ULSD-GO_spread_econs` Is Part of the Circular Loop (Not Pre-Loop Acyclic):**
   - `ULSD-GO_spread_econs` depends on `Input` (`46` refs) and **`NWE Cif` (`184` refs)**, while `KeyInputs` depends on `ULSD-GO_spread_econs` (`138` refs), and `NWE Cif` depends on `KeyInputs` (`158` refs).
   - **Rule:** Evaluate `ULSD-GO_spread_econs` **inside** each of the 10 Gauss-Seidel passes right before `KeyInputs`:
     `Input -> Freight -> Crudes -> ULSD-GO_spread_econs -> KeyInputs -> Op_Cost -> Carbon -> NWE Cif -> MED Cif -> NWE Fob -> MED Fob -> IMOfuels -> Links out`.

2. **Exact Hybrid Formula Split & Saved Baseline Toggles:**
   - `Yields` (`137` formulas, `0` cross-sheet/external refs) and `Info` (`1` formula) are 100% pure local formulas.
   - `KeyInputs` (`987` formulas: `184` local step-downs like `BA14 = BB14-0.25`, `513` internal cross-sheet formulas like `AT15 = AT18-Carbon!P10+BV19`, and `102` `[22] New LPD` external links) and `Checks` (`8,053` formulas, `96` external links) have **zero circular loops once `NWE Cif`, `MED Cif`, `Carbon`, etc. hold Cloud Run-solved values**—so all non-external formulas on `KeyInputs`, `Yields`, `Info`, and `Checks` remain **live Google Sheets formulas**.
   - **Saved Baseline State in `Eulr202409.xlsx`:** `KeyInputs!AT10:BT10 = 0` (`Base Case`), while **`Carbon!A5` is saved as `'Sensitivity with EU ETS cost and pass-through'`** (`Carbon!AS2`) and `Carbon!A6 = 'Variable cost increase and product allocation'` (`Carbon!AS5`). Note also that `Carbon` aligns `2024` in Column `P` (`P7=2024`, `Q7=2025`), whereas `KeyInputs` and `NWE Cif` align `2024` in Column `AT` (`AT7=2024`, `AU7=2025`).

3. **Real-World Upstream Peer Timing Deltas (`Uslr`, `Felr`, `Tankerlr`) & SharePoint Portability:**
   - Comparing `Eulr202409.xlsx` cached `<v>` values against the actual peer files in `references/`:
     - `[14] Uslr202409.xlsx`: `1,969` direct links match `<= 1e-8`; **`971` forecast cells have newer values** (up to `2.96%` delta, e.g., `Input!AU15` cached `3.9900` vs `Uslr` `'Links Out'!AU13 = 3.9982`).
     - `[18] Felr202409.xlsx`: `121` exact, **`106` updated cells** (`max_rel = 5.6e-5`).
     - `[19] Tankerlr202409.xlsx`: `38` exact, **`27` updated cells** (`max_rel = 2.2e-4`).
   - **Rule:** Seed `upstream_external_series` initially in `eulr_baseline_cached` mode so `<= 1e-8` parity tests against `Eulr202409.xlsx` are exact, and expose **Sync Upstream Peer Workbooks** (`peer_xlsx` mode in Argolis $\leftrightarrow$ `sharepoint_graph` mode in S&P) to ingest those `1,104` updated peer cells live and re-solve European equilibrium prices.
   - Classify all external links by `vintage` (`202409`) and health tier: `ACTIVE_PEER_MODEL`, `SHARED_REFERENCE_DB` (`PSD_*.xlsb`, `Worldscale.xlsx`), and `FROZEN_LEGACY_PATH` (legacy local/UNC paths).

4. **Empty Top-Left Region on `KeyInputs` for 3D Action Buttons:**
   - `KeyInputs` has `90` parameter cells in `AH2:AQ3`, leaving **`KeyInputs!A1:AF6` completely empty**. Place the 5-button **3D `OverGridImage` Execution Deck** at **`KeyInputs!B2:N5`** right above Row 7 Year headers and Row 10 Sensitivity Switches.
