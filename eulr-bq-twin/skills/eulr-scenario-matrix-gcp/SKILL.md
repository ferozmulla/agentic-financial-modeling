---
name: eulr-scenario-matrix-gcp
description: Direct shortcut workflow for the EULR 6-Way European Refining Margin, EU ETS Carbon Pass-Through (Cost+Allocation, Variable Cost Only, Carbon Off), and Live 3-Peer Upstream Sync (Uslr/Felr/Tankerlr) Scenario Matrix on eulr-refining-mcp.
---

# EULR 6-Way EU ETS Carbon, Margin Stress & Peer-Sync Matrix (`/eulr-scenario-matrix-gcp`)

Use this skill when the analyst invokes `/eulr-scenario-matrix-gcp` or asks to compare EU ETS carbon pass-through regimes, refinery margin shocks, and upstream global peer sync across European product prices.

1. **Prompt via `ask_question`** (unless `target_year` is already specified):
   - Ask which horizon milestone year to evaluate (`(Recommended) 2035 — EU CBAM Free-Allowance Phase-Out Active`, `2025 — Near-Term Prompt Year`, `2030 — Mid-Term Transition`, `2040 — Deep Decarbonization`, `2050 — Long-Run Horizon`).
2. **Execute**:
   - Call `run_eulr_scenario_matrix` (`{"session_id": "cowork_eulr_session", "target_year": <year>}`) on `eulr-refining-mcp`.
3. **Present**:
   - Render `echarts_option` inline via `render_chart`.
   - Write `artifact_markdown` to `eulr_scenario_matrix.md` via `write_to_file` (`UserFacing=true`, `RequestFeedback=false`) and highlight the dollar impact of EU ETS erosion and `Uslr`/`Felr`/`Tankerlr` peer sync.
   - Offer 18-tab `.xlsx` synthesis via `export_eulr_workbook`.
