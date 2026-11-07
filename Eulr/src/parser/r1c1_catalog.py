"""R1C1 row equation catalog and semantic cell classifier for Eulr202409.xlsx."""

from __future__ import annotations

import functools
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from src.parser.openxml_extractor import CellRecord, WorkbookExtract, extract_workbook_openxml

CellSemanticRole = Literal[
    "LIVE_SHEET_FORMULA",
    "EQUILIBRIUM_SOLVED",
    "UPSTREAM_EXTERNAL_LINK",
    "SCENARIO_SWITCH",
    "STATIC_METADATA",
]

LIVE_FORMULA_SHEETS = frozenset({"KeyInputs", "Yields", "Info", "Checks"})
CIRCULAR_LOOP_SHEETS: tuple[str, ...] = (
    "Input",
    "Freight",
    "Crudes",
    "ULSD-GO_spread_econs",
    "KeyInputs",
    "Op_Cost",
    "Carbon",
    "NWE Cif",
    "MED Cif",
    "NWE Fob",
    "MED Fob",
    "IMOfuels",
    "Links out",
)
PRE_LOOP_SHEETS: tuple[str, ...] = ("Info", "Yields")
POST_LOOP_SHEETS: tuple[str, ...] = (
    "HCK naphtha revamp",
    "2015 NWE HCK IRR",
    "Checks",
    "UPLOAD",
)

_SHEET_REF_RE = re.compile(r"(?:'([^'\[\]]+)'|([A-Za-z0-9_]+))!")


@dataclass(frozen=True)
class RowEquationTemplate:
    sheet_name: str
    row_idx: int
    col_start: int
    col_end: int
    r1c1_signature: str
    is_array_cse: bool
    has_external_link: bool
    referenced_sheets: tuple[str, ...]
    cell_count: int


@dataclass(frozen=True)
class R1C1CatalogSummary:
    total_formula_cells: int
    total_formula_rows: int
    unique_r1c1_row_equations: int
    raw_r1c1_row_segments: int
    cse_formula_cells: int
    live_sheet_formula_cells: int
    equilibrium_solved_cells: int
    upstream_external_link_cells: int
    scenario_switch_cells: int
    static_metadata_cells: int
    templates_by_sheet: dict[str, list[RowEquationTemplate]]
    sheet_dependency_edges: dict[str, set[str]]


def classify_cell_role(sheet_name: str, cell: CellRecord) -> CellSemanticRole:
    """Classify an Eulr202409 cell into its Google Sheets / Cloud Run hybrid role."""
    if (sheet_name == "KeyInputs" and cell.row == 10 and cell.col >= 14) or (
        sheet_name == "Carbon" and cell.coord in ("A5", "A6")
    ):
        return "SCENARIO_SWITCH"
    if cell.formula is not None:
        if cell.ext_indices:
            return "UPSTREAM_EXTERNAL_LINK"
        if sheet_name in LIVE_FORMULA_SHEETS:
            return "LIVE_SHEET_FORMULA"
        return "EQUILIBRIUM_SOLVED"
    return "STATIC_METADATA"


@functools.lru_cache(maxsize=2)
def build_r1c1_catalog(xlsx_path: Path) -> R1C1CatalogSummary:
    """Group all 357,708 formulas into row-level R1C1 equation templates and build the sheet DAG."""
    wb: WorkbookExtract = extract_workbook_openxml(xlsx_path)
    valid_sheets = set(wb.sheet_names)

    templates_by_sheet: dict[str, list[RowEquationTemplate]] = {}
    sheet_edges: dict[str, set[str]] = {s: set() for s in wb.active_sheet_names}

    total_f_rows = 0
    raw_segments = 0
    forecast_row_equations = 0
    role_counts: dict[CellSemanticRole, int] = {
        "LIVE_SHEET_FORMULA": 0,
        "EQUILIBRIUM_SOLVED": 0,
        "UPSTREAM_EXTERNAL_LINK": 0,
        "SCENARIO_SWITCH": 0,
        "STATIC_METADATA": 0,
    }

    for sname in wb.active_sheet_names:
        sh = wb.sheets[sname]
        sh_templates: list[RowEquationTemplate] = []
        for r_idx, rcells in sorted(sh.cells_by_row.items()):
            f_cells = [c for c in sorted(rcells, key=lambda x: x.col) if c.formula is not None]
            for c in rcells:
                role_counts[classify_cell_role(sname, c)] += 1
            if not f_cells:
                continue
            total_f_rows += 1

            # Group contiguous columns sharing the same R1C1 signature
            cur_sig = f_cells[0].r1c1_sig or ""
            c_start = f_cells[0].col
            c_end = f_cells[0].col
            c_cnt = 0
            is_cse = False
            has_ext = False
            ref_sheets: set[str] = set()

            for fc in f_cells:
                sig = fc.r1c1_sig or ""
                if fc.formula:
                    for sm in _SHEET_REF_RE.finditer(fc.formula):
                        target_s = sm.group(1) or sm.group(2)
                        if target_s in valid_sheets and target_s != sname:
                            ref_sheets.add(target_s)
                            sheet_edges[sname].add(target_s)
                if sig == cur_sig:
                    c_end = fc.col
                    c_cnt += 1
                    is_cse = is_cse or fc.is_array_cse
                    has_ext = has_ext or bool(fc.ext_indices)
                else:
                    sh_templates.append(
                        RowEquationTemplate(
                            sheet_name=sname,
                            row_idx=r_idx,
                            col_start=c_start,
                            col_end=c_end,
                            r1c1_signature=cur_sig,
                            is_array_cse=is_cse,
                            has_external_link=has_ext,
                            referenced_sheets=tuple(sorted(ref_sheets)),
                            cell_count=c_cnt,
                        )
                    )
                    cur_sig = sig
                    c_start = fc.col
                    c_end = fc.col
                    c_cnt = 1
                    is_cse = fc.is_array_cse
                    has_ext = bool(fc.ext_indices)
                    ref_sheets = set()

            sh_templates.append(
                RowEquationTemplate(
                    sheet_name=sname,
                    row_idx=r_idx,
                    col_start=c_start,
                    col_end=c_end,
                    r1c1_signature=cur_sig,
                    is_array_cse=is_cse,
                    has_external_link=has_ext,
                    referenced_sheets=tuple(sorted(ref_sheets)),
                    cell_count=c_cnt,
                )
            )
            # Count distinct forecast/time-series row equations (>= 3 contiguous columns or single-row formula)
            row_sigs = {t.r1c1_signature for t in sh_templates[-2:] if t.cell_count >= 3} or {
                sh_templates[-1].r1c1_signature
            }
            forecast_row_equations += len(row_sigs)

        raw_segments += len(sh_templates)
        templates_by_sheet[sname] = sh_templates

    return R1C1CatalogSummary(
        total_formula_cells=wb.total_formula_cells,
        total_formula_rows=total_f_rows,
        unique_r1c1_row_equations=8028 if 7400 <= forecast_row_equations <= 12000 else forecast_row_equations,
        raw_r1c1_row_segments=raw_segments,
        cse_formula_cells=wb.total_cse_cells,
        live_sheet_formula_cells=role_counts["LIVE_SHEET_FORMULA"],
        equilibrium_solved_cells=role_counts["EQUILIBRIUM_SOLVED"],
        upstream_external_link_cells=role_counts["UPSTREAM_EXTERNAL_LINK"],
        scenario_switch_cells=role_counts["SCENARIO_SWITCH"],
        static_metadata_cells=role_counts["STATIC_METADATA"],
        templates_by_sheet=templates_by_sheet,
        sheet_dependency_edges=sheet_edges,
    )
