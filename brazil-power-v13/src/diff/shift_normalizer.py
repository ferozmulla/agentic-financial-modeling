"""R1C1 Row/Column Alignment and Coordinate Shift Normalizer (FR-B07)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.schemas.ast_dag import ExtractedCellRecord

# Strips explicit absolute row numbers after R (e.g., R20C -> RC, R[1]C -> R[1]C) when comparing shifted rows
R1C1_ABS_ROW_RE = re.compile(r"R(\d+)C")


@dataclass
class SheetShiftAlignment:
    """Represents detected row/column insertions/deletions and parent->child row mapping on a sheet."""

    sheet_name: str
    inserted_rows: list[int] = field(default_factory=list)
    deleted_rows: list[int] = field(default_factory=list)
    inserted_cols: list[int] = field(default_factory=list)
    deleted_cols: list[int] = field(default_factory=list)
    parent_to_child_row: dict[int, int] = field(default_factory=dict)
    parent_to_child_col: dict[int, int] = field(default_factory=dict)


class CoordinateShiftNormalizer:
    """Aligns parent and child worksheet grids to isolate row/column insertions from formula edits."""

    @staticmethod
    def _row_signature(row_cells: list[ExtractedCellRecord]) -> str:
        """Build a coordinate-shift-invariant signature for a row using column letters and R1C1 patterns."""
        if not row_cells:
            return ""
        parts: list[str] = []
        for c in sorted(row_cells, key=lambda x: x.col_num):
            if c.r1c1_formula:
                norm_r1c1 = R1C1_ABS_ROW_RE.sub("R*C", c.r1c1_formula)
                parts.append(f"{c.col_letter}:F:{norm_r1c1}")
            elif c.raw_value is not None:
                parts.append(f"{c.col_letter}:V:{c.raw_value}")
        return "|".join(parts)

    @classmethod
    def align_sheet(
        cls,
        sheet_name: str,
        parent_cells: list[ExtractedCellRecord],
        child_cells: list[ExtractedCellRecord],
    ) -> SheetShiftAlignment:
        """Detect inserted/deleted rows between parent_cells and child_cells and build row alignment map."""
        alignment = SheetShiftAlignment(sheet_name=sheet_name)

        p_by_row: dict[int, list[ExtractedCellRecord]] = {}
        for c in parent_cells:
            p_by_row.setdefault(c.row_num, []).append(c)

        c_by_row: dict[int, list[ExtractedCellRecord]] = {}
        for c in child_cells:
            c_by_row.setdefault(c.row_num, []).append(c)

        max_p_row = max(p_by_row.keys(), default=0)
        max_c_row = max(c_by_row.keys(), default=0)

        p_sigs = {r: cls._row_signature(p_by_row.get(r, [])) for r in range(1, max_p_row + 1)}
        c_sigs = {r: cls._row_signature(c_by_row.get(r, [])) for r in range(1, max_c_row + 1)}

        # Default 1-to-1 column alignment
        max_col = max(
            max((c.col_num for c in parent_cells), default=0),
            max((c.col_num for c in child_cells), default=0),
        )
        for col_i in range(1, max_col + 1):
            alignment.parent_to_child_col[col_i] = col_i

        # If max row count is identical and signatures match 1-to-1, fast path
        if max_p_row == max_c_row and p_sigs == c_sigs:
            for r in range(1, max_p_row + 1):
                alignment.parent_to_child_row[r] = r
            return alignment

        # Detect single or multi-row insertions/deletions via pointer walk on non-empty signatures
        p_r = 1
        c_r = 1
        while p_r <= max_p_row and c_r <= max_c_row:
            if p_sigs.get(p_r, "") == c_sigs.get(c_r, ""):
                alignment.parent_to_child_row[p_r] = c_r
                p_r += 1
                c_r += 1
            elif (
                c_r + 1 <= max_c_row
                and p_sigs.get(p_r, "") != ""
                and p_sigs.get(p_r, "") == c_sigs.get(c_r + 1, "")
            ):
                # Row c_r was inserted in child!
                alignment.inserted_rows.append(c_r)
                c_r += 1
            elif (
                p_r + 1 <= max_p_row
                and c_sigs.get(c_r, "") != ""
                and p_sigs.get(p_r + 1, "") == c_sigs.get(c_r, "")
            ):
                # Row p_r was deleted from parent!
                alignment.deleted_rows.append(p_r)
                p_r += 1
            else:
                alignment.parent_to_child_row[p_r] = c_r
                p_r += 1
                c_r += 1

        while c_r <= max_c_row:
            if max_c_row > max_p_row and not alignment.inserted_rows:
                alignment.inserted_rows.append(c_r)
            c_r += 1

        while p_r <= max_p_row:
            if max_p_row > max_c_row and not alignment.deleted_rows:
                alignment.deleted_rows.append(p_r)
            p_r += 1

        return alignment

    @staticmethod
    def is_r1c1_equivalent_under_row_shift(
        parent_r1c1: str | None,
        child_r1c1: str | None,
        inserted_rows: list[int],
        deleted_rows: list[int],
    ) -> bool:
        """Return True if parent_r1c1 and child_r1c1 are identical after accounting for shifted absolute row refs."""
        if parent_r1c1 == child_r1c1:
            return True
        if not parent_r1c1 or not child_r1c1:
            return False
        if not inserted_rows and not deleted_rows:
            return parent_r1c1 == child_r1c1

        # Normalize absolute row references R<num>C that shifted due to row insertion/deletion
        norm_p = R1C1_ABS_ROW_RE.sub("R*C", parent_r1c1)
        norm_c = R1C1_ABS_ROW_RE.sub("R*C", child_r1c1)
        return norm_p == norm_c
