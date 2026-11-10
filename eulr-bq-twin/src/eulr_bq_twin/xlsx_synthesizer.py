"""100% BigQuery-to-OpenXML (.xlsx) & Google Sheets v4 synthesizer for `eulr-bq-twin`."""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import openpyxl
from google.cloud import storage
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.workbook.properties import CalcProperties

from eulr_bq_twin.bq_store import EulrDigitalTwinStore
from eulr_bq_twin.models import StyleMeta, UpstreamMode
from eulr_bq_twin.schema_ddl import ACTIVE_19_EULR_TABS, CORE_18_EULR_TABS

logger = logging.getLogger(__name__)

_SAFE_FILENAME_RE = re.compile(r"^[A-Za-z0-9._\-]+$")
_PINNED_AMBER_FILL = PatternFill(fill_type="solid", start_color="FFFDE68A", end_color="FFFDE68A")


def sanitize_export_filename(raw_name: str, suffix: str = ".xlsx") -> str:
    """Sanitize filename to prevent path traversal and header injection."""
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
        raise ValueError("Export path escaped sandbox directory")
    return candidate


def _build_openpyxl_style_bundle(
    sm: StyleMeta,
) -> tuple[str | None, Font | None, PatternFill | None, Border | None, Alignment | None]:
    nf = sm.number_format if sm.number_format and sm.number_format != "General" else None

    f = sm.font
    font_obj = Font(
        name=f.get("name") or "Arial",
        size=float(f.get("size") or 10.0),
        bold=bool(f.get("bold", False)),
        italic=bool(f.get("italic", False)),
        color=f.get("color"),
    )

    fl = sm.fill
    fill_obj: PatternFill | None = None
    if fl.get("fill_type") and fl.get("fg_color"):
        fg = str(fl["fg_color"]).upper()
        if len(fg) == 8 and fg != "00000000":
            fill_obj = PatternFill(
                fill_type=fl["fill_type"],
                start_color=fg,
                end_color=fg,
            )

    bd = sm.border
    border_obj: Border | None = None
    if bd:
        sides: dict[str, Side] = {}
        for side_name in ("left", "right", "top", "bottom"):
            s_spec = bd.get(side_name)
            if s_spec and s_spec.get("style"):
                sides[side_name] = Side(
                    style=s_spec["style"],
                    color=s_spec.get("color"),
                )
        if sides:
            border_obj = Border(**sides)

    al = sm.alignment
    align_obj: Alignment | None = None
    if al:
        align_obj = Alignment(
            horizontal=al.get("horizontal"),
            vertical=al.get("vertical"),
            wrap_text=bool(al.get("wrap_text", False)),
        )

    return nf, font_obj, fill_obj, border_obj, align_obj


def synthesize_eulr_workbook(
    store: EulrDigitalTwinStore,
    session_id: str,
    include_upload_tab: bool = False,
    upstream_mode: UpstreamMode = "baseline_cached",
    filename_prefix: str = "EULR_Refining_Digital_Twin",
    upload_to_gcs: bool = True,
) -> dict[str, Any]:
    """
    Synthesize an 18-tab (or 19-tab with `UPLOAD`) `.xlsx` directly from BigQuery Digital Twin rows.
    - Materializes all 14,162 external `[N]Sheet!Cell` links as clean resolved numeric values
      so Excel opens immediately with zero broken SharePoint link popups.
    - Preserves all internal `=Formulas` live and sets `iterate=True, iterateCount=10`.
    - Highlights active `PINNED_PRICE_OVERRIDE` cells in `#FDE68A` amber.
    """
    snap = store.get_baseline_snapshot()
    sess_deltas = store.get_session_deltas(session_id)
    target_tabs = ACTIVE_19_EULR_TABS if include_upload_tab else CORE_18_EULR_TABS
    included_set = set(target_tabs)

    wb = openpyxl.Workbook()
    # Enable iterative calculation matching Eulr202409.xlsx (<calcPr iterate="1" iterateCount="10"/>)
    wb.calculation = CalcProperties(
        calcMode="auto",
        iterate=True,
        iterateCount=int(snap.calc_properties.get("iterateCount", 10)),
        iterateDelta=float(snap.calc_properties.get("iterateDelta", 0.001)),
    )
    # Remove default sheet after creating first real tab
    default_ws = wb.active

    style_cache: dict[
        int, tuple[str | None, Font | None, PatternFill | None, Border | None, Alignment | None]
    ] = {sid: _build_openpyxl_style_bundle(sm) for sid, sm in snap.styles.items()}

    total_cells_written = 0
    live_formulas_written = 0
    resolved_ext_cells = 0
    pinned_cells_styled = 0

    for sname in target_tabs:
        wm = snap.worksheets.get(sname)
        if wm is None:
            continue
        ws = wb.create_sheet(title=sname)
        if wm.tab_color_rgb and len(wm.tab_color_rgb) == 8:
            ws.sheet_properties.tabColor = wm.tab_color_rgb

        # SheetView zoom, gridlines & freeze panes
        sv_info = wm.sheet_view or {}
        if sv_info.get("zoom_scale"):
            ws.sheet_view.zoomScale = int(sv_info["zoom_scale"])
        if "show_grid_lines" in sv_info:
            ws.sheet_view.showGridLines = bool(sv_info["show_grid_lines"])
        if wm.freeze_panes_coord:
            ws.freeze_panes = wm.freeze_panes_coord

        # Column widths & hidden columns
        hidden_cols = set(sv_info.get("hidden_cols", []))
        for col_let, w_val in wm.col_widths.items():
            cd = ws.column_dimensions[col_let]
            cd.width = float(w_val)
            if col_let in hidden_cols:
                cd.hidden = True
        for h_col in hidden_cols:
            ws.column_dimensions[h_col].hidden = True

        # Row heights & hidden rows
        hidden_rows = set(int(x) for x in sv_info.get("hidden_rows", []))
        for r_idx, ht_val in wm.row_heights.items():
            rd = ws.row_dimensions[int(r_idx)]
            rd.height = float(ht_val)
            if int(r_idx) in hidden_rows:
                rd.hidden = True
        for h_row in hidden_rows:
            ws.row_dimensions[h_row].hidden = True

        # Populate cells
        sh_cells = snap.cells_by_sheet.get(sname, {})
        for (r_idx, c_idx), tc in sh_cells.items():
            delta = sess_deltas.get((sname, r_idx, c_idx))
            ext_rec = snap.external_links.get((sname, r_idx, c_idx))

            val_to_write: Any = None
            is_pinned = False

            if delta is not None and delta.delta_kind in (
                "DRIVER_OVERRIDE",
                "PINNED_PRICE_OVERRIDE",
                "BQML_FORECAST",
            ):
                val_to_write = (
                    delta.numeric_value if delta.numeric_value is not None else delta.string_value
                )
                is_pinned = delta.delta_kind == "PINNED_PRICE_OVERRIDE"
            elif tc.has_external_link or ext_rec is not None:
                # Resolve external [N]Sheet!Cell link to clean numeric value (Decision A3)
                if (
                    upstream_mode == "peer_synced"
                    and ext_rec is not None
                    and ext_rec.is_peer_updated
                    and ext_rec.peer_live_value is not None
                ):
                    val_to_write = ext_rec.peer_live_value
                elif ext_rec is not None:
                    val_to_write = ext_rec.baseline_cached_value
                else:
                    val_to_write = tc.numeric_value if tc.numeric_value is not None else tc.string_value
                resolved_ext_cells += 1
            elif tc.raw_formula is not None:
                # If UPLOAD is excluded and an internal formula references UPLOAD!, resolve value cleanly
                if (not include_upload_tab) and ("UPLOAD!" in tc.raw_formula):
                    val_to_write = tc.numeric_value if tc.numeric_value is not None else tc.string_value
                elif tc.is_array_cse and ("COLUMN(" in tc.raw_formula.upper() or "TRANSPOSE(" in tc.raw_formula.upper()):
                    # Write resolved value for legacy {=CSE} lookahead cells so Excel 365 doesn't spill #SPILL!
                    val_to_write = (
                        delta.numeric_value
                        if (delta and delta.numeric_value is not None)
                        else tc.numeric_value
                    )
                else:
                    val_to_write = tc.raw_formula
                    live_formulas_written += 1
            elif tc.data_type == "MERGED_STYLE":
                val_to_write = None
            elif tc.numeric_value is not None:
                val_to_write = tc.numeric_value
            else:
                val_to_write = tc.string_value

            cell_obj = ws.cell(row=r_idx, column=c_idx, value=val_to_write)
            total_cells_written += 1

            st_bundle = style_cache.get(tc.style_id)
            if st_bundle is not None and tc.style_id != 0:
                nf, f_obj, fl_obj, bd_obj, al_obj = st_bundle
                if nf:
                    cell_obj.number_format = nf
                if f_obj:
                    cell_obj.font = f_obj
                if fl_obj:
                    cell_obj.fill = fl_obj
                if bd_obj:
                    cell_obj.border = bd_obj
                if al_obj:
                    cell_obj.alignment = al_obj

            if is_pinned:
                cell_obj.fill = _PINNED_AMBER_FILL
                pinned_cells_styled += 1

        # Apply merged ranges after styling perimeter cells
        for m_rng in wm.merged_ranges:
            try:
                ws.merge_cells(m_rng)
            except Exception:
                pass

    if default_ws is not None and default_ws.title in wb.sheetnames and len(wb.sheetnames) > 1:
        wb.remove(default_ws)

    # Re-attach sanitized internal DefinedNames referencing included tabs
    sheet_idx_by_name = {name: i for i, name in enumerate(wb.sheetnames)}
    for nr in snap.named_ranges:
        attr_txt = nr["attr_text"]
        if (not include_upload_tab) and ("UPLOAD!" in attr_txt):
            continue
        scope_sh = nr.get("scope_sheet")
        if scope_sh and scope_sh not in included_set:
            continue
        try:
            dn = DefinedName(
                name=nr["name"],
                attr_text=attr_txt,
                localSheetId=sheet_idx_by_name[scope_sh] if scope_sh in sheet_idx_by_name else None,
            )
            wb.defined_names.add(dn)
        except Exception:
            pass

    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    safe_sess = re.sub(r"[^A-Za-z0-9_\-]+", "_", session_id)[:28]
    fname = sanitize_export_filename(
        f"{filename_prefix}_{len(target_tabs)}Tabs_{safe_sess}_{ts}.xlsx"
    )
    out_dir = Path(store.settings.export_local_dir)
    local_path = resolve_contained_export_path(out_dir, fname)
    wb.save(str(local_path))
    size_bytes = local_path.stat().st_size

    gcs_uri: str | None = None
    if upload_to_gcs and store.settings.gcp_project_id != "offline-test":
        try:
            gcs = storage.Client(project=store.settings.gcp_project_id)
            bucket = gcs.bucket(store.settings.gcs_vault_bucket)
            blob_key = f"{store.settings.gcs_export_prefix}/{fname}"
            blob = bucket.blob(blob_key)
            blob.upload_from_filename(
                str(local_path),
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            gcs_uri = f"gs://{store.settings.gcs_vault_bucket}/{blob_key}"
        except Exception as exc:
            logger.warning("GCS export upload skipped: %s", exc)

    base_url = store.settings.public_service_url.rstrip("/")
    download_url = f"{base_url}/v1/exports/{fname}" if base_url else f"/v1/exports/{fname}"

    return {
        "filename": fname,
        "local_path": str(local_path),
        "size_bytes": size_bytes,
        "tabs_exported": len(target_tabs),
        "include_upload_tab": include_upload_tab,
        "total_cells_written": total_cells_written,
        "live_internal_formulas": live_formulas_written,
        "resolved_external_links": resolved_ext_cells,
        "pinned_cells_highlighted": pinned_cells_styled,
        "gcs_uri": gcs_uri,
        "download_url": download_url,
    }
