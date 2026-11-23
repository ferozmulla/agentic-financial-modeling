"""Tests for Stage 1 deterministic Workbook Hygiene Scanner, Exception Report & Go/No-Go Policy."""

from __future__ import annotations

import zipfile
from pathlib import Path

import openpyxl
import pytest

from model_onboarding.hygiene_gate import (
    evaluate_workbook_hygiene,
    validate_workbook_file,
    write_hygiene_gate_artifacts,
)
from model_onboarding.models import GoNoGoDecision

REPO_ROOT = Path(__file__).resolve().parents[2]
BRAZIL_SEED_XLSM = REPO_ROOT / "brazil-power-v13" / "seed" / "2023-11-27-Brazil_TT_v13_RJEB.xlsm"


def _create_clean_timeseries_xlsx(path: Path) -> Path:
    wb = openpyxl.Workbook()
    ws_in = wb.active
    assert ws_in is not None
    ws_in.title = "General_Inputs"
    for r in range(1, 22):
        ws_in.cell(row=r, column=1, value=f"Param_{r}")
        ws_in.cell(row=r, column=2, value=float(r * 10.5))

    ws_calc = wb.create_sheet("Forecast_Model")
    for idx, yr in enumerate(range(2025, 2040), start=2):
        col_let = openpyxl.utils.get_column_letter(idx)
        prev_let = openpyxl.utils.get_column_letter(idx - 1)
        ws_calc.cell(row=1, column=idx, value=yr)
        for r in range(2, 10):
            ws_calc.cell(row=r, column=idx, value=f"={col_let}$1*General_Inputs!$B${r}")
        ws_calc.cell(
            row=10,
            column=idx,
            value=f"={prev_let}10*1.02+{col_let}2" if idx > 2 else f"={col_let}2*1.05",
        )
    wb.save(path)

    # Inject cached values into XML so formulas evaluate cleanly without errors
    _inject_cached_formula_values(path, default_val="105.0")
    return path


def _inject_cached_formula_values(xlsx_path: Path, default_val: str = "100.0") -> None:
    import re

    tmp_zip = xlsx_path.with_suffix(".patched.xlsx")
    with zipfile.ZipFile(xlsx_path, "r") as zin, zipfile.ZipFile(tmp_zip, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename.startswith("xl/worksheets/sheet") and item.filename.endswith(".xml"):
                txt = data.decode("utf-8")
                txt = re.sub(r"(<f[^>]*>.*?</f>)(?!</v>)", rf"\1<v>{default_val}</v>", txt)
                data = txt.encode("utf-8")
            zout.writestr(item, data)
    tmp_zip.replace(xlsx_path)


def test_validate_workbook_file_rejects_bad_inputs(tmp_path: Path) -> None:
    bad_ext = tmp_path / "notes.txt"
    bad_ext.write_text("hello", encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported file extension"):
        validate_workbook_file(bad_ext)

    fake_xlsx = tmp_path / "fake.xlsx"
    fake_xlsx.write_bytes(b"NOT_A_ZIP_HEADER_1234")
    with pytest.raises(ValueError, match="OpenXML ZIP header"):
        validate_workbook_file(fake_xlsx)

    empty_zip = tmp_path / "empty.xlsx"
    with zipfile.ZipFile(empty_zip, "w") as zf:
        zf.writestr("readme.txt", "missing workbook.xml")
    with pytest.raises(ValueError, match="missing required OpenXML workbook"):
        validate_workbook_file(empty_zip)


def test_clean_synthetic_workbook_scores_go(tmp_path: Path) -> None:
    xlsx = _create_clean_timeseries_xlsx(tmp_path / "Clean_Solar_202601.xlsx")
    report = evaluate_workbook_hygiene(xlsx, model_slug="clean-solar-v1")

    assert report.decision == GoNoGoDecision.GO
    assert report.mes_score >= 90.0
    assert report.mdr_score <= 15.0
    assert "General_Inputs" in report.candidate_assumption_sheets
    assert "Forecast_Model" in report.candidate_timeseries_sheets

    out_dir = tmp_path / "reports"
    json_path, md_path = write_hygiene_gate_artifacts(report, out_dir)
    assert json_path.exists()
    assert md_path.exists()
    assert "`GO`" in md_path.read_text(encoding="utf-8")


def test_values_only_workbook_scores_no_go(tmp_path: Path) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "StaticOnly"
    ws["A1"] = 42.0
    xlsx = tmp_path / "values_only.xlsx"
    wb.save(xlsx)

    report = evaluate_workbook_hygiene(xlsx, model_slug="static-only")
    assert report.decision == GoNoGoDecision.NO_GO
    assert any(ex.code == "NO_FORMULAS_FOUND" and ex.severity == "BLOCKER" for ex in report.exceptions)


def test_locked_vba_and_uncached_xll_trigger_no_go(tmp_path: Path) -> None:
    xlsx = _create_clean_timeseries_xlsx(tmp_path / "LockedModel.xlsm")
    # Inject a locked DPB vbaProject.bin (>4096 bytes, no readable Sub/Function tokens)
    locked_payload = b'DPB="LOCKEDHEX"' + (b"\x00\xff" * 2500)
    patched = tmp_path / "LockedPatched.xlsm"
    with zipfile.ZipFile(xlsx, "r") as zin, zipfile.ZipFile(patched, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            zout.writestr(item, zin.read(item.filename))
        zout.writestr("xl/vbaProject.bin", locked_payload)

    report = evaluate_workbook_hygiene(patched, model_slug="locked-vba-test")
    assert report.decision == GoNoGoDecision.NO_GO
    assert any(ex.code == "LOCKED_VBA_PROJECT" for ex in report.exceptions)


def test_conditional_go_on_win32_vba_warning(tmp_path: Path) -> None:
    xlsx = _create_clean_timeseries_xlsx(tmp_path / "Win32Macro.xlsm")
    vba_stub = (
        b'Attribute VB_Name = "ModShell"\r\n'
        b"Sub RunDesktopHelper()\r\n"
        b'    Call Shell("notepad.exe")\r\n'
        b"End Sub\r\n"
    )
    patched = tmp_path / "Win32Patched.xlsm"
    with zipfile.ZipFile(xlsx, "r") as zin, zipfile.ZipFile(patched, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            zout.writestr(item, zin.read(item.filename))
        zout.writestr("xl/vbaProject.bin", vba_stub)

    report = evaluate_workbook_hygiene(patched, model_slug="win32-macro-test")
    assert report.decision == GoNoGoDecision.CONDITIONAL_GO
    assert any(ex.code == "NON_PORTABLE_VBA_HOST_CALLS" for ex in report.exceptions)


@pytest.mark.skipif(not BRAZIL_SEED_XLSM.exists(), reason="Brazil seed workbook not present")
def test_brazil_power_v13_seed_smoke_check() -> None:
    report = evaluate_workbook_hygiene(BRAZIL_SEED_XLSM, model_slug="brazil-power-smoke")
    assert report.decision == GoNoGoDecision.GO
    assert report.mes_score == pytest.approx(97.1, abs=0.2)
    assert report.mdr_score == pytest.approx(10.8, abs=0.2)
    assert len(report.vba_modules) >= 10
    assert "General" in report.candidate_assumption_sheets
