from __future__ import annotations

from pathlib import Path

from conftest import build_synthetic_xlsx

from portfolio_assessment.extractability import compute_extractability_pillar
from portfolio_assessment.hygiene import compute_hygiene_pillar
from portfolio_assessment.reference_resolver import resolve_workbook_external_links
from portfolio_assessment.xml_inspector import scan_workbook_openxml


def test_extractability_penalizes_xll_sjpoint_and_marks_absent_vba_na(tmp_path: Path) -> None:
    cells = [
        {"r": "C1", "v": "2020"},
        {"r": "D1", "v": "2021"},
        {"r": "E1", "v": "2022"},
        {"r": "F1", "v": "2023"},
        {"r": "G1", "v": "2024"},
        {"r": "H1", "v": "2025"},
        {"r": "C2", "f": '_xll.sjpoint("SERIES_A")', "v": "42.5"},
        {"r": "D2", "f": '_xll.sjpoint("SERIES_A")', "v": "43.1"},
        {"r": "E2", "f": "SUM(C2:D2)", "v": "85.6"},
        {"r": "F2", "f": 'INDIRECT("C2")', "v": "42.5"},
        {"r": "G2", "f": "SUM(C2:E2)", "v": "128.1"},
        {"r": "H2", "f": "SUM(C2:F2)", "v": "170.6"},
    ]
    p = build_synthetic_xlsx(tmp_path / "XllModel.xlsx", sheets={"Data": cells})
    scan = scan_workbook_openxml(p)
    les, stats = compute_extractability_pillar(scan)
    by_code = {s.code: s for s in les.sub_metrics}

    assert stats["xll_udf_cells"] == 2
    assert stats["opaque_cells"] == 1
    assert by_code["E2"].applicable is False  # No VBA -> N/A
    assert by_code["E4"].applicable is False  # No ext links -> N/A
    # E1 credits: 2*0.5 + 1*0.0 + 3*1.0 = 4.0 / 6 = 66.67%
    assert 66.0 <= (by_code["E1"].score or 0.0) <= 67.0


def test_hygiene_excludes_intentional_na_and_detects_hardcoded_drag_islands_and_fill_glitch(
    tmp_path: Path,
) -> None:
    cells = []
    # Header years C1:K1 (9 cols)
    for idx, yr in enumerate(range(2020, 2029)):
        col_let = chr(ord("C") + idx)
        cells.append({"r": f"{col_let}1", "v": str(yr)})

    # Row 2: Shared R1C1 formula C1*2 across C2:K2, EXCEPT F2 is overwritten with hardcoded "999" (island!)
    for idx in range(9):
        col_let = chr(ord("C") + idx)
        if col_let == "F":
            cells.append({"r": "F2", "v": "999"})
        else:
            cells.append({"r": f"{col_let}2", "f": f"{col_let}1*2", "v": "4040"})

    # Row 3: Fill-handle +1.0 auto-increment glitch on decimals (0.25, 1.25, 2.25, 3.25, 4.25)
    for idx in range(5):
        col_let = chr(ord("C") + idx)
        cells.append({"r": f"{col_let}3", "v": str(0.25 + idx)})

    # Row 4: Intentional chart NA() vs genuine #VALUE! error
    cells.append({"r": "C4", "t": "e", "f": "NA()", "v": "#N/A"})
    cells.append({"r": "D4", "t": "e", "f": "IF(D1>2030,NA(),D2)", "v": "#N/A"})
    cells.append({"r": "E4", "t": "e", "f": 'E2+"bad_text"', "v": "#VALUE!"})

    p = build_synthetic_xlsx(tmp_path / "DirtyHygiene.xlsx", sheets={"Model": cells})
    scan = scan_workbook_openxml(p)
    audits = resolve_workbook_external_links(scan)
    mhs, defects, hstats = compute_hygiene_pillar(scan, audits)

    defect_types = {d.defect_type for d in defects}
    assert "HARDCODED_ISLAND_IN_FORMULA_RUN" in defect_types
    assert "AUTO_INCREMENT_FILL_GLITCH" in defect_types
    assert "EVALUATED_CELL_ERROR" in defect_types
    # Only E4 (#VALUE!) is counted as an unintentional error; C4 and D4 (NA()) are excluded!
    assert hstats["unintentional_error_cells"] == 1
    assert hstats["intentional_na_cells"] == 2
    assert mhs.score < 95.0
