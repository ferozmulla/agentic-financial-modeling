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


def _classify_formula_template(ft: str) -> tuple[bool, str]:
    """Return (is_volatile, bucket) cached per unique formula string."""
    is_vol = bool(_VOLATILE_RE.search(ft))
    if _OPAQUE_RE.search(ft):
        return (is_vol, "opaque")
    if _XLL_RE.search(ft):
        return (is_vol, "xll")
    if _ADV_RE.search(ft):
        return (is_vol, "adv")
    return (is_vol, "std")


def compute_extractability_pillar(scan: WorkbookScanResult) -> tuple[PillarScore, dict[str, int]]:
    """Compute LES (0-100%) and sub-metrics E1..E5 across active workbook surfaces."""
    n_f = scan.total_formula_cells
    credit_sum = 0.0
    xll_cells = 0
    opaque_cells = 0
    cse_or_adv_cells = 0
    volatile_cells = 0
    template_cache: dict[str, tuple[bool, str]] = {}

    for sh in scan.sheets.values():
        for row_cells in sh.cells_by_row.values():
            for c in row_cells:
                if c.formula is None:
                    continue
                ft = c.formula
                cached_cls = template_cache.get(ft)
                if cached_cls is None:
                    cached_cls = _classify_formula_template(ft)
                    template_cache[ft] = cached_cls
                is_vol, bucket = cached_cls
                if is_vol:
                    volatile_cells += 1
                if bucket == "opaque":
                    opaque_cells += 1
                elif bucket == "xll":
                    xll_cells += 1
                    if c.value is not None and c.ctype != "e":
                        credit_sum += 0.25
                    else:
                        opaque_cells += 1
                elif c.is_array_cse or bucket == "adv":
                    cse_or_adv_cells += 1
                    credit_sum += 0.85
                else:
                    credit_sum += 1.00

    # E1: Formula & UDF Portability
    a_e1 = n_f >= 1
    e1_score = clamp(100.0 * (credit_sum / max(n_f, 1))) if a_e1 else None
    e1_summary = (
        f"{n_f:,} formulas ({xll_cells:,} XLL UDF, "
        f"{cse_or_adv_cells:,} CSE/OFFSET/_xlfn, {opaque_cells:,} opaque/failed-XLL)"
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
        iter_desc = f"Iterative (iterateCount={iter_cnt})" if is_iter else "Acyclic DAG"
        e3_summary = f"{iter_desc}, {volatile_cells:,} volatile cells"

    # E4: External Feed & Connection Decoupling (includes proprietary _xll.* desktop feeds)
    active_ext_books = len({r.link_index for r in scan.active_ext_refs})
    a_e4 = (
        scan.ext_formula_cell_count > 0
        or scan.has_connections_xml
        or scan.external_pivot_caches > 0
        or xll_cells > 0
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
        if xll_cells > 0:
            xll_share = xll_cells / max(n_f, 1)
            sc4 -= min(28.0, 8.0 + 40.0 * xll_share)
        sc4 -= min(10.0, 0.15 * active_ext_books)
        e4_score = clamp(sc4)
        e4_summary = (
            f"{scan.ext_formula_cell_count:,} ext-link cells ({cache_cov*100:.1f}% cached) "
            f"across {active_ext_books} books, {xll_cells:,} XLL feed cells; "
            f"connections.xml={scan.has_connections_xml}"
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
