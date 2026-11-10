---
name: eulr-refining-model-gcp
description: "End-to-end guided workflow for the 100% Excel-free BigQuery Digital Twin of the EULR European Refining & Product Equilibrium Model (comm-model-mod.eulr_digital_twin via eulr-refining-mcp). Publishes eulr_refining_baseline_assumptions.md in the side-pane Artifact viewer first, presents Card 1 (Hub/Scope Selection & Driver, EU ETS Switch, or Pinned Price Overrides), stages overrides to BigQuery dt_scenario_deltas, presents Card 2 (Quantitative Analysis Selection), renders ECharts + Artifacts, and synthesizes 18-tab or 19-tab .xlsx workbooks purely from BigQuery rows."
---

# EULR European Refining Equilibrium — GCP BigQuery Digital Twin Orchestrator (`/eulr-refining-model-gcp`)

Use this skill whenever the analyst invokes `/eulr-refining-model-gcp` or asks to start, configure, or run an interactive European Crude & Refined Products (`EULR`) modeling session backed by `comm-model-mod.eulr_digital_twin`.

> [!CAUTION]
> **HARD GATE FOR TURN 1 — `write_to_file` MUST COMPLETE BEFORE `ask_question` (ZERO PRE-CARD TOOL CALLS)**:
> 1. **YOUR FIRST TOOL CALL MUST BE ONLY `write_to_file` (STEP 1)**: Do **NOT** call `get_eulr_session_assumptions`, `run_command`, `find_by_name`, or `ask_question` in Step 1. Calling `write_to_file` alone with the verified baseline tables below opens `eulr_refining_baseline_assumptions.md` in the right-hand Artifact pane immediately.
> 2. **IMMEDIATELY PRESENT CARD 1 (`ask_question` WITH QUESTIONS `1/2` AND `2/2`) IN STEP 2**: As soon as `write_to_file` returns, call `ask_question` with **Question `1/2` = Hub & Analytical Focus** and **Question `2/2` = Driver, EU ETS Carbon, or Pinned Price Overrides**. Do **NOT** ask which quantitative solver to run on Card 1 — that belongs on **Card 2 (Step 4)** after overrides are staged!

---

## Dual-Mode Backend Invocation (`eulr-refining-mcp` or Direct Cloud Run HTTPS)

1. **Mode A — Native MCP Toolset**: If `eulr-refining-mcp` tools (`get_eulr_session_assumptions`, `update_eulr_session_overrides`, `run_eulr_equilibrium_solve`, `run_eulr_scenario_matrix`, `run_eulr_bqml_forecast_refresh`, `run_eulr_hck_and_ulsd_economics`, `export_eulr_workbook`) are in your active MCP tool list, call them directly with a consistent `session_id` (e.g. `"cowork_eulr_session"`).
2. **Mode B — Direct Cloud Run HTTPS Fallback**:
   ```bash
   python3 -c '
   import json, sys, urllib.request
   body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": sys.argv[1], "arguments": json.loads(sys.argv[2])}}).encode()
   req = urllib.request.Request("https://eulr-bq-twin-mcp-2wcxwkmdga-uc.a.run.app/mcp", data=body, headers={"Content-Type": "application/json", "Mcp-Session-Id": sys.argv[3]}, method="POST")
   resp = json.loads(urllib.request.urlopen(req, timeout=120).read().decode())
   print(resp["result"]["content"][0]["text"])
   ' "<tool_name>" '<json_args>' "cowork_eulr_session"
   ```

---

## 6-Step Sequential Guided Workflow

### Step 1 (Mandatory Standalone First Tool Call): Publish `eulr_refining_baseline_assumptions.md` via `write_to_file`

Unless the analyst already specified exact overrides and a target analysis in their prompt, your **sole tool call in Step 1** MUST be `write_to_file`:
- `TargetFile`: `"<artifact_dir>/eulr_refining_baseline_assumptions.md"` (or `"eulr_refining_baseline_assumptions.md"` in workspace)
- `Overwrite`: `true`
- `Description`: `"Publish upfront EULR Digital Twin LR202409 baseline margins, EU ETS switches, benchmark crudes, and NWE/MED CIF & FOB product prices"`
- `ArtifactMetadata`: `{"UserFacing": true, "RequestFeedback": false, "Summary": "EULR Digital Twin Baseline: KeyInputs, Carbon, Crudes, NWE/MED CIF & FOB, IMOfuels (2024–2050)"}`
- `CodeContent`:

```markdown
# EULR European Refining & Product Equilibrium — Digital Twin Snapshot (`comm-model-mod.eulr_digital_twin`)

- **EU ETS Carbon Toggle (`Carbon!A5`)**: `Sensitivity with EU ETS cost and pass-through`
- **EU ETS Pass-Through Allocation (`Carbon!A6`)**: `Variable cost increase and product allocation`
- **Active Session Overrides**: `0` cells (`0` pinned price cells)

## 1. European Refinery Yardstick Margins & EU ETS Pass-Through (`$/bbl`)
| Metric | Sheet!Row | Units | 2024 | 2025 | 2030 | 2035 | 2040 | 2045 | 2050 |
| :--- | :--- | :---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| **Cat Cracking Margin (Dated Brent, incl. ETS)** | `KeyInputs!Row15` | $/bbl | 2.31 | 0.26 | 1.05 | -0.00 | -1.85 | -3.43 | -4.94 |
| **Cat Cracking Margin (Dated Brent, excl. ETS)** | `KeyInputs!Row18` | $/bbl | 2.31 | 0.26 | 1.05 | 0.25 | -0.65 | -1.65 | -2.90 |
| **Incremental FCC/HSK ROCE (CRF)** | `KeyInputs!Row16` | $/bbl | 12.93 | 9.16 | 8.31 | 7.43 | 5.17 | 4.02 | 3.80 |
| **USGC Coking ICRF Benchmark** | `KeyInputs!Row25` | $/bbl | 25.25 | 22.22 | 18.67 | 22.77 | 24.27 | 25.37 | 26.47 |
| **EU ETS Variable Cost Push to FCC** | `Carbon!Row9` | $/bbl | 0.45 | 0.54 | 0.99 | 2.25 | 4.30 | 5.28 | 5.69 |
| **EU ETS Margin Erosion on FCC** | `Carbon!Row10` | $/bbl | 0.00 | 0.00 | 0.00 | 0.25 | 1.20 | 1.78 | 2.04 |

## 2. Benchmark Crude Slate (`$/bbl`)
| Crude Grade | Sheet!Row | Units | 2024 | 2025 | 2030 | 2035 | 2040 | 2045 | 2050 |
| :--- | :--- | :---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Dated Brent Spot FOB | `Input!Row37` | $/bbl | 84.28 | 78.72 | 88.99 | 95.64 | 101.96 | 108.86 | 116.32 |
| Urals CIF NWE | `Input!Row43` | $/bbl | 69.72 | 62.13 | 65.73 | 64.54 | 62.93 | 62.45 | 62.63 |
| Azeri Light FOB Ceyhan (23$) | `Input!Row44` | $/bbl | 83.72 | 76.33 | 76.96 | 73.81 | 70.94 | 68.25 | 65.70 |
| Arab Light FOB (NWE Formula, 23$) | `Input!Row45` | $/bbl | 83.61 | 75.48 | 74.52 | 71.43 | 68.54 | 65.85 | 63.15 |
| Es Sider Sweet Med FOB (23$) | `Input!Row47` | $/bbl | 81.83 | 74.81 | 74.73 | 71.53 | 68.82 | 66.14 | 63.32 |

## 3. Northwest Europe (`NWE Cif` — ARA) Refined Product Prices (`$/mt`)
| Product | Sheet!Row | Units | 2024 | 2025 | 2030 | 2035 | 2040 | 2045 | 2050 |
| :--- | :--- | :---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| LPG (CIF NWE) | `NWE Cif!Row114` | $/mt | 528.58 | 476.40 | 643.14 | 651.61 | 639.02 | 621.82 | 600.96 |
| Naphtha (CIF NWE) | `NWE Cif!Row115` | $/mt | 666.91 | 615.47 | 720.60 | 708.55 | 692.89 | 672.90 | 649.04 |
| Euro Gasoline Premium (CIF NWE) | `NWE Cif!Row119` | $/mt | 798.94 | 711.33 | 734.83 | 705.67 | 676.04 | 641.68 | 605.87 |
| Jet / Kerosene (CIF NWE) | `NWE Cif!Row121` | $/mt | 832.63 | 765.29 | 730.75 | 721.21 | 712.30 | 693.86 | 672.94 |
| Diesel EN590 10ppm (CIF NWE) | `NWE Cif!Row122` | $/mt | 789.85 | 716.40 | 689.43 | 680.45 | 672.21 | 654.80 | 634.70 |
| Gasoil 0.1%S (CIF NWE) | `NWE Cif!Row130` | $/mt | 772.62 | 698.21 | 672.82 | 660.11 | 647.87 | 628.90 | 608.09 |
| LSFO 1.0%S (CIF NWE) | `NWE Cif!Row131` | $/mt | 490.46 | 457.69 | 468.48 | 437.68 | 407.73 | 378.33 | 345.77 |
| HSFO 3.5%S (CIF NWE) | `NWE Cif!Row132` | $/mt | 452.16 | 423.17 | 423.78 | 393.93 | 364.98 | 337.58 | 308.52 |

## 4. Mediterranean (`MED Cif`) & IMO Marine Bunker Highlights (`$/mt`)
| Series | Sheet!Row | Units | 2024 | 2025 | 2030 | 2035 | 2040 | 2045 | 2050 |
| :--- | :--- | :---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Diesel EN590 10ppm (CIF MED) | `MED Cif!Row135` | $/mt | 785.80 | 710.83 | 689.93 | 681.05 | 672.81 | 655.40 | 635.30 |
| Euro Gasoline Premium (CIF MED) | `MED Cif!Row132` | $/mt | 812.53 | 716.13 | 734.83 | 705.67 | 676.04 | 641.68 | 605.87 |
| Diesel EN590 (FOB NWE) | `NWE Fob!Row156` | $/mt | 776.56 | 706.26 | 681.58 | 672.59 | 664.35 | 646.93 | 626.84 |
| IMO 0.1%S MGO Bunker | `IMOfuels!Row21` | $/mt | 757.72 | 684.74 | 659.85 | 647.38 | 635.38 | 616.78 | 596.36 |
| IMO 0.5%S VLSFO Bunker | `IMOfuels!Row22` | $/mt | 721.82 | 654.01 | 632.11 | 617.60 | 603.61 | 583.97 | 562.54 |
```

---

### Step 2 (Immediately After `write_to_file` Returns): Present Card 1 (`ask_question` — Questions `1/2` & `2/2`)

```json
{
  "questions": [
    {
      "question": "Which European refining hub, margin yardstick, or product segment in EULR would you like to focus on?",
      "is_multi_select": true,
      "options": [
        "(Recommended) Northwest Europe (NWE ARA CIF & FOB — Diesel EN590, Euro Gasoline, Jet/Kero & FCC Margins)",
        "Mediterranean Hub (MED Lavera/Augusta CIF & FOB & Cross-Hub NWE–MED Spreads)",
        "EU ETS Carbon Compliance & Pass-Through (`Carbon!A5:A6` -> FCC Yardstick Erosion)",
        "IMO Marine Bunker Blends (`IMOfuels` 0.1% MGO & 0.5% VLSFO) & Tanker Freight Feedback",
        "Deep-Conversion Hydrocracker (`200 kb/d` HCK IRR & ULSD–Gasoil Cost-Coverage Economics)"
      ]
    },
    {
      "question": "Which driver, EU ETS Carbon switch, or Pinned Price overrides would you like to stage in BigQuery `dt_scenario_deltas`?",
      "is_multi_select": true,
      "options": [
        "(Recommended) Keep current LR202409 baseline assumptions (EU ETS Cost+Allocation ON, 2025 NWE Diesel=$716.40/mt)",
        "Turn EU ETS Carbon Pass-Through OFF (`Carbon!A5` = 'Base case LTO without carbon pricing')",
        "Tight European Refining Shock: +$1.50/bbl FCC Margin Shock (`fcc_margin_shock_usd_bbl: 1.5`) + +$5/bbl Dated Brent (`dated_brent_shock_usd_bbl: 5.0`)",
        "Pin 2025 NWE EN590 Diesel CIF (`NWE Cif!AU122`) to $750.00/mt across all 10 Gauss-Seidel passes",
        "Reset all active session overrides in BigQuery back to clean `lr202409_baseline`"
      ]
    }
  ]
}
```

---

### Step 3: Stage Overrides in BigQuery & Refresh `eulr_refining_baseline_assumptions.md`

1. If the analyst chose `"Keep current LR202409 baseline assumptions"`, make **zero** MCP tool calls in Step 3 and proceed directly to **Step 4 (Card 2)**.
2. Otherwise, call `update_eulr_session_overrides` (`session_id="cowork_eulr_session"`) with the selected `eu_ets_mode`, `driver_overrides`, `pinned_price_overrides`, or `reset_to_baseline=true`, overwrite `eulr_refining_baseline_assumptions.md` with the returned `full_artifact_markdown`, and proceed immediately to **Step 4 (Card 2)**.

---

### Step 4: Present Card 2 — Quantitative Analysis Selection (`ask_question`)

```json
{
  "questions": [
    {
      "question": "Which EULR quantitative analysis workflows would you like to run against the BigQuery Digital Twin?",
      "is_multi_select": true,
      "options": [
        "(Recommended) 10-Pass NWE/MED Circular Equilibrium Solve & Arbitrage Checks (`run_eulr_equilibrium_solve`)",
        "6-Way EU ETS Carbon, FCC Margin Stress & Global 3-Peer (`Uslr`/`Felr`/`Tankerlr`) Matrix (`run_eulr_scenario_matrix`)",
        "BigQuery ML `ARIMA_PLUS` 2025–2050 Trajectory Refresh for Macro, Crudes & Tanker Freight (`run_eulr_bqml_forecast_refresh`)",
        "200 kb/d Hydrocracker Project IRR Sensitivity & ULSD–Gasoil Spread Economics (`run_eulr_hck_and_ulsd_economics`)"
      ]
    }
  ]
}
```

---

### Step 5 & Step 6: Execute Solvers, Render ECharts (`render_chart`), Update Artifacts & Offer 18/19-Tab `.xlsx` Export

1. Call each selected MCP tool on `eulr-refining-mcp` (`session_id="cowork_eulr_session"`).
2. Render `echarts_option` inline via `render_chart` (when available) and write full tables (`artifact_markdown`) to a dedicated side-pane Artifact (`eulr_analysis_results.md`, `UserFacing=true`, `RequestFeedback=false`).
3. Offer on-demand workbook synthesis via `export_eulr_workbook` (`include_upload_tab=false` for the fast 18-tab core workbook, or `include_upload_tab=true` for all 19 active tabs including the 93,935-cell `UPLOAD` staging sheet).
