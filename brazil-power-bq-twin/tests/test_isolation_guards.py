"""Strict isolation, zero-Excel-file, and BigQuery DDL tests for brazil-power-bq-twin."""

from __future__ import annotations

import ast
from pathlib import Path

from brazil_power_bq_twin.config import get_twin_settings
from brazil_power_bq_twin.models import col_letter_to_index, index_to_col_letter, split_a1_coord
from brazil_power_bq_twin.schema_ddl import EXPECTED_22_TABS, build_digital_twin_ddl_statements

TWIN_ROOT = Path(__file__).resolve().parents[1]


def test_zero_excel_files_and_zero_cross_package_imports() -> None:
    excel_files = [
        p
        for p in TWIN_ROOT.rglob("*")
        if p.is_file() and p.suffix.lower() in {".xlsm", ".xlsx", ".xls", ".xlsb"}
    ]
    assert excel_files == [], f"Forbidden Excel files found in brazil-power-bq-twin: {excel_files}"

    dockerfile_text = (TWIN_ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "seed/" not in dockerfile_text
    assert ".xlsm" not in dockerfile_text

    forbidden_roots = {"src", "brazil_power_agent"}
    for py_file in (TWIN_ROOT / "src").rglob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in forbidden_roots
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] not in forbidden_roots


def test_settings_coords_and_ddl_generation() -> None:
    settings = get_twin_settings()
    assert settings.bq_dataset == "brazil_power_digital_twin"
    assert settings.max_bytes_billed == 50 * 1024 * 1024
    assert len(EXPECTED_22_TABS) == 22
    assert split_a1_coord("$C$20") == ("C", 20)
    assert index_to_col_letter(col_letter_to_index("AN")) == "AN"

    ddls = build_digital_twin_ddl_statements("comm-model-mod", "brazil_power_digital_twin")
    joined = "\n".join(ddls)
    for obj_name in (
        "dt_workbook_versions",
        "dt_worksheets",
        "dt_styles",
        "dt_cells",
        "dt_scenario_deltas",
        "vw_dt_latest_session_deltas",
        "dt_audit_events",
        "dt_lt_trajectories",
    ):
        assert f"`comm-model-mod.brazil_power_digital_twin.{obj_name}`" in joined
    assert "CLUSTER BY" in joined
    assert "PARTITION BY DATE(" in joined
