# Workbook Modernization Portfolio Scoring (`LES`, `MHS`, `MRI`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a self-contained, read-only Python CLI and assessment package (`portfolio-assessment/`) that scans `.xlsx`/`.xlsm` commodity modeling workbooks and produces deterministic `0–100%` **Logic Extractability (`LES`)**, **Model Hygiene (`MHS` + `Defect Rate`)**, and **Modernization Readiness Index (`MRI`)** scorecards alongside cell-level defect and external-link verification logs.

**Architecture:** A single-pass streaming OpenXML (`ElementTree.iterparse`) and pure-Python MS-OVBA binary inspector extracts formulas (expanded to row/column-relative `R1C1`), cached `<v>` values/errors, VBA procedural calls, and external links without mutating source files. Active-Surface Proportional Weight Re-Normalization scores only applicable capabilities per workbook archetype, optionally confirming live external workbook/sheet/cell targets via `--reference-roots` when run on an S&P corporate laptop.

**Tech Stack:** Python `>=3.11`, standard library (`zipfile`, `xml.etree.ElementTree`, `csv`, `dataclasses`, `argparse`, `math`, `re`), `defusedxml>=0.7.1` (optional safe XML wrapper, already in workspace `.venv`), `pytest>=8.0`, `ruff>=0.3`.

## Global Constraints

- **Strictly Read-Only File Access:** Every `.xlsx` / `.xlsm` open call MUST use `zipfile.ZipFile(path, mode="r")`. Never modify, touch, or re-save any workbook.
- **Zero New Third-Party Dependencies:** Use only Python 3.11+ standard library modules (plus `pytest` and `ruff` already installed in the shared root `.venv` or a local `.venv`).
- **Exact Headline Metric Names & Polarity:**
  - `LES` = `Logic Extractability Score` (`0.0–100.0`, higher = more extractable)
  - `MHS` = `Model Hygiene Score` (`0.0–100.0`, higher = cleaner) paired with `Defect Rate (%) = round(100.0 - MHS, 2)`
  - `MRI` = `Modernization Readiness Index` (`clamp(0.55 * LES + 0.45 * MHS - 0.15 * max(0.0, 60.0 - min(LES, MHS)), 0.0, 100.0)`)
- **Active-Surface Weight Re-Normalization:** Sub-metrics whose applicability gate is `False` MUST be reported with `applicable=False, score=None, effective_weight=0.0` (`N/A`), redistributing their base weight proportionally across active sub-metrics (`w_eff = w_i / sum_active_w`).
- **Intentional Chart `=NA()` Exclusion:** Cached `#N/A` cells whose formula explicitly calls `NA()` MUST NOT be penalized in `H1`.
- **Workspace Isolation:** Do not modify any files inside `brazil-power-v13/` or `Eulr/`.

---

## File Structure

- `portfolio-assessment/pyproject.toml` — Package metadata, CLI script entry point (`assess-portfolio`), `pytest` (`pythonpath = ["src"]`), and `ruff` configuration.
- `portfolio-assessment/Makefile` — Auto-detects local `.venv` or parent `../.venv` (`lint`, `test`, `run`).
- `portfolio-assessment/src/portfolio_assessment/__init__.py` — Package version export.
- `portfolio-assessment/src/portfolio_assessment/models.py` — Frozen/typed dataclasses for sub-metrics, pillar scores, cell defects, external link audits, and workbook scorecards.
- `portfolio-assessment/src/portfolio_assessment/weights.py` — Active-Surface Proportional Weight Re-Normalization, Archetype Badge classifier, and `MRI` + Tier calculator.
- `portfolio-assessment/src/portfolio_assessment/vba_inspector.py` — Pure-Python MS-OVBA binary container scanner (`xl/vbaProject.bin`) detecting executable VBA lines, lock state, and Win32/Shell/COM/ADO calls.
- `portfolio-assessment/src/portfolio_assessment/xml_inspector.py` — Single-pass `iterparse` OpenXML scanner, shared-formula expander, `R1C1` normalizer, and time-axis detector.
- `portfolio-assessment/src/portfolio_assessment/reference_resolver.py` — Syntactic SharePoint/vintage/ghost link classifier + optional `--reference-roots` live `.xlsx`/`.xlsm` target sheet/cell/drift verifier for S&P corporate laptops.
- `portfolio-assessment/src/portfolio_assessment/extractability.py` — Pillar 1 (`E1`–`E5` + `LES`) calculator.
- `portfolio-assessment/src/portfolio_assessment/hygiene.py` — Pillar 2 (`H1`–`H5` + `MHS` + cell-level drag/island/error defect detectors).
- `portfolio-assessment/src/portfolio_assessment/scorer.py` — Directory discovery, vintage deduplication, and `assess_workbook` / `assess_portfolio` orchestrator.
- `portfolio-assessment/src/portfolio_assessment/reporter.py` — Generates `portfolio_executive_scorecard.md`, `portfolio_scorecard.csv`, `portfolio_cell_defects.csv`, and `portfolio_external_links_audit.csv`.
- `portfolio-assessment/src/portfolio_assessment/cli.py` — Command-line interface (`--scan-dirs`, `--reference-roots`, `--output-dir`, `--include-all-vintages`).
- `portfolio-assessment/README.md` — Usage guide for both standalone and S&P corporate laptop execution.
- `portfolio-assessment/tests/conftest.py` — Helper that builds minimal valid in-memory/temp `.xlsx`/`.xlsm` OpenXML archives for fast deterministic unit tests.
- `portfolio-assessment/tests/test_archetype_weights.py` — Unit tests for Task 1.
- `portfolio-assessment/tests/test_xml_and_vba_inspector.py` — Unit tests for Task 2.
- `portfolio-assessment/tests/test_reference_resolver.py` — Unit tests for Task 3.
- `portfolio-assessment/tests/test_scorers_and_hygiene_detectors.py` — Unit tests for Task 4.
- `portfolio-assessment/tests/test_cli_and_portfolio_e2e.py` — End-to-end CLI & workspace integration tests for Task 5.

---

### Task 1: Package Scaffolding, Data Models & Dynamic Archetype Weight Engine

**Files:**
- Create: `portfolio-assessment/pyproject.toml`
- Create: `portfolio-assessment/Makefile`
- Create: `portfolio-assessment/src/portfolio_assessment/__init__.py`
- Create: `portfolio-assessment/src/portfolio_assessment/models.py`
- Create: `portfolio-assessment/src/portfolio_assessment/weights.py`
- Test: `portfolio-assessment/tests/test_archetype_weights.py`

**Interfaces:**
- Consumes: Python standard library (`dataclasses`, `typing`).
- Produces:
  - `models.SubMetricScore`, `models.PillarScore`, `models.CellDefectRecord`, `models.ExternalLinkAuditRecord`, `models.WorkbookScorecard`
  - `weights.clamp(val: float, lo: float = 0.0, hi: float = 100.0) -> float`
  - `weights.renormalize_sub_metrics(specs: list[tuple[str, str, float, bool, float | None, str]]) -> tuple[float, list[SubMetricScore]]`
  - `weights.classify_archetype(total_formula_cells: int, xll_udf_cells: int, has_vba: bool, is_iterative: bool, has_time_axis: bool) -> str`
  - `weights.compute_mri_and_tier(les: float, mhs: float) -> tuple[float, str, str]`

- [ ] **Step 1: Create `pyproject.toml`, `Makefile`, `__init__.py`, and write the failing test**

Create `portfolio-assessment/pyproject.toml`:
```toml
[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.build_meta"

[project]
name = "portfolio-assessment"
version = "1.0.0"
description = "Workbook Modernization Portfolio Scoring Engine (LES, MHS, MRI)"
requires-python = ">=3.11"
dependencies = []

[project.scripts]
assess-portfolio = "portfolio_assessment.cli:main"

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]

[tool.ruff]
line-length = 108
target-version = "py311"
```

Create `portfolio-assessment/Makefile`:
```makefile
.PHONY: lint test run

VENV_DIR := $(shell if [ -d .venv ]; then echo .venv; else echo ../.venv; fi)
PYTHON := $(VENV_DIR)/bin/python
PYTEST := $(VENV_DIR)/bin/pytest
RUFF := $(VENV_DIR)/bin/ruff

lint:
	$(RUFF) check src tests

test:
	$(PYTEST) -v

run:
	PYTHONPATH=src $(PYTHON) -m portfolio_assessment.cli
```

Create `portfolio-assessment/src/portfolio_assessment/__init__.py`:
```python
"""Workbook Modernization Portfolio Scoring Package (LES, MHS, MRI)."""

__version__ = "1.0.0"
```

Create `portfolio-assessment/tests/test_archetype_weights.py`:
```python
from __future__ import annotations

import pytest

from portfolio_assessment.weights import (
    classify_archetype,
    compute_mri_and_tier,
    renormalize_sub_metrics,
)


def test_macro_free_archetype_redistributes_e2_weight_without_free_bonus() -> None:
    specs = [
        ("E1", "Formula & UDF Portability", 0.35, True, 50.0, "50% XLL"),
        ("E2", "Macro & Procedural Transparency", 0.20, False, None, "Macro-free"),
        ("E3", "Graph & Convergence Determinism", 0.15, True, 100.0, "DAG"),
        ("E4", "External Feed & Connection Decoupling", 0.15, False, None, "Self-contained"),
        ("E5", "Time-Series & R1C1 Regularity", 0.15, False, None, "Cross-sectional"),
    ]
    pillar_score, subs = renormalize_sub_metrics(specs)
    by_code = {s.code: s for s in subs}

    assert by_code["E2"].applicable is False
    assert by_code["E2"].score is None
    assert by_code["E2"].effective_weight == 0.0
    assert by_code["E1"].effective_weight == pytest.approx(0.70)
    assert by_code["E3"].effective_weight == pytest.approx(0.30)
    # 0.70 * 50 + 0.30 * 100 = 65.0 (NOT 82.5 from static free-100% padding)
    assert pillar_score == pytest.approx(65.0)


def test_self_contained_vba_dcf_weights_sum_to_one() -> None:
    specs = [
        ("E1", "Formula & UDF Portability", 0.35, True, 100.0, "Clean"),
        ("E2", "Macro & Procedural Transparency", 0.20, True, 90.0, "38 VBA subs"),
        ("E3", "Graph & Convergence Determinism", 0.15, True, 100.0, "DAG"),
        ("E4", "External Feed & Connection Decoupling", 0.15, False, None, "No ext links"),
        ("E5", "Time-Series & R1C1 Regularity", 0.15, True, 95.0, "23-yr horizon"),
    ]
    score, subs = renormalize_sub_metrics(specs)
    active_weight_sum = sum(s.effective_weight for s in subs if s.applicable)
    assert active_weight_sum == pytest.approx(1.0)
    assert by_e4 := [s for s in subs if s.code == "E4"][0]
    assert by_e4.effective_weight == 0.0
    assert 96.0 <= score <= 97.0


def test_mri_guardrail_penalizes_weak_pillar_and_assigns_tiers() -> None:
    mri_high, tier_high, _ = compute_mri_and_tier(les=95.0, mhs=92.0)
    assert mri_high == pytest.approx(0.55 * 95.0 + 0.45 * 92.0)
    assert tier_high.startswith("Tier 1")

    # Weakest-link guardrail triggers when min(LES, MHS) < 60.0
    mri_penalized, tier_pen, _ = compute_mri_and_tier(les=90.0, mhs=40.0)
    # 0.55*90 + 0.45*40 - 0.15*(60 - 40) = 49.5 + 18.0 - 3.0 = 64.5
    assert mri_penalized == pytest.approx(64.5)
    assert tier_pen.startswith("Tier 3")


def test_archetype_badge_classification() -> None:
    assert classify_archetype(400_000, 260_000, False, False, True) == "XLL / Add-In Time-Series Model"
    assert classify_archetype(15_961, 0, True, False, True) == "DCF / Solver + VBA Macro Model"
    assert classify_archetype(357_708, 0, False, True, True) == "Circular Equilibrium Time-Series Model"
    assert classify_archetype(500, 0, False, False, False) == "Cross-Sectional / Tabular Calculator"
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `portfolio-assessment/`): `../.venv/bin/pytest tests/test_archetype_weights.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'portfolio_assessment.weights'`

- [ ] **Step 3: Write minimal implementation of `models.py` and `weights.py`**

Create `portfolio-assessment/src/portfolio_assessment/models.py`:
```python
"""Typed data structures for LES, MHS, MRI scorecards and cell-level defects."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SubMetricScore:
    code: str
    title: str
    base_weight: float
    applicable: bool
    effective_weight: float
    score: float | None
    summary: str


@dataclass(frozen=True)
class PillarScore:
    name: str
    acronym: str
    score: float
    sub_metrics: list[SubMetricScore]


@dataclass(frozen=True)
class CellDefectRecord:
    workbook_name: str
    sheet_name: str
    cell_coord: str
    sub_metric: str
    defect_type: str
    severity: str
    detail: str


@dataclass(frozen=True)
class ExternalLinkAuditRecord:
    workbook_name: str
    link_index: str
    raw_target: str
    link_health_tier: str
    syntactic_score: float
    active_formula_refs: int
    resolution_status: str
    resolved_local_path: str
    missing_sheets_count: int
    exact_match_cells: int
    drifted_cells: int
    max_rel_drift: float


@dataclass(frozen=True)
class WorkbookScorecard:
    workbook_name: str
    workbook_path: str
    file_size_mb: float
    archetype: str
    vintage_tag: str
    sheet_count: int
    total_populated_cells: int
    total_formula_cells: int
    les: PillarScore
    mhs: PillarScore
    defect_rate: float
    mri: float
    readiness_tier: str
    recommended_action: str
    telemetry: dict[str, Any] = field(default_factory=dict)
```

Create `portfolio-assessment/src/portfolio_assessment/weights.py`:
```python
"""Active-Surface Proportional Weight Re-Normalization, Archetypes, and MRI Composite."""

from __future__ import annotations

from portfolio_assessment.models import SubMetricScore


def clamp(val: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, float(val)))


def renormalize_sub_metrics(
    specs: list[tuple[str, str, float, bool, float | None, str]],
) -> tuple[float, list[SubMetricScore]]:
    """Re-normalize base weights proportionally across applicable sub-metrics."""
    active_base_sum = sum(base_w for _, _, base_w, app, sc, _ in specs if app and sc is not None)
    results: list[SubMetricScore] = []
    weighted_total = 0.0

    for code, title, base_w, app, sc, summary in specs:
        if not app or sc is None or active_base_sum <= 0.0:
            results.append(
                SubMetricScore(
                    code=code,
                    title=title,
                    base_weight=base_w,
                    applicable=False,
                    effective_weight=0.0,
                    score=None,
                    summary=summary,
                )
            )
        else:
            eff_w = base_w / active_base_sum
            clamped_sc = round(clamp(sc), 2)
            weighted_total += eff_w * clamped_sc
            results.append(
                SubMetricScore(
                    code=code,
                    title=title,
                    base_weight=base_w,
                    applicable=True,
                    effective_weight=round(eff_w, 6),
                    score=clamped_sc,
                    summary=summary,
                )
            )

    final_score = 100.0 if active_base_sum <= 0.0 else round(clamp(weighted_total), 2)
    return final_score, results


def classify_archetype(
    total_formula_cells: int,
    xll_udf_cells: int,
    has_vba: bool,
    is_iterative: bool,
    has_time_axis: bool,
) -> str:
    xll_share = xll_udf_cells / max(total_formula_cells, 1)
    if xll_share >= 0.05 and has_time_axis:
        return "XLL / Add-In Time-Series Model"
    if has_vba and is_iterative:
        return "Hybrid VBA + Circular Model"
    if has_vba and not is_iterative:
        return "DCF / Solver + VBA Macro Model"
    if is_iterative and has_time_axis:
        return "Circular Equilibrium Time-Series Model"
    if has_time_axis:
        return "Standard Acyclic Time-Series Model"
    return "Cross-Sectional / Tabular Calculator"


def compute_mri_and_tier(les: float, mhs: float) -> tuple[float, str, str]:
    penalty = 0.15 * max(0.0, 60.0 - min(les, mhs))
    mri = round(clamp(0.55 * les + 0.45 * mhs - penalty), 2)
    if mri >= 85.0:
        return (
            mri,
            "Tier 1 — Fast-Track Automated Port",
            "Direct Google Sheets + Cloud Run solver + BigQuery ML deployment.",
        )
    if mri >= 70.0:
        return (
            mri,
            "Tier 2 — Guided Cloud Equilibrium Port",
            "Compile R1C1 solver + decouple SharePoint links to BigQuery + prune #REF! names.",
        )
    if mri >= 50.0:
        return (
            mri,
            "Tier 3 — Connector & Hygiene Remediation First",
            "Replace _xll / connections.xml feeds with BigQuery and fix #VALUE! / drag defects.",
        )
    return (
        mri,
        "Tier 4 — Re-Specification Required",
        "Remediate locked desktop binaries and structural corruption with model owners.",
    )
```

- [ ] **Step 4: Run tests & linter to verify PASS**

Run (from `portfolio-assessment/`): `make lint && make test`
Expected: `All checks passed!` and `4 passed`.

- [ ] **Step 5: Commit**

```bash
git add portfolio-assessment/pyproject.toml portfolio-assessment/Makefile portfolio-assessment/src/portfolio_assessment/__init__.py portfolio-assessment/src/portfolio_assessment/models.py portfolio-assessment/src/portfolio_assessment/weights.py portfolio-assessment/tests/test_archetype_weights.py
git commit -m "feat(portfolio-assessment): add core scorecard models and dynamic archetype weighting"
```

---

### Task 2: Streaming OpenXML (`iterparse`), Shared-Formula R1C1 Normalizer & MS-OVBA Inspector

**Files:**
- Create: `portfolio-assessment/src/portfolio_assessment/vba_inspector.py`
- Create: `portfolio-assessment/src/portfolio_assessment/xml_inspector.py`
- Create: `portfolio-assessment/tests/conftest.py`
- Test: `portfolio-assessment/tests/test_xml_and_vba_inspector.py`

**Interfaces:**
- Consumes: Standard library `zipfile`, `xml.etree.ElementTree`, `re`, `pathlib.Path`.
- Produces:
  - `vba_inspector.VBAInspectionSummary` & `vba_inspector.inspect_vba_project_bytes(data: bytes) -> VBAInspectionSummary`
  - `xml_inspector.CellInfo`, `xml_inspector.ExternalLinkRef`, `xml_inspector.SheetScanSummary`, `xml_inspector.WorkbookScanResult`
  - `xml_inspector.normalize_formula_to_r1c1(formula: str, base_row: int, base_col: int) -> str`
  - `xml_inspector.scan_workbook_openxml(xlsx_path: Path) -> WorkbookScanResult`

- [ ] **Step 1: Write synthetic OpenXML fixture builder in `conftest.py` and failing tests in `test_xml_and_vba_inspector.py`**

Create `portfolio-assessment/tests/conftest.py`:
```python
from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Any


def build_synthetic_xlsx(
    target_path: Path,
    sheets: dict[str, list[dict[str, Any]]],
    calc_pr_attrs: dict[str, str] | None = None,
    defined_names: list[tuple[str, str]] | None = None,
    external_links: list[str] | None = None,
    connections_xml: bool = False,
    vba_payload: bytes | None = None,
    hidden_sheets: set[str] | None = None,
) -> Path:
    """Create a minimal valid OpenXML .xlsx/.xlsm archive for deterministic unit tests."""
    hidden = hidden_sheets or set()
    calc_attrs = " ".join(f'{k}="{v}"' for k, v in (calc_pr_attrs or {"calcId": "191029"}).items())

    sheet_entries = []
    wb_rels = []
    for idx, sname in enumerate(sheets, start=1):
        state_attr = ' state="veryHidden"' if sname in hidden else ""
        sheet_entries.append(f'<sheet name="{sname}" sheetId="{idx}" r:id="rId{idx}"{state_attr}/>')
        wb_rels.append(
            f'<Relationship Id="rId{idx}" '
            f'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            f'Target="worksheets/sheet{idx}.xml"/>'
        )

    ext_refs_xml = []
    for e_idx, _ in enumerate(external_links or [], start=1):
        rid = f"rIdExt{e_idx}"
        ext_refs_xml.append(f'<externalReference r:id="{rid}"/>')
        wb_rels.append(
            f'<Relationship Id="{rid}" '
            f'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/externalLink" '
            f'Target="externalLinks/externalLink{e_idx}.xml"/>'
        )

    dnames_xml = "".join(
        f'<definedName name="{n}">{body}</definedName>' for n, body in (defined_names or [])
    )
    ext_block = f"<externalReferences>{''.join(ext_refs_xml)}</externalReferences>" if ext_refs_xml else ""
    dn_block = f"<definedNames>{dnames_xml}</definedNames>" if dnames_xml else ""

    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<sheets>{''.join(sheet_entries)}</sheets>"
        f"{ext_block}{dn_block}"
        f"<calcPr {calc_attrs}/>"
        "</workbook>"
    )
    workbook_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f"{''.join(wb_rels)}"
        "</Relationships>"
    )

    with zipfile.ZipFile(target_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("xl/workbook.xml", workbook_xml)
        zf.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml)

        for e_idx, url in enumerate(external_links or [], start=1):
            zf.writestr(
                f"xl/externalLinks/externalLink{e_idx}.xml",
                '<externalLink xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                '<externalBook xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" r:id="rId1"/>'
                "</externalLink>",
            )
            zf.writestr(
                f"xl/externalLinks/_rels/externalLink{e_idx}.xml.rels",
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                f'<Relationship Id="rId1" Type="externalLinkPath" Target="{url}" TargetMode="External"/>'
                "</Relationships>",
            )

        if connections_xml:
            zf.writestr(
                "xl/connections.xml",
                '<connections xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                '<connection id="1" name="ODBC_Feed"/></connections>',
            )

        if vba_payload is not None:
            zf.writestr("xl/vbaProject.bin", vba_payload)

        for idx, (_, cell_list) in enumerate(sheets.items(), start=1):
            c_tags = []
            for item in cell_list:
                r = item["r"]
                t_attr = f' t="{item["t"]}"' if item.get("t") else ""
                s_attr = f' s="{item["s"]}"' if item.get("s") else ""
                inner = ""
                if "f" in item and item["f"] is not None:
                    f_attrs = item.get("f_attrs", "")
                    sp = f" {f_attrs}" if f_attrs else ""
                    inner += f"<f{sp}>{item['f']}</f>" if item["f"] != "" else f"<f{sp}/>"
                if "v" in item and item["v"] is not None:
                    inner += f"<v>{item['v']}</v>"
                if inner:
                    c_tags.append(f'<c r="{r}"{t_attr}{s_attr}>{inner}</c>')
                else:
                    c_tags.append(f'<c r="{r}"{t_attr}{s_attr}/>')
            sheet_xml = (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                f"<sheetData><row r=\"1\">{''.join(c_tags)}</row></sheetData>"
                "</worksheet>"
            )
            zf.writestr(f"xl/worksheets/sheet{idx}.xml", sheet_xml)

    return target_path
```

Create `portfolio-assessment/tests/test_xml_and_vba_inspector.py`:
```python
from __future__ import annotations

from pathlib import Path

from conftest import build_synthetic_xlsx
from portfolio_assessment.vba_inspector import inspect_vba_project_bytes
from portfolio_assessment.xml_inspector import normalize_formula_to_r1c1, scan_workbook_openxml


def test_r1c1_normalizer_preserves_locked_and_relative_offsets() -> None:
    sig_c10 = normalize_formula_to_r1c1("C8*$B$5+D10", base_row=10, base_col=3)
    sig_d10 = normalize_formula_to_r1c1("D8*$B$5+E10", base_row=10, base_col=4)
    assert sig_c10 == sig_d10
    assert "$B$5" in sig_c10 or "R5C2" in sig_c10


def test_shared_formula_expansion_and_time_axis_detection(tmp_path: Path) -> None:
    cells = []
    # Years 2020..2026 in C1:I1
    for offset, yr in enumerate(range(2020, 2027)):
        col_let = chr(ord("C") + offset)
        cells.append({"r": f"{col_let}1", "v": str(yr)})
    # Shared formula in C2:I2: master C2 has "=C1*1.05", slaves D2:I2 have si="0"
    cells.append({"r": "C2", "f": "C1*1.05", "f_attrs": 't="shared" ref="C2:I2" si="0"', "v": "2121"})
    for offset in range(1, 7):
        col_let = chr(ord("C") + offset)
        cells.append({"r": f"{col_let}2", "f": "", "f_attrs": 't="shared" si="0"', "v": "2200"})

    wb_path = build_synthetic_xlsx(
        tmp_path / "Model202409.xlsx",
        sheets={"Forecast": cells},
        defined_names=[("CleanName", "Forecast!$C$1:$I$1"), ("BadName", "#REF!")],
        external_links=["https://spgl.sharepoint.com/sites/Test/LR202409/Peer202409.xlsx"],
    )

    scan = scan_workbook_openxml(wb_path)
    assert scan.vintage_tag == "202409"
    assert scan.total_formula_cells == 7
    assert scan.has_time_axis is True
    assert scan.time_aligned_formula_cells == 7
    assert scan.unique_time_r1c1_patterns == 1
    assert len(scan.defined_names) == 2
    assert scan.broken_defined_names == 1


def test_vba_inspector_detects_empty_vs_procedural_and_win32() -> None:
    empty_res = inspect_vba_project_bytes(b"")
    assert empty_res.has_executable_vba is False

    clean_vba = b"Attribute VB_Name = \"Module1\"\r\nSub GoalSeekLoop()\r\nRange(\"B18\").GoalSeek Goal:=0.12, ChangingCell:=Range(\"B16\")\r\nEnd Sub\r\n"
    res_clean = inspect_vba_project_bytes(clean_vba)
    assert res_clean.has_executable_vba is True
    assert res_clean.has_win32_or_shell is False
    assert res_clean.procedural_lines >= 3

    win32_vba = b"Declare PtrSafe Function GetTickCount Lib \"kernel32\" () As Long\r\nSub RunIt()\r\nCall Shell(\"cmd.exe\")\r\nEnd Sub\r\n"
    res_win32 = inspect_vba_project_bytes(win32_vba)
    assert res_win32.has_executable_vba is True
    assert res_win32.has_win32_or_shell is True
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `portfolio-assessment/`): `make test`
Expected: FAIL with `ModuleNotFoundError: No module named 'portfolio_assessment.vba_inspector'`

- [ ] **Step 3: Implement `vba_inspector.py` and `xml_inspector.py`**

Create `portfolio-assessment/src/portfolio_assessment/vba_inspector.py`:
```python
"""Pure-Python MS-OVBA binary container inspector for xl/vbaProject.bin."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class VBAInspectionSummary:
    has_executable_vba: bool
    is_locked: bool
    procedural_lines: int
    has_win32_or_shell: bool
    has_com_or_db: bool
    module_names: list[str]


_ASCII_RUN_RE = re.compile(rb"[\x09\x0a\x0d\x20-\x7e]{6,}")
_MOD_NAME_RE = re.compile(r'Attribute\s+VB_Name\s*=\s*"([^"]+)"', re.IGNORECASE)
_PROC_TOKEN_RE = re.compile(r"\b(Sub|Function|Property\s+Get|Property\s+Let)\b", re.IGNORECASE)
_WIN32_RE = re.compile(r"\b(Declare\s+(?:PtrSafe\s+)?(?:Function|Sub)|Shell\s*\(|\.dll\b)", re.IGNORECASE)
_COM_DB_RE = re.compile(
    r"(CreateObject\s*\(\s*\"(?:ADODB|DAO|Scripting\.FileSystemObject|Excel\.Application)|Workbooks\.Open)",
    re.IGNORECASE,
)


def inspect_vba_project_bytes(data: bytes) -> VBAInspectionSummary:
    """Extract readable ASCII/UTF-16LE fragments & MS-OVBA tokens without executing code."""
    if not data or len(data) < 16:
        return VBAInspectionSummary(False, False, 0, False, False, [])

    # Combine raw ASCII runs and MS-OVBA compressed single-byte literal tokens (strips flag bytes)
    chunks = [m.group(0).decode("latin-1", errors="ignore") for m in _ASCII_RUN_RE.finditer(data)]
    # Also strip solitary MS-OVBA flag bytes (\x00) to catch split keywords like "Sub " / "Declare "
    stripped = re.sub(rb"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\xff]+", b" ", data).decode(
        "latin-1", errors="ignore"
    )
    combined_text = "\n".join(chunks)

    module_names = sorted(set(_MOD_NAME_RE.findall(combined_text)))
    lines = [
        ln.strip()
        for ln in combined_text.splitlines()
        if ln.strip()
        and not ln.strip().startswith(("Attribute VB_", "'"))
    ]
    has_proc = bool(_PROC_TOKEN_RE.search(combined_text) or _PROC_TOKEN_RE.search(stripped))
    proc_lines = len(lines) if has_proc else 0

    has_dpb_lock = b"DPB=\"" in data and not has_proc and len(data) > 4096
    has_win32 = bool(_WIN32_RE.search(combined_text) or _WIN32_RE.search(stripped))
    has_com = bool(_COM_DB_RE.search(combined_text) or _COM_DB_RE.search(stripped))

    return VBAInspectionSummary(
        has_executable_vba=proc_lines > 0,
        is_locked=has_dpb_lock,
        procedural_lines=proc_lines,
        has_win32_or_shell=has_win32,
        has_com_or_db=has_com,
        module_names=module_names,
    )
```

Create `portfolio-assessment/src/portfolio_assessment/xml_inspector.py`:
```python
"""Single-pass streaming OpenXML scanner with shared-formula expansion & R1C1 normalization."""

from __future__ import annotations

import re
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from portfolio_assessment.vba_inspector import VBAInspectionSummary, inspect_vba_project_bytes

NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_REL_DOC = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_REL_PKG = "http://schemas.openxmlformats.org/package/2006/relationships"

_COORD_RE = re.compile(r"^([A-Z]+)(\d+)$")
_A1_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9_])(\$?)([A-Z]{1,3})(\$?)(\d+)(?![A-Za-z0-9_(])")
_EXT_REF_RE = re.compile(
    r"(?:'\[(\d+)\]([^']+)'!|\[(\d+)\]([A-Za-z0-9_ -]+)!)\$?([A-Z]{1,3})\$?(\d+)"
)
_VINTAGE_RE = re.compile(r"(20\d{4})")


def col_to_idx(col_str: str) -> int:
    n = 0
    for ch in col_str:
        n = n * 26 + (ord(ch) - 64)
    return n


def idx_to_col(idx: int) -> str:
    out = []
    n = max(idx, 1)
    while n > 0:
        n, rem = divmod(n - 1, 26)
        out.append(chr(65 + rem))
    return "".join(reversed(out))


def split_coord(coord: str) -> tuple[int, int]:
    m = _COORD_RE.match(coord)
    if not m:
        return (1, 1)
    return (int(m.group(2)), col_to_idx(m.group(1)))


def shift_formula_a1(formula: str, d_row: int, d_col: int) -> str:
    if d_row == 0 and d_col == 0:
        return formula

    def _repl(m: re.Match[str]) -> str:
        c_lock, col_s, r_lock, row_s = m.groups()
        new_col = col_s if c_lock else idx_to_col(col_to_idx(col_s) + d_col)
        new_row = int(row_s) if r_lock else max(1, int(row_s) + d_row)
        return f"{c_lock}{new_col}{r_lock}{new_row}"

    return _A1_TOKEN_RE.sub(_repl, formula)


def normalize_formula_to_r1c1(formula: str, base_row: int, base_col: int) -> str:
    """Convert A1 references inside formula to row/col-relative R1C1 signature."""

    def _repl(m: re.Match[str]) -> str:
        c_lock, col_s, r_lock, row_s = m.groups()
        c_num = col_to_idx(col_s)
        r_num = int(row_s)
        r_part = f"R{r_num}" if r_lock else f"R[{r_num - base_row}]"
        c_part = f"C{c_num}" if c_lock else f"C[{c_num - base_col}]"
        return f"{r_part}{c_part}"

    return _A1_TOKEN_RE.sub(_repl, formula.strip().lstrip("="))


@dataclass(frozen=True)
class CellInfo:
    coord: str
    row: int
    col: int
    ctype: str
    value: str | None
    formula: str | None
    r1c1_sig: str | None
    is_array_cse: bool
    ext_indices: tuple[str, ...]


@dataclass(frozen=True)
class ExternalLinkRef:
    sheet_name: str
    cell_coord: str
    link_index: str
    ext_sheet: str
    ext_cell: str
    cached_value: str | None
    formula_text: str


@dataclass(frozen=True)
class SheetScanSummary:
    name: str
    state: str
    total_c_tags: int
    empty_styled_c_tags: int
    populated_cells: int
    formula_cells: int
    has_time_axis: bool
    cells_by_row: dict[int, list[CellInfo]]
    cells_by_col: dict[int, list[CellInfo]]


@dataclass(frozen=True)
class WorkbookScanResult:
    path: Path
    file_size_mb: float
    vintage_tag: str
    calc_pr: dict[str, str]
    sheet_names: list[str]
    sheet_states: dict[str, str]
    defined_names: list[tuple[str, str]]
    broken_defined_names: int
    has_connections_xml: bool
    external_pivot_caches: int
    declared_external_links: dict[str, str]
    active_ext_refs: list[ExternalLinkRef]
    ext_formula_cell_count: int
    ext_formula_valid_cache_count: int
    vba: VBAInspectionSummary
    sheets: dict[str, SheetScanSummary]
    total_c_tags: int
    empty_styled_c_tags: int
    total_populated_cells: int
    total_formula_cells: int
    time_aligned_formula_cells: int
    unique_time_r1c1_patterns: int
    has_time_axis: bool


def _is_period_header_row(row_cells: list[CellInfo]) -> bool:
    nums: list[float] = []
    for c in row_cells:
        if c.formula is None and c.value is not None and c.ctype != "e":
            try:
                v = float(c.value)
                # Calendar years 1970..2100 or Excel serial dates 25569..73050 (1970..2100)
                if 1970 <= v <= 2100 or 25569 <= v <= 73050:
                    nums.append(v)
            except ValueError:
                continue
    if len(nums) < 6:
        return False
    monotonic_steps = sum(1 for i in range(len(nums) - 1) if nums[i + 1] >= nums[i])
    return monotonic_steps >= int(0.85 * (len(nums) - 1)) and nums[-1] > nums[0]


def scan_workbook_openxml(xlsx_path: Path) -> WorkbookScanResult:
    """Stream-scan an OpenXML .xlsx/.xlsm file strictly read-only."""
    file_size_mb = round(xlsx_path.stat().st_size / (1024 * 1024), 2)
    vm = _VINTAGE_RE.search(xlsx_path.stem)
    vintage_tag = vm.group(1) if vm else ""

    with zipfile.ZipFile(xlsx_path, mode="r") as zf:
        namelist = set(zf.namelist())
        wb_root = ET.fromstring(zf.read("xl/workbook.xml"))
        rels_root = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        rid_map = {
            r.attrib["Id"]: r.attrib["Target"]
            for r in rels_root.findall(f"{{{NS_REL_PKG}}}Relationship")
        }

        # Shared strings
        sst: list[str] = []
        if "xl/sharedStrings.xml" in namelist:
            with zf.open("xl/sharedStrings.xml") as sfp:
                for _, elem in ET.iterparse(sfp, events=("end",)):
                    if elem.tag == f"{{{NS_MAIN}}}si":
                        sst.append("".join(t.text or "" for t in elem.iter(f"{{{NS_MAIN}}}t")))
                        elem.clear()

        calc_el = wb_root.find(f"{{{NS_MAIN}}}calcPr")
        calc_pr = dict(calc_el.attrib) if calc_el is not None else {}

        # Defined names
        defined_names: list[tuple[str, str]] = []
        broken_dnames = 0
        for dn in wb_root.findall(f".//{{{NS_MAIN}}}definedNames/{{{NS_MAIN}}}definedName"):
            dname = dn.attrib.get("name", "")
            dbody = (dn.text or "").strip()
            if dname.startswith("_xlnm.") and "#REF!" not in dbody:
                continue
            defined_names.append((dname, dbody))
            if "#REF!" in dbody:
                broken_dnames += 1

        # External links
        declared_ext: dict[str, str] = {}
        for idx_i, ext_el in enumerate(
            wb_root.findall(f".//{{{NS_MAIN}}}externalReferences/{{{NS_MAIN}}}externalReference"),
            start=1,
        ):
            rid = ext_el.attrib.get(f"{{{NS_REL_DOC}}}id", "")
            tfile = rid_map.get(rid, "").split("/")[-1]
            rel_file = f"xl/externalLinks/_rels/{tfile}.rels"
            target_url = ""
            if rel_file in namelist:
                rxml = ET.fromstring(zf.read(rel_file))
                urls = [
                    urllib.parse.unquote(x.attrib.get("Target", ""))
                    for x in rxml.findall(f"{{{NS_REL_PKG}}}Relationship")
                ]
                target_url = urls[0] if urls else ""
            declared_ext[str(idx_i)] = target_url

        has_connections = "xl/connections.xml" in namelist
        ext_pivots = sum(
            1 for n in namelist if n.startswith("xl/pivotCache/pivotCacheDefinition") and n.endswith(".xml")
        )
        vba = (
            inspect_vba_project_bytes(zf.read("xl/vbaProject.bin"))
            if "xl/vbaProject.bin" in namelist
            else inspect_vba_project_bytes(b"")
        )

        sheet_names: list[str] = []
        sheet_states: dict[str, str] = {}
        sheets_summary: dict[str, SheetScanSummary] = {}
        active_ext_refs: list[ExternalLinkRef] = []
        ext_f_cells = 0
        ext_f_valid_cache = 0

        total_c = empty_styled_c = total_pop = total_f = 0
        time_f_cells = 0
        unique_time_patterns = 0
        any_time_axis = False

        c_tag = f"{{{NS_MAIN}}}c"
        f_tag = f"{{{NS_MAIN}}}f"
        v_tag = f"{{{NS_MAIN}}}v"

        for sh_el in wb_root.findall(f".//{{{NS_MAIN}}}sheets/{{{NS_MAIN}}}sheet"):
            sname = sh_el.attrib["name"]
            sstate = sh_el.attrib.get("state", "visible")
            rid = sh_el.attrib[f"{{{NS_REL_DOC}}}id"]
            s_target = "xl/" + rid_map[rid].lstrip("/")
            sheet_names.append(sname)
            sheet_states[sname] = sstate
            if s_target not in namelist:
                continue

            sh_c_tags = sh_empty_styled = sh_pop = sh_f = 0
            shared_masters: dict[str, tuple[int, int, str]] = {}
            by_row: dict[int, list[CellInfo]] = defaultdict(list)
            by_col: dict[int, list[CellInfo]] = defaultdict(list)

            with zf.open(s_target) as wfp:
                for _, elem in ET.iterparse(wfp, events=("end",)):
                    if elem.tag != c_tag:
                        continue
                    sh_c_tags += 1
                    coord = elem.attrib.get("r", "A1")
                    r_idx, c_idx = split_coord(coord)
                    ctype = elem.attrib.get("t", "")
                    f_el = elem.find(f_tag)
                    v_el = elem.find(v_tag)

                    if f_el is None and v_el is None:
                        if "s" in elem.attrib:
                            sh_empty_styled += 1
                        elem.clear()
                        continue

                    sh_pop += 1
                    raw_v = v_el.text if v_el is not None else None
                    if ctype == "s" and raw_v is not None and raw_v.isdigit():
                        s_i = int(raw_v)
                        val = sst[s_i] if 0 <= s_i < len(sst) else raw_v
                    else:
                        val = raw_v

                    formula_str: str | None = None
                    r1c1_sig: str | None = None
                    is_cse = False
                    ext_idxs: tuple[str, ...] = ()

                    if f_el is not None:
                        sh_f += 1
                        f_type = f_el.attrib.get("t", "")
                        is_cse = f_type == "array"
                        raw_f = f_el.text or ""
                        if f_type == "shared":
                            si = f_el.attrib.get("si", "")
                            if raw_f:
                                shared_masters[si] = (r_idx, c_idx, raw_f)
                                formula_str = raw_f
                            elif si in shared_masters:
                                mr, mc, mf = shared_masters[si]
                                formula_str = shift_formula_a1(mf, r_idx - mr, c_idx - mc)
                            else:
                                formula_str = raw_f
                        else:
                            formula_str = raw_f

                        r1c1_sig = normalize_formula_to_r1c1(formula_str, r_idx, c_idx)

                        if "[" in formula_str:
                            found_idxs = tuple(sorted(set(re.findall(r"\[(\d+)\]", formula_str))))
                            if found_idxs:
                                ext_idxs = found_idxs
                                ext_f_cells += 1
                                if val is not None and val not in ("#REF!", "#NAME?"):
                                    ext_f_valid_cache += 1
                                for em in _EXT_REF_RE.finditer(formula_str):
                                    l_idx = em.group(1) or em.group(3)
                                    e_sh = em.group(2) or em.group(4)
                                    e_cell = f"{em.group(5)}{em.group(6)}"
                                    active_ext_refs.append(
                                        ExternalLinkRef(
                                            sheet_name=sname,
                                            cell_coord=coord,
                                            link_index=l_idx,
                                            ext_sheet=e_sh,
                                            ext_cell=e_cell,
                                            cached_value=val,
                                            formula_text=formula_str,
                                        )
                                    )

                    cinfo = CellInfo(
                        coord=coord,
                        row=r_idx,
                        col=c_idx,
                        ctype=ctype,
                        value=val,
                        formula=formula_str,
                        r1c1_sig=r1c1_sig,
                        is_array_cse=is_cse,
                        ext_indices=ext_idxs,
                    )
                    by_row[r_idx].append(cinfo)
                    by_col[c_idx].append(cinfo)
                    elem.clear()

            sh_has_time = any(_is_period_header_row(rcells) for rcells in by_row.values()) and sh_f >= 6
            if sh_has_time:
                any_time_axis = True
                time_f_cells += sh_f
                sh_patterns = {
                    (r_num, c.r1c1_sig)
                    for r_num, rcells in by_row.items()
                    for c in rcells
                    if c.r1c1_sig is not None
                }
                unique_time_patterns += len(sh_patterns)

            total_c += sh_c_tags
            empty_styled_c += sh_empty_styled
            total_pop += sh_pop
            total_f += sh_f

            sheets_summary[sname] = SheetScanSummary(
                name=sname,
                state=sstate,
                total_c_tags=sh_c_tags,
                empty_styled_c_tags=sh_empty_styled,
                populated_cells=sh_pop,
                formula_cells=sh_f,
                has_time_axis=sh_has_time,
                cells_by_row=dict(by_row),
                cells_by_col=dict(by_col),
            )

    return WorkbookScanResult(
        path=xlsx_path,
        file_size_mb=file_size_mb,
        vintage_tag=vintage_tag,
        calc_pr=calc_pr,
        sheet_names=sheet_names,
        sheet_states=sheet_states,
        defined_names=defined_names,
        broken_defined_names=broken_dnames,
        has_connections_xml=has_connections,
        external_pivot_caches=ext_pivots,
        declared_external_links=declared_ext,
        active_ext_refs=active_ext_refs,
        ext_formula_cell_count=ext_f_cells,
        ext_formula_valid_cache_count=ext_f_valid_cache,
        vba=vba,
        sheets=sheets_summary,
        total_c_tags=total_c,
        empty_styled_c_tags=empty_styled_c,
        total_populated_cells=total_pop,
        total_formula_cells=total_f,
        time_aligned_formula_cells=time_f_cells,
        unique_time_r1c1_patterns=unique_time_patterns,
        has_time_axis=any_time_axis,
    )
```

- [ ] **Step 4: Run tests & linter to verify PASS**

Run (from `portfolio-assessment/`): `make lint && make test`
Expected: `All checks passed!` and `7 passed`.

- [ ] **Step 5: Commit**

```bash
git add portfolio-assessment/src/portfolio_assessment/vba_inspector.py portfolio-assessment/src/portfolio_assessment/xml_inspector.py portfolio-assessment/tests/conftest.py portfolio-assessment/tests/test_xml_and_vba_inspector.py
git commit -m "feat(portfolio-assessment): add streaming OpenXML R1C1 scanner and MS-OVBA inspector"
```

---

### Task 3: S&P Corporate External Reference Resolver (`reference_resolver.py`)

**Files:**
- Create: `portfolio-assessment/src/portfolio_assessment/reference_resolver.py`
- Test: `portfolio-assessment/tests/test_reference_resolver.py`

**Interfaces:**
- Consumes: `models.ExternalLinkAuditRecord`, `xml_inspector.WorkbookScanResult`.
- Produces:
  - `reference_resolver.classify_link_target_syntactic(raw_target: str, host_vintage: str) -> tuple[str, float]`
  - `reference_resolver.resolve_workbook_external_links(scan: WorkbookScanResult, reference_roots: Sequence[Path] = ()) -> list[ExternalLinkAuditRecord]`

- [ ] **Step 1: Write the failing test in `tests/test_reference_resolver.py`**

Create `portfolio-assessment/tests/test_reference_resolver.py`:
```python
from __future__ import annotations

from pathlib import Path

from conftest import build_synthetic_xlsx
from portfolio_assessment.reference_resolver import (
    classify_link_target_syntactic,
    resolve_workbook_external_links,
)
from portfolio_assessment.xml_inspector import scan_workbook_openxml


def test_syntactic_link_classification_tiers() -> None:
    tier_clean, sc_clean = classify_link_target_syntactic(
        "https://spgl.sharepoint.com/sites/Downstream_HOU/Job/LONGTERM/LR202409/Uslr202409.xlsx",
        host_vintage="202409",
    )
    assert tier_clean == "CLEAN_CORPORATE_LINK"
    assert sc_clean == 1.0

    tier_drift, sc_drift = classify_link_target_syntactic(
        "https://spgl.sharepoint.com/sites/Downstream_HOU/Job/LONGTERM/LR202406/Uslr202406.xlsx",
        host_vintage="202409",
    )
    assert tier_drift == "PRIOR_VINTAGE_DRIFT"
    assert sc_drift == 0.5

    tier_ghost, sc_ghost = classify_link_target_syntactic(
        "file:///C:\\Users\\analyst\\Downloads\\Inputs.xlsx",
        host_vintage="202409",
    )
    assert tier_ghost == "GHOST_OR_LOCAL_PATH"
    assert sc_ghost == 0.0


def test_live_reference_roots_confirms_exact_and_drifted_peer_cells(tmp_path: Path) -> None:
    ref_dir = tmp_path / "onedrive_sp_sync"
    ref_dir.mkdir()
    build_synthetic_xlsx(
        ref_dir / "Uslr202409.xlsx",
        sheets={"Links Out": [{"r": "B2", "v": "100.0"}, {"r": "C2", "v": "105.0"}]},
    )

    host_path = build_synthetic_xlsx(
        tmp_path / "Eulr202409.xlsx",
        sheets={
            "Input": [
                {"r": "B2", "f": "'[1]Links Out'!$B$2", "v": "100.0"},
                {"r": "C2", "f": "'[1]Links Out'!$C$2", "v": "100.0"},  # drifted vs 105.0 in peer!
            ]
        },
        external_links=["https://spgl.sharepoint.com/sites/Downstream_HOU/LR202409/Uslr202409.xlsx"],
    )

    scan = scan_workbook_openxml(host_path)
    audits = resolve_workbook_external_links(scan, reference_roots=[ref_dir])
    assert len(audits) == 1
    rec = audits[0]
    assert rec.resolution_status == "CONFIRMED_STALE_CACHE_DRIFT"
    assert rec.exact_match_cells == 1
    assert rec.drifted_cells == 1
    assert rec.max_rel_drift > 0.04
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `portfolio-assessment/`): `make test`
Expected: FAIL with `ModuleNotFoundError: No module named 'portfolio_assessment.reference_resolver'`

- [ ] **Step 3: Implement `reference_resolver.py`**

Create `portfolio-assessment/src/portfolio_assessment/reference_resolver.py`:
```python
"""Syntactic link classifier and optional S&P corporate --reference-roots live cell verifier."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Sequence
from pathlib import Path

from portfolio_assessment.models import ExternalLinkAuditRecord
from portfolio_assessment.xml_inspector import WorkbookScanResult, scan_workbook_openxml

_VINTAGE_RE = re.compile(r"(20\d{4})")
_DIRECT_EXT_CELL_RE = re.compile(r"^=?'?\[\d+\][^!]+'?!\$?[A-Z]{1,3}\$?\d+$")
_GHOST_PATTERNS = re.compile(
    r"(^file:///|[A-Za-z]:\\|^\\\\|-my\.sharepoint\.com/personal/|/Users/|/Downloads/|/Temp/)",
    re.IGNORECASE,
)


def classify_link_target_syntactic(raw_target: str, host_vintage: str) -> tuple[str, float]:
    """Classify an external link path into CLEAN_CORPORATE_LINK (1.0), PRIOR_VINTAGE_DRIFT (0.5), or GHOST (0.0)."""
    target = (raw_target or "").strip()
    if not target or _GHOST_PATTERNS.search(target):
        return ("GHOST_OR_LOCAL_PATH", 0.0)

    vintages = _VINTAGE_RE.findall(target)
    if host_vintage and vintages:
        latest_link_vintage = max(vintages)
        if latest_link_vintage < host_vintage:
            return ("PRIOR_VINTAGE_DRIFT", 0.5)

    if "sharepoint.com/sites/" in target.lower() or target.startswith(("/sites/", "../")):
        return ("CLEAN_CORPORATE_LINK", 1.0)

    # Bare filename in same working folder (e.g., Uslr202409.xlsx)
    if "/" not in target and "\\" not in target and target.lower().endswith((".xlsx", ".xlsm", ".xlsb")):
        return ("CLEAN_CORPORATE_LINK", 1.0)

    return ("GHOST_OR_LOCAL_PATH", 0.0)


def _index_reference_files(reference_roots: Sequence[Path]) -> dict[str, Path]:
    by_name: dict[str, Path] = {}
    for root in reference_roots:
        if not root.exists():
            continue
        if root.is_file() and root.suffix.lower() in (".xlsx", ".xlsm", ".xlsb", ".xls"):
            by_name[root.name.lower()] = root
        elif root.is_dir():
            for p in root.rglob("*"):
                if p.is_file() and p.suffix.lower() in (".xlsx", ".xlsm", ".xlsb", ".xls"):
                    by_name.setdefault(p.name.lower(), p)
    return by_name


def resolve_workbook_external_links(
    scan: WorkbookScanResult,
    reference_roots: Sequence[Path] = (),
) -> list[ExternalLinkAuditRecord]:
    """Audit all declared external links and optionally confirm target sheets/cells via reference_roots."""
    ref_index = _index_reference_files(reference_roots) if reference_roots else {}
    peer_scan_cache: dict[Path, WorkbookScanResult] = {}

    refs_by_idx = defaultdict(list)
    active_counts: Counter[str] = Counter()
    for ref in scan.active_ext_refs:
        refs_by_idx[ref.link_index].append(ref)
        active_counts[ref.link_index] += 1

    audits: list[ExternalLinkAuditRecord] = []
    wb_name = scan.path.name

    for link_idx, raw_target in sorted(scan.declared_external_links.items(), key=lambda x: int(x[0])):
        tier, syn_score = classify_link_target_syntactic(raw_target, scan.vintage_tag)
        fname = raw_target.replace("\\", "/").split("/")[-1].split("?")[0]
        matched_path = ref_index.get(fname.lower())

        # Also check if raw_target is a directly mounted UNC/local path on an S&P laptop
        if matched_path is None and reference_roots and raw_target and not raw_target.startswith("http"):
            candidate = Path(raw_target.replace("file:///", ""))
            if candidate.exists() and candidate.suffix.lower() in (".xlsx", ".xlsm", ".xlsb", ".xls"):
                matched_path = candidate

        if not reference_roots:
            status = "NOT_PROBED_OFFLINE"
            audits.append(
                ExternalLinkAuditRecord(
                    workbook_name=wb_name,
                    link_index=link_idx,
                    raw_target=raw_target,
                    link_health_tier=tier,
                    syntactic_score=syn_score,
                    active_formula_refs=active_counts[link_idx],
                    resolution_status=status,
                    resolved_local_path="",
                    missing_sheets_count=0,
                    exact_match_cells=0,
                    drifted_cells=0,
                    max_rel_drift=0.0,
                )
            )
            continue

        if matched_path is None:
            audits.append(
                ExternalLinkAuditRecord(
                    workbook_name=wb_name,
                    link_index=link_idx,
                    raw_target=raw_target,
                    link_health_tier=tier,
                    syntactic_score=syn_score,
                    active_formula_refs=active_counts[link_idx],
                    resolution_status="UNRESOLVED_IN_REFERENCE_ROOTS",
                    resolved_local_path="",
                    missing_sheets_count=0,
                    exact_match_cells=0,
                    drifted_cells=0,
                    max_rel_drift=0.0,
                )
            )
            continue

        if matched_path.suffix.lower() in (".xlsb", ".xls"):
            audits.append(
                ExternalLinkAuditRecord(
                    workbook_name=wb_name,
                    link_index=link_idx,
                    raw_target=raw_target,
                    link_health_tier=tier,
                    syntactic_score=syn_score,
                    active_formula_refs=active_counts[link_idx],
                    resolution_status="CONFIRMED_BINARY_FILE_EXISTS",
                    resolved_local_path=str(matched_path),
                    missing_sheets_count=0,
                    exact_match_cells=0,
                    drifted_cells=0,
                    max_rel_drift=0.0,
                )
            )
            continue

        if matched_path not in peer_scan_cache:
            peer_scan_cache[matched_path] = scan_workbook_openxml(matched_path)
        peer_scan = peer_scan_cache[matched_path]

        peer_lookup: dict[tuple[str, str], str | None] = {}
        for ps_name, ps_summary in peer_scan.sheets.items():
            for row_cells in ps_summary.cells_by_row.values():
                for c in row_cells:
                    peer_lookup[(ps_name, c.coord)] = c.value

        missing_sheets: set[str] = set()
        exact_cnt = 0
        drift_cnt = 0
        max_drift = 0.0

        for ref in refs_by_idx[link_idx]:
            if ref.ext_sheet not in peer_scan.sheets:
                missing_sheets.add(ref.ext_sheet)
                continue
            if not _DIRECT_EXT_CELL_RE.match(ref.formula_text.strip()):
                continue
            peer_val = peer_lookup.get((ref.ext_sheet, ref.ext_cell))
            if peer_val is None or ref.cached_value is None:
                continue
            try:
                v_host = float(ref.cached_value)
                v_peer = float(peer_val)
                rel = abs(v_host - v_peer) / max(abs(v_host), 1e-9)
                if rel <= 1e-8:
                    exact_cnt += 1
                else:
                    drift_cnt += 1
                    max_drift = max(max_drift, rel)
            except ValueError:
                if peer_val.strip() == ref.cached_value.strip():
                    exact_cnt += 1
                else:
                    drift_cnt += 1

        if missing_sheets:
            res_status = "RESOLVED_SHEET_MISSING"
        elif drift_cnt > 0:
            res_status = "CONFIRMED_STALE_CACHE_DRIFT"
        else:
            res_status = "CONFIRMED_EXACT_MATCH"

        audits.append(
            ExternalLinkAuditRecord(
                workbook_name=wb_name,
                link_index=link_idx,
                raw_target=raw_target,
                link_health_tier=tier,
                syntactic_score=syn_score,
                active_formula_refs=active_counts[link_idx],
                resolution_status=res_status,
                resolved_local_path=str(matched_path),
                missing_sheets_count=len(missing_sheets),
                exact_match_cells=exact_cnt,
                drifted_cells=drift_cnt,
                max_rel_drift=round(max_drift, 6),
            )
        )

    return audits
```

- [ ] **Step 4: Run tests & linter to verify PASS**

Run (from `portfolio-assessment/`): `make lint && make test`
Expected: `All checks passed!` and `9 passed`.

- [ ] **Step 5: Commit**

```bash
git add portfolio-assessment/src/portfolio_assessment/reference_resolver.py portfolio-assessment/tests/test_reference_resolver.py
git commit -m "feat(portfolio-assessment): add external link classifier and live S&P reference resolver"
```

---

### Task 4: Pillar 1 (`LES`) & Pillar 2 (`MHS` + Cell Defect Detectors) Scoring Engines

**Files:**
- Create: `portfolio-assessment/src/portfolio_assessment/extractability.py`
- Create: `portfolio-assessment/src/portfolio_assessment/hygiene.py`
- Test: `portfolio-assessment/tests/test_scorers_and_hygiene_detectors.py`

**Interfaces:**
- Consumes: `models.PillarScore`, `models.CellDefectRecord`, `models.ExternalLinkAuditRecord`, `weights.clamp`, `weights.renormalize_sub_metrics`, `xml_inspector.WorkbookScanResult`.
- Produces:
  - `extractability.compute_extractability_pillar(scan: WorkbookScanResult) -> tuple[PillarScore, dict[str, int]]`
  - `hygiene.compute_hygiene_pillar(scan: WorkbookScanResult, link_audits: Sequence[ExternalLinkAuditRecord]) -> tuple[PillarScore, list[CellDefectRecord], dict[str, int]]`

- [ ] **Step 1: Write the failing tests in `tests/test_scorers_and_hygiene_detectors.py`**

Create `portfolio-assessment/tests/test_scorers_and_hygiene_detectors.py`:
```python
from __future__ import annotations

from pathlib import Path

from conftest import build_synthetic_xlsx
from portfolio_assessment.extractability import compute_extractability_pillar
from portfolio_assessment.hygiene import compute_hygiene_pillar
from portfolio_assessment.reference_resolver import resolve_workbook_external_links
from portfolio_assessment.xml_inspector import scan_workbook_openxml


def test_extractability_penalizes_xll_sjpoint_and_marks_absent_vba_na(tmp_path: Path) -> None:
    cells = [
        {"r": "C1", "v": "2020"},
        {"r": "D1", "v": "2021"},
        {"r": "E1", "v": "2022"},
        {"r": "F1", "v": "2023"},
        {"r": "G1", "v": "2024"},
        {"r": "H1", "v": "2025"},
        {"r": "C2", "f": "_xll.sjpoint(\"SERIES_A\")", "v": "42.5"},
        {"r": "D2", "f": "_xll.sjpoint(\"SERIES_A\")", "v": "43.1"},
        {"r": "E2", "f": "SUM(C2:D2)", "v": "85.6"},
        {"r": "F2", "f": "INDIRECT(\"C2\")", "v": "42.5"},
        {"r": "G2", "f": "SUM(C2:E2)", "v": "128.1"},
        {"r": "H2", "f": "SUM(C2:F2)", "v": "170.6"},
    ]
    p = build_synthetic_xlsx(tmp_path / "XllModel.xlsx", sheets={"Data": cells})
    scan = scan_workbook_openxml(p)
    les, stats = compute_extractability_pillar(scan)
    by_code = {s.code: s for s in les.sub_metrics}

    assert stats["xll_udf_cells"] == 2
    assert stats["opaque_cells"] == 1
    assert by_code["E2"].applicable is False  # No VBA -> N/A
    assert by_code["E4"].applicable is False  # No ext links -> N/A
    # E1 credits: 2*0.5 + 1*0.0 + 3*1.0 = 4.0 / 6 = 66.67%
    assert 66.0 <= (by_code["E1"].score or 0.0) <= 67.0


def test_hygiene_excludes_intentional_na_and_detects_hardcoded_drag_islands_and_fill_glitch(
    tmp_path: Path,
) -> None:
    cells = []
    # Header years C1:K1 (9 cols)
    for idx, yr in enumerate(range(2020, 2029)):
        col_let = chr(ord("C") + idx)
        cells.append({"r": f"{col_let}1", "v": str(yr)})

    # Row 2: Shared R1C1 formula C1*2 across C2:K2, EXCEPT F2 is overwritten with hardcoded "999" (island!)
    for idx in range(9):
        col_let = chr(ord("C") + idx)
        if col_let == "F":
            cells.append({"r": "F2", "v": "999"})
        else:
            cells.append({"r": f"{col_let}2", "f": f"{col_let}1*2", "v": "4040"})

    # Row 3: Fill-handle +1.0 auto-increment glitch on decimals (0.25, 1.25, 2.25, 3.25, 4.25)
    for idx in range(5):
        col_let = chr(ord("C") + idx)
        cells.append({"r": f"{col_let}3", "v": str(0.25 + idx)})

    # Row 4: Intentional chart NA() vs genuine #VALUE! error
    cells.append({"r": "C4", "t": "e", "f": "NA()", "v": "#N/A"})
    cells.append({"r": "D4", "t": "e", "f": "IF(D1>2030,NA(),D2)", "v": "#N/A"})
    cells.append({"r": "E4", "t": "e", "f": "E2+\"bad_text\"", "v": "#VALUE!"})

    p = build_synthetic_xlsx(tmp_path / "DirtyHygiene.xlsx", sheets={"Model": cells})
    scan = scan_workbook_openxml(p)
    audits = resolve_workbook_external_links(scan)
    mhs, defects, hstats = compute_hygiene_pillar(scan, audits)

    defect_types = {d.defect_type for d in defects}
    assert "HARDCODED_ISLAND_IN_FORMULA_RUN" in defect_types
    assert "AUTO_INCREMENT_FILL_GLITCH" in defect_types
    assert "EVALUATED_CELL_ERROR" in defect_types
    # Only E4 (#VALUE!) is counted as an unintentional error; C4 and D4 (NA()) are excluded!
    assert hstats["unintentional_error_cells"] == 1
    assert hstats["intentional_na_cells"] == 2
    assert mhs.score < 95.0
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `portfolio-assessment/`): `make test`
Expected: FAIL with `ModuleNotFoundError: No module named 'portfolio_assessment.extractability'`

- [ ] **Step 3: Implement `extractability.py` and `hygiene.py`**

Create `portfolio-assessment/src/portfolio_assessment/extractability.py`:
```python
"""Pillar 1: Logic Extractability Score (LES, 0-100%) with Active-Surface Re-Normalization."""

from __future__ import annotations

import math
import re

from portfolio_assessment.models import PillarScore
from portfolio_assessment.weights import clamp, renormalize_sub_metrics
from portfolio_assessment.xml_inspector import WorkbookScanResult

_OPAQUE_RE = re.compile(r"\b(INDIRECT|RTD|CUBEVALUE|CUBEMEMBER|CALL)\s*\(", re.IGNORECASE)
_XLL_RE = re.compile(r"_xll\.[a-z0-9_]+\s*\(", re.IGNORECASE)
_ADV_RE = re.compile(r"(\bOFFSET\s*\(|_xlfn\.[a-z0-9_]+\s*\()", re.IGNORECASE)
_VOLATILE_RE = re.compile(r"\b(NOW|TODAY|RAND|RANDBETWEEN|CELL)\s*\(", re.IGNORECASE)


def compute_extractability_pillar(scan: WorkbookScanResult) -> tuple[PillarScore, dict[str, int]]:
    """Compute LES (0-100%) and sub-metrics E1..E5 across active workbook surfaces."""
    n_f = scan.total_formula_cells
    credit_sum = 0.0
    xll_cells = 0
    opaque_cells = 0
    cse_or_adv_cells = 0
    volatile_cells = 0

    for sh in scan.sheets.values():
        for row_cells in sh.cells_by_row.values():
            for c in row_cells:
                if c.formula is None:
                    continue
                ft = c.formula
                if _VOLATILE_RE.search(ft):
                    volatile_cells += 1
                if _OPAQUE_RE.search(ft):
                    opaque_cells += 1
                    credit_sum += 0.0
                elif _XLL_RE.search(ft):
                    xll_cells += 1
                    if c.value is not None and c.value != "#NAME?":
                        credit_sum += 0.50
                    else:
                        opaque_cells += 1
                elif c.is_array_cse or _ADV_RE.search(ft):
                    cse_or_adv_cells += 1
                    credit_sum += 0.85
                else:
                    credit_sum += 1.00

    # E1: Formula & UDF Portability
    a_e1 = n_f >= 1
    e1_score = clamp(100.0 * (credit_sum / max(n_f, 1))) if a_e1 else None
    e1_summary = (
        f"{n_f:,} formulas ({xll_cells:,} XLL UDF, {cse_or_adv_cells:,} CSE/OFFSET/_xlfn, {opaque_cells:,} opaque)"
        if a_e1
        else "N/A (0 formulas)"
    )

    # E2: Macro & Procedural Transparency
    vba = scan.vba
    a_e2 = vba.has_executable_vba or vba.is_locked
    if not a_e2:
        e2_score = None
        e2_summary = "N/A (Macro-free)"
    elif vba.is_locked:
        e2_score = 20.0
        e2_summary = "Locked/unviewable VBA project"
    else:
        sc2 = 95.0
        if vba.has_win32_or_shell:
            sc2 -= 35.0
        if vba.has_com_or_db:
            sc2 -= 20.0
        if vba.procedural_lines > 500:
            sc2 -= 5.0
        if vba.procedural_lines > 1500:
            sc2 -= 5.0
        e2_score = clamp(sc2)
        e2_summary = f"{vba.procedural_lines} VBA lines across {len(vba.module_names)} modules"

    # E3: Graph & Convergence Determinism
    a_e3 = n_f >= 1
    if not a_e3:
        e3_score = None
        e3_summary = "N/A (0 formulas)"
    else:
        sc3 = 100.0
        is_iter = scan.calc_pr.get("iterate") == "1"
        iter_cnt = int(scan.calc_pr.get("iterateCount", "100") or "100")
        if is_iter:
            sc3 -= 10.0 if iter_cnt <= 25 else 15.0
            if scan.calc_pr.get("calcCompleted") == "0":
                sc3 -= 12.0
        vol_rate = volatile_cells / max(n_f, 1)
        sc3 -= min(25.0, 250.0 * vol_rate)
        e3_score = clamp(sc3)
        e3_summary = (
            f"{'Iterative (iterateCount=' + str(iter_cnt) + ')' if is_iter else 'Acyclic DAG'}, "
            f"{volatile_cells:,} volatile cells"
        )

    # E4: External Feed & Connection Decoupling
    active_ext_books = len({r.link_index for r in scan.active_ext_refs})
    a_e4 = (
        scan.ext_formula_cell_count > 0
        or scan.has_connections_xml
        or scan.external_pivot_caches > 0
    )
    if not a_e4:
        e4_score = None
        e4_summary = "N/A (Self-contained)"
    else:
        cache_cov = (
            scan.ext_formula_valid_cache_count / scan.ext_formula_cell_count
            if scan.ext_formula_cell_count > 0
            else 1.0
        )
        sc4 = 88.0 * cache_cov
        if scan.has_connections_xml:
            sc4 -= 18.0
        if scan.external_pivot_caches > 0:
            sc4 -= 10.0
        sc4 -= min(10.0, 0.15 * active_ext_books)
        e4_score = clamp(sc4)
        e4_summary = (
            f"{scan.ext_formula_cell_count:,} ext-link cells ({cache_cov*100:.1f}% cached) "
            f"across {active_ext_books} active books; connections.xml={scan.has_connections_xml}"
        )

    # E5: Time-Series & R1C1 Structural Regularity
    a_e5 = scan.has_time_axis
    if not a_e5:
        e5_score = None
        e5_summary = "N/A (Cross-sectional / no >=6-period axis)"
    else:
        ratio = scan.time_aligned_formula_cells / max(scan.unique_time_r1c1_patterns, 1)
        e5_score = clamp(45.0 + 36.0 * math.log10(max(ratio, 1.0)), 45.0, 100.0)
        e5_summary = (
            f"{ratio:.1f}x R1C1 compression "
            f"({scan.time_aligned_formula_cells:,} cells -> {scan.unique_time_r1c1_patterns:,} patterns)"
        )

    specs = [
        ("E1", "Formula & UDF Portability", 0.35, a_e1, e1_score, e1_summary),
        ("E2", "Macro & Procedural Transparency", 0.20, a_e2, e2_score, e2_summary),
        ("E3", "Graph & Convergence Determinism", 0.15, a_e3, e3_score, e3_summary),
        ("E4", "External Feed & Connection Decoupling", 0.15, a_e4, e4_score, e4_summary),
        ("E5", "Time-Series & R1C1 Regularity", 0.15, a_e5, e5_score, e5_summary),
    ]
    les_total, subs = renormalize_sub_metrics(specs)
    stats = {
        "xll_udf_cells": xll_cells,
        "opaque_cells": opaque_cells,
        "cse_or_adv_cells": cse_or_adv_cells,
        "volatile_cells": volatile_cells,
    }
    return PillarScore("Logic Extractability Score", "LES", les_total, subs), stats
```

Create `portfolio-assessment/src/portfolio_assessment/hygiene.py`:
```python
"""Pillar 2: Model Hygiene Score (MHS, 0-100%) and deterministic cell-level defect detectors."""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Sequence

from portfolio_assessment.models import CellDefectRecord, ExternalLinkAuditRecord, PillarScore
from portfolio_assessment.weights import clamp, renormalize_sub_metrics
from portfolio_assessment.xml_inspector import CellInfo, WorkbookScanResult

_INTENTIONAL_NA_RE = re.compile(r"\bNA\s*\(\s*\)", re.IGNORECASE)
_SHEET_REF_RE = re.compile(r"(?:'([^'\[\]]+)'|([A-Za-z0-9_]+))!")
_DEAD_TAB_RE = re.compile(r"(shooju_addin|_old$|^old_|not_updated|archive|backup|temp)", re.IGNORECASE)
_REL_UNANCHORED_RE = re.compile(r"(?<![A-Za-z0-9_$])([A-Z]{1,3})(\d+)")


def _scan_line_for_islands_and_drift(
    wb_name: str,
    sheet_name: str,
    cells: list[CellInfo],
    is_row: bool,
    defects: list[CellDefectRecord],
    max_defects_per_wb: int = 500,
) -> tuple[int, int, int]:
    """Detect hardcoded islands inside R1C1 runs, unlocked drag drift, and +1.0 fill glitches."""
    ordered = sorted(cells, key=lambda x: x.col if is_row else x.row)
    if len(ordered) < 6:
        return (0, 0, 0)

    structured_cnt = sum(1 for c in ordered if c.r1c1_sig is not None)
    anomalies = 0
    fill_glitches = 0

    # 1. Hardcoded Value Islands inside dominant R1C1 runs (>= 6 matching formula cells)
    sig_counts = Counter(c.r1c1_sig for c in ordered if c.r1c1_sig is not None)
    for sig, cnt in sig_counts.items():
        if cnt < 6:
            continue
        positions = [i for i, c in enumerate(ordered) if c.r1c1_sig == sig]
        first_i, last_i = positions[0], positions[-1]
        idx_pos = first_i + 1
        while idx_pos < last_i:
            c = ordered[idx_pos]
            if c.formula is None and c.value is not None and c.ctype != "e":
                # Count contiguous literal island width
                end_pos = idx_pos
                while (
                    end_pos < last_i
                    and ordered[end_pos].formula is None
                    and ordered[end_pos].value is not None
                ):
                    end_pos += 1
                island_len = end_pos - idx_pos
                # Ensure matching R1C1 exists immediately before and after the 1..5 cell island
                if (
                    1 <= island_len <= 5
                    and ordered[idx_pos - 1].r1c1_sig == sig
                    and ordered[end_pos].r1c1_sig == sig
                ):
                    for k in range(idx_pos, end_pos):
                        anomalies += 1
                        if len(defects) < max_defects_per_wb:
                            defects.append(
                                CellDefectRecord(
                                    workbook_name=wb_name,
                                    sheet_name=sheet_name,
                                    cell_coord=ordered[k].coord,
                                    sub_metric="H2",
                                    defect_type="HARDCODED_ISLAND_IN_FORMULA_RUN",
                                    severity="HIGH",
                                    detail=f"Static value {ordered[k].value!r} interrupts R1C1 series ({cnt} cells)",
                                )
                            )
                idx_pos = end_pos
            else:
                idx_pos += 1

    # 2. Unlocked Relative-Reference Drift causing #VALUE! or #REF! inside a >=4 formula run
    if structured_cnt >= 4:
        for c in ordered:
            if (
                c.ctype == "e"
                and c.value in ("#VALUE!", "#REF!")
                and c.formula
                and sig_counts.get(c.r1c1_sig, 0) >= 4
                and _REL_UNANCHORED_RE.search(c.formula)
            ):
                anomalies += 1
                if len(defects) < max_defects_per_wb:
                    defects.append(
                        CellDefectRecord(
                            workbook_name=wb_name,
                            sheet_name=sheet_name,
                            cell_coord=c.coord,
                            sub_metric="H2",
                            defect_type="UNLOCKED_DRAG_REFERENCE_DRIFT",
                            severity="MEDIUM",
                            detail=f"Dragged formula '{c.formula[:60]}' evaluated to {c.value}",
                        )
                    )

    # 3. Fill-handle +1.0 auto-increment glitch on decimal static rows (e.g. 0.25, 1.25, 2.25, 3.25)
    if is_row:
        run_len = 1
        prev_val: float | None = None
        for idx_c, c in enumerate(ordered):
            val_f: float | None = None
            if c.formula is None and c.value is not None and c.ctype not in ("s", "e"):
                try:
                    cand = float(c.value)
                    # Must have a fractional decimal part (excludes integer years 2020, 2021 or 1, 2, 3)
                    if abs(cand - round(cand)) > 1e-4:
                        val_f = cand
                except ValueError:
                    val_f = None
            if val_f is not None and prev_val is not None and abs((val_f - prev_val) - 1.0) <= 1e-6:
                run_len += 1
                if run_len == 4:
                    fill_glitches += 4
                    if len(defects) < max_defects_per_wb:
                        defects.append(
                            CellDefectRecord(
                                workbook_name=wb_name,
                                sheet_name=sheet_name,
                                cell_coord=ordered[idx_c - 3].coord,
                                sub_metric="H2",
                                defect_type="AUTO_INCREMENT_FILL_GLITCH",
                                severity="HIGH",
                                detail=f"Decimal input stepped by +1.0 across >=4 cells starting at {val_f - 3.0:.4f}",
                            )
                        )
                elif run_len > 4:
                    fill_glitches += 1
            else:
                run_len = 1
            prev_val = val_f

    return (structured_cnt, anomalies, fill_glitches)


def compute_hygiene_pillar(
    scan: WorkbookScanResult,
    link_audits: Sequence[ExternalLinkAuditRecord],
) -> tuple[PillarScore, list[CellDefectRecord], dict[str, int]]:
    """Compute MHS (0-100%), emit cell-level defect evidence, and return defect telemetry."""
    wb_name = scan.path.name
    defects: list[CellDefectRecord] = []
    valid_sheets = set(scan.sheet_names)

    err_counts: Counter[str] = Counter()
    intentional_na = 0
    dead_formula_refs = 0

    structured_cells = 0
    drag_anomalies = 0
    fill_glitches = 0

    for sh_name, sh in scan.sheets.items():
        for r_cells in sh.cells_by_row.values():
            for c in r_cells:
                # H1: Cached error check (excluding intentional NA())
                if c.ctype == "e" and c.value:
                    if c.value == "#N/A" and c.formula and _INTENTIONAL_NA_RE.search(c.formula):
                        intentional_na += 1
                    else:
                        err_counts[c.value] += 1
                        if len(defects) < 500:
                            defects.append(
                                CellDefectRecord(
                                    workbook_name=wb_name,
                                    sheet_name=sh_name,
                                    cell_coord=c.coord,
                                    sub_metric="H1",
                                    defect_type="EVALUATED_CELL_ERROR",
                                    severity="HIGH" if c.value in ("#REF!", "#NAME!", "#VALUE!") else "MEDIUM",
                                    detail=f"Cell evaluated to {c.value} (formula={c.formula or 'literal'})",
                                )
                            )

                # H3: In-formula literal #REF! or missing internal sheet
                if c.formula:
                    has_dead = "#REF!" in c.formula
                    if not has_dead and "[" not in c.formula:
                        for sm in _SHEET_REF_RE.finditer(c.formula):
                            ref_sh = sm.group(1) or sm.group(2)
                            if ref_sh not in valid_sheets:
                                has_dead = True
                                break
                    if has_dead:
                        dead_formula_refs += 1
                        if len(defects) < 500:
                            defects.append(
                                CellDefectRecord(
                                    workbook_name=wb_name,
                                    sheet_name=sh_name,
                                    cell_coord=c.coord,
                                    sub_metric="H3",
                                    defect_type="BROKEN_FORMULA_REFERENCE",
                                    severity="HIGH",
                                    detail=f"Dead reference in formula: {c.formula[:80]}",
                                )
                            )

            s_cnt, anom_cnt, fg_cnt = _scan_line_for_islands_and_drift(
                wb_name, sh_name, r_cells, is_row=True, defects=defects
            )
            structured_cells += s_cnt
            drag_anomalies += anom_cnt
            fill_glitches += fg_cnt

        # Also scan vertical table columns (>= 6 cells) when sheet lacks a horizontal time axis
        if not sh.has_time_axis:
            for col_cells in sh.cells_by_col.values():
                s_cnt, anom_cnt, _ = _scan_line_for_islands_and_drift(
                    wb_name, sh_name, col_cells, is_row=False, defects=defects
                )
                structured_cells += s_cnt
                drag_anomalies += anom_cnt

    # H1 Score
    a_h1 = scan.total_populated_cells >= 1
    weighted_err = (
        3.0 * (err_counts["#REF!"] + err_counts["#NAME?"] + err_counts["#NULL!"])
        + 2.0 * err_counts["#VALUE!"]
        + 1.0 * (err_counts["#DIV/0!"] + err_counts["#NUM!"] + err_counts["#N/A"])
    )
    unintentional_total = sum(err_counts.values())
    e_rate = weighted_err / max(scan.total_formula_cells, 1)
    h1_score = clamp(100.0 - 22.0 * math.log10(1.0 + 1000.0 * e_rate)) if a_h1 else None
    h1_summary = (
        f"{unintentional_total:,} error cells ({dict(err_counts)}), {intentional_na:,} intentional NA() excluded"
        if a_h1
        else "N/A"
    )

    # H2 Score
    a_h2 = structured_cells >= 6 or fill_glitches > 0
    total_h2_defects = drag_anomalies + fill_glitches
    d_rate = total_h2_defects / max(structured_cells, 6)
    h2_score = clamp(100.0 - 28.0 * math.log10(1.0 + 500.0 * d_rate)) if a_h2 else None
    h2_summary = (
        f"{drag_anomalies:,} island/drift cells + {fill_glitches:,} fill glitches across {structured_cells:,} series cells"
        if a_h2
        else "N/A (No >=6-cell formula series)"
    )

    # H3 Score
    n_dnames = len(scan.defined_names)
    a_h3 = scan.total_formula_cells >= 1 or n_dnames >= 1
    r_f = dead_formula_refs / max(scan.total_formula_cells, 1)
    s_f = 100.0 * ((1.0 - min(r_f, 1.0)) ** 5)
    if not a_h3:
        h3_score = None
        h3_summary = "N/A"
    elif n_dnames == 0:
        h3_score = clamp(s_f)
        h3_summary = f"{dead_formula_refs:,} dead formula refs; 0 defined names"
    else:
        r_n = scan.broken_defined_names / n_dnames
        s_n = 100.0 * (1.0 - r_n)
        h3_score = clamp(0.60 * s_f + 0.40 * s_n)
        h3_summary = (
            f"{dead_formula_refs:,} dead formula refs; "
            f"{scan.broken_defined_names}/{n_dnames} ({r_n*100:.1f}%) #REF! defined names"
        )

    # H4 Score (Active ONLY when external links or connections exist)
    n_decl_ext = len(scan.declared_external_links)
    a_h4 = n_decl_ext >= 1 or scan.ext_formula_cell_count >= 1
    if not a_h4:
        h4_score = None
        h4_summary = "N/A (0 external links)"
    else:
        total_active_refs = sum(a.active_formula_refs for a in link_audits)
        if total_active_refs > 0:
            active_link_score = 100.0 * (
                sum(a.syntactic_score * a.active_formula_refs for a in link_audits) / total_active_refs
            )
        else:
            active_link_score = (
                100.0 * (sum(a.syntactic_score for a in link_audits) / max(len(link_audits), 1))
            )
        orphans = sum(1 for a in link_audits if a.active_formula_refs == 0)
        orphan_ratio = orphans / max(len(link_audits), 1)
        sc4 = 0.75 * active_link_score + 25.0 * (1.0 - orphan_ratio)
        # Deduct if live S&P reference verification detected missing target sheets
        missing_sheet_links = sum(1 for a in link_audits if a.resolution_status == "RESOLVED_SHEET_MISSING")
        sc4 -= 10.0 * missing_sheet_links
        h4_score = clamp(sc4)
        ghosts = sum(1 for a in link_audits if a.link_health_tier == "GHOST_OR_LOCAL_PATH")
        drifts = sum(1 for a in link_audits if a.link_health_tier == "PRIOR_VINTAGE_DRIFT")
        h4_summary = f"{n_decl_ext} declared links ({orphans} unused, {drifts} vintage-drift, {ghosts} local/ghost)"

    # H5 Score (Always active)
    sc5 = 100.0
    if scan.calc_pr.get("calcCompleted") == "0":
        sc5 -= 25.0
    if scan.calc_pr.get("calcMode") == "manual":
        sc5 -= 15.0
    dead_tabs = [s for s in scan.sheet_names if _DEAD_TAB_RE.search(s)]
    sc5 -= min(25.0, 5.0 * len(dead_tabs))
    bloat_ratio = scan.empty_styled_c_tags / max(scan.total_c_tags, 1)
    if bloat_ratio > 0.35:
        sc5 -= min(25.0, 50.0 * (bloat_ratio - 0.35))
    h5_score = clamp(sc5)
    h5_summary = (
        f"calcCompleted={scan.calc_pr.get('calcCompleted', '1')}, "
        f"dead_tabs={len(dead_tabs)}, empty_style_bloat={bloat_ratio*100:.1f}%"
    )

    specs = [
        ("H1", "Evaluated Cell Error Cleanliness", 0.25, a_h1, h1_score, h1_summary),
        ("H2", "Formula Continuity & Drag Integrity", 0.25, a_h2, h2_score, h2_summary),
        ("H3", "Reference & Named-Range Validity", 0.20, a_h3, h3_score, h3_summary),
        ("H4", "External Link & Vintage Hygiene", 0.20, a_h4, h4_score, h4_summary),
        ("H5", "Calculation State & Sheet Hygiene", 0.10, True, h5_score, h5_summary),
    ]
    mhs_total, subs = renormalize_sub_metrics(specs)
    stats = {
        "unintentional_error_cells": unintentional_total,
        "intentional_na_cells": intentional_na,
        "drag_and_island_cells": drag_anomalies,
        "fill_glitch_cells": fill_glitches,
        "dead_formula_refs": dead_formula_refs,
        "broken_defined_names": scan.broken_defined_names,
    }
    return PillarScore("Model Hygiene Score", "MHS", mhs_total, subs), defects, stats
```

- [ ] **Step 4: Run tests & linter to verify PASS**

Run (from `portfolio-assessment/`): `make lint && make test`
Expected: `All checks passed!` and `11 passed`.

- [ ] **Step 5: Commit**

```bash
git add portfolio-assessment/src/portfolio_assessment/extractability.py portfolio-assessment/src/portfolio_assessment/hygiene.py portfolio-assessment/tests/test_scorers_and_hygiene_detectors.py
git commit -m "feat(portfolio-assessment): implement LES and MHS engines with drag and error detectors"
```

---

### Task 5: Portfolio Orchestrator, Executive Markdown/CSV Reporters & CLI (`scorer.py`, `reporter.py`, `cli.py`)

**Files:**
- Create: `portfolio-assessment/src/portfolio_assessment/scorer.py`
- Create: `portfolio-assessment/src/portfolio_assessment/reporter.py`
- Create: `portfolio-assessment/src/portfolio_assessment/cli.py`
- Create: `portfolio-assessment/README.md`
- Modify: `Makefile` (root platform convenience target `assess-portfolio`)
- Test: `portfolio-assessment/tests/test_cli_and_portfolio_e2e.py`

**Interfaces:**
- Consumes: Tasks 1–4 modules (`models`, `weights`, `xml_inspector`, `reference_resolver`, `extractability`, `hygiene`).
- Produces:
  - `scorer.discover_workbooks(scan_dirs: Sequence[Path], include_all_vintages: bool = False) -> list[Path]`
  - `scorer.assess_workbook(xlsx_path: Path, reference_roots: Sequence[Path] = ()) -> tuple[WorkbookScorecard, list[CellDefectRecord], list[ExternalLinkAuditRecord]]`
  - `scorer.assess_portfolio(scan_dirs: Sequence[Path], output_dir: Path, reference_roots: Sequence[Path] = (), include_all_vintages: bool = False) -> list[WorkbookScorecard]`
  - `reporter.write_portfolio_reports(...) -> dict[str, Path]`
  - `cli.main(argv: Sequence[str] | None = None) -> int`

- [ ] **Step 1: Write the failing end-to-end test in `tests/test_cli_and_portfolio_e2e.py`**

Create `portfolio-assessment/tests/test_cli_and_portfolio_e2e.py`:
```python
from __future__ import annotations

from pathlib import Path

from conftest import build_synthetic_xlsx
from portfolio_assessment.cli import main
from portfolio_assessment.scorer import discover_workbooks


def test_discover_workbooks_deduplicates_older_vintages_by_default(tmp_path: Path) -> None:
    build_synthetic_xlsx(tmp_path / "Callr202406.xlsx", sheets={"S1": [{"r": "A1", "v": "1"}]})
    build_synthetic_xlsx(tmp_path / "Callr202409.xlsx", sheets={"S1": [{"r": "A1", "v": "1"}]})
    build_synthetic_xlsx(tmp_path / "Latinlr202409 3Q.xlsx", sheets={"S1": [{"r": "A1", "v": "1"}]})
    build_synthetic_xlsx(tmp_path / "Latinlr202409.xlsx", sheets={"S1": [{"r": "A1", "v": "1"}]})

    deduped = [p.name for p in discover_workbooks([tmp_path], include_all_vintages=False)]
    assert "Callr202409.xlsx" in deduped
    assert "Callr202406.xlsx" not in deduped
    assert "Latinlr202409.xlsx" in deduped
    assert "Latinlr202409 3Q.xlsx" not in deduped

    all_files = [p.name for p in discover_workbooks([tmp_path], include_all_vintages=True)]
    assert len(all_files) == 4


def test_cli_generates_markdown_and_csv_reports_across_synthetic_and_seed_models(tmp_path: Path) -> None:
    models_dir = tmp_path / "models"
    out_dir = tmp_path / "reports"
    models_dir.mkdir()

    # Clean Tier 1 model vs dirty XLL Tier 3 model
    clean_cells = [{"r": f"{chr(67+i)}1", "v": str(2020 + i)} for i in range(6)] + [
        {"r": f"{chr(67+i)}2", "f": f"{chr(67+i)}1*1.1", "v": "2200"} for i in range(6)
    ]
    build_synthetic_xlsx(models_dir / "CleanModel202409.xlsx", sheets={"Main": clean_cells})

    dirty_cells = [{"r": f"{chr(67+i)}1", "v": str(2020 + i)} for i in range(6)] + [
        {"r": f"{chr(67+i)}2", "t": "e", "f": "_xll.sjpoint(\"X\")", "v": "#VALUE!"} for i in range(6)
    ]
    build_synthetic_xlsx(models_dir / "DirtyXll202409.xlsx", sheets={"Main": dirty_cells})

    rc = main(["--scan-dirs", str(models_dir), "--output-dir", str(out_dir)])
    assert rc == 0

    md_file = out_dir / "portfolio_executive_scorecard.md"
    csv_file = out_dir / "portfolio_scorecard.csv"
    defects_file = out_dir / "portfolio_cell_defects.csv"
    links_file = out_dir / "portfolio_external_links_audit.csv"

    assert md_file.exists()
    assert csv_file.exists()
    assert defects_file.exists()
    assert links_file.exists()

    md_text = md_file.read_text(encoding="utf-8")
    assert "Logic Extractability Score" in md_text or "LES" in md_text
    assert "CleanModel202409.xlsx" in md_text
    assert "DirtyXll202409.xlsx" in md_text
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `portfolio-assessment/`): `make test`
Expected: FAIL with `ModuleNotFoundError: No module named 'portfolio_assessment.cli'`

- [ ] **Step 3: Implement `scorer.py`, `reporter.py`, `cli.py`, `README.md`, and root `Makefile` target**

Create `portfolio-assessment/src/portfolio_assessment/scorer.py`:
```python
"""Portfolio discovery, vintage deduplication, and end-to-end workbook assessment."""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

from portfolio_assessment.extractability import compute_extractability_pillar
from portfolio_assessment.hygiene import compute_hygiene_pillar
from portfolio_assessment.models import (
    CellDefectRecord,
    ExternalLinkAuditRecord,
    WorkbookScorecard,
)
from portfolio_assessment.reference_resolver import resolve_workbook_external_links
from portfolio_assessment.reporter import write_portfolio_reports
from portfolio_assessment.weights import classify_archetype, compute_mri_and_tier
from portfolio_assessment.xml_inspector import scan_workbook_openxml

_FAMILY_KEY_RE = re.compile(r"(20\d{4}).*$", re.IGNORECASE)


def _family_and_rank(path: Path) -> tuple[str, tuple[str, int]]:
    stem = path.stem
    m = _FAMILY_KEY_RE.search(stem)
    if not m:
        return (stem.lower(), ("999999", 1))
    family = stem[: m.start()].strip(" _-").lower()
    vintage = m.group(1)
    # Prefer canonical vintage file (e.g. Latinlr202409.xlsx) over suffixed draft ("Latinlr202409 3Q.xlsx")
    is_canonical = 1 if stem.lower() == f"{family}{vintage}" else 0
    return (family, (vintage, is_canonical))


def discover_workbooks(
    scan_dirs: Sequence[Path],
    include_all_vintages: bool = False,
) -> list[Path]:
    """Find all .xlsx and .xlsm files across scan_dirs, optionally deduplicating older vintages."""
    found: dict[Path, Path] = {}
    for d in scan_dirs:
        if not d.exists():
            continue
        if d.is_file() and d.suffix.lower() in (".xlsx", ".xlsm") and not d.name.startswith("~$"):
            found[d.resolve()] = d
        elif d.is_dir():
            for p in sorted(d.rglob("*")):
                if (
                    p.is_file()
                    and p.suffix.lower() in (".xlsx", ".xlsm")
                    and not p.name.startswith("~$")
                    and ".venv" not in p.parts
                ):
                    found[p.resolve()] = p

    candidates = sorted(found.values(), key=lambda x: x.name.lower())
    if include_all_vintages:
        return candidates

    best_by_family: dict[str, tuple[tuple[str, int], Path]] = {}
    for p in candidates:
        fam, rank_key = _family_and_rank(p)
        prev = best_by_family.get(fam)
        if prev is None or rank_key > prev[0]:
            best_by_family[fam] = (rank_key, p)

    return sorted((v[1] for v in best_by_family.values()), key=lambda x: x.name.lower())


def assess_workbook(
    xlsx_path: Path,
    reference_roots: Sequence[Path] = (),
) -> tuple[WorkbookScorecard, list[CellDefectRecord], list[ExternalLinkAuditRecord]]:
    """Run full read-only OpenXML + VBA + reference assessment on a single workbook."""
    scan = scan_workbook_openxml(xlsx_path)
    link_audits = resolve_workbook_external_links(scan, reference_roots=reference_roots)
    les, e_stats = compute_extractability_pillar(scan)
    mhs, defects, h_stats = compute_hygiene_pillar(scan, link_audits)

    defect_rate = round(100.0 - mhs.score, 2)
    mri, tier, action = compute_mri_and_tier(les.score, mhs.score)
    archetype = classify_archetype(
        total_formula_cells=scan.total_formula_cells,
        xll_udf_cells=e_stats["xll_udf_cells"],
        has_vba=scan.vba.has_executable_vba,
        is_iterative=scan.calc_pr.get("iterate") == "1",
        has_time_axis=scan.has_time_axis,
    )

    scorecard = WorkbookScorecard(
        workbook_name=xlsx_path.name,
        workbook_path=str(xlsx_path),
        file_size_mb=scan.file_size_mb,
        archetype=archetype,
        vintage_tag=scan.vintage_tag or "N/A",
        sheet_count=len(scan.sheet_names),
        total_populated_cells=scan.total_populated_cells,
        total_formula_cells=scan.total_formula_cells,
        les=les,
        mhs=mhs,
        defect_rate=defect_rate,
        mri=mri,
        readiness_tier=tier,
        recommended_action=action,
        telemetry={**e_stats, **h_stats, "external_links_declared": len(scan.declared_external_links)},
    )
    return scorecard, defects, link_audits


def assess_portfolio(
    scan_dirs: Sequence[Path],
    output_dir: Path,
    reference_roots: Sequence[Path] = (),
    include_all_vintages: bool = False,
) -> list[WorkbookScorecard]:
    """Assess all discovered workbooks, sort by MRI descending, and emit Markdown + CSV reports."""
    workbooks = discover_workbooks(scan_dirs, include_all_vintages=include_all_vintages)
    scorecards: list[WorkbookScorecard] = []
    all_defects: list[CellDefectRecord] = []
    all_links: list[ExternalLinkAuditRecord] = []

    for wb_path in workbooks:
        sc, defs, lnks = assess_workbook(wb_path, reference_roots=reference_roots)
        scorecards.append(sc)
        all_defects.extend(defs)
        all_links.extend(lnks)

    scorecards.sort(key=lambda s: (-s.mri, s.workbook_name.lower()))
    write_portfolio_reports(output_dir, scorecards, all_defects, all_links)
    return scorecards
```

Create `portfolio-assessment/src/portfolio_assessment/reporter.py`:
```python
"""Executive Markdown scorecard and CSV evidence writers."""

from __future__ import annotations

import csv
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from portfolio_assessment.models import (
    CellDefectRecord,
    ExternalLinkAuditRecord,
    SubMetricScore,
    WorkbookScorecard,
)


def _fmt_sub(sub: SubMetricScore) -> str:
    if not sub.applicable or sub.score is None:
        return "N/A"
    return f"{sub.score:.1f}% ({sub.effective_weight*100:.0f}%)"


def write_portfolio_reports(
    output_dir: Path,
    scorecards: Sequence[WorkbookScorecard],
    defects: Sequence[CellDefectRecord],
    link_audits: Sequence[ExternalLinkAuditRecord],
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    md_path = output_dir / "portfolio_executive_scorecard.md"
    csv_path = output_dir / "portfolio_scorecard.csv"
    defects_path = output_dir / "portfolio_cell_defects.csv"
    links_path = output_dir / "portfolio_external_links_audit.csv"

    ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# Commodity Modeling Portfolio — Modernization Readiness Scorecard",
        "",
        f"**Generated:** `{ts}` | **Workbooks Evaluated:** `{len(scorecards)}`",
        "",
        "## 1. Executive Headline Summary (`MRI`, `LES`, `MHS`, `Defect Rate`)",
        "",
        "| Rank | Workbook | Archetype | Populated Cells | Formulas | `LES` (Extractability) | `MHS` (Hygiene) | Defect Rate (`100-MHS`) | Overall `MRI` | Readiness Tier |",
        "| :---: | :--- | :--- | ---: | ---: | ---: | ---: | ---: | ---: | :--- |",
    ]

    for idx, sc in enumerate(scorecards, start=1):
        lines.append(
            f"| {idx} | `{sc.workbook_name}` | {sc.archetype} | {sc.total_populated_cells:,} | "
            f"{sc.total_formula_cells:,} | **{sc.les.score:.1f}%** | **{sc.mhs.score:.1f}%** | "
            f"{sc.defect_rate:.1f}% | **{sc.mri:.1f}%** | {sc.readiness_tier} |"
        )

    lines.extend(
        [
            "",
            "## 2. Pillar 1 Breakdown — Logic Extractability Score (`LES`) With Dynamic Archetype Weights",
            "",
            "| Workbook | `LES` | `E1` Formula/UDF | `E2` Macros | `E3` Graph | `E4` Ext Feeds | `E5` Time-Series |",
            "| :--- | ---: | :---: | :---: | :---: | :---: | :---: |",
        ]
    )
    for sc in scorecards:
        em = {s.code: s for s in sc.les.sub_metrics}
        lines.append(
            f"| `{sc.workbook_name}` | **{sc.les.score:.1f}%** | {_fmt_sub(em['E1'])} | "
            f"{_fmt_sub(em['E2'])} | {_fmt_sub(em['E3'])} | {_fmt_sub(em['E4'])} | {_fmt_sub(em['E5'])} |"
        )

    lines.extend(
        [
            "",
            "## 3. Pillar 2 Breakdown — Model Hygiene Score (`MHS`) With Dynamic Archetype Weights",
            "",
            "| Workbook | `MHS` | Defect Rate | `H1` Cell Errors | `H2` Drag/Continuity | `H3` Refs/Names | `H4` Link Hygiene | `H5` Calc/Bloat |",
            "| :--- | ---: | ---: | :---: | :---: | :---: | :---: | :---: |",
        ]
    )
    for sc in scorecards:
        hm = {s.code: s for s in sc.mhs.sub_metrics}
        lines.append(
            f"| `{sc.workbook_name}` | **{sc.mhs.score:.1f}%** | {sc.defect_rate:.1f}% | "
            f"{_fmt_sub(hm['H1'])} | {_fmt_sub(hm['H2'])} | {_fmt_sub(hm['H3'])} | "
            f"{_fmt_sub(hm['H4'])} | {_fmt_sub(hm['H5'])} |"
        )

    lines.extend(["", "## 4. Per-Workbook Key Findings & Recommended Playbook", ""])
    for sc in scorecards:
        lines.append(f"### `{sc.workbook_name}` — `MRI: {sc.mri:.1f}%` ({sc.readiness_tier})")
        lines.append(f"- **Recommended Action:** {sc.recommended_action}")
        for s in [*sc.les.sub_metrics, *sc.mhs.sub_metrics]:
            if s.applicable:
                lines.append(
                    f"- **`{s.code}` {s.title} (`{s.score:.1f}%`, eff. weight `{s.effective_weight*100:.1f}%`):** {s.summary}"
                )
        lines.append("")

    md_path.write_text("\n".join(lines), encoding="utf-8")

    # Write Scorecard CSV
    csv_headers = [
        "workbook_name",
        "archetype",
        "vintage_tag",
        "file_size_mb",
        "sheet_count",
        "total_populated_cells",
        "total_formula_cells",
        "les_score",
        "mhs_score",
        "defect_rate_pct",
        "mri_score",
        "readiness_tier",
        "E1_score",
        "E2_score",
        "E3_score",
        "E4_score",
        "E5_score",
        "H1_score",
        "H2_score",
        "H3_score",
        "H4_score",
        "H5_score",
        "xll_udf_cells",
        "unintentional_error_cells",
        "drag_and_island_cells",
        "broken_defined_names",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.writer(fp)
        writer.writerow(csv_headers)
        for sc in scorecards:
            em = {s.code: s.score for s in sc.les.sub_metrics}
            hm = {s.code: s.score for s in sc.mhs.sub_metrics}
            writer.writerow(
                [
                    sc.workbook_name,
                    sc.archetype,
                    sc.vintage_tag,
                    sc.file_size_mb,
                    sc.sheet_count,
                    sc.total_populated_cells,
                    sc.total_formula_cells,
                    sc.les.score,
                    sc.mhs.score,
                    sc.defect_rate,
                    sc.mri,
                    sc.readiness_tier,
                    em["E1"],
                    em["E2"],
                    em["E3"],
                    em["E4"],
                    em["E5"],
                    hm["H1"],
                    hm["H2"],
                    hm["H3"],
                    hm["H4"],
                    hm["H5"],
                    sc.telemetry.get("xll_udf_cells", 0),
                    sc.telemetry.get("unintentional_error_cells", 0),
                    sc.telemetry.get("drag_and_island_cells", 0),
                    sc.telemetry.get("broken_defined_names", 0),
                ]
            )

    with defects_path.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.writer(fp)
        writer.writerow(["workbook_name", "sheet_name", "cell_coord", "sub_metric", "defect_type", "severity", "detail"])
        for d in defects:
            writer.writerow([d.workbook_name, d.sheet_name, d.cell_coord, d.sub_metric, d.defect_type, d.severity, d.detail])

    with links_path.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.writer(fp)
        writer.writerow(
            [
                "workbook_name",
                "link_index",
                "link_health_tier",
                "syntactic_score",
                "active_formula_refs",
                "resolution_status",
                "resolved_local_path",
                "missing_sheets_count",
                "exact_match_cells",
                "drifted_cells",
                "max_rel_drift",
                "raw_target",
            ]
        )
        for a in link_audits:
            writer.writerow(
                [
                    a.workbook_name,
                    a.link_index,
                    a.link_health_tier,
                    a.syntactic_score,
                    a.active_formula_refs,
                    a.resolution_status,
                    a.resolved_local_path,
                    a.missing_sheets_count,
                    a.exact_match_cells,
                    a.drifted_cells,
                    a.max_rel_drift,
                    a.raw_target,
                ]
            )

    return {
        "markdown": md_path,
        "csv": csv_path,
        "defects": defects_path,
        "links": links_path,
    }
```

Create `portfolio-assessment/src/portfolio_assessment/cli.py`:
```python
"""CLI entrypoint for scanning modeling workbooks and generating LES/MHS/MRI scorecards."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

from portfolio_assessment.scorer import assess_portfolio


def _default_workspace_root() -> Path:
    return Path(__file__).resolve().parents[3]


def build_parser() -> argparse.ArgumentParser:
    root = _default_workspace_root()
    parser = argparse.ArgumentParser(
        prog="assess-portfolio",
        description="Compute Logic Extractability (LES), Model Hygiene (MHS), and Modernization Readiness (MRI).",
    )
    parser.add_argument(
        "--scan-dirs",
        nargs="+",
        type=Path,
        default=[
            root / "brazil-power-v13" / "seed",
            root / "Eulr",
            root / "other models",
        ],
        help="Directories or .xlsx/.xlsm files to scan (read-only).",
    )
    parser.add_argument(
        "--reference-roots",
        nargs="*",
        type=Path,
        default=[],
        help="Optional local/synced SharePoint/OneDrive folders on S&P laptop to confirm external links & drift.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=root / "portfolio-assessment" / "reports",
        help="Output directory for Markdown and CSV scorecards.",
    )
    parser.add_argument(
        "--include-all-vintages",
        action="store_true",
        help="Score superseded vintage archive files (e.g. Callr202406 alongside Callr202409).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    scorecards = assess_portfolio(
        scan_dirs=args.scan_dirs,
        output_dir=args.output_dir,
        reference_roots=args.reference_roots,
        include_all_vintages=args.include_all_vintages,
    )
    print(f"Evaluated {len(scorecards)} workbooks -> reports written to {args.output_dir}")
    for sc in scorecards:
        print(
            f"  {sc.workbook_name:48s} | LES={sc.les.score:5.1f}% | "
            f"MHS={sc.mhs.score:5.1f}% (Defect={sc.defect_rate:4.1f}%) | MRI={sc.mri:5.1f}% | {sc.readiness_tier}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Create `portfolio-assessment/README.md`:
```markdown
# Portfolio Assessment — Workbook Modernization Scoring (`LES`, `MHS`, `MRI`)

Read-only OpenXML + MS-OVBA scanner evaluating candidate spreadsheets across:
- **Logic Extractability Score (`LES`, 0–100%)**
- **Model Hygiene Score (`MHS`, 0–100%)** + **Defect Rate (`100% - MHS`)**
- **Modernization Readiness Index (`MRI`, 0–100%)**

## Quickstart

```bash
# Run lint + unit/E2E tests
make -C portfolio-assessment lint
make -C portfolio-assessment test

# Scan workspace models (offline link hygiene mode)
PYTHONPATH=portfolio-assessment/src .venv/bin/python -m portfolio_assessment.cli

# Scan on S&P Corporate Laptop with live SharePoint/OneDrive reference verification
PYTHONPATH=portfolio-assessment/src .venv/bin/python -m portfolio_assessment.cli \
  --scan-dirs "brazil-power-v13/seed" "Eulr" "other models" \
  --reference-roots "Eulr/docs/references" "$HOME/OneDrive - S&P Global"
```
```

Modify root `Makefile` (`commodity-modeling-sheets-platform/Makefile`) to add `lint-assessment`, `test-assessment`, and `assess-portfolio`:
```makefile
.PHONY: lint-brazil test-brazil check-brazil lint-assessment test-assessment assess-portfolio lint-all test-all

lint-brazil:
	$(MAKE) -C brazil-power-v13 lint

test-brazil:
	$(MAKE) -C brazil-power-v13 test

check-brazil: lint-brazil test-brazil

lint-assessment:
	$(MAKE) -C portfolio-assessment lint

test-assessment:
	$(MAKE) -C portfolio-assessment test

assess-portfolio:
	$(MAKE) -C portfolio-assessment run

lint-all: lint-brazil lint-assessment

test-all: test-brazil test-assessment
```

- [ ] **Step 4: Run full lint, test suite, and live portfolio scan to verify PASS**

Run (from platform root):
```bash
make lint-all && make test-all && PYTHONPATH=portfolio-assessment/src .venv/bin/python -m portfolio_assessment.cli --reference-roots Eulr/docs/references
```
Expected: `All checks passed!`, all `brazil-power-v13` (`31`) and `portfolio-assessment` (`13`) tests PASS, and `portfolio-assessment/reports/portfolio_executive_scorecard.md` + CSV reports are generated in `< 20 seconds`.

- [ ] **Step 5: Commit**

```bash
git add Makefile portfolio-assessment/README.md portfolio-assessment/src/portfolio_assessment/scorer.py portfolio-assessment/src/portfolio_assessment/reporter.py portfolio-assessment/src/portfolio_assessment/cli.py portfolio-assessment/tests/test_cli_and_portfolio_e2e.py
git commit -m "feat(portfolio-assessment): add CLI, Markdown/CSV executive scorecard reporters, and E2E tests"
```
