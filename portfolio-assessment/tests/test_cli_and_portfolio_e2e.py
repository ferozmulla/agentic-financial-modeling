from __future__ import annotations

from pathlib import Path

from conftest import build_synthetic_xlsx

from portfolio_assessment.cli import main
from portfolio_assessment.scorer import discover_workbooks


def test_discover_workbooks_deduplicates_older_vintages_by_default(tmp_path: Path) -> None:
    build_synthetic_xlsx(tmp_path / "Callr202406.xlsx", sheets={"S1": [{"r": "A1", "v": "1"}]})
    build_synthetic_xlsx(tmp_path / "Callr202409.xlsx", sheets={"S1": [{"r": "A1", "v": "1"}]})
    build_synthetic_xlsx(tmp_path / "Latinlr202409 3Q.xlsx", sheets={"S1": [{"r": "A1", "v": "1"}]})
    build_synthetic_xlsx(tmp_path / "Latinlr202409.xlsx", sheets={"S1": [{"r": "A1", "v": "1"}]})

    deduped = [p.name for p in discover_workbooks([tmp_path], include_all_vintages=False)]
    assert "Callr202409.xlsx" in deduped
    assert "Callr202406.xlsx" not in deduped
    assert "Latinlr202409.xlsx" in deduped
    assert "Latinlr202409 3Q.xlsx" not in deduped

    all_files = [p.name for p in discover_workbooks([tmp_path], include_all_vintages=True)]
    assert len(all_files) == 4


def test_cli_generates_markdown_and_csv_reports_across_synthetic_and_seed_models(
    tmp_path: Path,
) -> None:
    models_dir = tmp_path / "models"
    out_dir = tmp_path / "reports"
    models_dir.mkdir()

    # Clean Tier 1 model vs dirty XLL Tier 3 model
    clean_cells = [{"r": f"{chr(67+i)}1", "v": str(2020 + i)} for i in range(6)] + [
        {"r": f"{chr(67+i)}2", "f": f"{chr(67+i)}1*1.1", "v": "2200"} for i in range(6)
    ]
    build_synthetic_xlsx(models_dir / "CleanModel202409.xlsx", sheets={"Main": clean_cells})

    dirty_cells = [{"r": f"{chr(67+i)}1", "v": str(2020 + i)} for i in range(6)] + [
        {"r": f"{chr(67+i)}2", "t": "e", "f": '_xll.sjpoint("X")', "v": "#VALUE!"}
        for i in range(6)
    ]
    build_synthetic_xlsx(models_dir / "DirtyXll202409.xlsx", sheets={"Main": dirty_cells})

    rc = main(["--scan-dirs", str(models_dir), "--output-dir", str(out_dir)])
    assert rc == 0

    md_file = out_dir / "portfolio_executive_scorecard.md"
    csv_file = out_dir / "portfolio_scorecard.csv"
    defects_file = out_dir / "portfolio_cell_defects.csv"
    links_file = out_dir / "portfolio_external_links_audit.csv"

    assert md_file.exists()
    assert csv_file.exists()
    assert defects_file.exists()
    assert links_file.exists()

    md_text = md_file.read_text(encoding="utf-8")
    assert "Logic Extractability Score" in md_text or "LES" in md_text
    assert "CleanModel202409.xlsx" in md_text
    assert "DirtyXll202409.xlsx" in md_text
