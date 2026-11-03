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
_STR_LIT_RE = re.compile(r'"[^"]*"')
_SHEET_REF_RE = re.compile(
    r"(?:'((?:[^'\[\]]|'')+)'|(?<![A-Za-z0-9_.'\"\[])([A-Za-z0-9_.]+))!(?=\$?[A-Za-z0-9_])"
)
_DEAD_TAB_RE = re.compile(
    r"(shooju_addin|_old$|^old_|not_updated|archive|backup|temp)",
    re.IGNORECASE,
)
_REL_UNANCHORED_RE = re.compile(r"(?<![A-Za-z0-9_$])([A-Z]{1,3})(\d+)")


def _axis_pos(cell: CellInfo, is_row: bool) -> int:
    return cell.col if is_row else cell.row


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
    if len(ordered) < 4:
        return (0, 0, 0)

    structured_cnt = sum(1 for c in ordered if c.r1c1_sig is not None)
    anomalies = 0
    fill_glitches = 0

    # 1. Hardcoded Value Islands inside dominant R1C1 runs (>= 6 matching formula cells)
    min_run_cnt = 6 if is_row else max(6, int(0.55 * len(ordered)))
    sig_counts = Counter(c.r1c1_sig for c in ordered if c.r1c1_sig is not None)
    for sig, cnt in sig_counts.items():
        if cnt < min_run_cnt:
            continue
        positions = [i for i, c in enumerate(ordered) if c.r1c1_sig == sig]
        first_i, last_i = positions[0], positions[-1]
        idx_pos = first_i + 1
        while idx_pos < last_i:
            c = ordered[idx_pos]
            if c.formula is None and c.value is not None and c.ctype not in ("e", "s"):
                end_pos = idx_pos
                while (
                    end_pos < last_i
                    and ordered[end_pos].formula is None
                    and ordered[end_pos].value is not None
                    and ordered[end_pos].ctype not in ("e", "s")
                ):
                    end_pos += 1
                island_len = end_pos - idx_pos
                coord_span = _axis_pos(ordered[end_pos], is_row) - _axis_pos(
                    ordered[idx_pos - 1], is_row
                )
                if (
                    1 <= island_len <= 5
                    and coord_span == island_len + 1
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
                                    detail=(
                                        f"Static value {ordered[k].value!r} interrupts "
                                        f"R1C1 series ({cnt} cells)"
                                    ),
                                )
                            )
                idx_pos = max(end_pos, idx_pos + 1)
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
                    if abs(cand - round(cand)) > 1e-4:
                        val_f = cand
                except ValueError:
                    val_f = None
            if (
                val_f is not None
                and prev_val is not None
                and c.col - ordered[idx_c - 1].col == 1
                and abs((val_f - prev_val) - 1.0) <= 1e-6
            ):
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
                                detail=(
                                    "Decimal input stepped by +1.0 across >=4 cells "
                                    f"starting at {val_f - 3.0:.4f}"
                                ),
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
    valid_sheets_lower = {s.lower() for s in scan.sheet_names}
    dead_ref_cache: dict[str, bool] = {}

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
                            sev = (
                                "HIGH"
                                if c.value in ("#REF!", "#NAME?", "#VALUE!")
                                else "MEDIUM"
                            )
                            defects.append(
                                CellDefectRecord(
                                    workbook_name=wb_name,
                                    sheet_name=sh_name,
                                    cell_coord=c.coord,
                                    sub_metric="H1",
                                    defect_type="EVALUATED_CELL_ERROR",
                                    severity=sev,
                                    detail=(
                                        f"Cell evaluated to {c.value} "
                                        f"(formula={c.formula or 'literal'})"
                                    ),
                                )
                            )

                # H3: In-formula literal #REF! or missing internal sheet (cached per formula template)
                if c.formula:
                    has_dead = dead_ref_cache.get(c.formula)
                    if has_dead is None:
                        unquoted_f = _STR_LIT_RE.sub('""', c.formula)
                        has_dead = "#REF!" in unquoted_f
                        if not has_dead and "[" not in unquoted_f and "!" in unquoted_f:
                            for sm in _SHEET_REF_RE.finditer(unquoted_f):
                                ref_sh = (sm.group(1) or sm.group(2)).replace("''", "'")
                                if ref_sh.lower() not in valid_sheets_lower:
                                    has_dead = True
                                    break
                        dead_ref_cache[c.formula] = has_dead
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

        # Scan vertical table columns (>= 6 cells) when sheet lacks a horizontal time axis
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
        f"{unintentional_total:,} error cells ({dict(err_counts)}), "
        f"{intentional_na:,} intentional NA() excluded"
        if a_h1
        else "N/A"
    )

    # H2 Score
    a_h2 = structured_cells >= 6 or fill_glitches > 0
    total_h2_defects = drag_anomalies + fill_glitches
    d_rate = total_h2_defects / max(structured_cells, 6)
    h2_score = clamp(100.0 - 28.0 * math.log10(1.0 + 500.0 * d_rate)) if a_h2 else None
    h2_summary = (
        f"{drag_anomalies:,} island/drift cells + {fill_glitches:,} fill glitches "
        f"across {structured_cells:,} series cells"
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

    # H4 Score (Active ONLY when external links exist)
    n_decl_ext = len(scan.declared_external_links)
    a_h4 = n_decl_ext >= 1 or scan.ext_formula_cell_count >= 1
    if not a_h4:
        h4_score = None
        h4_summary = "N/A (0 external links)"
    else:
        total_active_refs = sum(a.active_formula_refs for a in link_audits)
        orphans = sum(1 for a in link_audits if a.active_formula_refs == 0)
        ghosts = sum(1 for a in link_audits if a.link_health_tier == "GHOST_OR_LOCAL_PATH")
        drifts = sum(1 for a in link_audits if a.link_health_tier == "PRIOR_VINTAGE_DRIFT")
        if total_active_refs == 0:
            # Zero active formula references -> unpruned dormant link stubs only (not live broken feeds)
            h4_score = clamp(85.0 - 1.5 * orphans - 0.5 * ghosts, 55.0, 85.0)
            h4_summary = (
                f"{n_decl_ext} dormant/unused link stubs (0 active formula refs; "
                f"{ghosts} legacy local/ghost paths)"
            )
        else:
            active_link_score = 100.0 * (
                sum(a.syntactic_score * a.active_formula_refs for a in link_audits)
                / total_active_refs
            )
            orphan_ratio = orphans / max(len(link_audits), 1)
            sc4 = 0.75 * active_link_score + 25.0 * (1.0 - orphan_ratio)
            missing_sheet_links = sum(
                1 for a in link_audits if a.resolution_status == "RESOLVED_SHEET_MISSING"
            )
            sc4 -= 10.0 * missing_sheet_links
            h4_score = clamp(sc4)
            h4_summary = (
                f"{n_decl_ext} declared links "
                f"({orphans} unused, {drifts} vintage-drift, {ghosts} local/ghost)"
            )

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
