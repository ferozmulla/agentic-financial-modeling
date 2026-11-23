"""Path-safe pure-BigQuery OpenXML (.xlsx) synthesizer helpers template."""

from __future__ import annotations

import re
from pathlib import Path

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


def synthesize_workbook_from_snapshot(snapshot, export_dir: Path, filename: str = "Latinlr202409_export.xlsx") -> Path:
    """Synthesize a clean .xlsx workbook from in-memory Digital Twin snapshot with strict path containment."""
    import openpyxl

    out_path = resolve_contained_export_path(export_dir, filename)
    wb = openpyxl.Workbook()
    default_ws = wb.active
    for idx, (sheet_name, grid) in enumerate(snapshot.cells_by_sheet.items()):
        ws = default_ws if idx == 0 and default_ws is not None else wb.create_sheet(title=sheet_name[:31])
        ws.title = sheet_name[:31]
        for (r, c), cell in grid.items():
            if cell.numeric_value is not None:
                ws.cell(row=r, column=c, value=cell.numeric_value)
            elif cell.string_value is not None:
                ws.cell(row=r, column=c, value=cell.string_value)
    wb.save(out_path)
    return out_path
