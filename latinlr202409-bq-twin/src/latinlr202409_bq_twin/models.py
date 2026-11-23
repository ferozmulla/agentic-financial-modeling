"""Domain models and coordinate helpers for `latinlr202409-bq-twin`."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

_COORD_RE = re.compile(r"^\$?([A-Za-z]{1,3})\$?(\d+)$")

DeltaKind = Literal["DRIVER_OVERRIDE", "PINNED_PRICE_OVERRIDE", "SOLVED_OUTPUT", "BQML_FORECAST", "TOMBSTONE"]


def col_letter_to_index(col_str: str) -> int:
    idx = 0
    for ch in col_str.strip().upper():
        idx = idx * 26 + (ord(ch) - ord("A") + 1)
    return idx


def index_to_col_letter(col_idx: int) -> str:
    if col_idx < 1:
        raise ValueError(f"Column index must be >= 1, got {col_idx}")
    chars: list[str] = []
    n = col_idx
    while n > 0:
        n, rem = divmod(n - 1, 26)
        chars.append(chr(ord("A") + rem))
    return "".join(reversed(chars))


def split_a1_coord(coord: str) -> tuple[int, int]:
    m = _COORD_RE.match(coord.strip())
    if not m:
        raise ValueError(f"Invalid A1 coordinate: {coord!r}")
    return int(m.group(2)), col_letter_to_index(m.group(1))


@dataclass(frozen=True)
class TwinCell:
    sheet_name: str
    cell_coord: str
    row_num: int
    col_num: int
    data_type: str
    numeric_value: float | None
    string_value: str | None
    raw_formula: str | None
    has_external_link: bool
    style_id: int
    semantic_role: str


@dataclass
class BaselineSnapshot:
    workbook_id: str
    version_id: str
    cells_by_sheet: dict[str, dict[tuple[int, int], TwinCell]] = field(default_factory=dict)
    calc_properties: dict[str, Any] = field(default_factory=dict)
