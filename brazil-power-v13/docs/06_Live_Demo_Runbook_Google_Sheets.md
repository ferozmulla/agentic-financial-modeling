# Live Demo Runbook & Functional Guide: Enterprise Commodity Modeling — Google Sheets Modernization & Structural Governance Platform

| Document Metadata | Details |
| :--- | :--- |
| **Document ID** | `ENT-DEMO-SHEETS-MOD-006` |
| **Companion Documents** | `docs/01_PRD_Google_Sheets.md`, `docs/02_Design_Document_Google_Sheets.md`, `docs/03_Implementation_Plan_Google_Sheets.md`, `docs/GCP_System_Architecture_Diagram_Google_Sheets.png` |
| **Central Google Sheet** | `Regional Power Generation Techno-Economic Model — Brazil v13 (Governed)` (`1apbos5xVpK4yBLiRFxQqAEyPVNkkYQ2ZvgAASibYYJI`) |
| **Cloud Run Solver & Governance Gateway** | `https://sheets-commodity-mod-gateway-1024543888590.us-central1.run.app` (`comm-model-mod`, `us-central1`) |
| **BigQuery Governance Dataset** | `comm-model-mod.sheets_commodity_mod_governance` (`audit_events`, `vw_audit_4w_summary`, `vw_manual_overrides`) |

---

## 1. Executive Functional Overview: How the Workbook Works

The **Regional Power Generation Techno-Economic Model** evaluates the project finance, thermal dispatch, and breakeven electricity tariff (**LCOE** — Levelized Cost of Energy) across **12 Brazilian power generation technologies** (`_01_CF` Natural Gas CCGT through `_12_CF` Commercial Solar PV Distributed Generation).

Functionally, the analysis in the workbook is divided into **two distinct layers**:
1. **Layer 1: Live Formula-Driven Analysis (Happens Automatically *Outside* the Buttons via 15,961 Native Formulas)**
2. **Layer 2: Button-Driven "Reverse Goal-Seek" Sweeps (Triggered by the 31 Solver Buttons)**

---

### Layer 1: What Happens *Outside* the Buttons (15,961 Live Spreadsheet Formulas)

Even without clicking any button, the 22 tabs operate as an interconnected **45-Year Project Finance & Dispatch Model**:

* **Single-Scenario 45-Year Discounted Cash-Flow (DCF) & IRR (`_01_CF` to `_12_CF`):**
  * Each technology tab models 5 construction years (`Cols B:F`) and up to 40 operating years (`Cols G:AT`, `Rows 20:63`).
  * Whenever an analyst edits a technology assumption on `General!C5:N40`, changes an active scenario multiplier in `H6:H12` on a technology tab, or types a trial electricity price (`R$/MWh`) into cell **`B16` (`price_lst`)**, **native Google Sheets formulas immediately recalculate**:
    * Annual power generation (MWh), gross revenue, Brazilian revenue taxes (`PIS/COFINS`, `ICMS`), fuel costs, fixed and variable O&M, sector charges (`P&D`, `TFSEE`), EBITDA, depreciation, debt service (principal + interest), corporate income taxes (`IRPJ/CSLL`), annual Free Cash Flow (`Row 63`), and the resulting **Project IRR in cell `B18` (`=IRR(B63:AT63)`)**.
* **Engineering Bottom-Up Capex Breakdown (`_CAPEX 01`):**
  * Calculates plant construction, equipment, and civil engineering costs via standard formulas.
* **Thermal Dispatch & Auction Index (`CVU_GF` & Row 81 / Row 105 on Thermal Tabs):**
  * Uses polynomial regression coefficients on `CVU_GF` to calculate a thermal plant's **Variable Unit Cost (`CVU`)**, expected dispatch factor (**Physical Guarantee / `GF`**), and **Cost-Benefit Index (`ICB`)** for Brazilian power auctions.
* **Executive Summary Tables & Charts (`Output_1`, `Output_2`, `Output_3`):**
  * Live formulas and charts that aggregate and visualize the outputs from `_01_CF`–`_12_CF`.

---

### Layer 2: Why the 31 Buttons Exist (Iterative "Reverse Goal-Seek" Across 854 Scenarios)

Standard spreadsheet formulas calculate **forward**:
$$\text{Given Electricity Price } (\texttt{B16}) \xrightarrow{\text{Formulas}} \text{Calculate Project IRR } (\texttt{B18})$$

However, energy economists need to solve the problem **in reverse** across hundreds of sensitivity scenarios:
$$\text{Target Hurdle IRR } (\texttt{B18} = 12.00\%) \xrightarrow{\text{Iterative Goal-Seek Solver}} \text{Find Required Breakeven Price / LCOE } (\texttt{B16})$$

Because spreadsheet formulas cannot loop through hundreds of scenarios, overwrite inputs, run an iterative root-finder (`GoalSeek` + discrete stepping) until `IRR = 12.00%`, and record each result into a static table without creating circular references, the **31 buttons** on `General!B42:N52` automate four families of multi-scenario sweeps:

| Button Group on `General` | Count | What the Button Does Functionally | Where Results Are Written |
| :--- | :---: | :--- | :--- |
| **1. Tornado IRR Suite** (`Tornado 1` .. `Tornado 12` in `Row 42`) | 12 buttons | Tests **21 variations** per technology (Low / Base / High across 7 parameters: Capex, Fuel/CF, Efficiency, O&M, Debt %, Interest Rate, Economic Life), solving for the breakeven LCOE price (`B16`) or fixed revenue (`C16`) at each point. | `_01_CF`..`_12_CF` cells **`E6:G12`** (feeds Tornado charts on `Output_1`) |
| **2. Fuel / CVU Sweeps** (`Fuel/CVU1` .. `Fuel/CVU12` in `Row 45`) | 12 buttons | Sweeps **10 levels** of Fuel Cost or Capacity Factor (`B70:B79`), solving the breakeven LCOE for each point. | `_01_CF`..`_12_CF` cells **`C70:C79`** (feeds curves on `Output_2`) |
| **3. 1D & 2D Sensitivity Matrices** (`BI LCOE`, `Capex vs IRR`, `Price vs IRR` in `Rows 48 & 52`) | 6 buttons | Runs 10-point 1D sweeps or **10 $\times$ 10 = 100-solve 2D bivariate grids** (varying Capex $\times$ Capacity Factor or Fuel simultaneously for Biomass, Wind, Solar, and Hydro). | 1D/2D matrix blocks in **`Rows 82..114`** on `_02_CF`, `_04_CF`, `_05_CF`, `_06_CF` |
| **4. Master Multi-Decade Forecast** (`Forecast LCOE` in `B43`) | 1 master button | Loops across **23 years (2018–2040)** using the long-term cost trajectories (`LT Capex`, `LT Fuel`, `LT CF`) across 8 technologies (**184 solves in one click**). | **`Output_3!B9:J31`** (23-year LCOE & ICB forecast table) |

---

### Executive Talk Track Summary (Leadership Brief)

* **Functional Purpose of the Brazil Workbook:**
  This workbook serves as a techno-economic valuation and dispatch model for Brazil's power sector, evaluating 12 utility-scale and distributed power generation technologies (including Natural Gas CCGT, Biomass, Onshore Wind, Solar PV, Small Hydro, and Coal) over a 45-year asset lifecycle. It enables analysts to compare capital costs, Brazilian tax and debt structures, and thermal dispatch rules to determine the breakeven electricity tariff (**LCOE**) and auction Cost-Benefit Index (**ICB**) needed for capacity expansion and investment decisions.
* **Financial Insights Across the Three Calculation Tiers:**
  1. **Native Formula-Based Calculations (`15,961` formulas):** Compute forward project-finance fundamentals for a single scenario—translating capital drawdowns, fuel burn, O&M, Brazilian tax regimes (`PIS/COFINS`, `ICMS`, `IRPJ/CSLL`), debt service, and thermal Physical Guarantee (`GF`) curves into annual Free Cash Flows and the resulting **Project IRR**.
  2. **Macro / Cloud-Solver Calculations (`31` 3D buttons, `854` outputs):** Solve the capital-budgeting problem *in reverse* across hundreds of sensitivity scenarios—finding the exact breakeven electricity price (**LCOE**) or auction **ICB** required to hit a target **12% hurdle IRR** across 7-parameter Tornado rankings, fuel sweeps, 100-point bivariate Capex-vs.-CF matrices, and 23-year (`2018–2040`) technology outlooks.
  3. **Time-Series ML Calculations (`LT_Capex_BQML`, `LT_Fuel_BQML`, `LT_CF_BQML`, `BQML_LCOE_Surrogate`):** Use BigQuery ML (`ARIMA_PLUS`) via Connected Sheets to forecast multi-decade (`2026–2040`) structural cost learning curves for plant Capex, fuel prices, and renewable capacity factors from `<=2025` historical actuals, providing data-driven long-term input trajectories and instant `ML.PREDICT` LCOE what-if estimates.

---

## 2. Translation Matrix: Legacy Excel (`.xlsm`) vs. Modernized Google Sheets + GCP

| Capability | Original Legacy Excel Workbook (`.xlsm`) | Modernized Google Sheets + Google Cloud Platform |
| :--- | :--- | :--- |
| **1. Forward Cash-Flow & IRR Model (`15,961` formulas across 22 tabs)** | Native Excel formulas on `_01_CF`–`_12_CF`, `General`, `CVU_GF`, `_CAPEX 01`, and `Output_1`–`Output_3`. | **100% preserved as native Google Sheets formulas** across the exact same 22 tabs and cell coordinates. |
| **2. The 31 Button Solvers (`854` Goal-Seek outputs)** | Single-threaded desktop **VBA Macros (`Module1`–`Module3`)** mutating cells one by one on the user's laptop (`GoalSeek` + `0.001` stepping loop), freezing Excel for minutes. | **Google Apps Script + Cloud Run Vectorized Python Solver** (`CombinedSheetScript.gs` $\rightarrow$ `POST /v1/solve/{macro_name}`). Solves in milliseconds in the cloud with **$\le 10^{-8}$ numerical parity** to legacy VBA and writes results back to the exact same cells. |
| **3. Long-Term Cost Curve Forecasting & ML Surrogates (Connected Sheets + BQML)** | Static, manually pasted numbers on `LT Capex`, `LT Fuel`, and `LT CF` (`2018–2040` only); no warehouse ML integration. | **Live BQML Tabs (`LT_Capex_BQML`, `LT_Fuel_BQML`, `LT_CF_BQML`, & `BQML_LCOE_Surrogate`):** Links directly to BigQuery ML **`ARIMA_PLUS` time-series forecasts (`2026–2040`)** and a **Vertex AI–registered BQML LCOE Surrogate model (`bqml_lcoe_surrogate_v1`)**, carrying over automatically to every copy. |
| **4. Analyst Workflow (`File -> Make a copy`)** | Analysts emailed `.xlsm` files around (`v12_final_RJEB.xlsm`); zero visibility into who changed what across copies. | Analysts work naturally via **`File -> Make a copy`** in Google Drive, and the bound Apps Script, 31 3D cell buttons, and Connected Sheets / BQML tabs carry over automatically to every copy. |
| **5. Structural Governance & Audit Trail (`4-Ws`)** | Manual text notes typed into a `Version Control` tab; no detection of overwritten formulas or altered headers. | **Silent Real-Time BigQuery Change Log (`audit_events`, `vw_audit_4w_summary`, & Connected Sheet `BQ_4Ws_Audit_Log`):** Automatically tracks **Formula Overrides/Edits**, **Table Header/Label Changes**, and **Row/Column/Sheet Structural Changes** across the central sheet and all personal copies (logging *Who*, *What*, *When*, *Before/After*, *Copy Name*, and *Drive URL*), while ignoring routine scenario input tweaks. |

---

## 3. Step-by-Step 5-Minute Live Demo Script

### Pre-Demo Browser Tabs to Have Open
1. **Tab 1:** Your Google Sheet copy (or the central sheet `Regional Power Generation Techno-Economic Model — Brazil v13 (Governed)`).
2. **Tab 2:** BigQuery Console in project `comm-model-mod` with the `vw_audit_4w_summary` SQL query ready to run (or the **`BQ_4Ws_Audit_Log`** Connected Sheet tab right inside the workbook).
3. **Tab 3 (Optional Reference):** The system architecture diagram (`docs/GCP_System_Architecture_Diagram_Google_Sheets.png`).

---

### Minute 1: The Model & Live Formula Layer (Analysis *Outside* the Buttons)
* **Where to be:** Open the Google Sheet on the **`General`** tab (`Rows 5–40`), then click into **`_01_CF`** (Natural Gas CCGT).
* **What to show:**
  1. On **`General`**, point out columns **`C` through `N`** (`C5:N40`), representing the 12 Brazilian power generation technologies (Gas CCGT, Biomass, Wind, Solar Utility, Small Hydro, Coal, and Distributed Solar).
  2. Click into **`_01_CF`** and show the 45-year Discounted Cash-Flow table (`Cols B:AT`, `Rows 20:63`), the trial electricity price in **`B16`** (`price_lst`), and the Project IRR formula in **`B18`** (`=IRR(B63:AT63)`).
* **Talk Track:**
  > *"This model evaluates the techno-economic viability of 12 power generation technologies across a 45-year cash-flow horizon. All 15,961 formulas across the 22 tabs were migrated directly from Excel into native Google Sheets formulas. For any single scenario, standard spreadsheet formulas do the work automatically: if we change an assumption or type a trial electricity price into `B16`, the 45-year cash flows, Brazilian tax schedules, thermal dispatch regression (`CVU_GF`), and Project IRR in `B18` recalculate immediately."*

---

### Minute 2: The Distributed Analyst Workflow (`File -> Make a copy`) & Connected Sheets + BQML
* **Where to be:** In the Google Sheet menu bar (`File > Make a copy`), then click **`LT_Capex_BQML`**, **`LT_Fuel_BQML`**, **`LT_CF_BQML`**, and **`BQML_LCOE_Surrogate`** at the bottom tab bar.
* **What to show:**
  1. Show that analysts create their own working copy in Google Drive (`File > Make a copy`) to run scenarios independently.
  2. Click **`LT_Capex_BQML`** (right next to `LT CF`) to show the exact `LT Capex` format populated dynamically via Connected Sheets (`2018–2025` Historical Actuals + blue-highlighted `2026–2040` BigQuery ML `ARIMA_PLUS` Forecasts, with the **`Refresh BQML`** button in `M1`).
  3. Click **`BQML_LCOE_Surrogate`** to show `ML.PREDICT` results from `bqml_lcoe_surrogate_v1` (registered in the Vertex AI Model Registry) alongside exact solver LCOEs.
* **Talk Track:**
  > *"Unlike isolated Excel files where long-term trajectories (`LT Capex`, `LT Fuel`, `LT CF`) had to be manually copy-pasted, Google Sheets connects natively to BigQuery ML via Connected Sheets. Here in `LT_Capex_BQML`, `LT_Fuel_BQML`, and `LT_CF_BQML`, our `ARIMA_PLUS` model forecasts the `2026–2040` curves live from BigQuery while preserving the exact layout and formatting of the workbook, and `BQML_LCOE_Surrogate` surfaces ML predictions from our Vertex AI–registered surrogate model. Best of all, when an analyst selects `File > Make a copy`, the bound Apps Script, all solver buttons, and all Connected Sheets links carry over automatically."*

---

### Minute 3: Cloud-Accelerated Goal-Seek Solvers (What the 31 Buttons Do)
* **Where to be:** On the **`General`** tab (`Rows 42–52`) of your copy.
* **What to click & show:**
  1. **Click `Tornado 5` (`G42` — Utility Solar) or `Tornado 1` (`C42` — Gas CCGT):**
     * Point to the bottom-right toast notification showing the 21 solves completing on Cloud Run.
     * Click into **`_05_CF`** (or **`_01_CF`**) to show the 21 solved breakeven prices populated in **`E6:G12`**, and click **`Output_1`** to show the updated Tornado chart.
  2. **Click `Forecast LCOE` (`B43` — Master Multi-Decade Forecast):**
     * Click into **`Output_3`** (`B9:J31`) to show the 23-year (2018–2040) $\times$ 8-technology LCOE and Cost-Benefit Index (`ICB`) forecast table (184 solves in one click).
* **Talk Track:**
  > *"Here is why the 31 buttons exist: while spreadsheet formulas calculate IRR forward from a given price, energy economists need to solve the problem in reverse—finding the exact breakeven electricity price (`B16`) that yields a 12.00% target IRR across 854 different sensitivity scenarios. In legacy Excel, clicking these buttons ran desktop VBA `GoalSeek` loops cell-by-cell, locking up Excel. In Google Sheets, clicking a button sends the current sheet inputs to our vectorized Python solver on Cloud Run, which solves all 21 Tornado points or all 184 multi-decade forecast points in milliseconds with $\le 10^{-8}$ numerical parity to the original VBA, and writes the results back to the sheet."*

---

### Minute 4: Silent Structural Governance vs. Routine Scenario Edits
* **Where to be:** In your personal copy on **`General`** and **`_01_CF`**.
* **Perform 4 quick actions live:**
  1. **Routine Scenario Input (Ignored):** On **`General`**, change a normal numeric assumption such as **`C16`** (Capacity Factor, e.g., `0.50` $\rightarrow$ `0.55`).
  2. **Formula Override (`CRITICAL`):** Switch to **`_01_CF`**, click a formula cell in the cash-flow grid (e.g., **`G23`** or **`H23`**), and overwrite the formula with a hardcoded number (e.g., `25000`).
  3. **Table Header Edit (`WARNING`):** On **`_01_CF`**, change a table header cell (e.g., **`B2`** from `"Gas"` to `"Petrol"`).
  4. **Spreadsheet Metadata / Structure Edit (`WARNING`):** Right-click a row on **`_01_CF`** (e.g., Row 15) and click **Insert 1 row above**.
* **Talk Track:**
  > *"Now let's look at governance across distributed analyst copies. First, I changed a normal scenario input on `General!C16`—that's routine analysis, so we don't want to clutter the audit log. Next, on `_01_CF`, I made three structural changes: I overwrote a live cash-flow formula with a hardcoded number, I renamed a table header in `B2`, and I inserted a new row. Notice there were zero popups interrupting the analyst's workflow—everything is classified and logged silently in the background."*

---

### Minute 5: Reviewing the 4-Ws Audit Log in BigQuery (or via Connected Sheets)
* **Where to be:** Switch to the **`BQ_4Ws_Audit_Log`** Connected Sheet tab and click **Refresh** (or switch to **Tab 2: BigQuery Console**):
  ```sql
  SELECT
    FORMAT_TIMESTAMP('%Y-%m-%d %H:%M:%S UTC', when_event_utc) AS event_time_utc,
    copy_name,
    sheet_name,
    cell_coord,
    what_change_type,
    severity,
    before_formula,
    before_value,
    after_value,
    who_google_user,
    copy_location_url
  FROM `comm-model-mod.sheets_commodity_mod_governance.vw_audit_4w_summary`
  ORDER BY when_event_utc DESC
  LIMIT 10;
  ```
* **What to highlight in the query results:**
  1. **Zero Noise:** The routine scenario input edit (`General!C16`) was automatically suppressed.
  2. **Complete 4-Ws Lineage:** The three structural edits appear at the top:
     * `MANUAL_OVERRIDE` (`CRITICAL`) showing the exact overwritten formula (`before_formula`), old value, and hardcoded new value.
     * `HEADER_OR_LABEL_MODIFIED` (`WARNING`) showing the header change (`"Gas"` $\rightarrow$ `"Petrol"`).
     * `ROW_INSERTED` (`WARNING`) showing the structural sheet mutation.
  3. **Distributed Copy Traceability:** Every row captures **who** made the change (`who_google_user`), **which personal copy** it happened in (`copy_name`), and the **direct Google Drive URL** (`copy_location_url`) to open that exact copy.
  4. **Surgical & Full-Workbook Rollback:** If an edit is undesired, `before_formula` / `before_value` allows immediate single-cell restoration, while opening `copy_location_url` and matching `when_event_utc` in Google Sheets **File > Version history** (`Cmd + Option + Shift + H`) provides full point-in-time sheet recovery.

