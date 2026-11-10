"""Domain models, coordinate helpers, and Digital Twin snapshot structures for `eulr-bq-twin`."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

_COORD_RE = re.compile(r"^\$?([A-Za-z]{1,3})\$?(\d+)$")

DeltaKind = Literal[
    "DRIVER_OVERRIDE",
    "PINNED_PRICE_OVERRIDE",
    "SOLVED_OUTPUT",
    "BQML_FORECAST",
    "TOMBSTONE",
]
UpstreamMode = Literal["baseline_cached", "peer_synced"]
EuEtsMode = Literal[
    "cost_and_allocation",
    "variable_cost_only",
    "carbon_off",
]


def col_letter_to_index(col_str: str) -> int:
    """Convert 1-indexed Excel column letters ('A' -> 1, 'AT' -> 46) to integer."""
    idx = 0
    for ch in col_str.strip().upper():
        if not ("A" <= ch <= "Z"):
            raise ValueError(f"Invalid column letter: {col_str!r}")
        idx = idx * 26 + (ord(ch) - ord("A") + 1)
    return idx


def index_to_col_letter(col_idx: int) -> str:
    """Convert 1-indexed column integer (1 -> 'A', 46 -> 'AT') to Excel column letters."""
    if col_idx < 1:
        raise ValueError(f"Column index must be >= 1, got {col_idx}")
    chars: list[str] = []
    n = col_idx
    while n > 0:
        n, rem = divmod(n - 1, 26)
        chars.append(chr(ord("A") + rem))
    return "".join(reversed(chars))


def split_a1_coord(coord: str) -> tuple[int, int]:
    """Split 'AT15' or '$AT$15' into 1-indexed (row_num, col_num)."""
    m = _COORD_RE.match(coord.strip())
    if not m:
        raise ValueError(f"Invalid A1 coordinate: {coord!r}")
    return int(m.group(2)), col_letter_to_index(m.group(1))


def split_sheet_cell(sheet_cell: str) -> tuple[str, str, int, int]:
    """Parse \"'NWE Cif'!AU122\" or 'KeyInputs!AT15' into (sheet_name, clean_coord, row, col)."""
    if "!" not in sheet_cell:
        raise ValueError(f"Expected 'Sheet!Cell' coordinate, got {sheet_cell!r}")
    sh_part, c_part = sheet_cell.split("!", 1)
    sheet_name = sh_part.strip().strip("'")
    row_num, col_num = split_a1_coord(c_part)
    clean_coord = f"{index_to_col_letter(col_num)}{row_num}"
    return sheet_name, clean_coord, row_num, col_num


@dataclass(frozen=True)
class WorksheetMeta:
    sheet_index: int
    sheet_name: str
    visibility: str
    tab_color_rgb: str | None
    max_row: int
    max_col: int
    merged_ranges: list[str]
    col_widths: dict[str, float]
    row_heights: dict[int, float]
    freeze_panes_coord: str | None
    sheet_view: dict[str, Any]


@dataclass(frozen=True)
class StyleMeta:
    style_id: int
    number_format: str | None
    font: dict[str, Any]
    fill: dict[str, Any]
    border: dict[str, Any]
    alignment: dict[str, Any]


@dataclass
class TwinCell:
    sheet_name: str
    cell_coord: str
    row_num: int
    col_num: int
    data_type: str  # NUMERIC | STRING | FORMULA | BOOL | ERROR | MERGED_STYLE
    numeric_value: float | None
    string_value: str | None
    raw_formula: str | None
    is_array_cse: bool
    has_external_link: bool
    style_id: int
    semantic_role: str


@dataclass(frozen=True)
class ExternalLinkCell:
    vintage_tag: str
    link_health_tier: str
    external_link_idx: str
    sharepoint_url: str
    external_workbook_name: str
    source_sheet: str | None
    source_cell_a1: str | None
    target_sheet: str
    target_coord: str
    target_row: int
    target_col: int
    baseline_cached_value: float
    peer_live_value: float | None
    is_peer_updated: bool
    raw_formula: str


@dataclass(frozen=True)
class SessionCellDelta:
    sheet_name: str
    cell_coord: str
    row_num: int
    col_num: int
    delta_kind: DeltaKind
    numeric_value: float | None
    string_value: str | None
    source_tool: str


@dataclass
class EulrBaselineSnapshot:
    """In-memory hydrated baseline of the 19-tab EULR Digital Twin from BigQuery."""

    workbook_id: str
    version_id: str
    worksheets: dict[str, WorksheetMeta]
    styles: dict[int, StyleMeta]
    cells_by_sheet: dict[str, dict[tuple[int, int], TwinCell]]
    external_links: dict[tuple[str, int, int], ExternalLinkCell]
    named_ranges: list[dict[str, Any]] = field(default_factory=list)
    calc_properties: dict[str, Any] = field(default_factory=dict)
