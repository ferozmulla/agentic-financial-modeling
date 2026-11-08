---
name: brazil-dcf
description: Direct shortcut workflow for the Brazil Power v13 30-Year Project & Shareholder DCF Cash Flow Schedule (2024–2053 across _01_CF.._12_CF Rows 33–101, Col K..Col AN) and 10-point Thermal CVU / Physical Guarantee sweep (CVU_GF). Collects target technology and financial parameters via ask_question, executes run_dcf_cashflow_analysis on brazil-power-mcp, renders the executive valuation header + milestone DCF table + ECharts cash-flow waterfall inline via render_chart, writes the complete 30-column horizontal _0N_CF replica to a side-pane Artifact, and offers 22-tab .xlsx or Google Sheets export.
---

# Brazil Energy Model (v13) — 30-Year Project DCF & Thermal CVU/GF Sweep Shortcut (`/brazil-dcf`)

Use this skill whenever the analyst invokes `/brazil-dcf` or asks to inspect the 30-year (`2024–2053`) Project & Shareholder Discounted Cash Flow (DCF) statement (`_01_CF` .. `_12_CF` Rows `33–101`, `Col K` .. `Col AN`) or the 10-point Thermal CVU / Physical Guarantee (`GF` & `ICB`) sweep (`CVU_GF` and `calculo_cvu1..12`).

---

## Excel Coordinate Architecture (`_01_CF.._12_CF` Rows 2–101, `CVU_GF`, `General!B5:N40`)

Each of the 12 technology tabs (`_01_CF` .. `_12_CF`) in `2023-11-27-Brazil_TT_v13_RJEB.xlsm` models a 30-year (`2024–2053`) generation project lifecycle fed by `General!B5:N40` (and linked to `Output_1`, `Output_2`, and `Output_3!B8:J31`):

1. **Executive Summary & Valuation Header (`_0N_CF!B2:H14`)**:
   - `_0N_CF!C3`: Installed Capacity (`MW` or `kW` from `General!Row 8`)
   - `_0N_CF!C4`: Net Capacity (`MW` from `General!Row 9`)
   - `_0N_CF!C5`: Specific Base CAPEX (`R$/kW` from `General!Row 11`)
   - `_0N_CF!C6`: Construction Lead Time (`Years` from `General!Row 14`)
   - `_0N_CF!C7`: Plant Economic Life (`Years` from `General!Row 15`)
   - `_0N_CF!C8`: Capacity Factor (`%` from `General!Row 16`)
   - `_0N_CF!C11`: Real WACC Discount Rate (`%` from `General!Row 34`)
   - `_0N_CF!G2`: Thermal ICB Index (`R$/MWh`, for thermal sheets `_01_CF, _07_CF, _08_CF, _09_CF, _10_CF`)
   - `_0N_CF!G3`: Solved Breakeven LCOE Tariff (`R$/MWh`)
   - `_0N_CF!F6`: Project Real IRR (`%`, unlevered across 30-year FCF)
2. **30-Year Horizontal DCF Schedule (`_0N_CF!K33:AN101`, Years `2024..2053`)**:
   - **`Row 33` (`Col K` .. `Col AN`)**: Calendar Year `2024` (`Col K`) through `2053` (`Col AN`)
   - **`Row 36`**: Gross Generation (`GWh`)
   - **`Row 38`**: Net Generation Delivered (`GWh`)
   - **`Row 42`**: Gross Operating Revenue (`kR$`)
   - **`Row 45`**: Total Operating Costs & Sector Charges (`kR$`: Fuel + Fixed O&M + Variable O&M + TUST/TUSD + Insurance + Water)
   - **`Row 46`**: Fixed O&M (`kR$`)
   - **`Row 47`**: Variable O&M (`kR$`)
   - **`Row 49`**: Fuel Cost (`kR$`)
   - **`Row 61`**: Depreciation (`kR$`)
   - **`Row 70`**: Income Tax & Social Contribution (`IRPJ + CSLL`, `kR$`)
   - **`Row 71`**: Net Operating Cash Flow (`kR$`)
   - **`Row 72`**: CAPEX Drawdown Schedule (`kR$` during construction lead-time years)
   - **`Row 73`**: **Free Cash Flow to Firm (Project FCF, `kR$`)**
   - **`Row 101`**: **Shareholder / Equity Free Cash Flow (`kR$`)**
3. **10-Point Thermal CVU & Physical Guarantee Sweep (`CVU_GF` & `_0N_CF!K7:N16`)**:
   - Triggered by `calculo_cvu<N>` (`include_cvu_gf_sweep=True`), sweeping Unit Variable Cost (`CVU`, `R$/MWh`) from `0` to `450 R$/MWh` across `CVU_GF!C5:C14` (`GF / Capacity Factor`) and resolving `Breakeven LCOE Tariff (R$/MWh)` vs `Thermal ICB (R$/MWh)`.

---

## Step-by-Step Execution Workflow

> [!IMPORTANT]
> **FAST-START LATENCY RULE (ZERO PRE-CARD TOOL CALLS)**:
> When the analyst invokes `/brazil-dcf` without specifying a target technology tab, your **VERY FIRST AND ONLY tool call on Turn 1 MUST be `ask_question`**. Do **NOT** call `get_session_assumptions`, do **NOT** search the filesystem (`find_by_name`, `grep_search`, `list_dir`, `view_file`), and do **NOT** run shell commands before presenting the `ask_question` card below.

### Step 1: Interactive Technology & Financial Parameter Card (`ask_question`)

If the analyst invokes `/brazil-dcf` without specifying a target technology tab, immediately call `ask_question` on Turn 1 to present the technology and financial parameter card:

```json
{
  "questions": [
    {
      "question": "Which technology worksheet (_01_CF .. _12_CF) would you like to run the 30-Year Project & Shareholder DCF Schedule (2024–2053) for?",
      "is_multi_select": false,
      "options": [
        "(Recommended) _01_CF — Gas CCGT (500 MW, Capex=4,250 R$/kW, Fuel=4.50 R$/MMBtu, CF=85.0%, WACC=8.00%)",
        "_06_CF — Small Hydro SHP + 10-Point CVU/GF Sweep (20 MW, Capex=7,500 R$/kW, Lead Time=3.0 yrs, CF=55.0%)",
        "_07_CF — Local Coal CFBC + 10-Point Thermal CVU/ICB Sweep (350 MW, Capex=9,200 R$/kW, Fuel=3.20 US$/MMBtu)",
        "_04_CF — Onshore Wind WT Cl. 6 (30 MW, Capex=5,100 R$/kW, Lead Time=2.0 yrs, CF=45.0%)",
        "_05_CF — Utility Solar PV (30 MW, Capex=3,850 R$/kW, Lead Time=1.0 yr, CF=26.0%)"
      ]
    },
    {
      "question": "Should we include the 10-point Thermal CVU & Physical Guarantee (GF / ICB) sweep (CVU_GF) and/or stage any General!B5:N40 financial overrides?",
      "is_multi_select": false,
      "options": [
        "(Recommended) Run 30-Year DCF + 10-point CVU/GF Sweep with current session General!B5:N40 assumptions",
        "Run 30-Year DCF with High Gas Fuel (General!C20 = 6.50 R$/MMBtu) and Fast SHP Lead Time (General!H14 = 2.0 yrs)",
        "Run 30-Year DCF with Higher Real WACC (General!C34:N34 = 9.50%)",
        "Run 30-Year DCF only (skip CVU_GF sweep)"
      ]
    }
  ]
}
```

### Step 2: Apply Any Overrides & Call `run_dcf_cashflow_analysis`

1. If the analyst selected financial overrides in `General!B5:N40`, call `update_session_assumptions` on `brazil-power-mcp` first.
2. Call `run_dcf_cashflow_analysis(technology_code=..., start_year=2024, end_year=2053, include_cvu_gf_sweep=...)` on `brazil-power-mcp`. *(If `brazil-power-mcp` is not in your active MCP tool list, do NOT search the filesystem; invoke `mcp_server.py --call run_dcf_cashflow_analysis --args '<json>' --compact-llm` directly.)*

### Step 3: Dual Inline (Valuation Header + Milestone DCF Table + ECharts) & Pre-Saved 30-Column Side-Pane Artifact

1. **Inline Valuation Header & Milestone DCF Table**: Render `inline_markdown` (`inline_excel_table_md`) directly in chat. This presents:
   - The `_0N_CF!B2:H14` Executive Valuation Summary (`Installed Capacity`, `Base CAPEX`, `Lead Time`, `Economic Life`, `Capacity Factor`, `Real WACC`, `Breakeven LCOE Tariff`, `Project IRR`, `Equity IRR`, `Total 30-Yr Net Generation`, `Cumulative Undiscounted FCF`, `Discounted Payback`).
   - The 11-column Milestone Cash Flow table (`2024 (Col K)`, `2025 (Col L)`, `2026 (Col M)`, `2027 (Col N)`, `2028 (Col O)`, `2030 (Col Q)`, `2035 (Col V)`, `2040 (Col AA)`, `2045 (Col AF)`, `2050 (Col AK)`, `2053 (Col AN)`).
   - If `include_cvu_gf_sweep=True`, the 10-point `CVU_GF` & `_0N_CF!K7:N16` sweep table (`CVU 0..450 R$/MWh | GF (CF %) | Breakeven LCOE | Thermal ICB`).
2. **Inline 30-Year FCF & Cumulative Discounted NPV Chart**: Call `render_chart` (`mcp_data-agent-kit_render_chart`) with `echarts_option` (`echarts_spec`) to render the 30-year stacked Bar/Line Free Cash Flow visual inline (and also call `render_chart` with `cvu_sweep_echarts_option` if the CVU sweep was requested).
3. **Pre-Saved 30-Column (`Col K..Col AN`) Side-Pane Artifact**: `run_dcf_cashflow_analysis` automatically persists `full_artifact_table_md` (all 30 annual columns `2024..2053` across Rows `33–101`) to `artifact_file_path` (`artifact_file_uri`) on disk in `<1 ms`—do **not** regenerate all 30 columns token-by-token unless writing a conversation-scoped Artifact file via `write_to_file(UserFacing=True, RequestFeedback=False)` by copying from `artifact_file_path`.

### Step 4: Offer 1-Click 22-Tab Workbook Export (`export_full_22tab_workbook`)

Offer to export the active session to a complete 22-tab `.xlsx` workbook or cloned 22-tab Google Sheet via `export_full_22tab_workbook(export_format="xlsx" | "google_sheets" | "both")`.
