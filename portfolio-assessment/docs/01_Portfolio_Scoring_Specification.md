# Specification: Workbook Modernization Portfolio Scoring Framework (`LES`, `MHS`, `MRI`)

| Metadata | Details |
| :--- | :--- |
| **Document ID** | `ENT-SPEC-PORTFOLIO-SCORING-001` (v1.1 — Dry-Run Calibrated) |
| **Package Name** | `portfolio-assessment` (`src/portfolio_assessment/`) |
| **Headline Metrics** | **Logic Extractability Score (`LES`, 0–100%)**, **Model Hygiene Score (`MHS`, 0–100%)** + **Defect Rate (`100% - MHS`)**, **Modernization Readiness Index (`MRI`, 0–100%)** |
| **Execution Mode** | Standalone read-only OpenXML (`iterparse`) + MS-OVBA binary stream analyzer (`0` third-party runtime dependencies; zero mutations to source `.xlsx`/`.xlsm`/`.xlsb`/`.xls` files) |

---

## 1. Purpose, Scope & Non-Goals

### 1.1 Purpose
Provide Engineering and Business Leadership with an objective, auditable, cell-accurate `0–100%` scoring engine across all candidate commodity modeling spreadsheets (`.xlsx`, `.xlsm`), answering two executive questions per workbook alongside a single overall readiness score:
1. **Logic Extractability Score (`LES`, 0–100%):** How completely and deterministically can we extract the modeling logic (formulas, UDFs, macros, external feeds, and time-series structures) into governed Google Sheets, Cloud Run Python, and BigQuery ML?
2. **Model Hygiene Score (`MHS`, 0–100%) & Defect Rate (`100% - MHS`):** How free is the workbook from bad data (cached `#REF!`/`#VALUE!` errors, accidental drag/paste formula overwrites, unlocked reference drift, broken named ranges, and stale/local external links)?
3. **Modernization Readiness Index (`MRI`, 0–100%):** Guardrail-weighted composite score classifying every workbook into `Tier 1` through `Tier 4` with concrete remediation actions and cell-level evidence logs.

### 1.2 In-Scope Deliverables
* Self-contained Python package and CLI (`python -m portfolio_assessment.cli`) requiring only Python `>=3.11` standard library at runtime.
* Automated discovery across one or more target model directories (`--scan-dirs`), deduplicating superseded vintage/draft copies (e.g., `Callr202406.xlsx` vs. `Callr202409.xlsx`, `Latinlr202409 3Q.xlsx` vs. `Latinlr202409.xlsx`) by default while supporting `--include-all-vintages`.
* Four generated report artifacts in `reports/` (`--output-dir`):
  1. `portfolio_executive_scorecard.md` — Executive summary table, archetype badges, active vs. `N/A` sub-scores with effective weights, and top remediation recommendations per workbook.
  2. `portfolio_scorecard.csv` — Machine-readable flat table of all headline scores, sub-scores (`E1..E5`, `H1..H5`), and raw telemetry counts.
  3. `portfolio_cell_defects.csv` — Auditable `(workbook_name, sheet_name, cell_coord, sub_metric, defect_type, severity, detail)` evidence rows backing deductions.
  4. `portfolio_external_links_audit.csv` — Per-link syntactic classification (`CLEAN_CORPORATE_LINK`, `PRIOR_VINTAGE_DRIFT`, `GHOST_OR_LOCAL_PATH`) plus live `--reference-roots` sheet/cell/drift confirmation status.
* Automated `pytest` suite (`tests/`) covering synthetic archetype fixtures, live `--reference-roots` drift verification, and CLI E2E report generation.

### 1.3 Non-Goals & Strict Safety Rules
* **100% Read-Only:** Never modifies, touches, re-saves, or executes macros inside any target `.xlsx`, `.xlsm`, `.xlsb`, or `.xls` workbook (`zipfile.ZipFile(path, mode="r")` only).
* Legacy binary BIFF8/BIFF12 `.xls` / `.xlsb` files are not target inputs for primary OpenXML formula scoring, but when referenced *externally* by an `.xlsx`/`.xlsm` workbook via `xl/externalLinks`, their file existence inside `--reference-roots` is verified (`CONFIRMED_BINARY_FILE_EXISTS`).

---

## 2. Archetype Detection & Active-Surface Weight Re-Normalization

### 2.1 Why Static Weights Fail Across Archetypes
Static weights distort comparisons across heterogeneous models: awarding `E2 = 100%` (`+20` points) when a workbook has no macros inflates macro-free XLL workbooks, whereas penalizing `E5` when a workbook has no time-series axis punishes cross-sectional calculators.

### 2.2 Proportional Re-Normalization Law
Every sub-metric $i \in \{1..5\}$ has a **Base Weight $w_i$** ($\sum_{i=1}^{5} w_i = 1.0$) and a deterministic **Applicability Gate $a_i \in \{0, 1\}$**:
* If $a_i = 0$, sub-metric $i$ is recorded as **`N/A`** (`score = None`, `effective_weight = 0.0`).
* Active sub-metrics ($a_i = 1$) receive proportionally re-normalized weights summing to `1.0` (retained to 8 decimal places):
  $$w_i^{\text{eff}} = \frac{a_i \cdot w_i}{\sum_{j=1}^{5} a_j \cdot w_j}, \qquad \text{Pillar Score} = \sum_{i:\, a_i=1} w_i^{\text{eff}} \cdot S_i$$
* Edge-case fallback: if a degenerate empty workbook has $\sum a_j = 0$, its `LES` is `100.0` (nothing to extract) and `MHS` is evaluated via `H5`.

### 2.3 Automatic Archetype Badge Classification
Each workbook is tagged with a human-readable **Archetype Badge** derived from its active surfaces:
1. **`XLL / Add-In Time-Series Model`** — `xll_udf_cells / max(formula_cells, 1) >= 0.05` and $a_{E5} = 1$.
2. **`Hybrid VBA + Circular Model`** — $a_{E2} = 1$ and `iterate == 1`.
3. **`DCF / Solver + VBA Macro Model`** — $a_{E2} = 1$ and `iterate == 0`.
4. **`Circular Equilibrium Time-Series Model`** — `iterate == 1` and $a_{E5} = 1$ and $a_{E2} == 0$.
5. **`Standard Acyclic Time-Series Model`** — $a_{E5} = 1$, $a_{E2} = 0$, `iterate == 0`, `xll_share < 0.05`.
6. **`Cross-Sectional / Tabular Calculator`** — $a_{E5} = 0$.

---

## 3. Exact Mathematical Specification of Pillar 1: `LES` (`0–100%`)

### `E1` — Formula & UDF Portability (Base Weight `0.35`)
* **Gate ($a_{E1}$):** `1` iff `total_formula_cells >= 1`, else `0`.
* **Cell Credit Assignment ($c_f \in [0.0, 1.0]$ per formula cell $f$):**
  1. **`0.00` (Opaque / Unextractable):** Formula invokes `INDIRECT(`, `RTD(`, `CUBEVALUE(`, `CUBEMEMBER(`, `CALL(`, or contains `_xll.` / add-in UDFs **without** a valid non-error cached `<v>` value (`ctype == "e"` or `value is None`).
  2. **`0.25` (Proprietary XLL Feed With Non-Error Cached `<v>`):** Formula invokes `_xll.` (case-insensitive, e.g., `_xll.sjpoint(...)`) and carries a non-error cached `<v>` value (cached snapshot exists, but compiled C++ add-in logic requires a dedicated BigQuery data-connector replacement).
  3. **`0.85` (Compilable Advanced / Array Construct):** Formula is a `{=CSE}` array formula (`t="array"`), calls `OFFSET(`, or uses `_xlfn.` prefixed functions (without falling into rules 1–2).
  4. **`1.00` (Native Standard Formula):** All standard deterministic spreadsheet formulas (`SUM`, `IF`, `IFERROR`, `SUMIFS`, `INDEX`, `MATCH`, `VLOOKUP`, `HLOOKUP`, `SUMPRODUCT`, `IRR`, `NPV`, `MIN`, `MAX`, `AVERAGE`, `EOMONTH`, `DATE`, arithmetic, etc.).
* **Equation:**
  $$E_1 = \operatorname{clamp}_{[0, 100]}\left(100.0 \times \frac{\sum_{f=1}^{N_f} c_f}{N_f}\right)$$

### `E2` — Macro & Procedural Transparency (Base Weight `0.20`)
* **Gate ($a_{E2}$):** `1` iff `xl/vbaProject.bin` exists with $>0$ non-empty procedural VBA lines (excluding `Attribute VB_*` headers and comments) OR `DPB=` lock protection without readable module source. *(Note: `.xlsm` files whose `vbaProject.bin` is missing or `0`-byte / empty evaluate to $a_{E2} = 0$, `N/A`.)*
* **MS-OVBA Compression Handling:** Strip single-byte LZNT1 flag bytes between printable ASCII bytes before extracting `Attribute VB_Name = "..."` module names and procedural tokens.
* **Equation (when $a_{E2} = 1$):**
  * If VBA project stream is locked/unreadable (`DPB="` present with `0` readable procedures and size $> 4096$ bytes): $E_2 = 20.0$.
  * Otherwise start at `95.0` and apply bounded deductions:
    * `-35.0` if Win32 `Declare [PtrSafe] Function/Sub`, `[Call] Shell(`, `WScript.Shell`, or `URLDownloadToFile` calls appear. *(Do NOT match bare `.dll`, which falsely matches Excel's built-in `VBE7.DLL` runtime header embedded in every `vbaProject.bin`.)*
    * `-20.0` if external desktop COM/DB objects (`CreateObject("ADODB`, `DAO`, `Scripting.FileSystemObject`, `Excel.Application`, or `Workbooks.Open`) appear.
    * `-5.0` if total procedural VBA lines $> 500$ (and `-5.0` additional if $> 1,500$ lines).
    * $$E_2 = \operatorname{clamp}_{[0, 100]}(\text{score})$$

### `E3` — Graph & Convergence Determinism (Base Weight `0.15`)
* **Gate ($a_{E3}$):** `1` iff `total_formula_cells >= 1`, else `0`.
* **Equation (when $a_{E3} = 1$):**
  * Start at `100.0`.
  * **Circularity deduction:** If `calcPr.iterate == "1"`:
    * Deduct `10.0` for bounded iterative circular coupling (`iterateCount <= 25`), or `15.0` if `iterateCount > 25` or unspecified.
    * Deduct `12.0` if `calcPr.calcCompleted == "0"` on an iterative workbook.
  * **Volatility deduction:** Let $v_{\text{rate}} = \frac{\text{cells calling NOW/RAND/RANDBETWEEN/TODAY/CELL}}{\text{total\_formula\_cells}}$. Deduct $\min(25.0,\; 250.0 \times v_{\text{rate}})$.
  * $$E_3 = \operatorname{clamp}_{[0, 100]}(\text{score})$$

### `E4` — External Feed & Connection Decoupling (Base Weight `0.15`)
* **Gate ($a_{E4}$):** `1` iff `active_ext_link_formula_cells > 0` OR `xll_udf_cells > 0` OR `xl/connections.xml` exists OR external `pivotCache` exists; else `0` (`N/A`).
* **Equation (when $a_{E4} = 1$):**
  * If `active_ext_link_formula_cells > 0`, let $c_{\text{cache}} \in [0, 1]$ be the fraction of external-link formula cells carrying a valid non-missing, non-`#REF!` cached `<v>` value; base score $= 88.0 \times c_{\text{cache}}$. If `active_ext_link_formula_cells == 0`, base score $= 88.0$.
  * Deduct `18.0` if `xl/connections.xml` defines external ODBC/OLEDB/SQL/Web connections.
  * Deduct `10.0` if external PivotTable caches exist.
  * Deduct $\min(28.0,\; 8.0 + 40.0 \times \frac{\text{xll\_udf\_cells}}{\text{total\_formula\_cells}})$ if `xll_udf_cells > 0` (proprietary desktop add-in feed replacement).
  * Deduct $\min(10.0,\; 0.15 \times \text{active\_external\_workbook\_count})$ for multi-workbook fan-in complexity.
  * $$E_4 = \operatorname{clamp}_{[0, 100]}(\text{score})$$

### `E5` — Time-Series & R1C1 Structural Regularity (Base Weight `0.15`)
* **Gate ($a_{E5}$):** `1` iff at least one worksheet contains a monotonic horizontal period header row (within rows `1..35`) of $\ge 6$ calendar years (`1970..2100` integers, step $\le 10$) or Excel serial dates (`25569..73050`, step $\le 400$) — **whether stored as static literals or formula-computed headers (`=F5+1`, `='KeyInputs'!C5`)** — alongside $\ge 6$ formula cells on that sheet; else `0` (`N/A`).
* **Equation (when $a_{E5} = 1$):**
  * Across all formula cells on sheets with detected time axes, compute the **R1C1 Compression Ratio** $R = \frac{\text{time\_aligned\_formula\_cells}}{\max(\text{unique\_(row, r1c1)\_patterns\_on\_time\_sheets}, 1)}$.
  * Map $R$ smoothly to `[45.0, 100.0]`:
    $$E_5 = \operatorname{clamp}_{[45, 100]}\bigl(45.0 + 36.0 \cdot \log_{10}(\max(R, 1.0))\bigr)$$
    *(At $R=1\times \rightarrow 45.0$; $R=5\times \rightarrow 70.2$; $R=10\times \rightarrow 81.0$; $R=25\times \rightarrow 95.3$; $R \ge 34\times \rightarrow 100.0$.)*

---

## 4. Exact Mathematical Specification of Pillar 2: `MHS` (`0–100%`) & `Defect Rate`

### `H1` — Evaluated Cell Error Cleanliness (Base Weight `0.25`)
* **Gate ($a_{H1}$):** `1` iff `total_populated_cells >= 1`, else `0`.
* **Measurement:** Scan all cells with `t="e"` (`#REF!`, `#NAME?`, `#VALUE!`, `#DIV/0!`, `#NUM!`, `#N/A`, `#NULL!`), **excluding intentional chart-masking cells** whose `<f>` explicitly invokes `NA()`:
  * Weighted error sum:
    $$W_{\text{err}} = 3.0 \cdot (N_{\text{\#REF!}} + N_{\text{\#NAME?}} + N_{\text{\#NULL!}}) + 2.0 \cdot N_{\text{\#VALUE!}} + 1.0 \cdot (N_{\text{\#DIV/0!}} + N_{\text{\#NUM!}} + N_{\text{unintentional \#N/A}})$$
  * Weighted error rate $e = \frac{W_{\text{err}}}{\max(\text{total\_formula\_cells}, 1)}$.
* **Equation:**
  $$H_1 = \operatorname{clamp}_{[0, 100]}\bigl(100.0 - 22.0 \cdot \log_{10}(1.0 + 1000.0 \cdot e)\bigr)$$

### `H2` — Formula Continuity & Drag Integrity (Base Weight `0.25`)
* **Gate ($a_{H2}$):** `1` iff `structured_series_cells >= 6` or `fill_glitches > 0`, else `0`.
* **Three Deterministic Detectors (scanned across rows of length $\ge 4$, plus vertical columns on sheets without a horizontal time axis):**
  1. **`HARDCODED_ISLAND_IN_FORMULA_RUN`:** Within a row where $\ge 6$ cells share the exact same `R1C1` formula signature $P$ (or within a vertical column where $P$ occupies $\ge \max(6, \lfloor 0.55 \cdot N_{\text{col}} \rfloor)$ cells, preventing scattered financial-statement subtotals from misfiring), `1` to `5` contiguous coordinate-adjacent numeric cells (`ctype not in ("e", "s")`) immediately sandwiched between two $P$ cells contain a hardcoded value instead of $P$.
  2. **`UNLOCKED_DRAG_REFERENCE_DRIFT`:** Within a formula run (`>= 4` matching `R1C1` cells), a cell with unanchored relative coordinates evaluates to `#VALUE!` or `#REF!`.
  3. **`AUTO_INCREMENT_FILL_GLITCH`:** Within a horizontal row, $\ge 4$ coordinate-adjacent static floats with non-zero fractional part (`abs(x - round(x)) > 1e-4`, excluding integer years/indices) step by exact `+1.0` (`x, x+1.0, x+2.0, x+3.0` from dragging without holding `Ctrl`).
* **Equation:** Let $d = \frac{N_{\text{island}} + N_{\text{drift}} + N_{\text{fill\_glitch}}}{\max(\text{structured\_series\_cells}, 6)}$.
  $$H_2 = \operatorname{clamp}_{[0, 100]}\bigl(100.0 - 28.0 \cdot \log_{10}(1.0 + 500.0 \cdot d)\bigr)$$

### `H3` — Reference & Named-Range Validity (Base Weight `0.20`)
* **Gate ($a_{H3}$):** `1` iff `total_formula_cells >= 1` or `total_defined_names >= 1`, else `0`.
* **Measurement:**
  * `dead_formula_ref_rate` ($r_f$): Fraction of formula cells whose `<f>` text (after stripping double-quoted string literals) contains literal `#REF!` or references an internal worksheet name absent from `xl/workbook.xml` (**matched case-insensitively**, with `''` unescaped to `'`).
  * `broken_defined_name_rate` ($r_n$): Fraction of `<definedName>` definitions containing `#REF!` (ignoring built-in `_xlnm.*` names unless `#REF!`).
* **Equation:**
  * $S_{\text{formula\_refs}} = 100.0 \times (1.0 - r_f)^{5}$
  * If `total_defined_names == 0`: $H_3 = S_{\text{formula\_refs}}$.
  * Else: $S_{\text{names}} = 100.0 \times (1.0 - r_n)$, and $H_3 = 0.60 \cdot S_{\text{formula\_refs}} + 0.40 \cdot S_{\text{names}}$.

### `H4` — External Link & Vintage Hygiene (Base Weight `0.20`)
* **Gate ($a_{H4}$):** `1` iff `total_declared_external_links >= 1` OR `active_ext_link_formula_cells >= 1`, else `0` (`N/A` for self-contained workbooks).
* **Link Target Health Classification (for each `externalLink{k}`):**
  * **`1.0` (`CLEAN_CORPORATE_LINK`):** Corporate `https://...sharepoint.com/sites/...` (or `/sites/...`, `../...`, or bare `.xlsx`/`.xlsm`/`.xlsb` filename) whose vintage tag (`20\d{4}`, if present) is $\ge$ the host workbook's vintage tag.
  * **`0.5` (`PRIOR_VINTAGE_DRIFT`):** Link target carrying an older `20\d{4}` vintage tag than the host workbook (e.g., `LR202406` or `VGOLR202403` inside an `LR202409` workbook).
  * **`0.0` (`GHOST_OR_LOCAL_PATH`):** Local drive paths (`file:///C:\...`, `D:\...`, `/Users/.../Downloads/...`, `/Temp/`), personal OneDrive (`-my.sharepoint.com/personal/`), or legacy Windows UNC shares (`\\hou0\...`).
* **Equation (when $a_{H4} = 1$):**
  * If `active_ext_link_formula_cells == 0` (dormant/unpruned metadata stubs only, zero live external formula dependencies):
    $$H_4 = \operatorname{clamp}_{[55, 85]}(85.0 - 1.5 \cdot N_{\text{orphan}} - 0.5 \cdot N_{\text{ghost}})$$
  * Otherwise (`active_ext_link_formula_cells >= 1`):
    * `active_cell_link_score` ($S_{\text{active}}$): Cell-weighted average link health (`0..100`) across all `active_ext_link_formula_cells`.
    * `orphan_link_ratio` ($r_{\text{orphan}}$): Fraction of declared `xl/externalLinks` entries referenced by `0` formulas in the workbook.
    * $$H_4 = \operatorname{clamp}_{[0, 100]}\bigl(0.75 \cdot S_{\text{active}} + 25.0 \cdot (1.0 - r_{\text{orphan}}) - 10.0 \cdot N_{\text{missing\_sheets}}\bigr)$$

### `H5` — Calculation State & Sheet Hygiene (Base Weight `0.10`)
* **Gate ($a_{H5}$):** Always `1`.
* **Deductions from `100.0`:**
  * `-25.0` if `calcPr.calcCompleted == "0"`.
  * `-15.0` if `calcPr.calcMode == "manual"`.
  * `-5.0` per dead/archived/addin-stub sheet (`shooju_addin`, or sheet name matching `(?i)(_old$|^old_|not_updated|archive|backup|temp)`), capped at `-25.0`.
  * Empty formatting shell bloat: let $b = \frac{\text{empty\_styled\_c\_elements}}{\max(\text{total\_c\_elements}, 1)}$; if $b > 0.35$, deduct $\min(25.0,\; 50.0 \times (b - 0.35))$.
  * $$H_5 = \operatorname{clamp}_{[0, 100]}(\text{score})$$

### 4.4 Optional Live Reference Confirmation on Corporate Network (`--reference-roots`)
When executed on an S&P corporate laptop with synced SharePoint/OneDrive folders or mounted UNC drives (`--reference-roots <dir1> <dir2> ...`), the scanner augments syntactic `H4`/`E4` link classification with empirical target verification (`portfolio_external_links_audit.csv`), caching peer workbook cell values across the portfolio so each referenced workbook is parsed at most once:
1. Searches `--reference-roots` for each referenced external filename (`.xlsx`, `.xlsm`, `.xlsb`, `.xls`).
2. For `.xlsb`/`.xls` binary targets found on disk, records `CONFIRMED_BINARY_FILE_EXISTS`.
3. For `.xlsx`/`.xlsm` targets found on disk:
   * Verifies every referenced `ext_sheet` exists (`RESOLVED_SHEET_MISSING` if absent).
   * Compares direct cell references (`'[idx]Sheet'!$A$1`) against the host workbook's cached `<v>` value (`CONFIRMED_EXACT_MATCH` within $10^{-8}$ vs. `CONFIRMED_STALE_CACHE_DRIFT` with `max_rel_drift`).

---

## 5. Overall Score (`MRI`) & Readiness Tiers

$$\text{Defect Rate (\%)} = \operatorname{round}(100.0 - \text{MHS},\; 2)$$

$$\text{MRI} = \operatorname{clamp}_{[0, 100]}\Bigl(0.55 \cdot \text{LES} + 0.45 \cdot \text{MHS} - 0.15 \cdot \max\bigl(0.0,\; 60.0 - \min(\text{LES}, \text{MHS})\bigr)\Bigr)$$

| `MRI` Range | Readiness Tier | Action Playbook |
| :---: | :--- | :--- |
| **`85.0 – 100.0`** | **`Tier 1 — Fast-Track Automated Port`** | Direct Google Sheets + Cloud Run solver + BigQuery ML deployment. |
| **`70.0 – 84.9`** | **`Tier 2 — Guided Cloud Equilibrium Port`** | Compile R1C1 solver + decouple SharePoint links to BigQuery + prune `#REF!` names. |
| **`50.0 – 69.9`** | **`Tier 3 — Connector & Hygiene Remediation First`** | Replace `_xll` / `connections.xml` feeds with BigQuery and fix `#VALUE!` / drag defects. |
| **`< 50.0`** | **`Tier 4 — Re-Specification Required`** | Remediate locked desktop binaries and structural corruption with model owners. |

---

## 6. Module Architecture (`portfolio-assessment/`)

```text
portfolio-assessment/
├── README.md
├── Makefile
├── pyproject.toml
├── docs/
│   ├── 01_Portfolio_Scoring_Specification.md
│   ├── 02_Portfolio_Scoring_Implementation_Plan.md
│   └── 03_Antigravity_Handoff_Prompt_SP_Laptop.md
├── reports/                                      # Generated Markdown & CSV scorecards
├── src/
│   └── portfolio_assessment/
│       ├── __init__.py
│       ├── models.py                             # Frozen dataclasses for metrics & defects
│       ├── weights.py                            # Dynamic weight re-normalization, archetypes & MRI
│       ├── vba_inspector.py                      # Pure-Python MS-OVBA binary container inspector
│       ├── xml_inspector.py                      # Streaming OpenXML + shared-formula R1C1 scanner
│       ├── reference_resolver.py                 # Syntactic link audit + --reference-roots verifier
│       ├── extractability.py                     # Pillar 1 (E1..E5 + LES) calculator
│       ├── hygiene.py                            # Pillar 2 (H1..H5 + MHS + cell defect detectors)
│       ├── scorer.py                             # Discovery, vintage deduplication & peer-cached runner
│       ├── reporter.py                           # Executive Markdown + 3 CSV report writers
│       └── cli.py                                # CLI entrypoint (python -m portfolio_assessment.cli)
└── tests/
    ├── conftest.py                               # Synthetic in-memory OpenXML .xlsx/.xlsm builder
    ├── test_archetype_weights.py
    ├── test_xml_and_vba_inspector.py
    ├── test_reference_resolver.py
    ├── test_scorers_and_hygiene_detectors.py
    └── test_cli_and_portfolio_e2e.py
```

---

## 7. Empirical Dry-Run Calibration Benchmark (12-Workbook Reference Baseline)

When evaluated against the 12 reference commodity models (`--reference-roots` pointed at the Refining Long-Term peer folder), the calibrated engine produces the following exact scores (use to verify implementation parity on corporate hardware):

| Rank | Workbook | Archetype | `LES` | `MHS` | Defect Rate | `MRI` | Readiness Tier |
| :---: | :--- | :--- | ---: | ---: | ---: | ---: | :--- |
| 1 | `2023-11-27-Brazil_TT_v13_RJEB.xlsm` | DCF / Solver + VBA Macro Model | `97.1%` | `89.2%` | `10.8%` | `93.5%` | Tier 1 |
| 2 | `Eulr202409.xlsx` | Circular Equilibrium Time-Series Model | `91.8%` | `91.5%` | `8.5%` | `91.6%` | Tier 1 |
| 3 | `Felr202409.xlsx` | Circular Equilibrium Time-Series Model | `94.2%` | `82.6%` | `17.4%` | `89.0%` | Tier 1 |
| 4 | `Tankerlr202409.xlsx` | Circular Equilibrium Time-Series Model | `93.6%` | `79.8%` | `20.2%` | `87.4%` | Tier 1 |
| 5 | `Uslr202409.xlsx` | Standard Acyclic Time-Series Model | `93.9%` | `78.2%` | `21.9%` | `86.8%` | Tier 1 |
| 6 | `Canlr202409.xlsx` | Circular Equilibrium Time-Series Model | `92.7%` | `76.0%` | `23.9%` | `85.2%` | Tier 1 |
| 7 | `LAMLR202409.xlsx` | Standard Acyclic Time-Series Model | `91.2%` | `76.6%` | `23.4%` | `84.6%` | Tier 2 |
| 8 | `PADD_Diesel_Model_V4 1.xlsm` | XLL / Add-In Time-Series Model | `80.8%` | `89.2%` | `10.8%` | `84.6%` | Tier 2 |
| 9 | `Latinlr202409.xlsx` | Circular Equilibrium Time-Series Model | `92.5%` | `69.6%` | `30.4%` | `82.2%` | Tier 2 |
| 10 | `Callr202409.xlsx` | Circular Equilibrium Time-Series Model | `90.5%` | `71.1%` | `28.9%` | `81.8%` | Tier 2 |
| 11 | `PADD_Gasoline_Model_V3 (1).xlsm` | XLL / Add-In Time-Series Model | `79.1%` | `81.0%` | `19.0%` | `79.9%` | Tier 2 |
| 12 | `Big-5 balance and supply model rev1 Europe.xlsx` | XLL / Add-In Time-Series Model | `71.0%` | `77.4%` | `22.6%` | `73.9%` | Tier 2 |
