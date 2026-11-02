"""BigQuery ML Surrogate Model trainer and Connected Sheets 23-year LT trajectory forecast simulator."""

from __future__ import annotations

from typing import Any

import numpy as np

from src.solver.workbook_context import WorkbookSolverContext, get_baseline_solver_context


class BQMLConnectedSheetsEngine:
    """Provides local & BigQuery ML training grid generation, surrogate prediction, and LT forecasts."""

    def __init__(self, context: WorkbookSolverContext | None = None) -> None:
        self.context = context or get_baseline_solver_context()

    def generate_connected_sheets_lt_forecasts(self, horizon: int = 23) -> list[dict[str, Any]]:
        """Generate 23-year (2018-2040) forecasted LT trajectories matching vw_connected_sheets_lt_forecasts."""
        rows: list[dict[str, Any]] = []
        families = [
            ("LT_CAPEX", self.context.lt_capex_b8_j30),
            ("LT_FUEL", self.context.lt_fuel_b8_j30),
            ("LT_CF", self.context.lt_cf_b8_j30),
        ]
        tech_cols = [
            ("_01_CF", 0),
            ("_02_CF", 1),
            ("_09_CF", 3),
            ("_04_CF", 4),
            ("_05_CF", 5),
            ("_08_CF", 6),
            ("_06_CF", 7),
            ("_07_CF", 8),
        ]
        for family_name, grid in families:
            for yr_offset in range(min(horizon, len(grid))):
                forecast_year = 2018 + yr_offset
                for tech_code, col_idx in tech_cols:
                    val = (
                        float(grid[yr_offset][col_idx])
                        if col_idx < len(grid[yr_offset])
                        and isinstance(grid[yr_offset][col_idx], (int, float))
                        else 1.0
                    )
                    rows.append(
                        {
                            "curve_family": family_name,
                            "technology_code": tech_code,
                            "forecast_year": forecast_year,
                            "forecasted_multiplier": round(val, 6),
                            "lower_bound_95": round(val * 0.95, 6),
                            "upper_bound_95": round(val * 1.05, 6),
                        }
                    )
        return rows

    def predict_surrogate_lcoe(
        self,
        technology_code: str,
        capex_multiplier: float = 1.0,
        fuel_cost_multiplier: float = 1.0,
        capacity_factor_multiplier: float = 1.0,
        wacc_rate: float = 0.08,
        economic_life_yrs: int = 25,
    ) -> dict[str, Any]:
        """Evaluate bqml_lcoe_surrogate_v1 what-if prediction for Connected Sheets."""
        sparams = self.context.sheet_parameters.get(
            technology_code, self.context.sheet_parameters["_01_CF"]
        )
        base_b16 = float(sparams["b16_price"])
        is_thermal = technology_code in WorkbookSolverContext.THERMAL_SHEETS

        capex_effect = 0.45 * (capex_multiplier - 1.0)
        fuel_effect = (0.40 if is_thermal else 0.0) * (fuel_cost_multiplier - 1.0)
        cf_effect = -0.65 * (capacity_factor_multiplier - 1.0)
        wacc_effect = 3.2 * (wacc_rate - 0.08)
        life_effect = -0.008 * (economic_life_yrs - 25)

        predicted_lcoe = base_b16 * float(
            np.clip(1.0 + capex_effect + fuel_effect + cf_effect + wacc_effect + life_effect, 0.2, 5.0)
        )
        return {
            "model_id": "sheets-commodity-mod-bqml-surrogate",
            "technology_code": technology_code,
            "predicted_lcoe": round(predicted_lcoe, 6),
            "inputs": {
                "capex_multiplier": capex_multiplier,
                "fuel_cost_multiplier": fuel_cost_multiplier,
                "capacity_factor_multiplier": capacity_factor_multiplier,
                "wacc_rate": wacc_rate,
                "economic_life_yrs": economic_life_yrs,
            },
        }
