"""Tests for pure database-to-.xlsx and Google Sheets 22-tab synthesis (zero template file)."""

from __future__ import annotations

import io
from pathlib import Path

import openpyxl
import pytest

from brazil_power_bq_twin.bq_store import InMemoryDigitalTwinStore
from brazil_power_bq_twin.models import CellDelta
from brazil_power_bq_twin.schema_ddl import EXPECTED_22_TABS
from brazil_power_bq_twin.xlsm_compiler import compile_workbook_to_twin_payload
from brazil_power_bq_twin.xlsx_synthesizer import (
    export_digital_twin_workbook,
    sanitize_filename,
    synthesize_22tab_xlsx_bytes,
)

from test_xlsm_compiler import _create_synthetic_22tab_workbook


def test_synthesize_22tab_xlsx_from_database_rows_without_template(tmp_path: Path) -> None:
    src_wb = _create_synthetic_22tab_workbook(tmp_path / "ingest_only.xlsx")
    snap = compile_workbook_to_twin_payload(src_wb).snapshot
    # Delete the source file BEFORE synthesis to prove zero template dependency!
    src_wb.unlink()
    assert not src_wb.exists()

    store = InMemoryDigitalTwinStore(snap)
    store.append_session_deltas(
        "s_synth",
        [
            CellDelta(
                sheet_name="General",
                cell_coord="C20",
                row_num=20,
                col_num=3,
                delta_kind="USER_OVERRIDE",
                numeric_value=6.75,
                source_tool="update_session_assumptions",
            )
        ],
    )
    overlay = store.get_session_overlay("s_synth")
    xlsx_bytes, stats = synthesize_22tab_xlsx_bytes(snap, overlay)

    assert stats["sheet_count"] == 22
    assert stats["template_files_used"] == 0

    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes), data_only=False)
    assert tuple(wb.sheetnames) == EXPECTED_22_TABS
    gen = wb["General"]
    # Overridden input cell gets delta value
    assert gen["C20"].value == 6.75
    # Untouched formula cell preserves its live Excel formula!
    assert gen["C9"].value == "=C8*(1-0.03)"
    # Styles, number formats, merges, and column widths are reconstructed from DB metadata
    assert gen["C11"].number_format == "#,##0.00"
    assert gen["B2"].font.bold is True
    assert "B2:D2" in [str(r) for r in gen.merged_cells.ranges]
    assert abs(gen.column_dimensions["C"].width - 18.5) < 0.01
    wb.close()

    res = export_digital_twin_workbook(
        store=store,
        session_id="s_synth",
        export_format="xlsx",
        output_filename="Twin_Synthesized_Test",
        output_dir=tmp_path,
    )
    assert Path(res["xlsx_path"]).is_file()
    assert res["tabs_preserved"] == 22

    with pytest.raises(ValueError):
        sanitize_filename("../evil.xlsx", ".xlsx")


def test_theme_and_indexed_colors_never_render_black_fill(tmp_path: Path) -> None:
    src_wb_path = _create_synthetic_22tab_workbook(tmp_path / "theme_colors.xlsx")
    wb_edit = openpyxl.load_workbook(src_wb_path)
    gen = wb_edit["General"]
    # Simulate Excel theme=0 (white) solid fill on D10 and theme=0 tint=-0.15 (light gray) on C5
    gen["D10"].fill = openpyxl.styles.PatternFill(
        fill_type="solid",
        fgColor=openpyxl.styles.colors.Color(theme=0, tint=0.0),
    )
    gen["C5"].fill = openpyxl.styles.PatternFill(
        fill_type="solid",
        fgColor=openpyxl.styles.colors.Color(rgb="FF002060"),
    )
    gen["C5"].font = openpyxl.styles.Font(
        name="Arial",
        size=9,
        bold=True,
        color=openpyxl.styles.colors.Color(indexed=9),
    )
    wb_edit["Version Control"]["B3"].fill = openpyxl.styles.PatternFill(
        fill_type="solid",
        fgColor=openpyxl.styles.colors.Color(theme=0, tint=-0.15),
    )
    wb_edit.save(src_wb_path)
    wb_edit.close()

    snap = compile_workbook_to_twin_payload(src_wb_path).snapshot
    src_wb_path.unlink()

    store = InMemoryDigitalTwinStore(snap)
    xlsx_bytes, _ = synthesize_22tab_xlsx_bytes(snap, store.get_session_overlay("theme_s1"))
    out_wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes))

    # D10 must be opaque white FFFFFFFF (or unfilled), never 00000000 black
    d10_rgb = out_wb["General"]["D10"].fill.start_color.rgb
    assert d10_rgb in ("FFFFFFFF", None), f"Unexpected D10 fill rgb: {d10_rgb}"

    # C5 indexed=9 font must be opaque white FFFFFFFF on dark navy FF002060
    assert out_wb["General"]["C5"].fill.start_color.rgb == "FF002060"
    assert out_wb["General"]["C5"].font.color.rgb == "FFFFFFFF"

    # Version Control!B3 theme=0 tint=-0.15 must resolve to light gray FFD9D9D9
    vc_b3_rgb = out_wb["Version Control"]["B3"].fill.start_color.rgb
    assert vc_b3_rgb == "FFD9D9D9"
    out_wb.close()

