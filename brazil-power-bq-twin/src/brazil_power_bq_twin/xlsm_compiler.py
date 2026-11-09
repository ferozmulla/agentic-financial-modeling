"""Offline one-time workbook decompiler producing BigQuery Digital Twin rows and BaselineTwinSnapshot."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import openpyxl
from openpyxl.cell.cell import MergedCell
from openpyxl.worksheet.formula import ArrayFormula

from brazil_power_bq_twin.models import (
    BaselineTwinSnapshot,
    CellRecord,
    StyleRecord,
    WorksheetRecord,
    index_to_col_letter,
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


def _safe_rgb(color_obj: Any) -> str | None:
    if color_obj is None:
        return None
    rgb = getattr(color_obj, "rgb", None)
    if isinstance(rgb, str) and len(rgb) in (6, 8) and all(c in "0123456789ABCDEFabcdef" for c in rgb):
        return rgb.upper()
    return None


def _extract_style_tuple(cell: Any) -> tuple[str, str, str, str, str]:
    num_fmt = str(cell.number_format or "General")
    font = cell.font
    font_dict = {
        "name": getattr(font, "name", None) or "Calibri",
        "size": float(font.size) if getattr(font, "size", None) else 11.0,
        "bold": bool(getattr(font, "bold", False)),
        "italic": bool(getattr(font, "italic", False)),
        "color_rgb": _safe_rgb(getattr(font, "color", None)),
    }
    fill = cell.fill
    fill_type = getattr(fill, "fill_type", None)
    fill_dict = (
        {
            "fill_type": fill_type,
            "start_color_rgb": _safe_rgb(getattr(fill, "start_color", None)),
            "end_color_rgb": _safe_rgb(getattr(fill, "end_color", None)),
        }
        if fill_type
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
                    "color_rgb": _safe_rgb(getattr(side, "color", None)),
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

    for s_idx, sheet_name in enumerate(wb_formulas.sheetnames):
        ws_f = wb_formulas[sheet_name]
        ws_v = wb_values[sheet_name]

        merges = tuple(sorted(str(rng) for rng in ws_f.merged_cells.ranges))
        col_widths = {
            str(col_key).upper(): round(float(dim.width), 3)
            for col_key, dim in ws_f.column_dimensions.items()
            if dim.width is not None
        }
        row_heights = {
            str(row_key): round(float(dim.height), 3)
            for row_key, dim in ws_f.row_dimensions.items()
            if dim.height is not None
        }
        tab_rgb = _safe_rgb(getattr(ws_f.sheet_properties, "tabColor", None))
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
            }
        )

        sheet_map: dict[str, CellRecord] = {}
        for row_cells in ws_f.iter_rows():
            for cell_f in row_cells:
                if isinstance(cell_f, MergedCell):
                    continue
                raw_f_obj = cell_f.value
                style_tup = _extract_style_tuple(cell_f)
                has_non_default_style = style_tup != default_tuple
                if raw_f_obj is None and not has_non_default_style:
                    continue

                if style_tup not in style_index:
                    style_index[style_tup] = len(style_index)
                sid = style_index[style_tup]

                cell_v = ws_v.cell(row=cell_f.row, column=cell_f.column)
                cached_val = cell_v.value

                raw_formula: str | None = None
                numeric_val: float | None = None
                string_val: str | None = None
                data_type = "s"
                semantic_role = "INPUT"

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

    named_ranges: list[dict[str, Any]] = []
    for defn in wb_formulas.defined_names.values():
        named_ranges.append(
            {
                "name": str(defn.name),
                "attr_text": str(defn.attr_text or ""),
                "local_sheet_id": defn.localSheetId,
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
