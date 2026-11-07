"""Parallel 4-Way Scenario & EU ETS Carbon Matrix sweep for Scenario_Comparison."""

from __future__ import annotations

from src.schemas.models import (
    EquilibriumSolveRequest,
    ScenarioCaseMetrics,
    ScenarioMatrixRequest,
    ScenarioMatrixResponse,
)
from src.solver.equilibrium_engine import solve_eulr_equilibrium
from src.vertex.explainer import generate_scenario_attribution_narrative


def run_four_way_scenario_matrix(request: ScenarioMatrixRequest) -> ScenarioMatrixResponse:
    """
    Solve all 4 combinations of (Base vs Sensitivity Margin) x (EU ETS Carbon On vs Off)
    and format the Scenario_Comparison table + Gemini 3.8 Flash attribution summary.
    """
    configs = [
        (
            "BASE_ETS_ON",
            "1. Base Margins + EU ETS Pass-Through (Saved Baseline)",
            "base",
            "Sensitivity with EU ETS cost and pass-through",
            True,
        ),
        (
            "BASE_ETS_OFF",
            "2. Base Margins + EU ETS Carbon Off",
            "base",
            "Base without EU ETS carbon pass-through (Off)",
            False,
        ),
        (
            "SENS_ETS_ON",
            "3. Sensitivity Margins + EU ETS Pass-Through",
            "sensitivity",
            "Sensitivity with EU ETS cost and pass-through",
            True,
        ),
        (
            "SENS_ETS_OFF",
            "4. Sensitivity Margins + EU ETS Carbon Off",
            "sensitivity",
            "Base without EU ETS carbon pass-through (Off)",
            False,
        ),
    ]

    cases: list[ScenarioCaseMetrics] = []
    for case_id, label, scen_mode, carb_mode, carb_on in configs:
        solve_req = EquilibriumSolveRequest(
            spreadsheet_id=request.spreadsheet_id,
            scenario_mode=scen_mode,  # type: ignore[arg-type]
            carbon_mode=carb_mode,
            upstream_source_mode=request.upstream_source_mode,
            actor_email=request.actor_email,
        )
        res, _ = solve_eulr_equilibrium(solve_req)
        prices = res.key_prices_2025_usd_mt
        margins = res.key_margins_2025_usd_bbl

        diesel = prices["NWE_Diesel_EN590_CIF_ARA"]
        gasoil = prices["NWE_Gasoil_01S_CIF_ARA"]
        cases.append(
            ScenarioCaseMetrics(
                case_id=case_id,
                case_label=label,
                scenario_mode=scen_mode,
                carbon_enabled=carb_on,
                nwe_fcc_margin_2025_usd_bbl=margins["NWE_Cat_Cracking_Dated_Brent_USD_bbl"],
                nwe_hsk_margin_2025_usd_bbl=margins["NWE_Incremental_FCC_HSK_ROCE_USD_bbl"],
                med_fcc_margin_2025_usd_bbl=round(
                    margins["NWE_Cat_Cracking_Dated_Brent_USD_bbl"] - 0.35, 4
                ),
                nwe_diesel_en590_2025_usd_mt=diesel,
                nwe_gasoline_2025_usd_mt=prices["NWE_Euro_Gasoline_CIF_ARA"],
                nwe_jet_kero_2025_usd_mt=prices["NWE_Jet_Kero_CIF_ARA"],
                nwe_lsfo_2025_usd_mt=prices["NWE_LSFO_1S_CIF_ARA"],
                ulsd_gasoil_spread_2025_usd_mt=round(diesel - gasoil, 2),
            )
        )

    header: list[str | float] = [
        "Scenario Case",
        "Margin Mode",
        "EU ETS Carbon",
        "NWE FCC Margin ($/bbl)",
        "NWE FCC/HSK ROCE ($/bbl)",
        "NWE Diesel EN590 ($/mt)",
        "NWE Euro Gasoline ($/mt)",
        "NWE Jet/Kero ($/mt)",
        "NWE LSFO 1% ($/mt)",
        "ULSD-Gasoil Spread ($/mt)",
    ]
    rows: list[list[str | float]] = [header]
    for c in cases:
        rows.append(
            [
                c.case_label,
                c.scenario_mode.upper(),
                "ON" if c.carbon_enabled else "OFF",
                c.nwe_fcc_margin_2025_usd_bbl,
                c.nwe_hsk_margin_2025_usd_bbl,
                c.nwe_diesel_en590_2025_usd_mt,
                c.nwe_gasoline_2025_usd_mt,
                c.nwe_jet_kero_2025_usd_mt,
                c.nwe_lsfo_2025_usd_mt,
                c.ulsd_gasoil_spread_2025_usd_mt,
            ]
        )

    narrative, model_used = generate_scenario_attribution_narrative(cases)

    return ScenarioMatrixResponse(
        spreadsheet_id=request.spreadsheet_id,
        cases=cases,
        comparison_table_rows=rows,
        ai_attribution_summary=narrative,
        model_used=model_used,
    )
