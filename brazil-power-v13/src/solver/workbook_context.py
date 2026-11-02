"""Pre-warmed WorkbookSolverContext holding baseline parameters, LT curves, and scenario state."""

from __future__ import annotations

import copy
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from src.cli.extract_baseline_fixtures import build_baseline_fixture
from src.core.config import get_settings
from src.schemas.solver import GeneralOverrides


class WorkbookSolverContext:
    """In-memory quantitative model context for all 12 _XX_CF sheets, General, CVU_GF, and LT curves."""

    THERMAL_SHEETS = frozenset({"_01_CF", "_07_CF", "_08_CF", "_09_CF", "_10_CF"})
    RENEWABLE_SHEETS = frozenset({"_02_CF", "_03_CF", "_04_CF", "_05_CF", "_06_CF"})
    DG_SHEETS = frozenset({"_11_CF", "_12_CF"})

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

        # Active H6:H12 observer vector state per sheet
        self.active_h_vectors: dict[str, dict[int, float]] = {}
        for sname, sparams in self.sheet_parameters.items():
            h_list = sparams.get("active_scenario_h6_h12", [])
            self.active_h_vectors[sname] = {
                6 + idx: float(val) if isinstance(val, (int, float)) else 0.0
                for idx, val in enumerate(h_list)
            }

    def clone_with_overrides(
        self,
        general_overrides: GeneralOverrides | None = None,
        sheet_inputs: dict[str, dict[str, Any]] | None = None,
    ) -> WorkbookSolverContext:
        """Create an isolated request-scoped copy with optional Google Sheets overrides applied."""
        cloned = WorkbookSolverContext(self._fixture)
        if general_overrides is not None:
            if general_overrides.general_c5_n40:
                if general_overrides.general_c5_n40 != self.general_c5_n40:
                    cloned.has_custom_overrides = True
                cloned.general_c5_n40 = copy.deepcopy(general_overrides.general_c5_n40)
            if general_overrides.lt_capex_b8_j30:
                if general_overrides.lt_capex_b8_j30 != self.lt_capex_b8_j30:
                    cloned.has_custom_overrides = True
                cloned.lt_capex_b8_j30 = copy.deepcopy(general_overrides.lt_capex_b8_j30)
            if general_overrides.lt_fuel_b8_j30:
                if general_overrides.lt_fuel_b8_j30 != self.lt_fuel_b8_j30:
                    cloned.has_custom_overrides = True
                cloned.lt_fuel_b8_j30 = copy.deepcopy(general_overrides.lt_fuel_b8_j30)
            if general_overrides.lt_cf_b8_j30:
                if general_overrides.lt_cf_b8_j30 != self.lt_cf_b8_j30:
                    cloned.has_custom_overrides = True
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
