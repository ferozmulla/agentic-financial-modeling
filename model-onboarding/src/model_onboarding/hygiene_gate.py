"""Stage 1: Deterministic Workbook Hygiene Scanner, Exception Report & Go/No-Go Policy."""

from __future__ import annotations

import json
import re
import zipfile
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path

from portfolio_assessment.models import CellDefectRecord, ExternalLinkAuditRecord, WorkbookScorecard
from portfolio_assessment.scorer import assess_workbook
from portfolio_assessment.xml_inspector import WorkbookScanResult, scan_workbook_openxml

from model_onboarding.config import (
    OnboardingSettings,
    derive_default_slug,
    get_onboarding_settings,
    validate_model_slug,
)
from model_onboarding.models import (
    GoNoGoDecision,
    HygieneExceptionItem,
    HygieneGateReport,
    SubMetricSummary,
)

_ALLOWED_EXTENSIONS = {".xlsx", ".xlsm"}
_ZIP_MAGIC_PREFIXES = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")
_ASSUMPTION_TAB_RE = re.compile(
    r"(general|input|assum|param|control|driver|scen|macro|config)",
    re.IGNORECASE,
)

_DEFECT_REMEDIATIONS: dict[str, tuple[str, str]] = {
    "EVALUATED_CELL_ERROR": (
        "Evaluated Formula Cell Errors (#REF!, #VALUE!, #DIV/0!, #NAME?)",
        "Inspect flagged formula cells; fix broken references or guard intentional zero-divisors with IFERROR().",
    ),
    "HARDCODED_ISLAND_IN_FORMULA_RUN": (
        "Hardcoded Numeric Islands Interrupting Time-Series Formula Runs",
        "Confirm whether static overrides inside R1C1 series are intentional historical actuals or accidental paste-values.",
    ),
    "UNLOCKED_DRAG_REFERENCE_DRIFT": (
        "Unlocked Relative Reference Drift in Dragged Formulas",
        "Add '$' row/column anchors to lookup table ranges in dragged formulas.",
    ),
    "AUTO_INCREMENT_FILL_GLITCH": (
        "Excel Fill-Handle +1.0 Auto-Increment Glitch on Decimal Inputs",
        "Verify decimal static series did not accidentally step by +1.0 during horizontal drag-fill.",
    ),
}


def validate_workbook_file(xlsx_path: Path, max_size_mb: float = 100.0) -> Path:
    """Validate extension allowlist, file size cap, ZIP magic header, and OpenXML workbook entry."""
    resolved = xlsx_path.expanduser().resolve()
    if not resolved.exists() or not resolved.is_file():
        raise FileNotFoundError(f"Workbook file not found: {xlsx_path}")

    suffix = resolved.suffix.lower()
    if suffix not in _ALLOWED_EXTENSIONS:
        raise ValueError(f"Unsupported file extension {suffix!r}; only .xlsx and .xlsm are allowed.")

    size_mb = resolved.stat().st_size / (1024 * 1024)
    if size_mb > max_size_mb:
        raise ValueError(
            f"Workbook {resolved.name} ({size_mb:.2f} MB) exceeds maximum allowed size ({max_size_mb:.1f} MB)."
        )

    with resolved.open("rb") as fh:
        magic = fh.read(4)
    if magic not in _ZIP_MAGIC_PREFIXES:
        raise ValueError(f"File {resolved.name} does not have a valid OpenXML ZIP header.")

    try:
        with zipfile.ZipFile(resolved, mode="r") as zf:
            names = set(zf.namelist())
    except zipfile.BadZipFile as exc:
        raise ValueError(f"Corrupted OpenXML archive in {resolved.name}") from exc

    if "[Content_Types].xml" not in names or "xl/workbook.xml" not in names:
        raise ValueError(f"Archive {resolved.name} is missing required OpenXML workbook structure.")

    return resolved


def _detect_candidate_sheets(scan: WorkbookScanResult) -> tuple[list[str], list[str]]:
    """Identify candidate scenario assumption sheets and BQML ARIMA_PLUS time-series sheets."""
    assumption_sheets: list[str] = []
    timeseries_sheets: list[str] = []

    for sh_name in scan.sheet_names:
        sh = scan.sheets.get(sh_name)
        if sh is None:
            continue
        state = scan.sheet_states.get(sh_name, "visible")
        if sh.has_time_axis and state == "visible":
            timeseries_sheets.append(sh_name)

        numeric_literals = 0
        for row_cells in sh.cells_by_row.values():
            for c in row_cells:
                if c.formula is None and c.value is not None and c.ctype not in ("s", "e", "b"):
                    numeric_literals += 1

        pop = max(sh.populated_cells, 1)
        literal_ratio = numeric_literals / pop
        if state == "visible" and (
            _ASSUMPTION_TAB_RE.search(sh_name)
            or (numeric_literals >= 15 and literal_ratio >= 0.25 and sh.formula_cells < sh.populated_cells)
        ):
            assumption_sheets.append(sh_name)

    return assumption_sheets, timeseries_sheets


def _build_exceptions(
    scan: WorkbookScanResult,
    scorecard: WorkbookScorecard,
    defects: Sequence[CellDefectRecord],
    link_audits: Sequence[ExternalLinkAuditRecord],
    settings: OnboardingSettings,
) -> list[HygieneExceptionItem]:
    """Aggregate structural, VBA, external-link, and cell-level defects into prioritized exceptions."""
    exceptions: list[HygieneExceptionItem] = []

    # 1. Zero formulas check
    if scan.total_formula_cells == 0:
        exceptions.append(
            HygieneExceptionItem(
                code="NO_FORMULAS_FOUND",
                severity="BLOCKER",
                sub_metric="E1",
                title="Workbook Contains Zero Formula Cells",
                affected_count=0,
                sample_locations=[],
                remediation="Supply a calculation workbook containing live Excel formulas rather than a values-only export.",
            )
        )

    # 2. Locked VBA binary check
    if scan.vba.is_locked:
        exceptions.append(
            HygieneExceptionItem(
                code="LOCKED_VBA_PROJECT",
                severity="BLOCKER",
                sub_metric="E2",
                title="Password-Locked / Unviewable VBA Macro Project",
                affected_count=1,
                sample_locations=["xl/vbaProject.bin"],
                remediation="Unlock the VBA project in Excel before onboarding so procedural macros can be inspected and translated.",
            )
        )

    # 3. Non-portable Win32/Shell or COM/DB VBA host calls
    if scan.vba.has_win32_or_shell or scan.vba.has_com_or_db:
        flags = []
        if scan.vba.has_win32_or_shell:
            flags.append("Win32 DLL / Shell execution")
        if scan.vba.has_com_or_db:
            flags.append("COM / ADODB / Workbooks.Open coupling")
        exceptions.append(
            HygieneExceptionItem(
                code="NON_PORTABLE_VBA_HOST_CALLS",
                severity="WARNING",
                sub_metric="E2",
                title=f"Desktop-Coupled VBA Constructs Detected ({', '.join(flags)})",
                affected_count=len(scan.vba.module_names) or 1,
                sample_locations=scan.vba.module_names[:10],
                remediation="Verify desktop file/COM side-effects in VBA modules are replaced with BigQuery Digital Twin inputs during PR review.",
            )
        )

    # 4. Proprietary _xll.* UDF / desktop data-feed cells
    xll_cells = int(scorecard.telemetry.get("xll_udf_cells", 0))
    opaque_cells = int(scorecard.telemetry.get("opaque_cells", 0))
    if xll_cells > 0 or opaque_cells > 0:
        uncached_or_opaque = opaque_cells > 0
        exceptions.append(
            HygieneExceptionItem(
                code="XLL_OR_OPAQUE_UDF_FEEDS",
                severity="BLOCKER" if uncached_or_opaque else "WARNING",
                sub_metric="E1/E4",
                title="Proprietary _xll.* Add-In or Opaque Dynamic Functions (INDIRECT/RTD/CUBE)",
                affected_count=xll_cells + opaque_cells,
                sample_locations=[],
                remediation=(
                    "Uncached _xll.* or INDIRECT/RTD formulas lack deterministic cached values; materialize feed tables into BigQuery first."
                    if uncached_or_opaque
                    else "Cached _xll.* values will be snapshotted as static Digital Twin inputs; plan a BigQuery feed table for live refreshes."
                ),
            )
        )

    # 5. External workbook link coverage
    if scan.ext_formula_cell_count > 0:
        cache_cov = scan.ext_formula_valid_cache_count / max(scan.ext_formula_cell_count, 1)
        unresolved_links = [
            la for la in link_audits if la.active_formula_refs > 0 and la.resolution_status != "RESOLVED"
        ]
        sample_ext = [f"{r.sheet_name}!{r.cell_coord}" for r in scan.active_ext_refs[:10]]
        if cache_cov < settings.min_external_cache_coverage and unresolved_links:
            exceptions.append(
                HygieneExceptionItem(
                    code="UNCACHED_EXTERNAL_LINKS",
                    severity="BLOCKER",
                    sub_metric="E4/H4",
                    title=f"Uncached External Workbook Links ({cache_cov * 100:.1f}% cached < {settings.min_external_cache_coverage * 100:.0f}% threshold)",
                    affected_count=scan.ext_formula_cell_count - scan.ext_formula_valid_cache_count,
                    sample_locations=sample_ext,
                    remediation="Refresh and save external links in Excel or provide peer workbooks via --refs-dir before onboarding.",
                )
            )
        elif unresolved_links:
            exceptions.append(
                HygieneExceptionItem(
                    code="SNAPSHOT_EXTERNAL_LINKS",
                    severity="WARNING",
                    sub_metric="E4/H4",
                    title=f"External Workbook Links Snapshotted from Cached Values ({cache_cov * 100:.1f}% cached)",
                    affected_count=scan.ext_formula_cell_count,
                    sample_locations=sample_ext,
                    remediation="External [N]Sheet!Cell links will be materialized into dt_external_links using cached baseline values unless peer workbooks are supplied.",
                )
            )

    # 6. Broken #REF! defined names
    if scan.broken_defined_names > 0:
        broken_samples = [
            name for name, body in scan.defined_names if "#REF!" in body.upper()
        ][:10]
        exceptions.append(
            HygieneExceptionItem(
                code="BROKEN_DEFINED_NAMES",
                severity="INFO",
                sub_metric="H3",
                title="Dormant or Broken #REF! Defined Names in Workbook Metadata",
                affected_count=scan.broken_defined_names,
                sample_locations=broken_samples,
                remediation="Pruned automatically when compiling active named ranges into dt_workbook_versions.",
            )
        )

    # 7. Cell-level hygiene defects grouped by defect_type
    grouped: dict[tuple[str, str], list[CellDefectRecord]] = defaultdict(list)
    for d in defects:
        grouped[(d.sub_metric, d.defect_type)].append(d)

    for (sub_metric, defect_type), items in sorted(grouped.items()):
        has_high = any(it.severity == "HIGH" for it in items)
        title, remediation = _DEFECT_REMEDIATIONS.get(
            defect_type,
            (defect_type.replace("_", " ").title(), "Review flagged cell coordinates during PR inspection."),
        )
        # Only escalate cell-level anomalies to WARNING when volume is material or MDR exceeds threshold
        severity: str = "WARNING" if (has_high and len(items) >= 5) else "INFO"
        exceptions.append(
            HygieneExceptionItem(
                code=defect_type,
                severity=severity,  # type: ignore[arg-type]
                sub_metric=sub_metric,
                title=title,
                affected_count=len(items),
                sample_locations=[f"{it.sheet_name}!{it.cell_coord}" for it in items[:10]],
                remediation=remediation,
            )
        )

    # 8. Composite MRI / MDR threshold alert
    if scorecard.mri < settings.no_go_min_mri:
        exceptions.append(
            HygieneExceptionItem(
                code="MRI_BELOW_MINIMUM",
                severity="BLOCKER",
                sub_metric="MRI",
                title=f"Modernization Readiness Index ({scorecard.mri:.1f}%) Below Minimum ({settings.no_go_min_mri:.1f}%)",
                affected_count=1,
                sample_locations=[],
                remediation="Remediate structural corruption, uncached feeds, or high cell error rates before automated onboarding.",
            )
        )
    elif scorecard.mri < settings.go_min_mri or scorecard.defect_rate > settings.go_max_mdr:
        exceptions.append(
            HygieneExceptionItem(
                code="ELEVATED_DEFECT_OR_MODERATE_MRI",
                severity="WARNING",
                sub_metric="MRI/MDR",
                title=(
                    f"Moderate Readiness / Elevated Defect Rate "
                    f"(MRI={scorecard.mri:.1f}%, MDR={scorecard.defect_rate:.1f}%)"
                ),
                affected_count=1,
                sample_locations=[],
                remediation="Proceed with Conditional-Go; verify flagged defect coordinates against parity report in the Git PR.",
            )
        )

    severity_rank = {"BLOCKER": 0, "WARNING": 1, "INFO": 2}
    exceptions.sort(key=lambda ex: (severity_rank[ex.severity], -ex.affected_count, ex.code))
    return exceptions


def evaluate_workbook_hygiene(
    xlsx_path: Path,
    model_slug: str | None = None,
    reference_roots: Sequence[Path] = (),
    settings: OnboardingSettings | None = None,
) -> HygieneGateReport:
    """Execute deterministic Stage 1 hygiene scan, Exception Report, and Go/No-Go decision."""
    cfg = settings or get_onboarding_settings()
    validated_path = validate_workbook_file(xlsx_path, max_size_mb=cfg.max_workbook_size_mb)
    slug = validate_model_slug(model_slug or derive_default_slug(validated_path.name))

    scan = scan_workbook_openxml(validated_path)
    scorecard, defects, link_audits = assess_workbook(
        validated_path,
        reference_roots=reference_roots,
    )
    assumption_sheets, timeseries_sheets = _detect_candidate_sheets(scan)
    exceptions = _build_exceptions(scan, scorecard, defects, link_audits, cfg)

    blockers = [ex for ex in exceptions if ex.severity == "BLOCKER"]
    warnings = [ex for ex in exceptions if ex.severity == "WARNING"]

    rationale: list[str] = []
    if blockers:
        decision = GoNoGoDecision.NO_GO
        for b in blockers:
            rationale.append(f"[BLOCKER:{b.code}] {b.title} (affected={b.affected_count}).")
    elif warnings:
        decision = GoNoGoDecision.CONDITIONAL_GO
        rationale.append(
            f"Passed hard extractability blockers (MES={scorecard.les.score:.1f}%, MRI={scorecard.mri:.1f}%), "
            f"with {len(warnings)} warning(s) requiring reviewer verification in the Git PR."
        )
        for w in warnings[:4]:
            rationale.append(f"[WARNING:{w.code}] {w.title} (affected={w.affected_count}).")
    else:
        decision = GoNoGoDecision.GO
        rationale.append(
            f"Clean onboarding candidate: MES={scorecard.les.score:.1f}%, "
            f"MDR={scorecard.defect_rate:.1f}%, MRI={scorecard.mri:.1f}% ({scorecard.readiness_tier})."
        )

    is_iter = scan.calc_pr.get("iterate") == "1"
    iter_cnt = int(scan.calc_pr.get("iterateCount", "1") or "1") if is_iter else 1

    return HygieneGateReport(
        model_slug=slug,
        workbook_name=validated_path.name,
        file_size_mb=scorecard.file_size_mb,
        archetype=scorecard.archetype,
        vintage_tag=scorecard.vintage_tag,
        sheet_count=scorecard.sheet_count,
        total_populated_cells=scorecard.total_populated_cells,
        total_formula_cells=scorecard.total_formula_cells,
        mes_score=scorecard.les.score,
        mhs_score=scorecard.mhs.score,
        mdr_score=scorecard.defect_rate,
        mri_score=scorecard.mri,
        readiness_tier=scorecard.readiness_tier,
        recommended_action=scorecard.recommended_action,
        decision=decision,
        decision_rationale=rationale,
        exceptions=exceptions,
        extractability_metrics=[
            SubMetricSummary(
                code=m.code,
                title=m.title,
                applicable=m.applicable,
                effective_weight=m.effective_weight,
                score=m.score,
                summary=m.summary,
            )
            for m in scorecard.les.sub_metrics
        ],
        hygiene_metrics=[
            SubMetricSummary(
                code=m.code,
                title=m.title,
                applicable=m.applicable,
                effective_weight=m.effective_weight,
                score=m.score,
                summary=m.summary,
            )
            for m in scorecard.mhs.sub_metrics
        ],
        candidate_assumption_sheets=assumption_sheets,
        candidate_timeseries_sheets=timeseries_sheets,
        vba_modules=list(scan.vba.module_names),
        is_iterative_calc=is_iter,
        iterate_count=iter_cnt,
        telemetry=scorecard.telemetry,
    )


def render_hygiene_exception_markdown(report: HygieneGateReport) -> str:
    """Render human-reviewable Markdown Exception Report and Go/No-Go Scorecard."""
    lines: list[str] = [
        f"# Workbook Onboarding Hygiene & Exception Report — `{report.workbook_name}`",
        "",
        f"- **Onboarding Recommendation**: **`{report.decision.value}`**",
        f"- **Target Model Slug**: `{report.model_slug}`",
        f"- **Detected Archetype**: `{report.archetype}`",
        f"- **Readiness Tier**: {report.readiness_tier}",
        f"- **Scale**: `{report.sheet_count}` tabs | `{report.total_populated_cells:,}` populated cells | `{report.total_formula_cells:,}` formulas (`{report.file_size_mb:.2f}` MB)",
        f"- **Calculation Mode**: {'Iterative (`iterateCount=' + str(report.iterate_count) + '`)' if report.is_iterative_calc else 'Standard Acyclic DAG'}",
        "",
        "## 1. Executive Scorecard",
        "",
        "| Metric | Score | Interpretation |",
        "| :--- | ---: | :--- |",
        f"| **Model Extractability Score (`MES` / `LES`)** | **{report.mes_score:.1f}%** | Higher = more deterministic formula/VBA extraction |",
        f"| **Model Hygiene Score (`MHS`)** | **{report.mhs_score:.1f}%** | Structural cleanliness & reference integrity |",
        f"| **Model Defect Rate (`MDR = 100 - MHS`)** | **{report.mdr_score:.1f}%** | Lower = fewer broken cells, islands, or link issues |",
        f"| **Modernization Readiness Index (`MRI`)** | **{report.mri_score:.1f}%** | Composite readiness score (`>=80%` Go, `<50%` No-Go) |",
        "",
        "### Go / No-Go Rationale",
    ]
    for item in report.decision_rationale:
        lines.append(f"- {item}")

    lines.extend(
        [
            "",
            "## 2. Exception Report",
            "",
        ]
    )
    if not report.exceptions:
        lines.append("No structural, external-link, VBA, or cell-level exceptions detected.")
    else:
        lines.extend(
            [
                "| Severity | Sub-Metric | Code | Affected | Sample Locations | Remediation |",
                "| :---: | :---: | :--- | ---: | :--- | :--- |",
            ]
        )
        for ex in report.exceptions:
            samples = ", ".join(f"`{loc}`" for loc in ex.sample_locations[:5]) or "—"
            lines.append(
                f"| **{ex.severity}** | `{ex.sub_metric}` | `{ex.code}` | {ex.affected_count:,} | {samples} | {ex.remediation} |"
            )

    lines.extend(
        [
            "",
            "## 3. Detected Onboarding Targets",
            "",
            f"- **Candidate Scenario Assumption Tabs**: {', '.join(f'`{s}`' for s in report.candidate_assumption_sheets) or 'None auto-detected'}",
            f"- **Candidate BigQuery ML `ARIMA_PLUS` Time-Series Tabs**: {', '.join(f'`{s}`' for s in report.candidate_timeseries_sheets) or 'None auto-detected'}",
            f"- **VBA Modules (`{len(report.vba_modules)}`)**: {', '.join(f'`{m}`' for m in report.vba_modules[:15]) or 'Macro-free workbook'}",
            "",
        ]
    )
    return "\n".join(lines)


def write_hygiene_gate_artifacts(report: HygieneGateReport, output_dir: Path) -> tuple[Path, Path]:
    """Write `hygiene_exception_report.json` and `hygiene_exception_report.md` inside `output_dir`."""
    resolved_dir = output_dir.expanduser().resolve()
    resolved_dir.mkdir(parents=True, exist_ok=True)
    json_path = resolved_dir / "hygiene_exception_report.json"
    md_path = resolved_dir / "hygiene_exception_report.md"

    json_path.write_text(json.dumps(report.model_dump(mode="json"), indent=2), encoding="utf-8")
    md_path.write_text(render_hygiene_exception_markdown(report), encoding="utf-8")
    return json_path, md_path
