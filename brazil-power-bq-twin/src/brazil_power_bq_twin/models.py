"""Domain data models and A1 coordinate helpers for the BigQuery Digital Twin."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

_A1_RE = re.compile(r"^\$?([A-Za-z]{1,3})\$?([1-9][0-9]{0,6})$")


def split_a1_coord(coord: str) -> tuple[str, int]:
    """Split an A1 cell coordinate ('C20' or '$C$20') into ('C', 20)."""
    match = _A1_RE.match(coord.strip())
    if not match:
        raise ValueError(f"Invalid A1 cell coordinate: '{coord}'")
    return match.group(1).upper(), int(match.group(2))


def col_letter_to_index(col_letter: str) -> int:
    """Convert 1-based Excel column letters ('A'->1, 'Z'->26, 'AA'->27, 'AN'->40) to integer."""
    idx = 0
    for ch in col_letter.strip().upper():
        if not ("A" <= ch <= "Z"):
            raise ValueError(f"Invalid Excel column letter: '{col_letter}'")
        idx = idx * 26 + (ord(ch) - ord("A") + 1)
    return idx


def index_to_col_letter(col_index: int) -> str:
    """Convert 1-based Excel column index (1->'A', 40->'AN') to column letters."""
    if col_index < 1:
        raise ValueError(f"Column index must be >= 1, got {col_index}")
    chars: list[str] = []
    cur = col_index
    while cur > 0:
        cur, rem = divmod(cur - 1, 26)
        chars.append(chr(ord("A") + rem))
    return "".join(reversed(chars))


@dataclass(frozen=True)
class StyleRecord:
    """Deduplicated Excel cell formatting specification."""

    style_id: int
    number_format: str = "General"
    font: dict[str, Any] = field(default_factory=dict)
    fill: dict[str, Any] = field(default_factory=dict)
    border: dict[str, Any] = field(default_factory=dict)
    alignment: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WorksheetRecord:
    """Worksheet structural and layout metadata."""

    sheet_index: int
    sheet_name: str
    visibility: str = "visible"
    tab_color_rgb: str | None = None
    merged_ranges: tuple[str, ...] = ()
    col_widths: dict[str, float] = field(default_factory=dict)
    row_heights: dict[str, float] = field(default_factory=dict)
    freeze_panes_coord: str | None = None


@dataclass(frozen=True)
class CellRecord:
    """Single baseline spreadsheet cell stored in `dt_cells`."""

    sheet_name: str
    cell_coord: str
    row_num: int
    col_num: int
    data_type: str  # 'n' | 's' | 'b' | 'f'
    numeric_value: float | None = None
    string_value: str | None = None
    raw_formula: str | None = None  # Formula without leading '='
    style_id: int = 0
    semantic_role: str = "INPUT"  # INPUT | FORMULA | LABEL | OUTPUT

    @property
    def effective_baseline_value(self) -> Any:
        """Return the cached scalar value used during quantitative calculation."""
        if self.numeric_value is not None:
            return self.numeric_value
        return self.string_value


@dataclass(frozen=True)
class CellDelta:
    """Sparse per-session cell mutation stored in `dt_scenario_deltas`."""

    sheet_name: str
    cell_coord: str
    row_num: int
    col_num: int
    delta_kind: str  # USER_OVERRIDE | SOLVED_OUTPUT | BQML_REFRESH | RESET_TOMBSTONE
    numeric_value: float | None = None
    string_value: str | None = None
    source_tool: str = "manual"
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def value(self) -> Any:
        if self.numeric_value is not None:
            return self.numeric_value
        return self.string_value


@dataclass(frozen=True)
class AuditRow:
    """Immutable 4-Ws audit record stored in `dt_audit_events`."""

    event_id: str
    session_id: str
    what_sheet: str
    what_coord: str
    what_change_type: str
    before_value: str | None
    after_value: str | None
    who_principal: str
    when_event_utc: str
    why_context: str


@dataclass
class BaselineTwinSnapshot:
    """Immutable in-memory representation of a workbook version hydrated from BigQuery."""

    workbook_id: str
    version_id: str
    version_label: str
    worksheets: list[WorksheetRecord]
    styles: dict[int, StyleRecord]
    cells_by_sheet: dict[str, dict[str, CellRecord]]
    named_ranges: list[dict[str, Any]] = field(default_factory=list)
    solver_parameters: dict[str, Any] = field(default_factory=dict)

    def get_cell(self, sheet_name: str, coord: str) -> CellRecord | None:
        clean_coord = coord.replace("$", "").strip().upper()
        return self.cells_by_sheet.get(sheet_name, {}).get(clean_coord)


@dataclass
class SessionOverlay:
    """Active sparse delta overlay for a scenario `session_id`."""

    session_id: str
    workbook_id: str
    base_version_id: str
    deltas_by_sheet: dict[str, dict[str, CellDelta]] = field(default_factory=dict)

    def get_delta(self, sheet_name: str, coord: str) -> CellDelta | None:
        clean_coord = coord.replace("$", "").strip().upper()
        delta = self.deltas_by_sheet.get(sheet_name, {}).get(clean_coord)
        if delta is not None and delta.delta_kind == "RESET_TOMBSTONE":
            return None
        return delta

    def user_overrides_flat(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for sheet_name, cmap in sorted(self.deltas_by_sheet.items()):
            for coord, delta in sorted(cmap.items()):
                if delta.delta_kind == "USER_OVERRIDE":
                    out[f"{sheet_name}!{coord}"] = delta.value
        return out

    def all_effective_deltas_flat(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for sheet_name, cmap in sorted(self.deltas_by_sheet.items()):
            for coord, delta in sorted(cmap.items()):
                if delta.delta_kind != "RESET_TOMBSTONE":
                    out[f"{sheet_name}!{coord}"] = delta.value
        return out
