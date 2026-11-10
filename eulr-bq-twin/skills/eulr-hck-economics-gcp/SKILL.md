---
name: eulr-hck-economics-gcp
description: Direct shortcut workflow for the EULR 200 kb/d Sour Hydrocracker Project IRR & NPV 9-point sensitivity (2015 NWE HCK IRR), Naphtha vs. Diesel mode revamp (HCK naphtha revamp), and ULSD 10ppm vs. 0.1%S Gasoil cost-coverage thresholds (ULSD-GO_spread_econs) on eulr-refining-mcp.
---

# EULR Hydrocracker Project IRR & Distillate Spread Economics (`/eulr-hck-economics-gcp`)

Use this skill when the analyst invokes `/eulr-hck-economics-gcp` or asks to evaluate European hydrocracker conversion investment returns (`2015 NWE HCK IRR`), Naphtha vs. Diesel mode revamp (`HCK naphtha revamp`), or ULSD–Gasoil desulfurization cost-coverage spreads (`ULSD-GO_spread_econs`).

1. **Prompt via `ask_question`** (unless WACC is already specified):
   - Ask which real discount rate (`discount_rate_wacc`) to apply for the `200 kb/d` Hydrocracker NPV calculation (`(Recommended) 10.0% Real WACC (0.10)`, `8.0% Real WACC (0.08)`, `12.0% Hurdle Rate (0.12)`).
2. **Execute**:
   - Call `run_eulr_hck_and_ulsd_economics` (`{"session_id": "cowork_eulr_session", "discount_rate_wacc": <wacc>}`) on `eulr-refining-mcp`.
3. **Present**:
   - Render `echarts_option` inline via `render_chart`.
   - Write `artifact_markdown` to `eulr_hck_and_ulsd_economics.md` via `write_to_file` (`UserFacing=true`, `RequestFeedback=false`).
   - Offer 18-tab `.xlsx` synthesis via `export_eulr_workbook`.
