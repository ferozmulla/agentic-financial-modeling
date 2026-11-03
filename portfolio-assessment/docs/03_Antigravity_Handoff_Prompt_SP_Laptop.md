# Antigravity Session Initialization Prompt: Workbook Modernization Portfolio Scoring (`LES`, `MHS`, `MRI`) — S&P Laptop Standalone Handoff

## 1. Standalone Setup on Your S&P Corporate Laptop (3-Doc Email Workflow)

1. **Create a Clean Folder on Your S&P Laptop (e.g., `portfolio-assessment/`):**
   * Save the three emailed Markdown documents into a `docs/` subfolder (or directly into the folder root):
     * `01_Portfolio_Scoring_Specification.md`
     * `02_Portfolio_Scoring_Implementation_Plan.md`
     * `03_Antigravity_Handoff_Prompt_SP_Laptop.md`
2. **Stage or Locate Your Excel Workbooks (`.xlsx` / `.xlsm`):**
   * Either place the workbooks you want scored into a `./workbooks/` subfolder (or subfolders inside it), **or** leave them in their existing local/synced S&P folders — the Antigravity agent will ask/confirm `--scan-dirs` with you before running the scan.
   * **Optional Live S&P External Reference Confirmation (`--reference-roots`):**
     * Many commodity models (`Eulr`, `Uslr`, `Felr`, `Tankerlr`, `Canlr`, `Callr`, `Latinlr`, `Big-5`, `PADD_Diesel`, `PADD_Gasoline`) reference external files hosted on `spgl.sharepoint.com/sites/Downstream_HOU`, `Downstream_LON`, `Downstream_CAL`, or corporate UNC shares (`\\hou0\vol3\...`).
     * Passing any locally synced S&P OneDrive / SharePoint folders or mounted network drives to `--reference-roots` enables read-only confirmation of peer `.xlsx`/`.xlsm` target sheets and stale-cache drift (`CONFIRMED_EXACT_MATCH`, `CONFIRMED_STALE_CACHE_DRIFT`, `RESOLVED_SHEET_MISSING`) plus `.xlsb`/`.xls` binary existence (`CONFIRMED_BINARY_FILE_EXISTS`).
3. **Open the Folder in Antigravity on Your S&P Laptop** and paste the initialization prompt below.

---

## 2. Copy-Paste Initialization Prompt for Antigravity (S&P Corporate Laptop Session)

```markdown
You are a Staff Quantitative Systems & Data Governance Engineer building and executing the **Workbook Modernization Portfolio Scoring Engine (`LES`, `MHS`, `MRI`)** from a standalone folder on my S&P corporate laptop.

### 1. Mandatory First Step: Locate & Read Both Handoff Documents in Full
Locate and read these two documents completely before writing code (check `./docs/` first, or the workspace root `.` if saved flat):
1. `01_Portfolio_Scoring_Specification.md` (v1.1) — Defines the exact calibrated equations for **Logic Extractability Score (`LES`, 0–100%)**, **Model Hygiene Score (`MHS`, 0–100%) + Defect Rate (`100% - MHS`)**, **Modernization Readiness Index (`MRI`, 0–100%)**, Active-Surface Proportional Weight Re-Normalization across workbook archetypes (`N/A` gating), intentional `=NA()` chart-mask exclusion, dormant `0`-ref link handling, `_xll.*` C++ add-in calibration, live S&P `--reference-roots` confirmation, and the 12-workbook calibration benchmark in Section 7.
2. `02_Portfolio_Scoring_Implementation_Plan.md` (v1.1) — Contains the complete, dry-run-calibrated 5-task TDD implementation (`pyproject.toml`, `Makefile`, `src/portfolio_assessment/*.py`, and `tests/*.py`).

### 2. Strict Safety & Corporate Environment Guardrails
- **100% Read-Only on All Spreadsheets:** Never modify, touch, overwrite, execute macros inside, or re-save any `.xlsx`, `.xlsm`, `.xlsb`, or `.xls` file. Every archive open MUST use `zipfile.ZipFile(path, mode="r")`.
- **Standalone Root Layout:** If the current workspace root IS the standalone project folder (rather than a parent monorepo), create `pyproject.toml`, `Makefile`, `src/portfolio_assessment/`, `tests/`, and `reports/` directly in this workspace root (moving the 3 `.md` files into `docs/` only if needed, or leaving them where they are).
- **Zero-Dependency Runtime & Corporate Proxy Resilience:**
  - Detect the OS (Windows vs. macOS/Linux) and Python `>=3.11` binary.
  - Create a local `.venv` and install `pytest`, `ruff`, and `defusedxml` if corporate PyPI/Artifactory access succeeds.
  - Note that `src/portfolio_assessment/` uses **zero required third-party runtime dependencies** (`dependencies = []`, with C-accelerated stdlib `xml.etree.ElementTree` fallback guarded against `<!DOCTYPE`/`<!ENTITY`), so even if S&P corporate firewall/SSL blocks `pip`, the engine and CLI run natively on standard Python 3.11+.

### 3. Execution Sequence
1. **Discover Workbooks & S&P Corporate Reference Paths:**
   - Scan the workspace for any `.xlsx`/`.xlsm` folders already staged here, AND check standard S&P Global OneDrive / SharePoint sync locations on this laptop (e.g., `%USERPROFILE%\OneDrive - S&P Global*` / `%USERPROFILE%\S&P Global*` / mounted network drives on Windows, or `~/Library/CloudStorage/OneDrive*` on macOS).
   - Briefly show me the discovered workbook folders and any candidate SharePoint/OneDrive sync folders and confirm once if I want to add any other `--scan-dirs` or `--reference-roots` paths.
2. **Implement Tasks 1–5 from `02_Portfolio_Scoring_Implementation_Plan.md` via TDD:**
   - Implement `models.py`, `weights.py`, `vba_inspector.py`, `xml_inspector.py`, `reference_resolver.py`, `extractability.py`, `hygiene.py`, `scorer.py`, `reporter.py`, `cli.py`, and all 6 files under `tests/` (`conftest.py` + 5 test modules) matching the calibrated v1.1 plan.
   - Verify all `13/13` unit & E2E tests and `ruff` checks pass.
3. **Execute the Live Read-Only Portfolio Assessment (With `--reference-roots`):**
   - Run `portfolio_assessment.cli` across all confirmed `--scan-dirs`, passing all confirmed local peer/SharePoint/OneDrive/UNC folders to `--reference-roots`.
   - Confirm that any `.xlsx`/`.xlsm` workbooks overlapping the Section 7 benchmark (`Brazil`, `Eulr`, `Big-5`, `PADD_Diesel`, `PADD_Gasoline`, `Uslr`, `Felr`, etc.) match expected calibration behavior while newly resolved S&P SharePoint/UNC links record `CONFIRMED_EXACT_MATCH`, `CONFIRMED_STALE_CACHE_DRIFT`, `RESOLVED_SHEET_MISSING`, or `CONFIRMED_BINARY_FILE_EXISTS` (`.xlsb`/`.xls`).
4. **Deliver Executive Scorecard Readout:**
   - Verify all 4 generated files in `reports/`:
     - `portfolio_executive_scorecard.md`
     - `portfolio_scorecard.csv`
     - `portfolio_cell_defects.csv`
     - `portfolio_external_links_audit.csv`
   - Present a clear Leadership summary of the ranked `MRI`, `LES`, `MHS`, `Defect Rate (%)`, Readiness Tiers (`Tier 1`–`Tier 4`), top hygiene defects, and confirmed vs. drifted/unresolved S&P external links.
```
