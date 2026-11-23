"""Offline numeric parity, static Yields remediation, and MCP dispatcher verification for `latinlr202409-bq-twin`."""

from __future__ import annotations

import os
from pathlib import Path

from latinlr202409_bq_twin.config import TwinSettings
from latinlr202409_bq_twin.mcp_app import create_mcp_app
from latinlr202409_bq_twin.mcp_tools import TwinMcpDispatcher
from latinlr202409_bq_twin.schema_ddl import (
    build_bqml_arima_ddl,
    build_digital_twin_ddl,
    validate_bq_identifier,
)
from latinlr202409_bq_twin.solver_engine import (
    CRUDE_TO_YIELDS_COL,
    LatinRefiningSolverEngine,
)
from latinlr202409_bq_twin.xlsx_compiler import compile_workbook
from latinlr202409_bq_twin.xlsx_synthesizer import sanitize_export_filename

_PARITY_SHEETS = (
    "Dashboard_Annual",
    "Dashboard_Month",
    "Yields",
    "LinksIn_Annual",
    "Escalante",
    "Lula",
    "Marlim",
    "Vasconia",
    "Merey",
)


def _seed_workbook_path() -> Path:
  env_p = os.environ.get("ONBOARD_SEED_WORKBOOK_PATH", "")
  if env_p and Path(env_p).exists():
    return Path(env_p)
  default_in = Path("/.agent/job/input/Latinlr202409_remediated.xlsx")
  if default_in.exists():
    return default_in
  return Path(__file__).resolve().parents[2] / "Latinlr202409_remediated.xlsx"


def test_security_and_ddl_validation() -> None:
  assert validate_bq_identifier("comm-model-mod") == "comm-model-mod"
  assert sanitize_export_filename("../evil.xlsx") == "_evil.xlsx"
  ddls = build_digital_twin_ddl("comm-model-mod", "latinlr202409_digital_twin")
  assert len(ddls) >= 8
  bqml = build_bqml_arima_ddl("comm-model-mod", "latinlr202409_digital_twin")
  assert len(bqml) == 2


def test_workbook_compilation_and_numeric_parity() -> None:
  wb_path = _seed_workbook_path()
  assert wb_path.exists(), f"Seed workbook not found at {wb_path}"
  payload = compile_workbook(
      wb_path, include_row_dicts=False, sheets_subset=_PARITY_SHEETS
  )
  assert payload.version_row["total_sheets"] == len(_PARITY_SHEETS)
  assert payload.version_row["total_cells"] > 40_000

  solver = LatinRefiningSolverEngine(payload.snapshot)
  for sheet in (
      "Dashboard_Annual",
      "Dashboard_Month",
      "Yields",
      "Escalante",
      "Lula",
      "Marlim",
      "Vasconia",
      "Merey",
  ):
    res = solver.evaluate_sheet_parity(sheet)
    assert res["compared_cells"] > 0
    assert res["mismatched_cells"] == 0, f"Parity mismatch on {sheet}: {res}"


def test_crude_fcc_gpw_sumproduct_and_mcp_dispatcher(tmp_path: Path) -> None:
  wb_path = _seed_workbook_path()
  payload = compile_workbook(
      wb_path, include_row_dicts=False, sheets_subset=_PARITY_SHEETS
  )
  settings = TwinSettings(export_local_dir=str(tmp_path))
  disp = TwinMcpDispatcher(snapshot=payload.snapshot, settings=settings)
  app = create_mcp_app(disp)
  assert app.title == "latinlr202409-bq-twin-mcp"

  summary = disp.call_tool("get_latinlr202409_model_summary", {})
  assert summary["workbook_id"] == "latinlr202409"

  data = disp.call_tool("run_latinlr202409_equilibrium_scenario", {})
  assert len(data["crude_fcc_gpw_2025_usd_bbl"]) == len(CRUDE_TO_YIELDS_COL)
  assert data["crude_fcc_gpw_2025_usd_bbl"]["Escalante"] is not None
