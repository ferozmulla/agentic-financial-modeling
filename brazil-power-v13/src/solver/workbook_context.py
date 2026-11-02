"""Pre-warmed WorkbookSolverContext holding baseline parameters, LT curves, and scenario state."""

from __future__ import annotations

import copy
import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any, ClassVar

from src.cli.extract_baseline_fixtures import build_baseline_fixture
from src.core.config import get_settings
from src.schemas.solver import GeneralOverrides


def cells_differ(val_a: Any, val_b: Any, rel_tol: float = 1e-6) -> bool:
    """Compare two spreadsheet cell values, treating None and '' as equal and tolerating float roundoff."""
    empty_a = val_a is None or val_a == ""
    empty_b = val_b is None or val_b == ""
    if empty_a and empty_b:
        return False
    if empty_a != empty_b:
        return True
    if isinstance(val_a, (int, float)) and isinstance(val_b, (int, float)):
        fa, fb = float(val_a), float(val_b)
        return abs(fa - fb) > max(abs(fb) * rel_tol, 1e-7)
    return str(val_a).strip() != str(val_b).strip()


class WorkbookSolverContext:
    """In-memory quantitative model context for all 12 _XX_CF sheets, General, CVU_GF, and LT curves."""

    THERMAL_SHEETS = frozenset({"_01_CF", "_07_CF", "_08_CF", "_09_CF", "_10_CF"})
    RENEWABLE_SHEETS = frozenset({"_02_CF", "_03_CF", "_04_CF", "_05_CF", "_06_CF"})
    DG_SHEETS = frozenset({"_11_CF", "_12_CF"})

    # Exact General row numbers mapped to C6..C12 (or C6..C9 for DG) on each _XX_CF sheet
    GENERAL_TO_TORNADO_ROWS: ClassVar[dict[str, tuple[int, ...]]] = {
        "_01_CF": (11, 20, 27, 23, 24, 34, 15),
        "_02_CF": (11, 20, 27, 23, 24, 34, 15),
        "_03_CF": (11, 20, 27, 23, 24, 34, 15),
        "_04_CF": (11, 16, 27, 23, 29, 34, 15),
        "_05_CF": (11, 16, 27, 23, 29, 34, 15),
        "_06_CF": (11, 16, 27, 23, 24, 34, 15),
        "_07_CF": (11, 20, 27, 23, 24, 34, 15),
        "_08_CF": (11, 20, 27, 23, 24, 34, 15),
        "_09_CF": (11, 20, 27, 23, 24, 34, 15),
        "_10_CF": (11, 20, 27, 23, 24, 34, 15),
        "_11_CF": (11, 16, 23, 34),
        "_12_CF": (11, 16, 23, 34),
    }

    def __init__(self, fixture_data: dict[str, Any]) -> None:
        self._fixture = fixture_data
        self.general_c5_n40: list[list[Any]] = copy.deepcopy(fixture_data.get("general_c5_n40", []))
        self.lt_capex_b8_j30: list[list[Any]] = copy.deepcopy(fixture_data.get("lt_capex_b8_j30", []))
        self.lt_fuel_b8_j30: list[list[Any]] = copy.deepcopy(fixture_data.get("lt_fuel_b8_j30", []))
        self.lt_cf_b8_j30: list[list[Any]] = copy.deepcopy(fixture_data.get("lt_cf_b8_j30", []))
        self.sheet_parameters: dict[str, dict[str, Any]] = copy.deepcopy(
            fixture_data.get("sheet_parameters", {})
        )
        self.macros: dict[str, dict[str, Any]] = fixture_data.get("macros", {})
        self.has_custom_overrides: bool = False
        self.sheet_overrides: dict[str, dict[str, Any]] = {}
        self.general_param_ratios: dict[tuple[str, int], float] = {}
        self.modified_lt_cells: set[tuple[str, int, int]] = set()

        # Active H6:H12 observer vector state per sheet
        self.active_h_vectors: dict[str, dict[int, float]] = {}
        for sname, sparams in self.sheet_parameters.items():
            h_list = sparams.get("active_scenario_h6_h12", [])
            self.active_h_vectors[sname] = {
                6 + idx: float(val) if isinstance(val, (int, float)) else 0.0
                for idx, val in enumerate(h_list)
            }

    def _apply_general_grid_overrides(self, new_gen: list[list[Any]]) -> None:
        """Propagate edited General!C5:N40 cells into _XX_CF tornado_inputs_b6_d12 and ratios."""
        base_gen = self._fixture.get("general_c5_n40", [])
        for tech_idx in range(1, 13):
            col_idx = tech_idx - 1
            sname = f"_{tech_idx:02d}_CF"
            gen_rows = self.GENERAL_TO_TORNADO_ROWS.get(sname, [])
            b6_d12 = self.sheet_parameters[sname]["tornado_inputs_b6_d12"]

            for r_offset, gen_row in enumerate(gen_rows):
                g_r_idx = gen_row - 5
                if (
                    g_r_idx >= len(new_gen)
                    or g_r_idx >= len(base_gen)
                    or col_idx >= len(new_gen[g_r_idx])
                    or col_idx >= len(base_gen[g_r_idx])
                ):
                    continue
                new_val = new_gen[g_r_idx][col_idx]
                old_val = base_gen[g_r_idx][col_idx]
                if not cells_differ(new_val, old_val):
                    continue
                if isinstance(new_val, (int, float)):
                    self.has_custom_overrides = True
                    f_new = float(new_val)
                    f_old = float(old_val) if isinstance(old_val, (int, float)) and abs(float(old_val)) > 1e-12 else 1.0
                    param_row = 6 + r_offset
                    self.general_param_ratios[(sname, param_row)] = f_new / f_old
                    if r_offset < len(b6_d12):
                        if param_row == 12 and sname not in self.DG_SHEETS:
                            b6_d12[r_offset] = [math.floor(0.85 * f_new), f_new, math.ceil(1.15 * f_new)]
                        else:
                            b6_d12[r_offset] = [0.85 * f_new, f_new, 1.15 * f_new]

    def _track_lt_grid_overrides(self, curve_key: str, new_grid: list[list[Any]], base_grid: list[list[Any]]) -> None:
        """Record exact (curve_key, yr_idx, col_idx) coordinates that changed from baseline."""
        for yr_idx, row in enumerate(new_grid):
            if yr_idx >= len(base_grid):
                break
            for col_idx, val in enumerate(row):
                if col_idx >= len(base_grid[yr_idx]):
                    break
                if cells_differ(val, base_grid[yr_idx][col_idx]):
                    self.has_custom_overrides = True
                    self.modified_lt_cells.add((curve_key, yr_idx, col_idx))

    def clone_with_overrides(
        self,
        general_overrides: GeneralOverrides | None = None,
        sheet_inputs: dict[str, dict[str, Any]] | None = None,
    ) -> WorkbookSolverContext:
        """Create an isolated request-scoped copy with optional Google Sheets overrides applied."""
        cloned = WorkbookSolverContext(self._fixture)
        if general_overrides is not None:
            if general_overrides.general_c5_n40:
                cloned._apply_general_grid_overrides(general_overrides.general_c5_n40)
                cloned.general_c5_n40 = copy.deepcopy(general_overrides.general_c5_n40)
            if general_overrides.lt_capex_b8_j30:
                cloned._track_lt_grid_overrides(
                    "lt_capex", general_overrides.lt_capex_b8_j30, self.lt_capex_b8_j30
                )
                cloned.lt_capex_b8_j30 = copy.deepcopy(general_overrides.lt_capex_b8_j30)
            if general_overrides.lt_fuel_b8_j30:
                cloned._track_lt_grid_overrides(
                    "lt_fuel", general_overrides.lt_fuel_b8_j30, self.lt_fuel_b8_j30
                )
                cloned.lt_fuel_b8_j30 = copy.deepcopy(general_overrides.lt_fuel_b8_j30)
            if general_overrides.lt_cf_b8_j30:
                cloned._track_lt_grid_overrides(
                    "lt_cf", general_overrides.lt_cf_b8_j30, self.lt_cf_b8_j30
                )
                cloned.lt_cf_b8_j30 = copy.deepcopy(general_overrides.lt_cf_b8_j30)

        if sheet_inputs:
            cloned.has_custom_overrides = True
            cloned.sheet_overrides = copy.deepcopy(sheet_inputs)
            for sname, sdict in sheet_inputs.items():
                if sname in cloned.active_h_vectors:
                    for k, v in sdict.items():
                        if k.startswith("H") and k[1:].isdigit() and isinstance(v, (int, float)):
                            cloned.active_h_vectors[sname][int(k[1:])] = float(v)
        return cloned

    def rst_scenario(self, sheet_name: str) -> dict[int, float]:
        """Execute legacy rst_scenario: copy Base Case C6:C12 (or C6:C9 for DG) into H6:H12."""
        sparams = self.sheet_parameters[sheet_name]
        b6_d12 = sparams["tornado_inputs_b6_d12"]
        h_vec: dict[int, float] = {}
        for idx, row_vals in enumerate(b6_d12):
            base_val = row_vals[1] if len(row_vals) > 1 and isinstance(row_vals[1], (int, float)) else 0.0
            h_vec[6 + idx] = float(base_val)
        self.active_h_vectors[sheet_name] = h_vec
        return h_vec

    def get_base_c_vector(self, sheet_name: str) -> dict[int, float]:
        """Return C6:C12 (or C6:C9) baseline vector for a sheet."""
        sparams = self.sheet_parameters[sheet_name]
        b6_d12 = sparams["tornado_inputs_b6_d12"]
        return {
            6 + idx: float(row_vals[1]) if len(row_vals) > 1 and isinstance(row_vals[1], (int, float)) else 0.0
            for idx, row_vals in enumerate(b6_d12)
        }


@lru_cache(maxsize=1)
def get_baseline_solver_context() -> WorkbookSolverContext:
    """Load or build the singleton pre-warmed WorkbookSolverContext."""
    settings = get_settings()
    fixture_path: Path = settings.baseline_fixture_path
    if fixture_path.exists():
        data = json.loads(fixture_path.read_text(encoding="utf-8"))
    else:
        data = build_baseline_fixture(settings.seed_workbook_path)
        fixture_path.parent.mkdir(parents=True, exist_ok=True)
        fixture_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return WorkbookSolverContext(data)
