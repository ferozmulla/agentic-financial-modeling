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
        (
            "| Rank | Workbook | Archetype | Populated Cells | Formulas | "
            "`LES` (Extractability) | `MHS` (Hygiene) | Defect Rate (`100-MHS`) | "
            "Overall `MRI` | Readiness Tier |"
        ),
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
            (
                "| Workbook | `LES` | `E1` Formula/UDF | `E2` Macros | "
                "`E3` Graph | `E4` Ext Feeds | `E5` Time-Series |"
            ),
            "| :--- | ---: | :---: | :---: | :---: | :---: | :---: |",
        ]
    )
    for sc in scorecards:
        em = {s.code: s for s in sc.les.sub_metrics}
        lines.append(
            f"| `{sc.workbook_name}` | **{sc.les.score:.1f}%** | {_fmt_sub(em['E1'])} | "
            f"{_fmt_sub(em['E2'])} | {_fmt_sub(em['E3'])} | "
            f"{_fmt_sub(em['E4'])} | {_fmt_sub(em['E5'])} |"
        )

    lines.extend(
        [
            "",
            "## 3. Pillar 2 Breakdown — Model Hygiene Score (`MHS`) With Dynamic Archetype Weights",
            "",
            (
                "| Workbook | `MHS` | Defect Rate | `H1` Cell Errors | "
                "`H2` Drag/Continuity | `H3` Refs/Names | `H4` Link Hygiene | `H5` Calc/Bloat |"
            ),
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
            if s.applicable and s.score is not None:
                lines.append(
                    f"- **`{s.code}` {s.title} (`{s.score:.1f}%`, "
                    f"eff. weight `{s.effective_weight*100:.1f}%`):** {s.summary}"
                )
        lines.append("")

    md_path.write_text("\n".join(lines), encoding="utf-8")

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
            em_s = {s.code: s.score for s in sc.les.sub_metrics}
            hm_s = {s.code: s.score for s in sc.mhs.sub_metrics}
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
                    em_s["E1"],
                    em_s["E2"],
                    em_s["E3"],
                    em_s["E4"],
                    em_s["E5"],
                    hm_s["H1"],
                    hm_s["H2"],
                    hm_s["H3"],
                    hm_s["H4"],
                    hm_s["H5"],
                    sc.telemetry.get("xll_udf_cells", 0),
                    sc.telemetry.get("unintentional_error_cells", 0),
                    sc.telemetry.get("drag_and_island_cells", 0),
                    sc.telemetry.get("broken_defined_names", 0),
                ]
            )

    with defects_path.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.writer(fp)
        writer.writerow(
            [
                "workbook_name",
                "sheet_name",
                "cell_coord",
                "sub_metric",
                "defect_type",
                "severity",
                "detail",
            ]
        )
        for d in defects:
            writer.writerow(
                [
                    d.workbook_name,
                    d.sheet_name,
                    d.cell_coord,
                    d.sub_metric,
                    d.defect_type,
                    d.severity,
                    d.detail,
                ]
            )

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
