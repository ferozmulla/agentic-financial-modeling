"""Path-safe pure-BigQuery OpenXML (.xlsx) synthesizer helpers."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
import openpyxl
from openpyxl.styles import PatternFill

from .xlsx_compiler import split_a1

_SAFE_FILENAME_RE = re.compile(r"^[A-Za-z0-9._\-]+$")


def sanitize_export_filename(raw_name: str, suffix: str = ".xlsx") -> str:
    """Sanitize export filename to prevent path traversal and header injection."""
    base = Path(raw_name).name.strip()
    stem = re.sub(r"[^A-Za-z0-9._\-]+", "_", base)
    if not stem.lower().endswith(suffix):
        stem = f"{stem}{suffix}"
    if not _SAFE_FILENAME_RE.match(stem) or ".." in stem:
        raise ValueError(f"Invalid export filename: {raw_name!r}")
    return stem


def resolve_contained_export_path(export_dir: Path, filename: str) -> Path:
    """Verify resolved target path stays strictly inside `export_dir`."""
    safe_name = sanitize_export_filename(filename)
    root = export_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    candidate = (root / safe_name).resolve()
    if candidate.parent != root:
        raise ValueError("Export path escaped export directory")
    return candidate


def synthesize_workbook(
    seed_path_str: str,
    output_path: Path,
    session_id: str,
    store_or_deltas: Any,  # Either BaseDigitalTwinStore or a dict of deltas directly
) -> None:
    """Synthesize workbook by overlaying overrides onto the seed workbook and saving."""
    seed_path = Path(seed_path_str).expanduser().resolve()
    if not seed_path.is_file():
        raise FileNotFoundError(f"Seed workbook not found at: {seed_path_str}")

    # Load workbook using openpyxl
    wb = openpyxl.load_workbook(seed_path)

    # Fetch active overrides
    if hasattr(store_or_deltas, "get_session_deltas"):
        overrides = store_or_deltas.get_session_deltas(session_id)
    elif isinstance(store_or_deltas, dict):
        overrides = store_or_deltas
    else:
        overrides = {}

    # Overrides color highlight fill: Amber #FDE68A
    amber_fill = PatternFill(start_color="FDE68A", end_color="FDE68A", fill_type="solid")

    # Apply overrides
    for (sheet_name, cell_coord), delta in overrides.items():
        if sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            # Write overridden value
            val = delta.get("numeric_value") if delta.get("numeric_value") is not None else delta.get("string_value")
            ws[cell_coord] = val
            # Color overridden cell
            ws[cell_coord].fill = amber_fill

    # Save to safe destination
    wb.save(output_path)
