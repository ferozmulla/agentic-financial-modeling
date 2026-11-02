"""Extracts golden numerical parity fixtures and static context from 2023-11-27-Brazil_TT_v13_RJEB.xlsm."""

from __future__ import annotations

import hashlib
import json
import re
import zipfile
from pathlib import Path
from typing import Any

from defusedxml import ElementTree as ET

from src.core.config import get_settings
from src.core.logging import get_logger

logger = get_logger(__name__)

NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS = {"main": NS_MAIN, "r": NS_REL}

CELL_REF_RE = re.compile(r"^([A-Z]+)(\d+)$")


def col_letter_to_index(col_str: str) -> int:
    """Convert 1-based Excel column letters ('A', 'AA') to 1-based integer index."""
    result = 0
    for ch in col_str:
        result = result * 26 + (ord(ch) - ord("A") + 1)
    return result


def index_to_col_letter(col_idx: int) -> str:
    """Convert 1-based column index to Excel column letters ('A', 'AA')."""
    chars: list[str] = []
    n = col_idx
    while n > 0:
        n, rem = divmod(n - 1, 26)
        chars.append(chr(ord("A") + rem))
    return "".join(reversed(chars))


def split_coord(coord: str) -> tuple[str, int]:
    """Split 'B16' into ('B', 16)."""
    m = CELL_REF_RE.match(coord.replace("$", ""))
    if not m:
        raise ValueError(f"Invalid A1 coordinate: {coord}")
    return m.group(1), int(m.group(2))


def expand_range_coords(range_str: str) -> list[str]:
    """Expand 'E6:G12' into row-major list of A1 coordinates."""
    if ":" not in range_str:
        return [range_str.replace("$", "")]
    start_c, end_c = range_str.replace("$", "").split(":", 1)
    c1_str, r1 = split_coord(start_c)
    c2_str, r2 = split_coord(end_c)
    c1, c2 = col_letter_to_index(c1_str), col_letter_to_index(c2_str)
    coords: list[str] = []
    for r in range(r1, r2 + 1):
        for c in range(c1, c2 + 1):
            coords.append(f"{index_to_col_letter(c)}{r}")
    return coords


def extract_range_2d(
    sheet_cells: dict[str, dict[str, Any]],
    range_str: str,
) -> list[list[float | str | None]]:
    """Extract a 2D array of cached values for a rectangular range."""
    start_c, end_c = range_str.replace("$", "").split(":", 1) if ":" in range_str else (range_str, range_str)
    c1_str, r1 = split_coord(start_c)
    c2_str, r2 = split_coord(end_c)
    c1, c2 = col_letter_to_index(c1_str), col_letter_to_index(c2_str)
    grid: list[list[float | str | None]] = []
    for r in range(r1, r2 + 1):
        row_vals: list[float | str | None] = []
        for c in range(c1, c2 + 1):
            coord = f"{index_to_col_letter(c)}{r}"
            cell_info = sheet_cells.get(coord)
            val = cell_info["value"] if cell_info is not None else None
            row_vals.append(val)
        grid.append(row_vals)
    return grid


def extract_range_flat(
    sheet_name: str,
    sheet_cells: dict[str, dict[str, Any]],
    range_str: str,
) -> dict[str, float | str]:
    """Extract a flat {'Sheet!Coord': value} dictionary for a rectangular range."""
    out: dict[str, float | str] = {}
    for coord in expand_range_coords(range_str):
        cell_info = sheet_cells.get(coord)
        if cell_info is not None and cell_info["value"] is not None:
            out[f"{sheet_name}!{coord}"] = cell_info["value"]
    return out


def parse_workbook_xml(xlsm_path: Path) -> dict[str, Any]:
    """Fast OpenXML ZIP parser reading all 22 sheets, shared strings, formulas, and cached values."""
    raw_bytes = xlsm_path.read_bytes()
    sha256_hash = hashlib.sha256(raw_bytes).hexdigest()

    with zipfile.ZipFile(xlsm_path, "r") as zf:
        # 1. Shared Strings
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in zf.namelist():
            sst_xml = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in sst_xml.findall("main:si", NS):
                parts = [t.text or "" for t in si.findall(".//main:t", NS)]
                shared_strings.append("".join(parts))

        # 2. Workbook sheets & relationships
        wb_xml = ET.fromstring(zf.read("xl/workbook.xml"))
        rels_xml = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        rid_to_target = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels_xml}

        sheets_data: dict[str, dict[str, dict[str, Any]]] = {}
        sheet_order: list[str] = []
        total_populated = 0
        total_raw_f_tags = 0

        for sheet_el in wb_xml.findall(".//main:sheet", NS):
            sname = sheet_el.attrib["name"]
            rid = sheet_el.attrib[f"{{{NS_REL}}}id"]
            target = rid_to_target[rid].lstrip("/")
            if not target.startswith("xl/"):
                target = f"xl/{target}"
            sheet_order.append(sname)
            s_xml = ET.fromstring(zf.read(target))
            cells_map: dict[str, dict[str, Any]] = {}

            for c_el in s_xml.findall(".//main:c", NS):
                coord = c_el.attrib["r"]
                t_attr = c_el.attrib.get("t", "n")
                f_el = c_el.find("main:f", NS)
                v_el = c_el.find("main:v", NS)
                is_el = c_el.find("main:is", NS)

                has_f = f_el is not None
                f_text = f_el.text if f_el is not None else None
                f_type = f_el.attrib.get("t") if f_el is not None else None
                f_si = f_el.attrib.get("si") if f_el is not None else None
                f_ref = f_el.attrib.get("ref") if f_el is not None else None

                if has_f:
                    total_raw_f_tags += 1

                val: float | str | None = None
                if v_el is not None and v_el.text is not None:
                    raw_v = v_el.text
                    if t_attr == "s":
                        idx = int(raw_v)
                        val = shared_strings[idx] if 0 <= idx < len(shared_strings) else raw_v
                    elif t_attr in ("str", "e"):
                        val = raw_v
                    elif t_attr == "b":
                        val = "TRUE" if raw_v == "1" else "FALSE"
                    else:
                        try:
                            val = float(raw_v)
                        except ValueError:
                            val = raw_v
                elif is_el is not None:
                    val = "".join(t.text or "" for t in is_el.findall(".//main:t", NS))

                total_populated += 1
                cells_map[coord] = {
                    "value": val,
                    "formula": f_text,
                    "f_type": f_type,
                    "si": int(f_si) if f_si is not None else None,
                    "ref": f_ref,
                    "t": t_attr,
                }
            sheets_data[sname] = cells_map

    return {
        "sha256_hash": sha256_hash,
        "sheet_order": sheet_order,
        "total_populated_cells": total_populated,
        "total_raw_f_tags": total_raw_f_tags,
        "sheets_data": sheets_data,
    }


def build_baseline_fixture(xlsm_path: Path) -> dict[str, Any]:
    """Construct the complete golden baseline fixture dictionary from the seed .xlsm file."""
    parsed = parse_workbook_xml(xlsm_path)
    sheets = parsed["sheets_data"]

    macros: dict[str, dict[str, Any]] = {}
    unique_baseline_outputs: dict[str, float] = {}

    # 1. Tornado IRR macros: calcule_tir1..12 (234 cells)
    for i in range(1, 13):
        mname = f"calcule_tir{i}"
        sname = f"_{i:02d}_CF"
        rng = "E6:G9" if i >= 11 else "E6:G12"
        flat = extract_range_flat(sname, sheets[sname], rng)
        grid = extract_range_2d(sheets[sname], rng)
        macros[mname] = {
            "macro_name": mname,
            "target_sheet": sname,
            "target_range": rng,
            "solve_count": 12 if i >= 11 else 21,
            "values_2d": grid,
            "flat_outputs": flat,
        }
        for k, v in flat.items():
            if isinstance(v, (int, float)):
                unique_baseline_outputs[k] = float(v)

    # 2. 1D Fuel / CVU sweep macros: calculo_cvu1..12 (102 cells)
    for i in range(1, 13):
        mname = f"calculo_cvu{i}"
        sname = f"_{i:02d}_CF"
        rng = "B16" if i >= 11 else "C70:C79"
        flat = extract_range_flat(sname, sheets[sname], rng)
        grid = extract_range_2d(sheets[sname], rng)
        macros[mname] = {
            "macro_name": mname,
            "target_sheet": sname,
            "target_range": rng,
            "solve_count": 1 if i >= 11 else 10,
            "values_2d": grid,
            "flat_outputs": flat,
        }
        for k, v in flat.items():
            if isinstance(v, (int, float)):
                unique_baseline_outputs[k] = float(v)

    # 3. 6 Specialized 1D & 2D sensitivity macros + lcoe_forecast + fator_i (482 cells)
    specialized_specs = [
        ("calculo_capexvscf", "_05_CF", "G84:G93", 10),
        ("calculo_priceirr", "_06_CF", "B88:F97", 50),
        ("calculo_cvu2bi", "_02_CF", "E70:N79", 100),
        ("calculo_cvu4bi", "_04_CF", "E70:N79", 100),
        ("calculo_capexvscfbi", "_05_CF", "C99:L108", 100),
        ("calculo_priceirr_bi", "_06_CF", "C105:L114", 100),
        ("lcoe_forecast", "_05_CF", "U71:U82", 12),
        ("fator_i", "_01_CF", "G70:G79", 10),
    ]
    for mname, sname, rng, scount in specialized_specs:
        flat = extract_range_flat(sname, sheets[sname], rng)
        grid = extract_range_2d(sheets[sname], rng)
        macros[mname] = {
            "macro_name": mname,
            "target_sheet": sname,
            "target_range": rng,
            "solve_count": scount,
            "values_2d": grid,
            "flat_outputs": flat,
        }
        for k, v in flat.items():
            if isinstance(v, (int, float)):
                unique_baseline_outputs[k] = float(v)

    # 4. Master 23-year, 8-technology forecast: lcoe_exec (184 cells on Output_3)
    o3_flat: dict[str, float | str] = {}
    for col in ("B", "C", "E", "F", "G", "H", "I", "J"):
        col_flat = extract_range_flat("Output_3", sheets["Output_3"], f"{col}9:{col}31")
        o3_flat.update(col_flat)
        for k, v in col_flat.items():
            if isinstance(v, (int, float)):
                unique_baseline_outputs[k] = float(v)

    macros["lcoe_exec"] = {
        "macro_name": "lcoe_exec",
        "target_sheet": "Output_3",
        "target_range": "B9:J31",
        "solve_count": 184,
        "values_2d": extract_range_2d(sheets["Output_3"], "B9:J31"),
        "flat_outputs": o3_flat,
        "timestamp_b3": sheets["Output_3"].get("B3", {}).get("value"),
    }

    # 5. Helper routines (rst_scenario + 4 internal convergence helpers)
    rst_flat: dict[str, float | str] = {}
    for i in range(1, 13):
        sname = f"_{i:02d}_CF"
        max_r = 9 if i >= 11 else 12
        for r in range(6, max_r + 1):
            c_val = sheets[sname].get(f"C{r}", {}).get("value")
            if isinstance(c_val, (int, float)):
                rst_flat[f"{sname}!H{r}"] = float(c_val)
    macros["rst_scenario"] = {
        "macro_name": "rst_scenario",
        "target_sheet": "_01_CF.._12_CF",
        "target_range": "H6:H12",
        "solve_count": 12,
        "values_2d": [],
        "flat_outputs": rst_flat,
    }

    for helper_name, target_irr, step_p, tol in [
        ("iter_conv", 0.080001, 0.0, 1e-6),
        ("iter_refining", 0.12, 0.001, 1e-5),
        ("iter_conv_gd", 0.12001, 0.0, 1e-6),
        ("iter_refining_gd", 0.12, 0.001, 1e-5),
    ]:
        macros[helper_name] = {
            "macro_name": helper_name,
            "target_sheet": "_01_CF",
            "target_range": "B16",
            "solve_count": 1,
            "target_irr": target_irr,
            "step_p": step_p,
            "tolerance": tol,
            "flat_outputs": {"_01_CF!B16": float(sheets["_01_CF"]["B16"]["value"])},
        }

    # 6. Extract static context for General, LT sheets, CVU_GF, and _01_CF.._12_CF
    sheet_Parameters: dict[str, Any] = {}
    for i in range(1, 13):
        sname = f"_{i:02d}_CF"
        scells = sheets[sname]
        cf_row = 42 if i >= 11 else 63
        end_col = "AF" if i >= 11 else ("AT" if i in (1, 7, 8, 10) else "AR")
        cf_coords = expand_range_coords(f"B{cf_row}:{end_col}{cf_row}")
        cf_vector = [float(scells.get(c, {}).get("value") or 0.0) for c in cf_coords]
        sheet_Parameters[sname] = {
            "b16_price": float(scells.get("B16", {}).get("value") or 0.0),
            "c16_fxd_rev": scells.get("C16", {}).get("value"),
            "b17_gen": float(scells.get("B17", {}).get("value") or 0.0),
            "b18_irr": float(scells.get("B18", {}).get("value") or 0.0),
            "cf_row": cf_row,
            "cf_end_col": end_col,
            "baseline_cf_vector": cf_vector,
            "tornado_inputs_b6_d12": extract_range_2d(scells, "B6:D9" if i >= 11 else "B6:D12"),
            "active_scenario_h6_h12": [
                scells.get(f"H{r}", {}).get("value") for r in range(6, 10 if i >= 11 else 13)
            ],
            "cvu_inputs_b70_b79": [
                scells.get(f"B{r}", {}).get("value") for r in range(70, 80)
            ] if i <= 10 else [],
        }

    return {
        "workbook_metadata": {
            "filename": xlsm_path.name,
            "sha256_hash": parsed["sha256_hash"],
            "sheet_order": parsed["sheet_order"],
            "sheet_count": len(parsed["sheet_order"]),
            "total_populated_cells": parsed["total_populated_cells"],
            "total_raw_f_tags": parsed["total_raw_f_tags"],
            "ported_routine_count": len(macros),
        },
        "general_c5_n40": extract_range_2d(sheets["General"], "C5:N40"),
        "lt_capex_b8_j30": extract_range_2d(sheets["LT Capex"], "B8:J30"),
        "lt_fuel_b8_j30": extract_range_2d(sheets["LT Fuel"], "B8:J30"),
        "lt_cf_b8_j30": extract_range_2d(sheets["LT CF"], "B8:J30"),
        "sheet_parameters": sheet_Parameters,
        "macros": macros,
        "unique_baseline_outputs": unique_baseline_outputs,
    }


def main() -> None:
    """Extract baseline fixture JSON from seed workbook."""
    settings = get_settings()
    xlsm_path = settings.seed_workbook_path
    out_path = settings.baseline_fixture_path
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fixture = build_baseline_fixture(xlsm_path)
    out_path.write_text(json.dumps(fixture, indent=2), encoding="utf-8")
    logger.info(
        "Extracted baseline parity fixture",
        extra={
            "structured_data": {
                "fixture_path": str(out_path),
                "sheet_count": fixture["workbook_metadata"]["sheet_count"],
                "total_populated_cells": fixture["workbook_metadata"]["total_populated_cells"],
                "ported_routine_count": fixture["workbook_metadata"]["ported_routine_count"],
                "unique_output_cells": len(fixture["unique_baseline_outputs"]),
            }
        },
    )


if __name__ == "__main__":
    main()
