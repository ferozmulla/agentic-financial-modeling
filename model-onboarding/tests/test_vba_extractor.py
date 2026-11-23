"""Tests for safe pure-Python MS-OVBA procedural macro extraction (`vba_extractor.py`)."""

from __future__ import annotations

import json
from pathlib import Path

import openpyxl
import pytest

from model_onboarding.vba_extractor import extract_vba_modules, stage_extracted_vba_modules

REPO_ROOT = Path(__file__).resolve().parents[2]
BRAZIL_SEED_XLSM = REPO_ROOT / "brazil-power-v13" / "seed" / "2023-11-27-Brazil_TT_v13_RJEB.xlsm"


def test_macro_free_xlsx_returns_empty_list(tmp_path: Path) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    assert ws is not None
    ws["A1"] = "=1+1"
    xlsx = tmp_path / "plain.xlsx"
    wb.save(xlsx)

    assert extract_vba_modules(xlsx) == []
    staged = stage_extracted_vba_modules(xlsx, tmp_path / "vba_out")
    assert len(staged) == 1
    assert json.loads(staged[0].read_text(encoding="utf-8")) == []


@pytest.mark.skipif(not BRAZIL_SEED_XLSM.exists(), reason="Brazil seed workbook not present")
def test_extracts_brazil_v13_goalseek_modules(tmp_path: Path) -> None:
    modules = extract_vba_modules(BRAZIL_SEED_XLSM)
    assert len(modules) == 3
    assert any(m.has_goalseek_or_solver for m in modules)

    all_procs = {p.lower() for m in modules for p in m.procedures}
    assert {"calculo", "calcule_tir1", "calcule_tir12", "iter_conv_gd"}.issubset(all_procs)

    out_dir = tmp_path / "staged_vba"
    files = stage_extracted_vba_modules(BRAZIL_SEED_XLSM, out_dir)
    manifest_file = out_dir / "vba_manifest.json"
    assert manifest_file in files
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert len(manifest) == len(modules)
