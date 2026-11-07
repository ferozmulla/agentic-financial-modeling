"""R1C1 coordinate-shift normalizer and silent distributed 4-Ws edit classifier."""

from __future__ import annotations

from dataclasses import dataclass

from src.parser.openxml_extractor import normalize_formula_to_r1c1, split_coord
from src.schemas.models import GovernedEditEventRequest

PRICING_OVERRIDE_SHEETS = frozenset(
    {"Crudes", "NWE Cif", "MED Cif", "NWE Fob", "MED Fob", "IMOfuels"}
)


@dataclass(frozen=True)
class EditClassificationResult:
    suppressed: bool
    classification: str
    highlight_hex: str | None
    is_pinned_override: bool
    rollback_tier_hint: str
    r1c1_before: str | None
    r1c1_after: str | None


def is_r1c1_equivalent_after_row_shift(
    before_formula: str,
    after_formula: str,
    base_row: int,
    base_col: int,
    row_shift_delta: int = 0,
) -> bool:
    """
    Verify whether two A1 formulas have identical R1C1 structure after accounting for
    a structural row insertion or deletion (preventing N false-positive alerts).
    """
    sig_before = normalize_formula_to_r1c1(before_formula, base_row, base_col)
    sig_after = normalize_formula_to_r1c1(after_formula, base_row + row_shift_delta, base_col)
    return sig_before == sig_after


def classify_governed_edit(event: GovernedEditEventRequest) -> EditClassificationResult:
    """
    Classify an incoming Google Sheets edit or structural event according to the EULR 4-Ws rules:
    1. Suppress routine scenario/carbon switch toggles (KeyInputs!AT10:BT10, Carbon!A5:A6).
    2. Suppress pure coordinate shifts caused by row insertions/deletions where R1C1 is invariant.
    3. Classify structural changes (ROW_INSERTED, ROW_DELETED, SHEET_ADDED).
    4. Classify manual numeric price edits on pricing tabs as PINNED_PRICE_OVERRIDE (#FEF3C7).
    5. Classify formula modifications on live formula tabs as MANUAL_OVERRIDE.
    6. Classify label/header changes in Columns A:C as HEADER_OR_LABEL_MODIFIED.
    """
    if event.structural_change_type:
        return EditClassificationResult(
            suppressed=False,
            classification=event.structural_change_type.upper(),
            highlight_hex=None,
            is_pinned_override=False,
            rollback_tier_hint="TIER_3_VERSION_HISTORY",
            r1c1_before=None,
            r1c1_after=None,
        )

    r_idx, c_idx = split_coord(event.cell_a1.replace("$", ""))

    # Rule 1: Suppress routine switch tweaks on KeyInputs Row 10 (Cols N..BT) and Carbon!A5:A6
    if (event.sheet_name == "KeyInputs" and r_idx == 10 and c_idx >= 14) or (
        event.sheet_name == "Carbon" and event.cell_a1.upper() in ("A5", "A6")
    ):
        return EditClassificationResult(
            suppressed=True,
            classification="SUPPRESSED_SCENARIO_SWITCH",
            highlight_hex=None,
            is_pinned_override=False,
            rollback_tier_hint="NONE",
            r1c1_before=None,
            r1c1_after=None,
        )

    # Rule 2: Formula modification vs R1C1 shift-invariance check
    if event.before_formula or event.new_formula:
        r1c1_b = (
            normalize_formula_to_r1c1(event.before_formula, r_idx, c_idx)
            if event.before_formula
            else None
        )
        r1c1_a = (
            normalize_formula_to_r1c1(event.new_formula, r_idx + event.row_shift_delta, c_idx)
            if event.new_formula
            else None
        )
        if r1c1_b and r1c1_a and r1c1_b == r1c1_a:
            return EditClassificationResult(
                suppressed=True,
                classification="SUPPRESSED_R1C1_SHIFT_INVARIANT",
                highlight_hex=None,
                is_pinned_override=False,
                rollback_tier_hint="NONE",
                r1c1_before=r1c1_b,
                r1c1_after=r1c1_a,
            )
        return EditClassificationResult(
            suppressed=False,
            classification="MANUAL_OVERRIDE",
            highlight_hex="#FEF3C7",
            is_pinned_override=False,
            rollback_tier_hint="TIER_2_SURGICAL_FORMULA_RESTORE",
            r1c1_before=r1c1_b,
            r1c1_after=r1c1_a,
        )

    # Rule 3: Trader Pinned Price Override on equilibrium pricing tabs
    if event.sheet_name in PRICING_OVERRIDE_SHEETS and c_idx >= 4:
        try:
            if event.new_value is not None:
                float(event.new_value)
                return EditClassificationResult(
                    suppressed=False,
                    classification="PINNED_PRICE_OVERRIDE",
                    highlight_hex="#FEF3C7",
                    is_pinned_override=True,
                    rollback_tier_hint="TIER_1_ONE_CLICK_OVERRIDE_REVERT",
                    r1c1_before=None,
                    r1c1_after=None,
                )
        except (ValueError, TypeError):
            pass

    # Rule 4: Metadata label or header modification (Columns A:C or header rows 1..7)
    if c_idx <= 3 or r_idx <= 7:
        return EditClassificationResult(
            suppressed=False,
            classification="HEADER_OR_LABEL_MODIFIED",
            highlight_hex=None,
            is_pinned_override=False,
            rollback_tier_hint="TIER_2_SURGICAL_CELL_RESTORE",
            r1c1_before=None,
            r1c1_after=None,
        )

    return EditClassificationResult(
        suppressed=False,
        classification="DRIVER_VALUE_EDIT",
        highlight_hex=None,
        is_pinned_override=False,
        rollback_tier_hint="TIER_2_SURGICAL_CELL_RESTORE",
        r1c1_before=None,
        r1c1_after=None,
    )
