"""Pure Database-to-22-Tab `.xlsx` and Google Sheets Synthesizer (Zero Template Workbook Used)."""

from __future__ import annotations

import io
import logging
import os
import re
from pathlib import Path
from typing import Any

import openpyxl
from openpyxl.styles import Alignment, Border, Color, Font, PatternFill, Side
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.worksheet.dimensions import ColumnDimension

from brazil_power_bq_twin.bq_store import DigitalTwinStore
from brazil_power_bq_twin.config import get_twin_settings
from brazil_power_bq_twin.models import BaselineTwinSnapshot, SessionOverlay, StyleRecord

logger = logging.getLogger(__name__)

_SAFE_FILENAME_RE = re.compile(r"^[A-Za-z0-9_.\-]+$")


def sanitize_filename(raw_name: str | None, expected_ext: str) -> str:
    """Validate and sanitize a deliverable filename against path traversal."""
    ext = expected_ext if expected_ext.startswith(".") else f".{expected_ext}"
    candidate = (raw_name or f"Brazil_v13_BQ_Twin_Export{ext}").strip()
    if "/" in candidate or "\\" in candidate or ".." in candidate:
        raise ValueError(f"Unsafe filename '{raw_name}'. Path separators and '..' are prohibited.")
    if not candidate.lower().endswith(ext.lower()):
        candidate = f"{candidate}{ext}"
    if not _SAFE_FILENAME_RE.match(candidate):
        raise ValueError(f"Unsafe filename '{candidate}'. Only alphanumeric, '_', '-', and '.' are permitted.")
    return candidate


def _normalize_argb(val: Any) -> str | None:
    if not isinstance(val, str):
        return None
    up = val.strip().upper()
    if not up or up == "00000000":
        return None
    if len(up) in (6, 8) and all(c in "0123456789ABCDEF" for c in up):
        return f"FF{up[-6:]}"
    return None


def _hydrate_openpyxl_style(style_rec: StyleRecord) -> tuple[str, Font, PatternFill | None, Border | None, Alignment | None]:
    f = style_rec.font or {}
    f_rgb = _normalize_argb(f.get("color_rgb"))
    font_color = Color(rgb=f_rgb) if f_rgb else None
    font = Font(
        name=f.get("name", "Calibri"),
        size=float(f.get("size", 11.0)),
        bold=bool(f.get("bold", False)),
        italic=bool(f.get("italic", False)),
        color=font_color,
    )

    fl = style_rec.fill or {}
    fill: PatternFill | None = None
    sc = _normalize_argb(fl.get("start_color_rgb"))
    ec = _normalize_argb(fl.get("end_color_rgb")) or sc
    if fl.get("fill_type") and sc is not None:
        fill = PatternFill(
            fill_type=fl["fill_type"],
            start_color=sc,
            end_color=ec,
        )

    bd = style_rec.border or {}
    border: Border | None = None
    if bd:
        sides: dict[str, Side] = {}
        for s_name in ("left", "right", "top", "bottom"):
            if s_name in bd and bd[s_name].get("style"):
                c_rgb = _normalize_argb(bd[s_name].get("color_rgb"))
                sides[s_name] = Side(style=bd[s_name]["style"], color=c_rgb)
        if sides:
            border = Border(**sides)

    al = style_rec.alignment or {}
    alignment: Alignment | None = None
    if al:
        alignment = Alignment(
            horizontal=al.get("horizontal"),
            vertical=al.get("vertical"),
            wrap_text=bool(al.get("wrap_text", False)),
        )

    return style_rec.number_format or "General", font, fill, border, alignment


def synthesize_22tab_xlsx_bytes(
    snapshot: BaselineTwinSnapshot,
    overlay: SessionOverlay,
) -> tuple[bytes, dict[str, Any]]:
    """Construct a complete 22-tab `.xlsx` workbook purely from `BaselineTwinSnapshot` + `SessionOverlay`."""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    hydrated_styles = {
        sid: _hydrate_openpyxl_style(srec)
        for sid, srec in snapshot.styles.items()
    }

    total_written = 0
    overlaid_cells = 0

    for ws_rec in sorted(snapshot.worksheets, key=lambda w: w.sheet_index):
        ws = wb.create_sheet(title=ws_rec.sheet_name)
        ws.sheet_state = ws_rec.visibility
        if ws_rec.tab_color_rgb:
            ws.sheet_properties.tabColor = ws_rec.tab_color_rgb
        if ws_rec.freeze_panes_coord:
            ws.freeze_panes = ws_rec.freeze_panes_coord

        for col_let, width_val in ws_rec.col_widths.items():
            ws.column_dimensions[col_let].width = width_val
        for row_str, height_val in ws_rec.row_heights.items():
            if row_str.isdigit():
                ws.row_dimensions[int(row_str)].height = height_val

        sv = ws_rec.sheet_view or {}
        if "show_grid_lines" in sv:
            ws.sheet_view.showGridLines = bool(sv["show_grid_lines"])
        if sv.get("zoom_scale"):
            ws.sheet_view.zoomScale = int(sv["zoom_scale"])
        for hid_col in sv.get("hidden_cols", []):
            ws.column_dimensions[str(hid_col)].hidden = True
        for hid_row in sv.get("hidden_rows", []):
            ws.row_dimensions[int(hid_row)].hidden = True
        for col_let, out_lvl in (sv.get("col_outlines") or {}).items():
            ws.column_dimensions[str(col_let)].outlineLevel = int(out_lvl)
        for row_str, out_lvl in (sv.get("row_outlines") or {}).items():
            if str(row_str).isdigit():
                ws.row_dimensions[int(row_str)].outlineLevel = int(out_lvl)
        for span in sv.get("trailing_col_spans", []):
            from brazil_power_bq_twin.models import index_to_col_letter

            s_min = int(span["min"])
            s_max = int(span["max"])
            s_let = index_to_col_letter(s_min)
            ws.column_dimensions[s_let] = ColumnDimension(
                ws,
                index=s_let,
                min=s_min,
                max=s_max,
                width=span.get("width"),
                hidden=bool(span.get("hidden", False)),
            )

        base_cells = snapshot.cells_by_sheet.get(ws_rec.sheet_name, {})
        delta_cells = overlay.deltas_by_sheet.get(ws_rec.sheet_name, {})
        all_coords = set(base_cells.keys()) | set(delta_cells.keys())

        for coord in all_coords:
            base_c = base_cells.get(coord)
            delta_c = overlay.get_delta(ws_rec.sheet_name, coord)

            if base_c is not None:
                target_cell = ws.cell(row=base_c.row_num, column=base_c.col_num)
            elif delta_c is not None:
                target_cell = ws.cell(row=delta_c.row_num, column=delta_c.col_num)
            else:
                continue

            if delta_c is not None:
                target_cell.value = delta_c.value
                overlaid_cells += 1
            elif base_c is not None:
                if base_c.raw_formula:
                    target_cell.value = f"={base_c.raw_formula}"
                elif base_c.effective_baseline_value is not None:
                    target_cell.value = base_c.effective_baseline_value

            if base_c is not None and base_c.style_id in hydrated_styles:
                num_fmt, font, fill, border, alignment = hydrated_styles[base_c.style_id]
                target_cell.number_format = num_fmt
                target_cell.font = font
                if fill is not None:
                    target_cell.fill = fill
                if border is not None:
                    target_cell.border = border
                if alignment is not None:
                    target_cell.alignment = alignment

            total_written += 1

        for m_rng in ws_rec.merged_ranges:
            ws.merge_cells(m_rng)

    from brazil_power_bq_twin.xlsm_compiler import _is_valid_internal_defined_name

    valid_sheet_set = set(wb.sheetnames)
    for dn_entry in snapshot.named_ranges or []:
        dn_name = str(dn_entry.get("name") or "")
        dn_attr = str(dn_entry.get("attr_text") or "")
        local_sid = dn_entry.get("local_sheet_id")
        if not _is_valid_internal_defined_name(dn_name, dn_attr, valid_sheet_set):
            continue
        if isinstance(local_sid, int) and 0 <= local_sid < len(wb.worksheets) and hasattr(wb.worksheets[local_sid], "defined_names"):
            wb.worksheets[local_sid].defined_names.add(DefinedName(name=dn_name, attr_text=dn_attr))
        else:
            wb.defined_names.add(DefinedName(name=dn_name, attr_text=dn_attr, localSheetId=local_sid))

    buf = io.BytesIO()
    wb.save(buf)
    sheet_names = list(wb.sheetnames)
    wb.close()

    return buf.getvalue(), {
        "sheet_names": sheet_names,
        "sheet_count": len(sheet_names),
        "total_cells_synthesized": total_written,
        "overlaid_delta_cells": overlaid_cells,
        "template_files_used": 0,
    }


def _synthesize_google_sheet_from_twin(
    snapshot: BaselineTwinSnapshot,
    overlay: SessionOverlay,
    sheet_title: str,
) -> dict[str, Any]:
    """Create a fresh 22-tab Google Sheet from BigQuery Digital Twin rows using Google Sheets v4 API."""
    import google.auth
    from googleapiclient.discovery import build

    creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
    sheets_svc = build("sheets", "v4", credentials=creds, cache_discovery=False)

    ordered_ws = sorted(snapshot.worksheets, key=lambda w: w.sheet_index)
    create_body = {
        "properties": {"title": sheet_title},
        "sheets": [
            {
                "properties": {
                    "title": w.sheet_name,
                    "index": w.sheet_index,
                    "hidden": w.visibility != "visible",
                }
            }
            for w in ordered_ws
        ],
    }
    created = sheets_svc.spreadsheets().create(body=create_body).execute()
    spreadsheet_id = str(created["spreadsheetId"])

    value_ranges: list[dict[str, Any]] = []
    for w in ordered_ws:
        s_name = w.sheet_name
        escaped_s = f"'{s_name}'" if (" " in s_name or "-" in s_name) else s_name
        base_cells = snapshot.cells_by_sheet.get(s_name, {})
        delta_cells = overlay.deltas_by_sheet.get(s_name, {})
        for coord in sorted(set(base_cells.keys()) | set(delta_cells.keys())):
            delta_c = overlay.get_delta(s_name, coord)
            base_c = base_cells.get(coord)
            if delta_c is not None:
                val = delta_c.value
            elif base_c is not None:
                val = f"={base_c.raw_formula}" if base_c.raw_formula else base_c.effective_baseline_value
            else:
                continue
            if val is not None:
                value_ranges.append({"range": f"{escaped_s}!{coord}", "values": [[val]]})

    for chunk_start in range(0, len(value_ranges), 2500):
        chunk = value_ranges[chunk_start : chunk_start + 2500]
        sheets_svc.spreadsheets().values().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"valueInputOption": "USER_ENTERED", "data": chunk},
        ).execute()

    return {
        "spreadsheet_id": spreadsheet_id,
        "spreadsheet_url": f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit",
        "sheet_title": sheet_title,
        "cells_populated": len(value_ranges),
    }


def export_digital_twin_workbook(
    store: DigitalTwinStore,
    session_id: str,
    export_format: str = "xlsx",
    output_filename: str | None = None,
    output_dir: Path | None = None,
    sheet_title: str | None = None,
    cloud_base_url: str | None = None,
) -> dict[str, Any]:
    """Synthesize a 22-tab `.xlsx` and/or Google Sheet purely from `DigitalTwinStore`."""
    settings = get_twin_settings()
    fmt = export_format.strip().lower()
    if fmt not in ("xlsx", "excel", "google_sheets", "sheets", "both"):
        raise ValueError(f"Unsupported export_format '{export_format}'.")

    snapshot = store.get_baseline_snapshot(settings.default_version_id)
    overlay = store.get_session_overlay(session_id, settings.default_version_id)

    do_xlsx = fmt in ("xlsx", "excel", "both")
    do_gsheets = fmt in ("google_sheets", "sheets", "both")
    base_url = (cloud_base_url or settings.cloud_service_url).rstrip("/")

    result: dict[str, Any] = {
        "export_format": fmt,
        "source": "bigquery_digital_twin",
        "template_files_used": 0,
        "xlsx_path": None,
        "gcs_xlsx_uri": None,
        "cloud_download_url": None,
        "spreadsheet_id": None,
        "spreadsheet_url": None,
        "tabs_preserved": len(snapshot.worksheets),
        "active_overrides": overlay.user_overrides_flat(),
    }

    md_lines = [
        "# 22-Tab Workbook Synthesized From BigQuery Digital Twin",
        f"- **Data Source**: `comm-model-mod.{settings.bq_dataset}` (`template_files_used = 0`)",
        f"- **Session ID**: `{session_id}`",
    ]

    if do_xlsx:
        safe_name = sanitize_filename(output_filename, ".xlsx")
        xlsx_bytes, stats = synthesize_22tab_xlsx_bytes(snapshot, overlay)
        target_dir = output_dir or settings.local_export_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        out_path = (target_dir / safe_name).resolve()
        out_path.write_bytes(xlsx_bytes)

        result.update(stats)
        result["xlsx_path"] = str(out_path)
        result["tabs_preserved"] = stats["sheet_count"]
        md_lines.append(
            f"- **Synthesized Cells**: `{stats['total_cells_synthesized']:,}` across `{stats['sheet_count']}` tabs "
            f"(`{stats['overlaid_delta_cells']}` session delta cells overlaid)"
        )

        if os.environ.get("K_SERVICE") or os.environ.get("BQ_TWIN_UPLOAD_GCS", "").lower() in ("1", "true"):
            blob_key = f"{settings.gcs_exports_prefix}/{safe_name}"
            try:
                from google.cloud import storage

                gcs_client = storage.Client(project=settings.gcp_project_id)
                blob = gcs_client.bucket(settings.gcs_bucket).blob(blob_key)
                blob.upload_from_string(
                    xlsx_bytes,
                    content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
                result["gcs_xlsx_uri"] = f"gs://{settings.gcs_bucket}/{blob_key}"
                result["cloud_download_url"] = f"{base_url}/v1/exports/{safe_name}"
                md_lines.append(f"- **Cloud `.xlsx` Download URL**: [{safe_name}]({result['cloud_download_url']})")
            except Exception as exc:
                logger.warning("GCS upload skipped/failed for %s: %s", blob_key, exc)

    if do_gsheets:
        gs_info = _synthesize_google_sheet_from_twin(
            snapshot=snapshot,
            overlay=overlay,
            sheet_title=sheet_title or "Brazil Power v13 — BigQuery Digital Twin Export (22 Tabs)",
        )
        result.update(gs_info)
        md_lines.append(f"- **Synthesized Google Sheet**: [{gs_info['sheet_title']}]({gs_info['spreadsheet_url']})")

    summary_md = "\n".join(md_lines) + "\n"
    result["inline_markdown"] = summary_md
    result["artifact_markdown"] = summary_md
    result["full_artifact_table_md"] = summary_md
    return result
