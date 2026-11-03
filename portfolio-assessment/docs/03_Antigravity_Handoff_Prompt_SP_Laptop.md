# Antigravity Session Initialization Prompt: Workbook Modernization Portfolio Scoring (`LES`, `MHS`, `MRI`) — S&P Laptop Handoff

## 1. Pre-Flight Transfer Checklist (Before Opening Antigravity on Your S&P Laptop)

1. **Transfer the Workspace Folder (`commodity-modeling-sheets-platform/`):**
   * Copy (or `git clone` + copy gitignored `.xlsx`/`.xlsm` binaries) onto your S&P laptop so the workspace contains:
     * `portfolio-assessment/docs/01_Portfolio_Scoring_Specification.md`
     * `portfolio-assessment/docs/02_Portfolio_Scoring_Implementation_Plan.md`
     * `portfolio-assessment/docs/03_Antigravity_Handoff_Prompt_SP_Laptop.md`
     * Target workbooks to score (e.g., `brazil-power-v13/seed/*.xlsm`, `Eulr/docs/*.xlsx`, `Eulr/docs/references/*.xlsx`, `other models/*.xls*`, plus any additional S&P workbooks you want evaluated).
   * *(Note: Because `.gitignore` excludes `**/references/*.xls*` and `other models/*.xls*` to keep Git lightweight, remember to copy those binary `.xlsx`/`.xlsm` files separately if transferring via Git—or point `--scan-dirs` directly at your local S&P folders!)*
2. **Identify Any Synced S&P SharePoint / OneDrive / Network Reference Folders (Optional, High Value on S&P Laptop):**
   * Many workbooks (`Eulr`, `Uslr`, `Felr`, `Tankerlr`, `Canlr`, `Callr`, `Latinlr`, `Big-5`, `PADD_Diesel`, `PADD_Gasoline`) reference external files hosted on:
     * `https://spgl.sharepoint.com/sites/Downstream_HOU/...` (`LR202409`, `PSD_Crude_Oil.xlsb`, `PSD_Refined Products.xlsb`, `Worldscale.xlsx`)
     * `https://spgl.sharepoint.com/sites/Downstream_LON/...` (`STO_Europe_demand_workbook.xlsx`, `SR_Model.xlsx`)
     * `https://spgl.sharepoint.com/sites/Downstream_SG/...` & `Downstream_CAL/...`
     * Corporate UNC shares (`\\hou0\vol3\...`)
   * If any of those SharePoint libraries are synced locally on your S&P laptop (via OneDrive / SharePoint Sync or network drive mounts), passing their root folder(s) to `--reference-roots` enables **live external reference confirmation** (`CONFIRMED_EXACT_MATCH`, `CONFIRMED_STALE_CACHE_DRIFT`, `RESOLVED_SHEET_MISSING`).
3. **Open the Workspace in Antigravity on Your S&P Laptop** and paste the prompt below.

---

## 2. Copy-Paste Initialization Prompt for Antigravity (S&P Corporate Laptop Session)

```markdown
You are a Staff Quantitative Systems & Data Governance Engineer implementing and executing the **Workbook Modernization Portfolio Scoring Engine (`LES`, `MHS`, `MRI`)** inside `portfolio-assessment/` on my S&P corporate laptop.

### 1. Mandatory First Step: Read Both Specification & Implementation Plan Documents
Before writing any code or running any commands, read these two files in full:
1. `portfolio-assessment/docs/01_Portfolio_Scoring_Specification.md` — Defines the exact mathematical equations, Active-Surface Proportional Weight Re-Normalization across workbook archetypes (`N/A` gating), cell-level hygiene defect detectors (`H1`–`H5`, excluding intentional `=NA()` chart masks), S&P live external reference confirmation (`--reference-roots`), and the composite **Modernization Readiness Index (`MRI`)**.
2. `portfolio-assessment/docs/02_Portfolio_Scoring_Implementation_Plan.md` — Contains the complete 5-task TDD implementation blueprint (`models.py`, `weights.py`, `vba_inspector.py`, `xml_inspector.py`, `reference_resolver.py`, `extractability.py`, `hygiene.py`, `scorer.py`, `reporter.py`, `cli.py`, and `tests/`).

### 2. Strict Safety & Isolation Guardrails
- **100% Read-Only on All Spreadsheets:** Never modify, touch, overwrite, execute macros inside, or re-save any `.xlsx`, `.xlsm`, `.xlsb`, or `.xls` file. Every archive open MUST use `zipfile.ZipFile(path, mode="r")`.
- **Workspace Isolation:** Do NOT modify any code inside `brazil-power-v13/` or `Eulr/`. Build exclusively inside `portfolio-assessment/` (plus the convenience target in root `Makefile`).
- **Zero External Package Bloat:** Ensure a Python 3.11+ `.venv` exists (reusing or creating `.venv` with `pytest` and `ruff`); the scanner itself uses only Python's standard library so no restricted corporate proxy installs are required beyond `pytest` and `ruff`.

### 3. Execution Sequence
1. **Confirm Context & Discover S&P Reference Paths:**
   - Check which `.xlsx`/`.xlsm` workbooks are present across `brazil-power-v13/seed/`, `Eulr/`, and `other models/`.
   - Check whether standard OneDrive / SharePoint sync directories exist on this S&P machine (e.g., `~/Library/CloudStorage/` on macOS or `%USERPROFILE%\OneDrive*` / `%USERPROFILE%\S&P Global*` on Windows) and ask me once if I want to include any additional model folders (`--scan-dirs`) or SharePoint/UNC reference roots (`--reference-roots`) before running the final portfolio report.
2. **Execute Tasks 1–5 of `02_Portfolio_Scoring_Implementation_Plan.md` via Strict TDD:**
   - Implement Tasks 1 through 5 step-by-step (write failing test -> verify FAIL -> write implementation -> verify PASS & `ruff check`).
3. **Run the Full Live Portfolio Assessment (With `--reference-roots` Confirmation):**
   - Run `python -m portfolio_assessment.cli` across all target model folders, passing `Eulr/docs/references` plus any confirmed S&P SharePoint/OneDrive/UNC folders to `--reference-roots`.
   - Also inspect any referenced `.xlsb` / `.xls` filenames in `xl/externalLinks` on disk if present in `--reference-roots` so file-existence confirmation is recorded even for binary reference workbooks (`PSD_Crude_Oil.xlsb`, etc.) while `.xlsx`/`.xlsm` targets receive full sheet + cell-drift verification.
4. **Deliver Leadership Readout:**
   - Verify all generated artifacts in `portfolio-assessment/reports/`:
     - `portfolio_executive_scorecard.md`
     - `portfolio_scorecard.csv`
     - `portfolio_cell_defects.csv`
     - `portfolio_external_links_audit.csv`
   - Present a concise executive summary of the ranked `MRI`, `LES`, `MHS`, `Defect Rate (%)`, Readiness Tiers (`Tier 1`–`Tier 4`), and confirmed vs. broken/drifted external S&P SharePoint/UNC references.
```
