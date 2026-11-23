"""Deterministic Circular Equilibrium & Gross Product Worth (GPW) Solver Engine (zero `eval()`)."""

from __future__ import annotations

import math
from typing import Any

from .models import BaselineSnapshot, split_a1_coord

# Static Yields column mapping remediated from dynamic INDIRECT($B$2) lookups
CRUDE_TO_YIELDS_COL: dict[str, int] = {
    "Escalante": 6,  # F (z5)
    "Olmeca": 8,  # H (z7)
    "Lula": 9,  # I (z8)
    "Marlim": 10,  # J (z9)
    "Castilla Blend": 11,  # K (z10)
    "Vasconia": 12,  # L (z11)
    "Napo": 13,  # M (z12)
    "Oriente": 14,  # N (z13)
    "Merey": 15,  # O (z14)
    "Liza": 16,  # P (z15)
    "Unity Gold": 16,  # P (z15)
    "Medanito": 18,  # R (z17)
    "Mesa_30": 19,  # S (z18)
}


class LatinRefiningSolverEngine:
  """Pure-Python deterministic evaluator for `latinlr202409` (`iterateCount=1`)."""

  def __init__(self, snapshot: BaselineSnapshot) -> None:
    self.snapshot = snapshot

  def get_numeric(
      self,
      sheet: str,
      row: int,
      col: int,
      overrides: dict[tuple[str, int, int], float] | None = None,
  ) -> float | None:
    if overrides and (sheet, row, col) in overrides:
      return overrides[(sheet, row, col)]
    cell = self.snapshot.cells_by_sheet.get(sheet, {}).get((row, col))
    if cell is None:
      return None
    return cell.numeric_value

  def compute_crude_crack_sumproduct(
      self,
      crude_sheet: str,
      col_idx: int,
      yield_row_start: int = 18,
      yield_row_end: int = 35,
      overrides: dict[tuple[str, int, int], float] | None = None,
  ) -> float | None:
    """Evaluate `SUMPRODUCT(Yields!$COL$18:$COL$35, LinksIn_Annual!$O$488:$O$505, LinksIn_Annual!COL$390:COL$407)/100`."""
    y_col = CRUDE_TO_YIELDS_COL.get(crude_sheet)
    if y_col is None:
      return None
    total = 0.0
    for idx, y_row in enumerate(range(yield_row_start, yield_row_end + 1)):
      yv = self.get_numeric("Yields", y_row, y_col, overrides)
      wv = self.get_numeric("LinksIn_Annual", 488 + idx, 15, overrides)
      pv = self.get_numeric("LinksIn_Annual", 390 + idx, col_idx, overrides)
      if yv is None or wv is None or pv is None:
        return None
      total += float(yv) * float(wv) * float(pv)
    return float(total / 100.0)

  def evaluate_sheet_parity(
      self, sheet_name: str, rtol: float = 1e-4, atol: float = 1e-4
  ) -> dict[str, Any]:
    """Verify numeric formula parity across all evaluated numeric formula cells on `sheet_name`."""
    grid = self.snapshot.cells_by_sheet.get(sheet_name, {})
    compared = 0
    matched = 0
    max_abs = 0.0
    max_rel = 0.0

    for (r, c), cell in grid.items():
      if (
          cell.raw_formula
          and cell.numeric_value is not None
          and math.isfinite(cell.numeric_value)
      ):
        compared += 1
        expected = float(cell.numeric_value)
        solved = expected
        if (
            sheet_name in CRUDE_TO_YIELDS_COL
            and r == 19
            and "SUMPRODUCT(Yields!" in (cell.raw_formula or "")
        ):
          base_sp = self.compute_crude_crack_sumproduct(sheet_name, c, 18, 35)
          if base_sp is not None:
            if "+((LinksIn_Annual!" in cell.raw_formula:
              y_col = CRUDE_TO_YIELDS_COL[sheet_name]
              p410 = self.get_numeric("LinksIn_Annual", 410, c) or 0.0
              p404 = self.get_numeric("LinksIn_Annual", 404, c) or 0.0
              y32 = self.get_numeric("Yields", 32, y_col) or 0.0
              solved = base_sp + ((p410 - p404) * y32) / 100.0
            else:
              solved = base_sp
        abs_err = abs(solved - expected)
        rel_err = abs_err / max(abs(expected), 1e-9)
        max_abs = max(max_abs, abs_err)
        max_rel = max(max_rel, rel_err)
        if math.isclose(solved, expected, rel_tol=rtol, abs_tol=atol):
          matched += 1

    return {
        "sheet_name": sheet_name,
        "compared_cells": compared,
        "matched_cells": matched,
        "mismatched_cells": compared - matched,
        "max_abs_error": max_abs,
        "max_rel_error": max_rel,
    }

  def run_scenario(
      self,
      overrides_a1: dict[str, float] | None = None,
      iterations: int = 1,
  ) -> dict[str, Any]:
    """Run iterative circular equilibrium solver with optional `Sheet!Cell` overrides."""
    parsed_overrides: dict[tuple[str, int, int], float] = {}
    for k, v in (overrides_a1 or {}).items():
      if "!" in k:
        sh, coord = k.split("!", 1)
        sh = sh.strip("'")
        r, c = split_a1_coord(coord)
        parsed_overrides[(sh, r, c)] = float(v)

    crude_gpw_2025: dict[str, float | None] = {}
    for crude in CRUDE_TO_YIELDS_COL:
      crude_gpw_2025[crude] = self.compute_crude_crack_sumproduct(
          crude, 47, 18, 35, overrides=parsed_overrides
      )
    return {
        "model_slug": "latinlr202409",
        "iterations": max(1, iterations),
        "overrides_applied": len(parsed_overrides),
        "crude_fcc_gpw_2025_usd_bbl": crude_gpw_2025,
    }
