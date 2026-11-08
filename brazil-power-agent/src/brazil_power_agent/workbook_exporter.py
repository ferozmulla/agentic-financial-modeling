"""Full 22-Tab Excel (.xlsx) and Google Sheets Workbook Cloner for Brazil Power v13."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import openpyxl
from openpyxl.cell.cell import MergedCell

from brazil_power_agent.session_store import (
    DEFAULT_SEED_WORKBOOK_PATH,
    BrazilPowerSessionManager,
    col_letter_to_index,
    index_to_col_letter,
    split_coord,
)

GOLDEN_GOOGLE_SHEET_ID = "1apbos5xVpK4yBLiRFxQqAEyPVNkkYQ2ZvgAASibYYJI"
DEFAULT_EXPORT_DIR = Path.home() / ".gemini" / "jetski" / "exports"
DEFAULT_XLSX_FILENAME = "Brazil_TT_v13_Scenario_Export.xlsx"
DEFAULT_SHEET_TITLE = "Brazil Power v13 — Gemini Scenario Export (22 Tabs)"

EXPECTED_22_TABS: tuple[str, ...] = (
    "Version Control",
    "General",
    "Output_1",
    "Output_2",
    "Output_3",
    "_01_CF",
    "_02_CF",
    "_03_CF",
    "_04_CF",
    "_05_CF",
    "_06_CF",
    "_07_CF",
    "_08_CF",
    "_09_CF",
    "_10_CF",
    "_11_CF",
    "_12_CF",
    "_CAPEX 01",
    "CVU_GF",
    "LT Capex",
    "LT Fuel",
    "LT CF",
)


def deduplicate_range_updates(
    range_updates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Deduplicate 2D cell range updates by (sheet, range), preserving the latest update for each range."""
    deduped: dict[tuple[str, str], dict[str, Any]] = {}
    for item in range_updates:
        sheet = str(item.get("sheet", "")).strip()
        cell_range = str(item.get("range", "")).strip()
        if not sheet or not cell_range:
            continue
        key = (sheet, cell_range)
        if key in deduped:
            del deduped[key]
        deduped[key] = {
            "sheet": sheet,
            "range": cell_range,
            "values": item.get("values", []),
        }
    return list(deduped.values())


def expand_2d_range_to_cell_map(
    sheet: str,
    cell_range: str,
    values: list[list[Any]],
) -> dict[str, Any]:
    """Expand a 2D rectangular range update ('B9:J31' or 'B3') into {'Sheet!Coord': value} entries."""
    clean_range = cell_range.replace("$", "").strip()
    start_c, end_c = clean_range.split(":", 1) if ":" in clean_range else (clean_range, clean_range)
    c1_str, r1 = split_coord(start_c)
    c2_str, r2 = split_coord(end_c)
    c1, c2 = col_letter_to_index(c1_str), col_letter_to_index(c2_str)

    flat: dict[str, Any] = {}
    for r_offset, row_num in enumerate(range(r1, r2 + 1)):
        if r_offset >= len(values):
            break
        row_vals = values[r_offset]
        for c_offset, col_idx in enumerate(range(c1, c2 + 1)):
            if c_offset >= len(row_vals):
                break
            val = row_vals[c_offset]
            if val is None:
                continue
            coord = f"{index_to_col_letter(col_idx)}{row_num}"
            flat[f"{sheet}!{coord}"] = val
    return flat


def collect_session_cell_writes(
    session_mgr: BrazilPowerSessionManager,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """Collect deterministic per-sheet cell writes and deduplicated 2D range updates from session state.

    Precedence order (later layers overwrite earlier layers):
    1. Deduplicated 2D macro/BQML range updates (`cell_range_updates`)
    2. Flat solved macro outputs (`solved_outputs`)
    3. `session_mgr.get_all_cell_writes()` (supports both flat `'Sheet!Coord'` and nested `{sheet: {coord: val}}`)
    4. User input cell overrides (`cell_overrides`) — highest precedence
    """
    deduped_ranges = deduplicate_range_updates(getattr(session_mgr, "cell_range_updates", []))
    flat_writes: dict[str, Any] = {}

    for ru in deduped_ranges:
        flat_writes.update(
            expand_2d_range_to_cell_map(
                sheet=ru["sheet"],
                cell_range=ru["range"],
                values=ru["values"],
            )
        )

    for full_coord, val in getattr(session_mgr, "solved_outputs", {}).items():
        if val is not None:
            flat_writes[full_coord] = val

    if hasattr(session_mgr, "get_all_cell_writes"):
        raw_all = session_mgr.get_all_cell_writes()
        if isinstance(raw_all, dict):
            for k, v in raw_all.items():
                if isinstance(v, dict):
                    for sub_coord, sub_val in v.items():
                        if sub_val is not None:
                            flat_writes[f"{k}!{sub_coord}"] = sub_val
                elif v is not None:
                    flat_writes[k] = v

    for full_coord, val in getattr(session_mgr, "cell_overrides", {}).items():
        if val is not None:
            flat_writes[full_coord] = val

    writes_by_sheet: dict[str, dict[str, Any]] = {}
    for full_coord, val in flat_writes.items():
        sheet_name, coord = full_coord.split("!", 1) if "!" in full_coord else ("General", full_coord)
        clean_coord = coord.replace("$", "").strip().upper()
        writes_by_sheet.setdefault(sheet_name, {})[clean_coord] = val

    return writes_by_sheet, deduped_ranges


def _format_a1_sheet_range(sheet_name: str, a1_ref: str) -> str:
    """Format A1 sheet qualifier for Google Sheets API, quoting sheet names with spaces."""
    if " " in sheet_name or "-" in sheet_name:
        escaped = sheet_name.replace("'", "''")
        return f"'{escaped}'!{a1_ref}"
    return f"{sheet_name}!{a1_ref}"


def build_google_sheets_batch_data(
    writes_by_sheet: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build Google Sheets API v4 `ValueRange` entries for `spreadsheets.values.batchUpdate`."""
    value_ranges: list[dict[str, Any]] = []
    for sheet_name in sorted(writes_by_sheet.keys()):
        coord_map = writes_by_sheet[sheet_name]
        for coord in sorted(coord_map.keys(), key=lambda c: (split_coord(c)[1], col_letter_to_index(split_coord(c)[0]))):
            value_ranges.append(
                {
                    "range": _format_a1_sheet_range(sheet_name, coord),
                    "values": [[coord_map[coord]]],
                }
            )
    return value_ranges


def _build_default_google_services() -> tuple[Any, Any]:
    """Initialize Google Drive v3 and Google Sheets v4 API clients using Application Default Credentials."""
    import google.auth
    from googleapiclient.discovery import build

    scopes = [
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/spreadsheets",
    ]
    creds, _ = google.auth.default(scopes=scopes)
    drive_service = build("drive", "v3", credentials=creds, cache_discovery=False)
    sheets_service = build("sheets", "v4", credentials=creds, cache_discovery=False)
    return drive_service, sheets_service


def _export_to_xlsx(
    seed_workbook_path: Path,
    output_path: Path,
    writes_by_sheet: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Clone the 22-tab seed .xlsm into a standard .xlsx preserving all tabs, styles, and formulas."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    wb = openpyxl.load_workbook(seed_workbook_path, keep_vba=False, data_only=False)

    applied_cells = 0
    modified_sheets: list[str] = []

    for sheet_name, coord_map in writes_by_sheet.items():
        if sheet_name not in wb.sheetnames:
            continue
        ws = wb[sheet_name]
        sheet_touched = False
        for coord, val in coord_map.items():
            cell = ws[coord]
            if isinstance(cell, MergedCell):
                continue
            cell.value = val
            applied_cells += 1
            sheet_touched = True
        if sheet_touched:
            modified_sheets.append(sheet_name)

    wb.save(output_path)
    sheet_names = list(wb.sheetnames)
    wb.close()

    return {
        "xlsx_path": str(output_path),
        "sheet_names": sheet_names,
        "sheet_count": len(sheet_names),
        "applied_cell_count": applied_cells,
        "modified_sheets": sorted(modified_sheets),
    }


def _export_to_google_sheets(
    writes_by_sheet: dict[str, dict[str, Any]],
    sheet_title: str,
    golden_sheet_id: str = GOLDEN_GOOGLE_SHEET_ID,
    drive_service: Any | None = None,
    sheets_service: Any | None = None,
) -> dict[str, Any]:
    """Clone the 22-tab Golden Google Sheet in Drive and batch-apply all session edits and solved outputs."""
    if drive_service is None or sheets_service is None:
        default_drive, default_sheets = _build_default_google_services()
        drive_service = drive_service or default_drive
        sheets_service = sheets_service or default_sheets

    copied_file = (
        drive_service.files()
        .copy(
            fileId=golden_sheet_id,
            body={"name": sheet_title},
            supportsAllDrives=True,
        )
        .execute()
    )
    new_spreadsheet_id = str(copied_file["id"])
    value_ranges = build_google_sheets_batch_data(writes_by_sheet)

    if value_ranges:
        sheets_service.spreadsheets().values().batchUpdate(
            spreadsheetId=new_spreadsheet_id,
            body={
                "valueInputOption": "USER_ENTERED",
                "data": value_ranges,
            },
        ).execute()

    return {
        "golden_sheet_id": golden_sheet_id,
        "spreadsheet_id": new_spreadsheet_id,
        "spreadsheet_url": f"https://docs.google.com/spreadsheets/d/{new_spreadsheet_id}/edit",
        "sheet_title": sheet_title,
        "value_ranges_updated": len(value_ranges),
    }


def export_full_22tab_workbook(
    session_mgr: BrazilPowerSessionManager | None = None,
    export_format: str = "xlsx",
    output_dir: Path | str | None = None,
    filename: str | None = None,
    sheet_title: str | None = None,
    golden_sheet_id: str = GOLDEN_GOOGLE_SHEET_ID,
    drive_service: Any | None = None,
    sheets_service: Any | None = None,
) -> dict[str, Any]:
    """Export the full 22-tab Brazil Power v13 model with all session edits and solved outputs applied.

    Supports:
    - `export_format="xlsx"`: Clones `2023-11-27-Brazil_TT_v13_RJEB.xlsm` via `openpyxl(..., keep_vba=False)`
      preserving all 22 worksheets, styles, number formats, borders, column widths, merged cells, and formulas.
    - `export_format="google_sheets"`: Copies the 22-tab Golden Google Sheet (`1apbos5xVpK4yBLiRFxQqAEyPVNkkYQ2ZvgAASibYYJI`)
      in Google Drive and applies all modified inputs and solved outputs via `spreadsheets.values.batchUpdate`.
    - `export_format="both"`: Produces both the `.xlsx` file and the cloned Google Sheet.
    """
    mgr = session_mgr if session_mgr is not None else BrazilPowerSessionManager()
    fmt = export_format.strip().lower()
    if fmt not in ("xlsx", "excel", "google_sheets", "sheets", "gsheets", "both"):
        raise ValueError(
            f"Unsupported export_format '{export_format}'. Expected 'xlsx', 'google_sheets', or 'both'."
        )

    do_xlsx = fmt in ("xlsx", "excel", "both")
    do_gsheets = fmt in ("google_sheets", "sheets", "gsheets", "both")

    seed_path = Path(getattr(mgr, "seed_workbook_path", DEFAULT_SEED_WORKBOOK_PATH))
    writes_by_sheet, deduped_ranges = collect_session_cell_writes(mgr)
    total_cells = sum(len(cmap) for cmap in writes_by_sheet.values())

    result: dict[str, Any] = {
        "export_format": fmt,
        "xlsx_path": None,
        "spreadsheet_id": None,
        "spreadsheet_url": None,
        "golden_sheet_id": golden_sheet_id,
        "sheet_title": sheet_title or DEFAULT_SHEET_TITLE,
        "sheet_names": list(EXPECTED_22_TABS),
        "sheet_count": len(EXPECTED_22_TABS),
        "tabs_preserved": len(EXPECTED_22_TABS),
        "applied_cell_count": total_cells,
        "applied_range_count": len(deduped_ranges),
        "modified_sheets": sorted(writes_by_sheet.keys()),
        "applied_overrides": dict(getattr(mgr, "cell_overrides", {})),
    }

    summary_lines = [
        "### Full 22-Tab Brazil Power Workbook Export",
        f"- **Preserved Worksheets**: `{result['tabs_preserved']}` tabs (`Version Control`, `General`, `Output_1..3`, `_01_CF.._12_CF`, `_CAPEX 01`, `CVU_GF`, `LT Capex`, `LT Fuel`, `LT CF`)",
        f"- **Session Assumption Overrides Applied**: `{len(result['applied_overrides'])}`",
        f"- **Total Modified / Solved Cells Written**: `{total_cells}` across `{len(writes_by_sheet)}` tab(s) ({', '.join(f'`{s}`' for s in sorted(writes_by_sheet.keys())) or 'baseline'})",
    ]

    if do_xlsx:
        resolved_dir = Path(output_dir) if output_dir is not None else DEFAULT_EXPORT_DIR
        resolved_name = filename or DEFAULT_XLSX_FILENAME
        if not resolved_name.lower().endswith(".xlsx"):
            resolved_name = f"{resolved_name}.xlsx"
        xlsx_info = _export_to_xlsx(
            seed_workbook_path=seed_path,
            output_path=resolved_dir / resolved_name,
            writes_by_sheet=writes_by_sheet,
        )
        result.update(xlsx_info)
        result["tabs_preserved"] = xlsx_info["sheet_count"]
        summary_lines.append(f"- **Excel (`.xlsx`) File**: `{result['xlsx_path']}`")

    if do_gsheets:
        gs_info = _export_to_google_sheets(
            writes_by_sheet=writes_by_sheet,
            sheet_title=sheet_title or DEFAULT_SHEET_TITLE,
            golden_sheet_id=golden_sheet_id,
            drive_service=drive_service,
            sheets_service=sheets_service,
        )
        result.update(gs_info)
        summary_lines.append(
            f"- **Cloned Google Sheet**: [{result['sheet_title']}]({result['spreadsheet_url']}) (`{result['spreadsheet_id']}`)"
        )

    result["summary_md"] = "\n".join(summary_lines)
    return result
