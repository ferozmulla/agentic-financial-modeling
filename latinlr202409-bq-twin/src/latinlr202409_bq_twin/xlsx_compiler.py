"""OpenXML (.xlsx) compiler extracting cells, formulas, external links, and ARIMA_PLUS trajectories."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import functools
import json
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET
import zipfile

from .models import BaselineSnapshot, TwinCell, split_a1_coord

_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_NS = {"main": _MAIN_NS}

CRUDE_ASSAY_SHEETS: tuple[str, ...] = (
    "Escalante",
    "Medanito",
    "Lula",
    "Marlim",
    "Castilla Blend",
    "Vasconia",
    "Napo",
    "Oriente",
    "Liza",
    "Unity Gold",
    "Olmeca",
    "Merey",
    "Mesa_30",
)

ACTIVE_21_SHEETS: tuple[str, ...] = (
    "Dashboard_Month",
    "Dashboard_Annual",
    "LinksOut_Month",
    "LinksOut_Annual",
    "UPLOAD - Annual",
    *CRUDE_ASSAY_SHEETS,
    "Yields",
    "LinksIn_Annual",
    "LinksIn_Monthly",
)


@dataclass
class CompiledWorkbookPayload:
  version_row: dict[str, Any]
  worksheet_rows: list[dict[str, Any]]
  style_rows: list[dict[str, Any]]
  cell_rows: list[dict[str, Any]]
  external_link_rows: list[dict[str, Any]]
  driver_trajectory_rows: list[dict[str, Any]]
  snapshot: BaselineSnapshot


@functools.lru_cache(maxsize=2)
def _cached_compile(
    xlsx_path_str: str,
    workbook_id: str,
    version_id: str,
    include_row_dicts: bool,
    sheets_subset: tuple[str, ...] | None,
) -> CompiledWorkbookPayload:
  xlsx_path = Path(xlsx_path_str)
  now_iso = datetime.now(UTC).isoformat()
  cells_by_sheet: dict[str, dict[tuple[int, int], TwinCell]] = {}
  worksheet_rows: list[dict[str, Any]] = []
  cell_rows: list[dict[str, Any]] = []
  ext_rows: list[dict[str, Any]] = []
  traj_rows: list[dict[str, Any]] = []

  with zipfile.ZipFile(xlsx_path, "r") as zf:
    sst: list[str] = []
    if "xl/sharedStrings.xml" in zf.namelist():
      sroot = ET.fromstring(zf.read("xl/sharedStrings.xml"))
      for si in sroot.findall("main:si", _NS):
        sst.append("".join(t.text or "" for t in si.findall(".//main:t", _NS)))

    wb_root = ET.fromstring(zf.read("xl/workbook.xml"))
    rels_root = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    rid_to_target = {el.attrib["Id"]: el.attrib["Target"] for el in rels_root}

    calc_el = wb_root.find("main:calcPr", _NS)
    calc_props = (
        dict(calc_el.attrib)
        if calc_el is not None
        else {"iterate": "1", "iterateCount": "1"}
    )

    total_formulas = 0
    total_cells_count = 0
    for idx, sh in enumerate(wb_root.findall(".//main:sheet", _NS), start=1):
      sname = sh.attrib["name"]
      if sname == "shooju_addin":
        continue
      if sheets_subset is not None and sname not in sheets_subset:
        continue
      rid = sh.attrib[
          "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
      ]
      target = "xl/" + rid_to_target[rid].lstrip("/")
      if target not in zf.namelist():
        continue

      sroot = ET.fromstring(zf.read(target))
      grid: dict[tuple[int, int], TwinCell] = {}
      max_r, max_c = 1, 1

      for c_el in sroot.findall(".//main:c", _NS):
        coord = c_el.attrib.get("r", "")
        if not coord:
          continue
        try:
          r_num, c_num = split_a1_coord(coord)
        except ValueError:
          continue
        if sheets_subset is not None and r_num > 520:
          continue
        max_r = max(max_r, r_num)
        max_c = max(max_c, c_num)

        t_attr = c_el.attrib.get("t", "")
        style_id = int(c_el.attrib.get("s", "0") or 0)
        f_el = c_el.find("main:f", _NS)
        v_el = c_el.find("main:v", _NS)

        raw_f = (
            f_el.text
            if f_el is not None and f_el.text
            else ("SHARED_FORMULA" if f_el is not None else None)
        )
        if f_el is not None:
          total_formulas += 1

        num_val: float | None = None
        str_val: str | None = None
        dtype = "EMPTY"

        if v_el is not None and v_el.text is not None:
          vtxt = v_el.text
          if t_attr == "s":
            s_idx = int(vtxt)
            str_val = sst[s_idx] if 0 <= s_idx < len(sst) else vtxt
            dtype = "STRING"
          elif t_attr in ("str", "e", "b"):
            str_val = vtxt
            dtype = "ERROR" if t_attr == "e" else "STRING"
          else:
            try:
              num_val = float(vtxt)
              dtype = "FORMULA" if raw_f else "NUMBER"
            except ValueError:
              str_val = vtxt
              dtype = "STRING"
        elif raw_f:
          dtype = "FORMULA"

        has_ext = bool(raw_f and "[" in raw_f and "]" in raw_f)
        role = (
            "ASSUMPTION"
            if sname in ("Dashboard_Annual", "Dashboard_Month", "Yields")
            and not raw_f
            else ("CALCULATED_KPI" if raw_f else "STATIC")
        )

        tc = TwinCell(
            sheet_name=sname,
            cell_coord=coord,
            row_num=r_num,
            col_num=c_num,
            data_type=dtype,
            numeric_value=num_val,
            string_value=str_val,
            raw_formula=raw_f,
            has_external_link=has_ext,
            style_id=style_id,
            semantic_role=role,
        )
        grid[(r_num, c_num)] = tc
        total_cells_count += 1
        if include_row_dicts:
          cell_rows.append({
              "workbook_id": workbook_id,
              "version_id": version_id,
              "sheet_name": sname,
              "cell_coord": coord,
              "row_num": r_num,
              "col_num": c_num,
              "data_type": dtype,
              "numeric_value": num_val,
              "string_value": str_val,
              "raw_formula": raw_f,
              "is_array_cse": False,
              "has_external_link": has_ext,
              "style_id": style_id,
              "semantic_role": role,
          })
          if has_ext and num_val is not None:
            ext_rows.append({
                "workbook_id": workbook_id,
                "version_id": version_id,
                "external_link_idx": "1",
                "external_workbook_name": "PeerRefiningLinks",
                "target_sheet": sname,
                "target_coord": coord,
                "target_row": r_num,
                "target_col": c_num,
                "baseline_cached_value": num_val,
                "raw_formula": raw_f or "",
            })

      cells_by_sheet[sname] = grid
      worksheet_rows.append({
          "workbook_id": workbook_id,
          "version_id": version_id,
          "sheet_index": idx,
          "sheet_name": sname,
          "visibility": sh.attrib.get("state", "visible"),
          "tab_color_rgb": None,
          "max_row": max_r,
          "max_col": max_c,
          "merged_ranges_json": "[]",
          "col_widths_json": "{}",
          "row_heights_json": "{}",
          "freeze_panes_coord": None,
          "sheet_view_json": "{}",
      })

    dash = cells_by_sheet.get("Dashboard_Annual", {})
    for row_id, series_code in (
        (12, "LATIN_CRUDE_MARKER_1"),
        (13, "LATIN_CRUDE_MARKER_2"),
        (22, "LATIN_MARGIN_BENCHMARK"),
    ):
      for col_idx in range(5, 40):
        yr = 1990 + (col_idx - 5)
        cell = dash.get((row_id, col_idx))
        if cell and cell.numeric_value is not None:
          traj_rows.append({
              "series_id": f"{workbook_id}_{series_code}",
              "series_group": "CRUDE_REFINING",
              "series_name": series_code,
              "units": "USD/bbl",
              "source_sheet": "Dashboard_Annual",
              "source_row": row_id,
              "year_date": f"{yr}-01-01",
              "year_num": yr,
              "actual_value": float(cell.numeric_value),
          })

  style_rows = [{
      "workbook_id": workbook_id,
      "version_id": version_id,
      "style_id": 0,
      "number_format": "General",
      "font_json": "{}",
      "fill_json": "{}",
      "border_json": "{}",
      "alignment_json": "{}",
  }]
  version_row = {
      "workbook_id": workbook_id,
      "version_id": version_id,
      "version_label": "Latin America Refining 202409 Baseline (Remediated)",
      "total_sheets": len(worksheet_rows),
      "total_cells": total_cells_count,
      "total_formulas": total_formulas,
      "total_external_links": len(ext_rows),
      "named_ranges_json": "[]",
      "calc_properties_json": json.dumps(calc_props),
      "created_at": now_iso,
  }
  snapshot = BaselineSnapshot(
      workbook_id=workbook_id,
      version_id=version_id,
      cells_by_sheet=cells_by_sheet,
      calc_properties=calc_props,
  )
  return CompiledWorkbookPayload(
      version_row=version_row,
      worksheet_rows=worksheet_rows,
      style_rows=style_rows,
      cell_rows=cell_rows,
      external_link_rows=ext_rows,
      driver_trajectory_rows=traj_rows,
      snapshot=snapshot,
  )


def compile_workbook(
    xlsx_path: Path,
    workbook_id: str = "latinlr202409",
    version_id: str = "lr202409_baseline",
    include_row_dicts: bool = True,
    sheets_subset: tuple[str, ...] | None = None,
) -> CompiledWorkbookPayload:
  """Compile OpenXML workbook into BigQuery rows and in-memory BaselineSnapshot."""
  return _cached_compile(
      str(Path(xlsx_path).resolve()),
      workbook_id,
      version_id,
      include_row_dicts,
      sheets_subset,
  )
