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
    by_e4 = next(s for s in subs if s.code == "E4")
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
