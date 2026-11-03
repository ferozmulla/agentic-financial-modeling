from __future__ import annotations

from pathlib import Path

from conftest import build_synthetic_xlsx

from portfolio_assessment.vba_inspector import inspect_vba_project_bytes
from portfolio_assessment.xml_inspector import normalize_formula_to_r1c1, scan_workbook_openxml


def test_r1c1_normalizer_preserves_locked_and_relative_offsets() -> None:
    sig_c10 = normalize_formula_to_r1c1("C8*$B$5+D10", base_row=10, base_col=3)
    sig_d10 = normalize_formula_to_r1c1("D8*$B$5+E10", base_row=10, base_col=4)
    assert sig_c10 == sig_d10
    assert "$B$5" in sig_c10 or "R5C2" in sig_c10


def test_shared_formula_expansion_and_time_axis_detection(tmp_path: Path) -> None:
    cells = []
    # Years 2020..2026 in C1:I1
    for offset, yr in enumerate(range(2020, 2027)):
        col_let = chr(ord("C") + offset)
        cells.append({"r": f"{col_let}1", "v": str(yr)})
    # Shared formula in C2:I2: master C2 has "=C1*1.05", slaves D2:I2 have si="0"
    cells.append({"r": "C2", "f": "C1*1.05", "f_attrs": 't="shared" ref="C2:I2" si="0"', "v": "2121"})
    for offset in range(1, 7):
        col_let = chr(ord("C") + offset)
        cells.append({"r": f"{col_let}2", "f": "", "f_attrs": 't="shared" si="0"', "v": "2200"})

    wb_path = build_synthetic_xlsx(
        tmp_path / "Model202409.xlsx",
        sheets={"Forecast": cells},
        defined_names=[("CleanName", "Forecast!$C$1:$I$1"), ("BadName", "#REF!")],
        external_links=["https://spgl.sharepoint.com/sites/Test/LR202409/Peer202409.xlsx"],
    )

    scan = scan_workbook_openxml(wb_path)
    assert scan.vintage_tag == "202409"
    assert scan.total_formula_cells == 7
    assert scan.has_time_axis is True
    assert scan.time_aligned_formula_cells == 7
    assert scan.unique_time_r1c1_patterns == 1
    assert len(scan.defined_names) == 2
    assert scan.broken_defined_names == 1


def test_vba_inspector_detects_empty_vs_procedural_and_win32() -> None:
    empty_res = inspect_vba_project_bytes(b"")
    assert empty_res.has_executable_vba is False

    clean_vba = (
        b'Attribute VB_Name = "Module1"\r\n'
        b"Sub GoalSeekLoop()\r\n"
        b'Range("B18").GoalSeek Goal:=0.12, ChangingCell:=Range("B16")\r\n'
        b"End Sub\r\n"
    )
    res_clean = inspect_vba_project_bytes(clean_vba)
    assert res_clean.has_executable_vba is True
    assert res_clean.has_win32_or_shell is False
    assert res_clean.procedural_lines >= 3

    win32_vba = (
        b'Declare PtrSafe Function GetTickCount Lib "kernel32" () As Long\r\n'
        b"Sub RunIt()\r\n"
        b'Call Shell("cmd.exe")\r\n'
        b"End Sub\r\n"
    )
    res_win32 = inspect_vba_project_bytes(win32_vba)
    assert res_win32.has_executable_vba is True
    assert res_win32.has_win32_or_shell is True
