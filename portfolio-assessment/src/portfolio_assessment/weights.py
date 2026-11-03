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
                    effective_weight=round(eff_w, 8),
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
