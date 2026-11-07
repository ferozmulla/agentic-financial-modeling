"""Phase 3 Verification Tests: TEST-A06 (BQML & Surrogate) and TEST-B02..B08 (4-Ws Audit, R1C1 Shift Immunity, 3-Tier Rollback)."""

from __future__ import annotations

from pathlib import Path

from src.bqml.forecaster import (
    generate_bqml_breakout_tab_matrix,
    predict_crack_spread_surrogate,
)
from src.diff.ast_differ import (
    classify_governed_edit,
    is_r1c1_equivalent_after_row_shift,
)
from src.schemas.models import BQMLRefreshRequest, GovernedEditEventRequest
from src.storage.repository import GovernanceRepository
from src.vertex.explainer import generate_4ws_why_summary


def test_a06_bqml_breakout_tabs_and_crack_spread_surrogate() -> None:
    """TEST-A06: Verify 3 breakout BQML tabs (Macro_BQML, Crudes_BQML, Freight_BQML) and Vertex AI surrogate."""
    for tab in ("Macro_BQML", "Crudes_BQML", "Freight_BQML"):
        resp = generate_bqml_breakout_tab_matrix(BQMLRefreshRequest(tab_name=tab))  # type: ignore[arg-type]
        assert resp.tab_name == tab
        assert resp.years[0] == 1990
        assert resp.years[-1] == 2050
        assert len(resp.series_rows) >= 5
        assert resp.surrogate_model_registry_id == "eulr-sheets-mod-margin-surrogate"

    surrogate = predict_crack_spread_surrogate(
        dated_brent_usd_bbl=82.0, eu_ets_eur_tco2=90.0, urals_diff_usd_bbl=-2.50
    )
    assert surrogate.model_registry_name == "eulr-sheets-mod-margin-surrogate"
    assert surrogate.predicted_nwe_diesel_crack_usd_bbl > 20.0


def test_b02_r1c1_row_shift_immunity() -> None:
    """TEST-B02: Verify R1C1 normalization suppresses false-positive formula alerts when rows are inserted."""
    # Row 15 shifted to Row 16 after 1 row inserted above
    assert is_r1c1_equivalent_after_row_shift(
        before_formula="=AU18-Carbon!Q10+BW19",
        after_formula="=AU19-Carbon!Q11+BW20",
        base_row=15,
        base_col=47,
        row_shift_delta=1,
    )

    ev = GovernedEditEventRequest(
        spreadsheet_id="sheet-r1c1",
        sheet_name="KeyInputs",
        cell_a1="AU15",
        before_formula="=BB14-0.25",
        new_formula="=BB15-0.25",
        row_shift_delta=1,
    )
    cls = classify_governed_edit(ev)
    assert cls.suppressed is True
    assert cls.classification == "SUPPRESSED_R1C1_SHIFT_INVARIANT"


def test_b03_routine_switch_suppression_vs_manual_formula_override() -> None:
    """TEST-B03: Verify routine switch toggles on KeyInputs Row 10 and Carbon!A5:A6 are suppressed while formula overrides log."""
    sw_ev = GovernedEditEventRequest(
        spreadsheet_id="sheet-sw",
        sheet_name="KeyInputs",
        cell_a1="AT10",
        before_value=0,
        new_value=1,
    )
    sw_cls = classify_governed_edit(sw_ev)
    assert sw_cls.suppressed is True

    carb_ev = GovernedEditEventRequest(
        spreadsheet_id="sheet-sw",
        sheet_name="Carbon",
        cell_a1="A5",
        before_value="Sensitivity with EU ETS cost and pass-through",
        new_value="Base without EU ETS carbon pass-through",
    )
    assert classify_governed_edit(carb_ev).suppressed is True

    # Formula modification on KeyInputs!BA14 (=BB14-0.25 -> =BB14-0.15) must NOT be suppressed
    f_ev = GovernedEditEventRequest(
        spreadsheet_id="sheet-sw",
        sheet_name="KeyInputs",
        cell_a1="BA14",
        before_formula="=BB14-0.25",
        new_formula="=BB14-0.15",
    )
    f_cls = classify_governed_edit(f_ev)
    assert f_cls.suppressed is False
    assert f_cls.classification == "MANUAL_OVERRIDE"
    assert f_cls.highlight_hex == "#FEF3C7"


def test_b04_to_b08_per_spreadsheet_overrides_4ws_audit_and_three_tier_rollback(
    tmp_path: Path,
) -> None:
    """TEST-B04..B08: Verify per-spreadsheet #FEF3C7 override isolation, 4-Ws logging, and 3-tier rollback."""
    repo = GovernanceRepository(base_data_dir=tmp_path)

    # Central sheet vs analyst 'File -> Make a copy' sheet isolation
    repo.upsert_pinned_override("central-sheet", "NWE Cif", "AU122", 750.00)
    repo.upsert_pinned_override("analyst-copy-1", "NWE Cif", "AU122", 780.00)

    assert repo.get_pinned_overrides("central-sheet") == {"NWE Cif!AU122": 750.0}
    assert repo.get_pinned_overrides("analyst-copy-1") == {"NWE Cif!AU122": 780.0}

    # Log a formula override and a label rename with gemini-3.8-flash why_ai_summary
    f_ev = GovernedEditEventRequest(
        spreadsheet_id="central-sheet",
        copy_location_url="https://docs.google.com/spreadsheets/d/central-sheet/edit",
        actor_email="analyst@spglobal.com",
        sheet_name="KeyInputs",
        cell_a1="BA14",
        before_value=9.65,
        new_value=9.75,
        before_formula="=BB14-0.25",
        new_formula="=BB14-0.15",
    )
    f_cls = classify_governed_edit(f_ev)
    why = generate_4ws_why_summary(f_ev, f_cls.classification)
    repo.append_audit_event(
        actor_email=f_ev.actor_email,
        spreadsheet_id=f_ev.spreadsheet_id,
        copy_location_url=f_ev.copy_location_url,
        sheet_name=f_ev.sheet_name,
        cell_a1=f_ev.cell_a1,
        classification=f_cls.classification,
        before_value=f_ev.before_value,
        new_value=f_ev.new_value,
        before_formula=f_ev.before_formula,
        new_formula=f_ev.new_formula,
        why_ai_summary=why,
        rollback_tier_hint=f_cls.rollback_tier_hint,
    )

    # Tier 1 Rollback: 1-click revert of pinned override on central-sheet leaves analyst-copy-1 untouched
    reverted, remaining = repo.revert_pinned_overrides("central-sheet")
    assert reverted == ["NWE Cif!AU122"]
    assert remaining == {}
    assert repo.get_pinned_overrides("analyst-copy-1") == {"NWE Cif!AU122": 780.0}

    # Tier 2 Rollback: surgical formula restoration for KeyInputs!BA14
    surgical = repo.get_surgical_cell_rollback("central-sheet", "KeyInputs", "BA14")
    assert surgical is not None
    assert surgical.before_formula == "=BB14-0.25"
    assert surgical.before_value == "9.65"

    # Tier 3 Rollback: copy_location_url + when_event_utc preserved
    assert surgical.copy_location_url == "https://docs.google.com/spreadsheets/d/central-sheet/edit"
    assert "T" in surgical.when_event_utc
