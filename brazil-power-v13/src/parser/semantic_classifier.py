"""Deterministic 4-Role Cell Semantic Classifier (FR-B01)."""

from __future__ import annotations

from functools import lru_cache

from src.cli.extract_baseline_fixtures import expand_range_coords
from src.schemas.ast_dag import CellSemanticRole


@lru_cache(maxsize=1)
def get_solver_output_coordinates() -> frozenset[tuple[str, str]]:
    """Build exact lookup set of (sheet_name, cell_coord) written by the 38 solver routines."""
    coords: set[tuple[str, str]] = set()

    for i in range(1, 11):
        sname = f"_{i:02d}_CF"
        for c in expand_range_coords("E6:G12"):
            coords.add((sname, c))
        for c in expand_range_coords("C70:C79"):
            coords.add((sname, c))

    for c in expand_range_coords("G70:G79"):
        coords.add(("_01_CF", c))

    for i in (11, 12):
        sname = f"_{i:02d}_CF"
        for c in expand_range_coords("E6:G9"):
            coords.add((sname, c))

    for sname in ("_02_CF", "_04_CF"):
        for c in expand_range_coords("E70:N79"):
            coords.add((sname, c))

    for rng in ("G84:G93", "C99:L108", "U71:U82"):
        for c in expand_range_coords(rng):
            coords.add(("_05_CF", c))

    for rng in ("B88:F97", "C105:L114"):
        for c in expand_range_coords(rng):
            coords.add(("_06_CF", c))

    for c in expand_range_coords("B9:J31"):
        coords.add(("Output_3", c))
    coords.add(("Output_3", "B3"))

    for sname in ("_01_CF", "_07_CF", "_09_CF"):
        coords.add((sname, "C81"))
    coords.add(("_08_CF", "C105"))

    return frozenset(coords)


class CellSemanticClassifier:
    """Classifies every populated cell into one of 4 mutually exclusive semantic roles (FR-B01)."""

    SCENARIO_SHEETS = frozenset(
        {
            "General",
            "LT Capex",
            "LT Fuel",
            "LT CF",
            "_CAPEX 01",
            "CVU_GF",
            *{f"_{i:02d}_CF" for i in range(1, 13)},
        }
    )

    @classmethod
    def classify(
        cls,
        sheet_name: str,
        cell_coord: str,
        row_num: int,
        col_num: int,
        canonical_formula: str | None,
        numeric_value: float | None,
    ) -> CellSemanticRole:
        """Apply strict precedence: FORMULA_CELL > SOLVER_OUTPUT_CELL > SCENARIO_INPUT_CELL > LABEL_OR_STATIC_CELL."""
        if canonical_formula:
            return CellSemanticRole.FORMULA_CELL

        if (sheet_name, cell_coord) in get_solver_output_coordinates():
            return CellSemanticRole.SOLVER_OUTPUT_CELL

        if numeric_value is not None and sheet_name in cls.SCENARIO_SHEETS:
            if sheet_name == "General" and 5 <= row_num <= 40 and 3 <= col_num <= 14:
                return CellSemanticRole.SCENARIO_INPUT_CELL
            if sheet_name.endswith("_CF"):
                if (5 <= row_num <= 12 and 2 <= col_num <= 8) or (row_num == 16 and col_num == 2):
                    return CellSemanticRole.SCENARIO_INPUT_CELL
                if 66 <= row_num <= 80 and 2 <= col_num <= 8:
                    return CellSemanticRole.SCENARIO_INPUT_CELL
            if sheet_name in ("LT Capex", "LT Fuel", "LT CF") and 8 <= row_num <= 30 and col_num >= 2:
                return CellSemanticRole.SCENARIO_INPUT_CELL
            if sheet_name in ("_CAPEX 01", "CVU_GF") and col_num >= 2:
                return CellSemanticRole.SCENARIO_INPUT_CELL

        return CellSemanticRole.LABEL_OR_STATIC_CELL
