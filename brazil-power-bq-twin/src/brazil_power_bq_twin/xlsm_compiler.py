"""Offline one-time workbook decompiler producing BigQuery Digital Twin rows and BaselineTwinSnapshot."""

from __future__ import annotations

import colorsys
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import openpyxl
from openpyxl.cell.cell import MergedCell
from openpyxl.styles.colors import COLOR_INDEX
from openpyxl.worksheet.formula import ArrayFormula

from brazil_power_bq_twin.models import (
    BaselineTwinSnapshot,
    CellRecord,
    StyleRecord,
    WorksheetRecord,
    col_letter_to_index,
    index_to_col_letter,
)

_VALID_DN_NAME_RE = re.compile(r"^(?:_xlnm\.[A-Za-z_]+|[A-Za-z_\\][A-Za-z0-9_.]*)$")
_SHEET_REF_RE = re.compile(r"(?:'([^']+)'|([A-Za-z0-9_]+))!")
_ADDIN_DN_PREFIXES = ("_AtRisk_", "Risk", "SAPBEX", "wrn.", "HTML_", "_GV", "GVKey", "_Order", "IQ_")


def _is_valid_internal_defined_name(name: str, attr_text: str, valid_sheets: set[str]) -> bool:
    """Return True if a DefinedName is a valid internal name without broken external/#REF! links."""
    clean_name = name.strip()
    clean_attr = attr_text.strip()
    if not clean_name or not clean_attr or clean_name.endswith("."):
        return False
    if clean_name.startswith(_ADDIN_DN_PREFIXES):
        return False
    if not _VALID_DN_NAME_RE.match(clean_name):
        return False
    if "[" in clean_attr or "]" in clean_attr or "#REF!" in clean_attr or "#N/A" in clean_attr:
        return False
    if "!" in clean_attr:
        matches = _SHEET_REF_RE.findall(clean_attr)
        if not matches:
            return False
        for quoted_s, bare_s in matches:
            ref_sheet = quoted_s or bare_s
            if ref_sheet not in valid_sheets:
                return False
    return True

# Standard Office 2007+ theme palette in SpreadsheetML index order (lt1, dk1, lt2, dk2, accent1..6, hlink, folHlink)
_DEFAULT_OFFICE_THEME: tuple[str, ...] = (
    "FFFFFF",
    "000000",
    "EEECE1",
    "1F497D",
    "4F81BD",
    "C0504D",
    "9BBB59",
    "8064A2",
    "4BACC6",
    "F79646",
    "0000FF",
    "800080",
)


@dataclass
class CompiledTwinPayload:
    """Complete BigQuery batch-load payload extracted from a workbook."""

    version_row: dict[str, Any]
    worksheet_rows: list[dict[str, Any]]
    style_rows: list[dict[str, Any]]
    cell_rows: list[dict[str, Any]]
    lt_trajectory_rows: list[dict[str, Any]]
    snapshot: BaselineTwinSnapshot


def _parse_workbook_theme_palette(loaded_theme: bytes | str | None) -> tuple[str, ...]:
    """Parse `xl/theme/theme1.xml` into SpreadsheetML theme index order (swapping dk1/lt1 and dk2/lt2)."""
    if not loaded_theme:
        return _DEFAULT_OFFICE_THEME
    try:
        raw_bytes = loaded_theme.encode("utf-8") if isinstance(loaded_theme, str) else loaded_theme
        root = ET.fromstring(raw_bytes)
        ns = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
        scheme = root.find(".//a:clrScheme", ns)
        if scheme is None:
            return _DEFAULT_OFFICE_THEME
        by_tag: dict[str, str] = {}
        for child in list(scheme):
            tag = child.tag.split("}")[-1]
            srgb = child.find("a:srgbClr", ns)
            sys_c = child.find("a:sysClr", ns)
            hex6 = (
                srgb.attrib.get("val")
                if srgb is not None
                else (sys_c.attrib.get("lastClr") or sys_c.attrib.get("val") if sys_c is not None else None)
            )
            if hex6 and len(hex6) == 6:
                by_tag[tag] = hex6.upper()
        ordered_tags = (
            "lt1",
            "dk1",
            "lt2",
            "dk2",
            "accent1",
            "accent2",
            "accent3",
            "accent4",
            "accent5",
            "accent6",
            "hlink",
            "folHlink",
        )
        return tuple(by_tag.get(t, _DEFAULT_OFFICE_THEME[i]) for i, t in enumerate(ordered_tags))
    except Exception:
        return _DEFAULT_OFFICE_THEME


def _apply_ooxml_tint(rgb6: str, tint: float) -> str:
    """Apply OOXML HLS luminance tint (-1.0..+1.0) to a 6-char hex RGB color and return opaque 'FFRRGGBB'."""
    if abs(tint) <= 1e-6:
        return f"FF{rgb6.upper()}"
    r = int(rgb6[0:2], 16) / 255.0
    g = int(rgb6[2:4], 16) / 255.0
    b = int(rgb6[4:6], 16) / 255.0
    h, lum, sat = colorsys.rgb_to_hls(r, g, b)
    if tint < 0.0:
        lum = lum * (1.0 + tint)
    else:
        lum = lum * (1.0 - tint) + tint
    lum = min(1.0, max(0.0, lum))
    nr, ng, nb = colorsys.hls_to_rgb(h, lum, sat)
    return f"FF{int(round(nr * 255)):02X}{int(round(ng * 255)):02X}{int(round(nb * 255)):02X}"


def _resolve_color_argb(color_obj: Any, theme_palette: tuple[str, ...] = _DEFAULT_OFFICE_THEME) -> str | None:
    """Resolve an OpenPyXL `Color` (`rgb`, `theme`+`tint`, or `indexed`) into an opaque 'FFRRGGBB' hex string."""
    if color_obj is None:
        return None
    ctype = getattr(color_obj, "type", None)
    tint = float(getattr(color_obj, "tint", 0.0) or 0.0)

    if ctype == "rgb":
        rgb = getattr(color_obj, "rgb", None)
        if isinstance(rgb, str) and all(c in "0123456789ABCDEFabcdef" for c in rgb):
            up = rgb.upper()
            if up == "00000000":
                return None
            hex6 = up[-6:] if len(up) in (6, 8) else None
            if hex6:
                return _apply_ooxml_tint(hex6, tint)
        return None

    if ctype == "theme":
        t_idx = getattr(color_obj, "theme", None)
        if isinstance(t_idx, int) and 0 <= t_idx < len(theme_palette):
            return _apply_ooxml_tint(theme_palette[t_idx], tint)
        return None

    if ctype == "indexed":
        idx = getattr(color_obj, "indexed", None)
        # Indices >= 64 in Excel are system foreground/background auto colors (transparent/default)
        if isinstance(idx, int) and 0 <= idx < min(64, len(COLOR_INDEX)):
            raw_hex = str(COLOR_INDEX[idx]).upper()
            if len(raw_hex) in (6, 8):
                return _apply_ooxml_tint(raw_hex[-6:], tint)
        return None

    return None


def _extract_style_tuple(
    cell: Any,
    theme_palette: tuple[str, ...] = _DEFAULT_OFFICE_THEME,
) -> tuple[str, str, str, str, str]:
    num_fmt = str(cell.number_format or "General")
    font = cell.font
    font_dict = {
        "name": getattr(font, "name", None) or "Calibri",
        "size": float(font.size) if getattr(font, "size", None) else 11.0,
        "bold": bool(getattr(font, "bold", False)),
        "italic": bool(getattr(font, "italic", False)),
        "color_rgb": _resolve_color_argb(getattr(font, "color", None), theme_palette),
    }
    fill = cell.fill
    fill_type = getattr(fill, "fill_type", None)
    sc_rgb = _resolve_color_argb(getattr(fill, "start_color", None), theme_palette)
    ec_rgb = _resolve_color_argb(getattr(fill, "end_color", None), theme_palette)
    fill_dict = (
        {
            "fill_type": fill_type,
            "start_color_rgb": sc_rgb,
            "end_color_rgb": ec_rgb,
        }
        if (fill_type and sc_rgb is not None)
        else {}
    )
    border = cell.border
    border_dict: dict[str, Any] = {}
    if border is not None:
        for side_name in ("left", "right", "top", "bottom"):
            side = getattr(border, side_name, None)
            if side is not None and getattr(side, "style", None):
                border_dict[side_name] = {
                    "style": str(side.style),
                    "color_rgb": _resolve_color_argb(getattr(side, "color", None), theme_palette),
                }
    align = cell.alignment
    align_dict = {
        "horizontal": getattr(align, "horizontal", None),
        "vertical": getattr(align, "vertical", None),
        "wrap_text": bool(getattr(align, "wrap_text", False)),
    }
    align_dict = {k: v for k, v in align_dict.items() if v is not None and v is not False}
    return (
        num_fmt,
        json.dumps(font_dict, sort_keys=True),
        json.dumps(fill_dict, sort_keys=True),
        json.dumps(border_dict, sort_keys=True),
        json.dumps(align_dict, sort_keys=True),
    )


def _num(val: Any, default: float = 0.0) -> float:
    if isinstance(val, bool):
        return float(int(val))
    if isinstance(val, (int, float)):
        return float(val)
    return default


def _extract_solver_parameters(cells_by_sheet: dict[str, dict[str, CellRecord]]) -> dict[str, Any]:
    """Derive baseline per-technology quantitative parameters directly from `General` and `_01_CF.._12_CF` cells."""
    gen = cells_by_sheet.get("General", {})
    solver_params: dict[str, Any] = {}

    def _gval(col_letter: str, row_num: int, default: float = 0.0) -> float:
        rec = gen.get(f"{col_letter}{row_num}")
        if rec is None:
            return default
        return _num(rec.effective_baseline_value, default)

    def _gstr(col_letter: str, row_num: int, default: str = "") -> str:
        rec = gen.get(f"{col_letter}{row_num}")
        if rec is None or rec.effective_baseline_value is None:
            return default
        return str(rec.effective_baseline_value)

    for idx in range(1, 13):
        tech_code = f"_{idx:02d}_CF"
        col_letter = index_to_col_letter(2 + idx)  # C..N
        sheet_cells = cells_by_sheet.get(tech_code, {})

        def _sval(coord: str, default: float = 0.0) -> float:
            rec = sheet_cells.get(coord)
            return _num(rec.effective_baseline_value, default) if rec else default

        fuel_unit = _gstr(col_letter, 19, "")
        solver_params[tech_code] = {
            "general_col": col_letter,
            "fuel_name": _gstr(col_letter, 5, tech_code),
            "technology_label": _gstr(col_letter, 7, tech_code),
            "fuel_unit": fuel_unit,
            "capacity_mw": _gval(col_letter, 8, 100.0),
            "losses_pct": _gval(col_letter, 10, 0.025),
            "capex_brl_kw": _gval(col_letter, 11, 4500.0),
            "capex_low_brl_kw": _gval(col_letter, 12, 4000.0),
            "capex_high_brl_kw": _gval(col_letter, 13, 5000.0),
            "lead_time_yrs": max(1, int(round(_gval(col_letter, 14, 3.0)))),
            "economic_life_yrs": max(5, int(round(_gval(col_letter, 15, 25.0)))),
            "capacity_factor": _gval(col_letter, 16, 0.50),
            "heat_rate": _gval(col_letter, 17, 0.0),
            "availability_mwmed": _gval(col_letter, 18, 0.0),
            "fuel_cost": _gval(col_letter, 20, 0.0),
            "fixed_om_brl_kw_yr": _gval(col_letter, 23, 40.0),
            "variable_om_brl_mwh": _gval(col_letter, 24, 0.0),
            "op_insurance_pct": _gval(col_letter, 25, 0.003),
            "warranty_insurance_pct": _gval(col_letter, 26, 0.004),
            "transmission_brl_kw_mo": _gval(col_letter, 27, 4.5),
            "admin_pct": _gval(col_letter, 28, 0.01),
            "rental_pct": _gval(col_letter, 29, 0.0),
            "equity_share": _gval(col_letter, 32, 0.30),
            "debt_share": _gval(col_letter, 33, 0.70),
            "real_wacc": _gval(col_letter, 34, 0.08),
            "loan_tenor_yrs": max(1, int(round(_gval(col_letter, 35, 16.0)))),
            "target_irr": _gval(col_letter, 36, 0.10),
            "income_tax_rate": _gval(col_letter, 38, 0.34),
            "fx_brl_per_usd": _gval(col_letter, 40, 3.70),
            "base_tariff_brl_mwh": _sval("D25", 0.0) or _sval("C25", 0.0),
        }
    return solver_params


def compile_workbook_to_twin_payload(
    workbook_path: Path,
    workbook_id: str = "brazil_power_v13",
    version_id: str = "v13_baseline",
) -> CompiledTwinPayload:
    """Decompile a 22-tab `.xlsm`/`.xlsx` workbook into BigQuery Digital Twin rows and an in-memory snapshot."""
    wb_formulas = openpyxl.load_workbook(workbook_path, data_only=False, keep_vba=False)
    wb_values = openpyxl.load_workbook(workbook_path, data_only=True, keep_vba=False)
    theme_palette = _parse_workbook_theme_palette(getattr(wb_formulas, "loaded_theme", None))

    style_index: dict[tuple[str, str, str, str, str], int] = {}
    default_tuple = (
        "General",
        json.dumps({"name": "Calibri", "size": 11.0, "bold": False, "italic": False, "color_rgb": None}, sort_keys=True),
        "{}",
        "{}",
        "{}",
    )
    style_index[default_tuple] = 0

    worksheets: list[WorksheetRecord] = []
    worksheet_rows: list[dict[str, Any]] = []
    cells_by_sheet: dict[str, dict[str, CellRecord]] = {}
    cell_rows: list[dict[str, Any]] = []

    valid_sheets = set(wb_formulas.sheetnames)
    named_ranges: list[dict[str, Any]] = []
    seen_dn_keys: set[tuple[str, int | None]] = set()

    for s_idx, sheet_name in enumerate(wb_formulas.sheetnames):
        ws_f = wb_formulas[sheet_name]
        ws_v = wb_values[sheet_name]

        merges = tuple(sorted(str(rng) for rng in ws_f.merged_cells.ranges))
        col_widths: dict[str, float] = {}
        hidden_cols: list[str] = []
        col_outlines: dict[str, int] = {}
        trailing_col_spans: list[dict[str, Any]] = []

        for col_key, dim in ws_f.column_dimensions.items():
            try:
                c_min = int(dim.min) if getattr(dim, "min", None) else col_letter_to_index(str(col_key))
            except ValueError:
                continue
            c_max = int(dim.max) if getattr(dim, "max", None) else c_min
            w_val = round(float(dim.width), 3) if dim.width is not None else None
            is_hid = bool(getattr(dim, "hidden", False))
            out_lvl = int(getattr(dim, "outlineLevel", 0) or 0)

            if c_max <= 256:
                for c_idx in range(c_min, max(c_min, c_max) + 1):
                    c_let = index_to_col_letter(c_idx)
                    if w_val is not None:
                        col_widths[c_let] = w_val
                    if is_hid and c_let not in hidden_cols:
                        hidden_cols.append(c_let)
                    if out_lvl > 0:
                        col_outlines[c_let] = out_lvl
            else:
                trailing_col_spans.append(
                    {"min": c_min, "max": c_max, "width": w_val, "hidden": is_hid}
                )

        row_heights: dict[str, float] = {}
        hidden_rows: list[int] = []
        row_outlines: dict[str, int] = {}
        for row_key, dim in ws_f.row_dimensions.items():
            r_int = int(row_key)
            r_str = str(r_int)
            if dim.height is not None:
                row_heights[r_str] = round(float(dim.height), 3)
            if bool(getattr(dim, "hidden", False)):
                hidden_rows.append(r_int)
            r_out = int(getattr(dim, "outlineLevel", 0) or 0)
            if r_out > 0:
                row_outlines[r_str] = r_out

        sv_obj = ws_f.views.sheetView[0] if getattr(ws_f, "views", None) and ws_f.views.sheetView else None
        show_grid = False if getattr(sv_obj, "showGridLines", None) is False else True
        zoom_val = int(sv_obj.zoomScale) if getattr(sv_obj, "zoomScale", None) else None
        sheet_view_dict: dict[str, Any] = {"show_grid_lines": show_grid}
        if zoom_val is not None:
            sheet_view_dict["zoom_scale"] = zoom_val
        if hidden_cols:
            sheet_view_dict["hidden_cols"] = hidden_cols
        if hidden_rows:
            sheet_view_dict["hidden_rows"] = sorted(hidden_rows)
        if col_outlines:
            sheet_view_dict["col_outlines"] = col_outlines
        if row_outlines:
            sheet_view_dict["row_outlines"] = row_outlines
        if trailing_col_spans:
            sheet_view_dict["trailing_col_spans"] = trailing_col_spans

        tab_rgb = _resolve_color_argb(getattr(ws_f.sheet_properties, "tabColor", None), theme_palette)
        freeze_coord = str(ws_f.freeze_panes) if ws_f.freeze_panes else None
        visibility = str(ws_f.sheet_state or "visible")

        ws_rec = WorksheetRecord(
            sheet_index=s_idx,
            sheet_name=sheet_name,
            visibility=visibility,
            tab_color_rgb=tab_rgb,
            merged_ranges=merges,
            col_widths=col_widths,
            row_heights=row_heights,
            freeze_panes_coord=freeze_coord,
            sheet_view=sheet_view_dict,
        )
        worksheets.append(ws_rec)
        worksheet_rows.append(
            {
                "workbook_id": workbook_id,
                "version_id": version_id,
                "sheet_index": s_idx,
                "sheet_name": sheet_name,
                "visibility": visibility,
                "tab_color_rgb": tab_rgb,
                "merged_ranges_json": json.dumps(list(merges)),
                "col_widths_json": json.dumps(col_widths),
                "row_heights_json": json.dumps(row_heights),
                "freeze_panes_coord": freeze_coord,
                "sheet_view_json": json.dumps(sheet_view_dict, sort_keys=True),
            }
        )

        # Collect worksheet-scoped defined names (OpenPyXL 3.1 stores local names on ws.defined_names)
        if hasattr(ws_f, "defined_names"):
            for ws_dn in ws_f.defined_names.values():
                dn_name = str(ws_dn.name)
                dn_attr = str(ws_dn.attr_text or "")
                if _is_valid_internal_defined_name(dn_name, dn_attr, valid_sheets):
                    dn_key = (dn_name, s_idx)
                    if dn_key not in seen_dn_keys:
                        seen_dn_keys.add(dn_key)
                        named_ranges.append(
                            {"name": dn_name, "attr_text": dn_attr, "local_sheet_id": s_idx}
                        )

        sheet_map: dict[str, CellRecord] = {}
        for row_cells in ws_f.iter_rows():
            for cell_f in row_cells:
                is_merged_subcell = isinstance(cell_f, MergedCell)
                raw_f_obj = None if is_merged_subcell else cell_f.value
                if raw_f_obj is None and not cell_f.has_style:
                    continue
                style_tup = _extract_style_tuple(cell_f, theme_palette)
                has_visual_box = style_tup[2] != "{}" or style_tup[3] != "{}"
                if raw_f_obj is None and not has_visual_box:
                    continue

                if style_tup not in style_index:
                    style_index[style_tup] = len(style_index)
                sid = style_index[style_tup]

                cached_val = None if is_merged_subcell else ws_v.cell(row=cell_f.row, column=cell_f.column).value

                raw_formula: str | None = None
                numeric_val: float | None = None
                string_val: str | None = None
                data_type = "s"
                semantic_role = "MERGED_STYLE" if is_merged_subcell else "INPUT"

                if isinstance(raw_f_obj, ArrayFormula):
                    ftxt = str(raw_f_obj.text or "")
                    raw_formula = ftxt[1:] if ftxt.startswith("=") else ftxt
                    data_type = "f"
                    semantic_role = "FORMULA"
                elif isinstance(raw_f_obj, str) and raw_f_obj.startswith("="):
                    raw_formula = raw_f_obj[1:]
                    data_type = "f"
                    semantic_role = "FORMULA"

                eval_source = cached_val if data_type == "f" else raw_f_obj
                if isinstance(eval_source, bool):
                    data_type = "f" if raw_formula else "b"
                    numeric_val = float(int(eval_source))
                    string_val = str(eval_source)
                elif isinstance(eval_source, (int, float)):
                    if not raw_formula:
                        data_type = "n"
                        semantic_role = "OUTPUT" if sheet_name.startswith("Output_") else "INPUT"
                    numeric_val = float(eval_source)
                elif eval_source is not None:
                    if not raw_formula:
                        data_type = "s"
                        semantic_role = "LABEL"
                    string_val = str(eval_source)

                coord = f"{index_to_col_letter(cell_f.column)}{cell_f.row}"
                crec = CellRecord(
                    sheet_name=sheet_name,
                    cell_coord=coord,
                    row_num=cell_f.row,
                    col_num=cell_f.column,
                    data_type=data_type,
                    numeric_value=numeric_val,
                    string_value=string_val,
                    raw_formula=raw_formula,
                    style_id=sid,
                    semantic_role=semantic_role,
                )
                sheet_map[coord] = crec
                cell_rows.append(
                    {
                        "workbook_id": workbook_id,
                        "version_id": version_id,
                        "sheet_name": sheet_name,
                        "cell_coord": coord,
                        "row_num": crec.row_num,
                        "col_num": crec.col_num,
                        "data_type": crec.data_type,
                        "numeric_value": crec.numeric_value,
                        "string_value": crec.string_value,
                        "raw_formula": crec.raw_formula,
                        "style_id": crec.style_id,
                        "semantic_role": crec.semantic_role,
                    }
                )
        cells_by_sheet[sheet_name] = sheet_map

    for defn in wb_formulas.defined_names.values():
        dn_name = str(defn.name)
        dn_attr = str(defn.attr_text or "")
        local_sid = defn.localSheetId
        if _is_valid_internal_defined_name(dn_name, dn_attr, valid_sheets):
            dn_key = (dn_name, local_sid)
            if dn_key not in seen_dn_keys:
                seen_dn_keys.add(dn_key)
                named_ranges.append(
                    {
                        "name": dn_name,
                        "attr_text": dn_attr,
                        "local_sheet_id": local_sid,
                    }
                )

    wb_formulas.close()
    wb_values.close()

    styles: dict[int, StyleRecord] = {}
    style_rows: list[dict[str, Any]] = []
    for (num_fmt, font_j, fill_j, border_j, align_j), sid in sorted(style_index.items(), key=lambda kv: kv[1]):
        styles[sid] = StyleRecord(
            style_id=sid,
            number_format=num_fmt,
            font=json.loads(font_j),
            fill=json.loads(fill_j),
            border=json.loads(border_j),
            alignment=json.loads(align_j),
        )
        style_rows.append(
            {
                "workbook_id": workbook_id,
                "version_id": version_id,
                "style_id": sid,
                "number_format": num_fmt,
                "font_json": font_j,
                "fill_json": fill_j,
                "border_json": border_j,
                "alignment_json": align_j,
            }
        )

    solver_parameters = _extract_solver_parameters(cells_by_sheet)

    lt_cols = ("ccgt", "bio_chp", "bio_retro", "bio_wc", "wind", "solar", "coal_pc", "shp", "coal_cfbc")
    lt_map = (("CAPEX", "LT Capex"), ("FUEL", "LT Fuel"), ("CF", "LT CF"))
    lt_trajectory_rows: list[dict[str, Any]] = []
    for curve_type, tab_name in lt_map:
        tab_cells = cells_by_sheet.get(tab_name, {})
        for offset, yr in enumerate(range(2024, 2047)):
            r_num = 8 + offset
            row_dict: dict[str, Any] = {
                "curve_type": curve_type,
                "forecast_year": yr,
                "series_date": f"{yr}-01-01",
                "data_source": "digital_twin_seed",
            }
            for c_idx, col_key in enumerate(lt_cols, start=2):
                c_letter = index_to_col_letter(c_idx)
                cell_rec = tab_cells.get(f"{c_letter}{r_num}")
                row_dict[col_key] = _num(cell_rec.effective_baseline_value, 1.0) if cell_rec else 1.0
            lt_trajectory_rows.append(row_dict)

    version_row = {
        "workbook_id": workbook_id,
        "version_id": version_id,
        "version_label": f"Brazil Power v13 BigQuery Digital Twin ({version_id})",
        "total_sheets": len(worksheets),
        "total_cells": len(cell_rows),
        "named_ranges_json": json.dumps(named_ranges),
        "solver_parameters_json": json.dumps(solver_parameters),
        "created_at": datetime.now(UTC).isoformat(),
    }

    snapshot = BaselineTwinSnapshot(
        workbook_id=workbook_id,
        version_id=version_id,
        version_label=version_row["version_label"],
        worksheets=worksheets,
        styles=styles,
        cells_by_sheet=cells_by_sheet,
        named_ranges=named_ranges,
        solver_parameters=solver_parameters,
    )
    return CompiledTwinPayload(
        version_row=version_row,
        worksheet_rows=worksheet_rows,
        style_rows=style_rows,
        cell_rows=cell_rows,
        lt_trajectory_rows=lt_trajectory_rows,
        snapshot=snapshot,
    )
