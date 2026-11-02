"""Canonical A1 shared-formula expansion and relative R1C1 translation (FR-B02)."""

from __future__ import annotations

import hashlib
import re

from src.cli.extract_baseline_fixtures import col_letter_to_index, index_to_col_letter

# Matches optional sheet prefix followed by ($?)([A-Z]{1,3})($?)(\d+) not followed by '('
A1_TOKEN_RE = re.compile(
    r"(?<![A-Z0-9_])(\$?)([A-Z]{1,3})(\$?)(\d+)(?!\s*\()"
)


def expand_shared_formula(
    master_formula: str,
    master_row: int,
    master_col: int,
    target_row: int,
    target_col: int,
) -> str:
    """Shift relative A1 references in master_formula by (target_row - master_row, target_col - master_col)."""
    d_row = target_row - master_row
    d_col = target_col - master_col
    if d_row == 0 and d_col == 0:
        return master_formula

    def _shift_match(m: re.Match[str]) -> str:
        col_abs, col_str, row_abs, row_str = m.group(1), m.group(2), m.group(3), m.group(4)
        col_idx = col_letter_to_index(col_str)
        if col_idx > 16384:
            return m.group(0)
        new_col_idx = col_idx if col_abs == "$" else max(1, col_idx + d_col)
        row_idx = int(row_str)
        new_row_idx = row_idx if row_abs == "$" else max(1, row_idx + d_row)
        return f"{col_abs}{index_to_col_letter(new_col_idx)}{row_abs}{new_row_idx}"

    return A1_TOKEN_RE.sub(_shift_match, master_formula)


def canonicalize_a1_formula(raw_formula: str | None) -> str | None:
    """Normalize leading '=' and whitespace in an A1 formula string."""
    if raw_formula is None:
        return None
    cleaned = raw_formula.strip()
    if not cleaned:
        return None
    if not cleaned.startswith("="):
        cleaned = "=" + cleaned
    return cleaned


def a1_to_r1c1(canonical_formula: str | None, cell_row: int, cell_col: int) -> str | None:
    """Translate canonical A1 formula at (cell_row, cell_col) into relative R1C1 notation."""
    if not canonical_formula:
        return None

    def _to_r1c1_token(m: re.Match[str]) -> str:
        col_abs, col_str, row_abs, row_str = m.group(1), m.group(2), m.group(3), m.group(4)
        col_idx = col_letter_to_index(col_str)
        if col_idx > 16384:
            return m.group(0)
        row_idx = int(row_str)

        if row_abs == "$":
            r_part = f"R{row_idx}"
        else:
            dr = row_idx - cell_row
            r_part = "R" if dr == 0 else f"R[{dr}]"

        if col_abs == "$":
            c_part = f"C{col_idx}"
        else:
            dc = col_idx - cell_col
            c_part = "C" if dc == 0 else f"C[{dc}]"

        return f"{r_part}{c_part}"

    return A1_TOKEN_RE.sub(_to_r1c1_token, canonical_formula)


def compute_formula_hash(r1c1_or_canonical: str | None) -> str | None:
    """Compute deterministic SHA-256 hex digest of a normalized formula."""
    if not r1c1_or_canonical:
        return None
    return hashlib.sha256(r1c1_or_canonical.encode("utf-8")).hexdigest()
