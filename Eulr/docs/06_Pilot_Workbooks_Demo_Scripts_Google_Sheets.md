# Executive Live Demo Runbook: European Long-Range Crude & Refined Products Model (`Eulr202409` on Google Sheets & Google Cloud)

| Runbook Metadata | Details |
| :--- | :--- |
| **Document ID** | `ENT-DEMO-RUNBOOK-EULR-006` (v2.0 — Aligned with Refined Serverless & 3D Button Deck Architecture) |
| **Target Duration** | `6–8 Minutes` |
| **Target GCP Project** | `comm-model-mod` (`us-central1`), Dataset: `eulr_commodity_mod_governance`, AI Model: `gemini-3.8-flash` |
| **Target Audience** | Engineering Leadership, Product Management, Oil & Refined Products Analysts & Traders |

---

## Executive Talk Track Summary (Leadership Brief)

1. **Functional Purpose of the `Eulr` Workbook:**
   This workbook serves as the long-range valuation and refinery margin equilibrium model for the European crude oil and refined-products market (`1990–2050+`), pricing benchmark crudes (`Dated Brent`, `Urals`, `Arab Light`) and refined products (`Gasoline`, `Jet/Kero`, `EN590 Diesel`, `Gasoil`, `LSFO/HSFO`, `IMO Bunkers`) across **Northwest Europe (`NWE`)** and the **Mediterranean (`MED`)** on both **CIF** and **FOB** bases while interconnecting with global peer models (`Uslr`, `Felr`, `Tankerlr`).
2. **Financial Insights Across the Three Calculation Tiers:**
   - **Spreadsheet Formula Tier (`KeyInputs`, `Yields`, `Checks`):** Keeps ~6,000+ acyclic margin step-downs (`BA14 = BB14-0.25`), refinery yield checks (`100%`), and cross-hub arbitrage rules live and inspectable in Google Sheets with zero browser lag.
   - **Cloud Equilibrium Tier (`KeyInputs!B2:N5` 3D Buttons $\rightarrow$ Cloud Run 10-Pass Engine):** Solves `357,708` coupled formulas (`8,028` vectorized R1C1 equations + `6,745` `{=CSE}` arrays) across **10 circular Gauss-Seidel passes** in `< 150 ms` (`<= 1e-8` Excel parity), honoring trader `#FEF3C7` **Pinned Price Overrides** and running parallel 4-way (`Base/Sensitivity` $\times$ `EU ETS Carbon`) sweeps.
   - **BigQuery ML & Vertex AI Tier (`Macro_BQML`, `Crudes_BQML`, `Freight_BQML` + `gemini-3.8-flash`):** Generates data-driven `2025–2050` `ARIMA_PLUS` trajectories for macro deflators, crude differentials, and tanker rates, registers a crack-spread surrogate in **Vertex AI Model Registry**, and uses **`gemini-3.8-flash`** to explain cross-hub margin shifts and `4-Ws` governance events.

---

## Pre-Demo Browser Tab Setup
* **Tab 1:** The **EULR Governed Google Sheet** opened to **`KeyInputs`** (showing the **5-button 3D Execution Deck** at `KeyInputs!B2:N5`).
* **Tab 2:** **Google Cloud Console — BigQuery Studio** (`comm-model-mod:eulr_commodity_mod_governance`) & **Vertex AI Model Registry**.

---

## Minute-by-Minute Walkthrough

### Minute 1 — Control Switchboard (`KeyInputs`), Live Formulas & Baseline Prices
1. On **`KeyInputs`**, point out the **5-button 3D `OverGridImage` Execution Deck** right at `KeyInputs!B2:N5` (*Solve 10-Pass Equilibrium*, *Run 4-Way Scenario & Carbon Matrix*, *Sync Upstream Peer Workbooks*, *Revert Pinned Overrides*, *Publish UPLOAD & Links Out*).
2. Highlight **Row `7`** (`AT7=2024`, `AU7=2025`, `AV7=2026`), **Row `10`** (`AT10:AV10 = 0`, Base Case), and live spreadsheet formulas such as **`KeyInputs!AT15`** (`=AT18-Carbon!P10+BV19` $\rightarrow$ `$2.31/bbl`) and **`KeyInputs!BA14`** (`=BB14-0.25` $\rightarrow$ `$9.65/bbl`).
3. Click **`NWE Cif`** (`Rows 115–131`, Column `AU` for `2025`): show baseline CIF ARA prices (`Naphtha = $615.47/mt`, `Euro Gasoline = $711.33/mt`, `Jet/Kero = $765.29/mt`, `Diesel EN590 = $716.40/mt`, `LSFO 1% = $457.69/mt`).

### Minute 2 — SharePoint Portability & Live Upstream Peer Sync (`Upstream_Links_BQ`)
1. Open **`Upstream_Links_BQ`** (Connected Sheet over `vw_upstream_links_health`): point out preserved SharePoint URLs, exact cell coordinates across the 13 external workbooks, `vintage_tag = '202409'`, and the 3 link-health tiers (`ACTIVE_PEER_MODEL`, `SHARED_REFERENCE_DB`, `FROZEN_LEGACY_PATH`).
2. Return to **`KeyInputs`** and click the **`Sync Upstream Peer Workbooks`** 3D button: Cloud Run ingests the `1,104` updated cells from `Uslr202409.xlsx`, `Felr202409.xlsx`, and `Tankerlr202409.xlsx` (demonstrating drop-in SharePoint portability) and re-converges European prices.

### Minute 3 — 3 Breakout BQML Forecast Tabs (`Macro_BQML`, `Crudes_BQML`, `Freight_BQML`)
1. Open **`Macro_BQML`**, **`Crudes_BQML`**, and **`Freight_BQML`**: show `<= 2024` historical actuals alongside `2025–2050` BigQuery ML `ARIMA_PLUS` projections, and click the 3D **`Refresh BQML`** button in the top-right corner to refresh live from BigQuery ML.

### Minute 4 — Parallel 4-Way Scenario & EU ETS Carbon Sweep + `gemini-3.8-flash` Attribution
1. On **`KeyInputs`**, toggle `AT10:AZ10` from `0` to `1` (*Sensitivity Margin Case*), inspect **`Carbon!A5:A6`** (*EU ETS Pass-Through*), and click **`Run 4-Way Scenario & Carbon Matrix`**.
2. Switch to **`Scenario_Comparison`**: highlight the side-by-side `Base/Sens` $\times$ `Carbon Off/On` crack-spread and product price deltas, plus the executive attribution narrative generated by **Vertex AI `gemini-3.8-flash`**.

### Minute 5 — Trader `#FEF3C7` Pinned Price Override & 1-Click Equilibrium Reversion
1. On **`NWE Cif`**, type **`750.00`** into **`AU122`** (`2025 Diesel, EN590`, baseline `$716.40/mt`).
2. Point out the subtle **`#FEF3C7` amber cell highlight** (zero disruptive popups or cell hover notes).
3. Click **`Solve 10-Pass Equilibrium`** on `KeyInputs`: show that `NWE Cif!AU122` stays pinned at **`$750.00/mt`** across all 10 passes while `NWE Fob` netbacks, `IMOfuels` marine gasoil blends, and `NWE Cif` refinery `Product Realization` equilibrate around `$750.00/mt`.
4. Click **`Revert Pinned Overrides`**: within `< 2 seconds`, the amber fill clears and `AU122` restores to its exact mathematical equilibrium (`$716.40/mt`).

### Minute 6 — Silent Distributed `4-Ws` Governance, `UPLOAD_BQ` & Rollback
1. Rename **`KeyInputs!A50`** (*Metadata Rename*) and change **`KeyInputs!BA14`** from `=BB14-0.25` to `=BB14-0.15` (*Formula Override*), then click **`Publish UPLOAD & Links Out`**.
2. Open **`UPLOAD_BQ`** (`1,273` published series with mnemonics `RRFPN-...`, replacing `83,928` browser staging formulas and `shooju_addin`) and **`BQ_4Ws_Audit_Log`** (`vw_audit_4w_summary`):
   - Show the silent `4-Ws` entries (`PINNED_PRICE_OVERRIDE`, `HEADER_OR_LABEL_MODIFIED`, `MANUAL_OVERRIDE`, `SOLVER_RUN`) with **`gemini-3.8-flash`** `why_ai_summary` explanations.
   - Highlight the **Three-Tier Rollback** guarantee: (1) 1-click Override Reversion, (2) surgical formula restoration via `before_formula` / `before_value`, and (3) full-workbook point-in-time recovery via `copy_location_url` + `when_event_utc` in Google Sheets **File > Version history** across both the central sheet and personal `File -> Make a copy` sheets.
