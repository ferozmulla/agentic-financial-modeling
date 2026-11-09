"""Tests for the offline workbook-to-BigQuery Digital Twin compiler."""

from __future__ import annotations

from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill

from brazil_power_bq_twin.schema_ddl import EXPECTED_22_TABS
from brazil_power_bq_twin.xlsm_compiler import compile_workbook_to_twin_payload


def _create_synthetic_22tab_workbook(target: Path) -> Path:
    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    bold_font = Font(name="Calibri", size=11, bold=True, color="FF1F4E78")
    header_fill = PatternFill(fill_type="solid", start_color="FFD9E1F2", end_color="FFD9E1F2")

    for tab_name in EXPECTED_22_TABS:
        ws = wb.create_sheet(title=tab_name)
        ws["B2"] = f"Header — {tab_name}"
        ws["B2"].font = bold_font
        ws["B2"].fill = header_fill
        ws["B2"].alignment = Alignment(horizontal="center", wrap_text=True)
        ws.merge_cells("B2:D2")
        ws.column_dimensions["C"].width = 18.5

        if tab_name == "General":
            for col_offset in range(12):
                col_idx = 3 + col_offset
                ws.cell(row=8, column=col_idx, value=100.0 + col_offset * 10)
                c11 = ws.cell(row=11, column=col_idx, value=4000.0 + col_offset * 100)
                c11.number_format = "#,##0.00"
                ws.cell(row=14, column=col_idx, value=3.0)
                ws.cell(row=15, column=col_idx, value=25.0)
                c16 = ws.cell(row=16, column=col_idx, value=0.50)
                c16.number_format = "0.0%"
                ws.cell(row=17, column=col_idx, value=6600.0 if col_offset == 0 else 0.0)
                ws.cell(row=20, column=col_idx, value=4.50 if col_offset == 0 else 0.0)
                ws.cell(row=23, column=col_idx, value=60.0)
                ws.cell(row=24, column=col_idx, value=10.0)
                ws.cell(row=27, column=col_idx, value=4.5)
                ws.cell(row=32, column=col_idx, value=0.30)
                ws.cell(row=33, column=col_idx, value=0.70)
                ws.cell(row=34, column=col_idx, value=0.08)
                ws.cell(row=35, column=col_idx, value=16.0)
                ws.cell(row=36, column=col_idx, value=0.10)
                ws.cell(row=38, column=col_idx, value=0.34)
                ws.cell(row=40, column=col_idx, value=3.70)
            ws["C9"] = "=C8*(1-0.03)"
        elif tab_name in ("LT Capex", "LT Fuel", "LT CF"):
            for r_idx, yr in enumerate(range(2024, 2047), start=8):
                ws.cell(row=r_idx, column=1, value=yr)
                for c_idx in range(2, 11):
                    ws.cell(row=r_idx, column=c_idx, value=0.48 if tab_name == "LT CF" else 1.0)

    wb.save(target)
    wb.close()
    return target


def test_compile_workbook_extracts_cells_formulas_styles_and_solver_params(tmp_path: Path) -> None:
    wb_path = _create_synthetic_22tab_workbook(tmp_path / "synthetic_v13.xlsx")
    payload = compile_workbook_to_twin_payload(wb_path)

    assert payload.version_row["total_sheets"] == 22
    assert len(payload.worksheet_rows) == 22
    assert len(payload.style_rows) >= 2
    assert len(payload.lt_trajectory_rows) == 23 * 3

    snap = payload.snapshot
    f_cell = snap.get_cell("General", "C9")
    assert f_cell is not None
    assert f_cell.data_type == "f"
    assert f_cell.raw_formula == "C8*(1-0.03)"
    assert f_cell.semantic_role == "FORMULA"

    capex_cell = snap.get_cell("General", "C11")
    assert capex_cell is not None
    assert capex_cell.numeric_value == 4000.0
    style = snap.styles[capex_cell.style_id]
    assert style.number_format == "#,##0.00"

    gen_ws = next(w for w in snap.worksheets if w.sheet_name == "General")
    assert "B2:D2" in gen_ws.merged_ranges
    assert gen_ws.col_widths["C"] == 18.5
    assert "_01_CF" in snap.solver_parameters
    assert snap.solver_parameters["_01_CF"]["capex_brl_kw"] == 4000.0
