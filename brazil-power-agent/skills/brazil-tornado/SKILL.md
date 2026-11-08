---
name: brazil-tornado
description: Direct shortcut workflow for the Brazil Power v13 21-point IRR Tornado Sensitivity analysis (calcule_tir1..12 across _01_CF.._12_CF!A4:H12 and Output_1). Prompts for target technology and parameter overrides via ask_question, executes run_tornado_sensitivity on brazil-power-mcp, renders the exact _0N_CF!A4:H12 table and horizontal Tornado EChart inline via render_chart, writes the full multi-technology Output_1 replica to a side-pane Artifact, and offers 22-tab .xlsx or Google Sheets export.
---

# Brazil Energy Model (v13) — 21-Point IRR Tornado Sensitivity Shortcut (`/brazil-tornado`)

Use this skill whenever the analyst invokes `/brazil-tornado` or asks to run a Tornado IRR sensitivity analysis (`calcule_tir1` .. `calcule_tir12`) on one or all 12 generation technology tabs (`_01_CF` .. `_12_CF` and `Output_1`) in the Brazil Power v13 workbook (`2023-11-27-Brazil_TT_v13_RJEB.xlsm`).

---

## Excel Coordinate Architecture (`_01_CF.._12_CF!A4:H12` & `Output_1`)

In the original Excel workbook, each technology cash-flow tab `_01_CF` .. `_12_CF` contains a sensitivity block at **`_0N_CF!A4:H12`** populated by the VBA macro `calcule_tir<N>` (using a 2-Stage Discrete Lattice Binary Search over 7 parameters × 3 shock points = 21 solves per technology), which also links into the cross-technology **`Output_1`** summary tab and **`General!B5:N40`**:

| `_0N_CF` Row | Parameter Label (`Col D`) | Shock Axis (`Col E:G`) | Underlying `General!B5:N40` Driver Row | Solved Output Cell Coordinates |
| :---: | :--- | :--- | :--- | :--- |
| **Row 5** | Header Row | `-10%` (`Col E`) \| `Base` (`Col F`) \| `+10%` (`Col G`) | Baseline Assumptions (`General!C5:N40`) | `_0N_CF!E5:G5` |
| **Row 6** | **Interest rate (Real WACC)** | `-10%` / `Base` / `+10%` relative shock | `General!C34:N34` (`Interest Rate`, baseline `8.00%`) | `_0N_CF!E6:G6` & `Output_1` |
| **Row 7** | **Capex (Base Capital Cost)** | `-10%` / `Base` / `+10%` relative shock | `General!C11:N11` (`Base capital cost R$/kW`) | `_0N_CF!E7:G7` & `Output_1` |
| **Row 8** | **Capacity factor (CF)** | `-10%` / `Base` / `+10%` relative shock | `General!C16:N16` (`Capacity factor`) | `_0N_CF!E8:G8` & `Output_1` |
| **Row 9** | **O&M (Fixed + Variable)** | `-10%` / `Base` / `+10%` relative shock | `General!C23:N24` (`Fixed & Variable O&M`) | `_0N_CF!E9:G9` & `Output_1` |
| **Row 10** | **Construction lead time** | `-1 yr` / `Base` / `+1 yr` discrete step | `General!C14:N14` (`Construction lead time yrs`) | `_0N_CF!E10:G10` & `Output_1` |
| **Row 11** | **Tariff (Breakeven LCOE)** | `-10%` / `Base` / `+10%` relative shock | `_0N_CF!G3` (`Solved Base LCOE Tariff R$/MWh`) | `_0N_CF!E11:G11` & `Output_1` |
| **Row 12** | **Fuel cost** | `-10%` / `Base` / `+10%` relative shock | `General!C20:N20` (`Fuel cost R$/MMBtu or US$/MMBtu`) | `_0N_CF!E12:G12` & `Output_1` |

*(Note: Full workbook LCOE horizon linkages live in `Output_3!B8:J31`.)*

---

## Step-by-Step Execution Workflow

### Step 1: Interactive Technology & Baseline Assumption Card (`ask_question`)

If the analyst did not specify a target technology (`_01_CF` .. `_12_CF` or `ALL`) in their prompt, call `ask_question` to display a compact visual selection card with current `General!B5:N40` baseline values:

```json
{
  "questions": [
    {
      "question": "Which technology tab (_01_CF .. _12_CF) should we run the 21-point IRR Tornado Sensitivity (calcule_tir) on?",
      "is_multi_select": false,
      "options": [
        "(Recommended) _06_CF — Small Hydro SHP (General!Col H: Capex=7,500 R$/kW, Lead Time=3.0 yrs, CF=55.0%, WACC=8.00%)",
        "_01_CF — Gas CCGT (General!Col C: Capex=4,250 R$/kW, Fuel=4.50 R$/MMBtu, CF=85.0%, WACC=8.00%)",
        "_04_CF — Onshore Wind WT Cl. 6 (General!Col F: Capex=5,100 R$/kW, Lead Time=2.0 yrs, CF=45.0%, WACC=8.00%)",
        "_05_CF — Utility Solar PV (General!Col G: Capex=3,850 R$/kW, Lead Time=1.0 yr, CF=26.0%, WACC=8.00%)",
        "ALL — Execute calcule_tir1..12 across all 12 technology sheets (_01_CF.._12_CF) and populate Output_1"
      ]
    },
    {
      "question": "Would you like to stage any scenario assumption overrides in General!B5:N40 before solving the Tornado sensitivity?",
      "is_multi_select": false,
      "options": [
        "(Recommended) Run with active session / baseline assumptions in General!B5:N40",
        "Bump Gas CCGT Fuel Cost (General!C20) to 6.50 R$/MMBtu and Small Hydro Lead Time (General!H14) to 2.0 years",
        "Increase Real WACC (General!C34:N34) by +150 bps to 9.50%",
        "Reset session to clean 2023-11-27-Brazil_TT_v13_RJEB.xlsm baseline before running"
      ]
    }
  ]
}
```

### Step 2: Apply Any Assumption Overrides & Execute `run_tornado_sensitivity`

1. If the analyst requested parameter overrides or a baseline reset, call `update_session_assumptions` on `brazil-power-mcp` and show the affected `General!B5:N40` cell coordinate diff (`Baseline -> Current (Δ%)`).
2. Call `run_tornado_sensitivity(technology_code=..., parity_mode="strict_legacy_vba")` on `brazil-power-mcp`.

### Step 3: Render Inline Excel Replica Table (`_0N_CF!A4:H12`), ECharts Visual (`render_chart`), and Side-Pane Artifact

1. **Inline Excel Table**: Output `inline_excel_table_md` directly in your chat response. This displays the exact `_0N_CF!A4:H12` table (`Cell Range | Parameter | -10% Shock (Col E) | Base IRR (Col F) | +10% Shock (Col G) | Total Spread (bps)`) plus the `Output_1` summary block.
2. **Inline Horizontal Tornado Chart**: Call `render_chart` (`mcp_data-agent-kit_render_chart`) with the returned `echarts_spec` (`echarts_option`) so the analyst immediately sees the sorted horizontal Tornado bars (`-10% Shock` vs `+10% Shock` in bps around Base Project IRR).
3. **Side-Pane Artifact**: Write `full_artifact_table_md` into a side-pane **Artifact** (`brazil_v13_tornado_sensitivity.md`) via `write_to_file` (`UserFacing=True, RequestFeedback=False`) containing the full multi-block `_01_CF.._12_CF!A4:H12` and `Output_1` spreadsheet tables.

### Step 4: Offer 1-Click 22-Tab Workbook Export (`export_full_22tab_workbook`)

Ask if the analyst would like to export the updated 22-tab workbook (with `_01_CF.._12_CF!E6:G12` and `Output_1` populated) to a faithful 22-tab `.xlsx` file or cloned 22-tab Google Sheet via `export_full_22tab_workbook`, or chain directly into `/brazil-lcoe` (`Output_3!B8:J31`) or `/brazil-dcf`.
