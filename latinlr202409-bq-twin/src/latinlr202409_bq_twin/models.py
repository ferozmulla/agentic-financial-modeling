"""Data models for cell, style, delta and audit events in Latinlr202409 Digital Twin."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class CellModel:
    sheet_name: str
    cell_coord: str
    row_num: int
    col_num: int
    data_type: str
    numeric_value: float | None = None
    string_value: str | None = None
    raw_formula: str | None = None
    is_array_cse: bool = False
    has_external_link: bool = False
    style_id: int = 0
    semantic_role: str = "INPUT"


@dataclass
class StyleModel:
    style_id: int
    number_format: str | None = None
    font_json: str = "{}"
    fill_json: str = "{}"
    border_json: str = "{}"
    alignment_json: str = "{}"


@dataclass
class DeltaModel:
    session_id: str
    sheet_name: str
    cell_coord: str
    row_num: int
    col_num: int
    delta_kind: str
    numeric_value: float | None = None
    string_value: str | None = None
    source_tool: str = "user"
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class AuditEventModel:
    event_id: str
    session_id: str
    what_sheet: str
    what_coord: str
    what_change_type: str
    before_value: str | None = None
    after_value: str | None = None
    who_principal: str = "analyst"
    when_event_utc: datetime = field(default_factory=datetime.utcnow)
    why_context: str = ""
