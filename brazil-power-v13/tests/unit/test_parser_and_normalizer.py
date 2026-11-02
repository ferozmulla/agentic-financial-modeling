"""Unit tests for Pillar B formula R1C1 normalizer, shared formula expander, and shift detector."""

from __future__ import annotations

from src.diff.shift_normalizer import CoordinateShiftNormalizer
from src.parser.dag_builder import DependencyDAGBuilder
from src.parser.formula_normalizer import (
    a1_to_r1c1,
    canonicalize_a1_formula,
    compute_formula_hash,
    expand_shared_formula,
)
from src.parser.semantic_classifier import CellSemanticClassifier
from src.schemas.ast_dag import CellSemanticRole, ExtractedCellRecord


def test_r1c1_translation_invariance_across_row_shift() -> None:
    """Verify a relative formula shifted down by 1 row produces the exact same R1C1 string."""
    # Row 35, Col G (col=7): =E35*$C$4
    r1c1_row35 = a1_to_r1c1("=E35*$C$4", cell_row=35, cell_col=7)
    # Row 36, Col G (col=7) after inserting a row at Row 30: =E36*$C$4
    r1c1_row36 = a1_to_r1c1("=E36*$C$4", cell_row=36, cell_col=7)

    assert r1c1_row35 == "=RC[-2]*R4C3"
    assert r1c1_row35 == r1c1_row36
    assert compute_formula_hash(r1c1_row35) == compute_formula_hash(r1c1_row36)


def test_shared_formula_expansion_preserves_locked_and_relative_coords() -> None:
    """Verify OpenXML shared formula master expansion across rows and columns."""
    master_formula = "=E21*$C$4+F$10+$B21"
    expanded = expand_shared_formula(
        master_formula=master_formula,
        master_row=21,
        master_col=7,   # G21
        target_row=25,  # +4 rows
        target_col=8,   # H25 (+1 col)
    )
    assert expanded == "=F25*$C$4+G$10+$B25"


def test_dag_builder_handles_cross_sheet_and_ranges() -> None:
    """Verify precedent extraction expands bounded ranges and preserves sheet names."""
    fml = canonicalize_a1_formula("=IFERROR(NPV(I58,I21:I24)+'General'!$C$4,0)")
    cell = ExtractedCellRecord(
        sheet_name="_01_CF",
        cell_coord="I60",
        row_num=60,
        col_num=9,
        col_letter="I",
        data_type="n",
        raw_formula=fml,
        canonical_formula=fml,
        r1c1_formula=a1_to_r1c1(fml, 60, 9),
        formula_hash=compute_formula_hash(a1_to_r1c1(fml, 60, 9)),
        semantic_role=CellSemanticRole.FORMULA_CELL,
    )
    edges = DependencyDAGBuilder.build_edges([cell])
    prec_coords = {(e.precedent_sheet, e.precedent_coord) for e in edges}
    assert ("_01_CF", "I58") in prec_coords
    assert ("_01_CF", "I21") in prec_coords
    assert ("_01_CF", "I24") in prec_coords
    assert ("General", "C4") in prec_coords


def test_semantic_classifier_identifies_all_four_roles() -> None:
    """Verify semantic role classification for scenario inputs, solver outputs, formulas, and labels."""
    assert (
        CellSemanticClassifier.classify(
            "General", "C5", row_num=5, col_num=3, canonical_formula=None, numeric_value=0.95
        )
        == CellSemanticRole.SCENARIO_INPUT_CELL
    )
    assert (
        CellSemanticClassifier.classify(
            "_01_CF", "B16", row_num=16, col_num=2, canonical_formula=None, numeric_value=567.601
        )
        == CellSemanticRole.SCENARIO_INPUT_CELL
    )
    assert (
        CellSemanticClassifier.classify(
            "_01_CF", "E6", row_num=6, col_num=5, canonical_formula=None, numeric_value=0.12
        )
        == CellSemanticRole.SOLVER_OUTPUT_CELL
    )
    assert (
        CellSemanticClassifier.classify(
            "_01_CF", "G23", row_num=23, col_num=7, canonical_formula="=E23*$C$4", numeric_value=10.0
        )
        == CellSemanticRole.FORMULA_CELL
    )
    assert (
        CellSemanticClassifier.classify(
            "_01_CF", "A1", row_num=1, col_num=1, canonical_formula=None, numeric_value=None
        )
        == CellSemanticRole.LABEL_OR_STATIC_CELL
    )


def test_coordinate_shift_normalizer_identifies_insert_index() -> None:
    """Verify R1C1 row shift detector isolates inserted row index."""
    parent_cells = []
    child_cells = []

    for r in range(20, 40):
        coord = f"G{r}"
        f_a1 = f"=E{r}*$C$4"
        r1c1 = a1_to_r1c1(f_a1, cell_row=r, cell_col=7)
        parent_cells.append(
            ExtractedCellRecord(
                sheet_name="_01_CF",
                cell_coord=coord,
                row_num=r,
                col_num=7,
                col_letter="G",
                data_type="n",
                raw_formula=f_a1,
                canonical_formula=f_a1,
                r1c1_formula=r1c1,
                formula_hash=compute_formula_hash(r1c1),
                semantic_role=CellSemanticRole.FORMULA_CELL,
            )
        )

    for r in range(20, 40):
        target_r = r if r < 30 else r + 1
        coord = f"G{target_r}"
        f_a1 = f"=E{target_r}*$C$4"
        r1c1 = a1_to_r1c1(f_a1, cell_row=target_r, cell_col=7)
        child_cells.append(
            ExtractedCellRecord(
                sheet_name="_01_CF",
                cell_coord=coord,
                row_num=target_r,
                col_num=7,
                col_letter="G",
                data_type="n",
                raw_formula=f_a1,
                canonical_formula=f_a1,
                r1c1_formula=r1c1,
                formula_hash=compute_formula_hash(r1c1),
                semantic_role=CellSemanticRole.FORMULA_CELL,
            )
        )

    alignment = CoordinateShiftNormalizer.align_sheet("_01_CF", parent_cells, child_cells)
    assert alignment.inserted_rows == [30]
    assert alignment.parent_to_child_row[29] == 29
    assert alignment.parent_to_child_row[30] == 31
