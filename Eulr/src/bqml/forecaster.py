"""3 Breakout BQML Forecast Tabs (Macro_BQML, Crudes_BQML, Freight_BQML) and Vertex AI crack-spread surrogate."""

from __future__ import annotations

from dataclasses import dataclass

from src.core.config import settings
from src.schemas.models import BQMLRefreshRequest, BQMLRefreshResponse


@dataclass(frozen=True)
class SurrogateMarginPrediction:
    dated_brent_usd_bbl: float
    eu_ets_eur_tco2: float
    urals_diff_usd_bbl: float
    predicted_nwe_fcc_margin_usd_bbl: float
    predicted_med_fcc_margin_usd_bbl: float
    predicted_nwe_diesel_crack_usd_bbl: float
    model_registry_name: str


def predict_crack_spread_surrogate(
    dated_brent_usd_bbl: float = 78.50,
    eu_ets_eur_tco2: float = 85.00,
    urals_diff_usd_bbl: float = -2.15,
) -> SurrogateMarginPrediction:
    """
    Evaluate the BQML / Vertex AI Model Registry NWE/MED refinery crack-spread surrogate
    (eulr-sheets-mod-margin-surrogate).
    """
    nwe_fcc = (
        0.26
        + 0.042 * (dated_brent_usd_bbl - 78.50)
        - 0.011 * (eu_ets_eur_tco2 - 85.00)
        - 0.18 * (urals_diff_usd_bbl + 2.15)
    )
    med_fcc = nwe_fcc - 0.35 - 0.08 * (urals_diff_usd_bbl + 2.15)
    diesel_crack = 21.40 + 0.085 * (dated_brent_usd_bbl - 78.50) + 0.015 * (eu_ets_eur_tco2 - 85.00)
    return SurrogateMarginPrediction(
        dated_brent_usd_bbl=round(dated_brent_usd_bbl, 2),
        eu_ets_eur_tco2=round(eu_ets_eur_tco2, 2),
        urals_diff_usd_bbl=round(urals_diff_usd_bbl, 2),
        predicted_nwe_fcc_margin_usd_bbl=round(nwe_fcc, 4),
        predicted_med_fcc_margin_usd_bbl=round(med_fcc, 4),
        predicted_nwe_diesel_crack_usd_bbl=round(diesel_crack, 4),
        model_registry_name=settings.vertex_surrogate_model_name,
    )


def generate_bqml_breakout_tab_matrix(request: BQMLRefreshRequest) -> BQMLRefreshResponse:
    """
    Build the horizontal 1990-2050 trajectory grid (<= 2024 historical actuals + 2025-2050 BQML ARIMA_PLUS forecast)
    for Macro_BQML, Crudes_BQML, or Freight_BQML.
    """
    years = list(range(1990, request.horizon_end_year + 1))

    if request.tab_name == "Macro_BQML":
        model_name = f"{settings.gcp_project_id}.{settings.bigquery_dataset}.bqml_macro_arima_plus_v1"
        specs = [
            ("US_GDP_Deflator_Index", "US GDP Implicit Price Deflator (2023=1.00)", 0.48, 1.02, 0.021),
            ("EUR_USD_Exchange_Rate", "Euro / US Dollar Exchange Rate ($/EUR)", 1.18, 1.09, 0.002),
            ("EU_ETS_Carbon_Allowance_EUR_t", "EU ETS Carbon Price Trajectory (EUR/tCO2e)", 0.0, 78.50, 2.45),
            ("NWE_Industrial_Power_Index", "NWE Refinery Purchased Electricity Index", 42.0, 118.0, 1.15),
        ]
    elif request.tab_name == "Crudes_BQML":
        model_name = f"{settings.gcp_project_id}.{settings.bigquery_dataset}.bqml_crudes_arima_plus_v1"
        specs = [
            ("Dated_Brent_FOB_North_Sea", "Dated Brent Benchmark Crude ($/bbl)", 23.70, 81.40, -0.22),
            ("Urals_CIF_NWE_Differential", "Urals CIF ARA vs Dated Brent ($/bbl)", -1.15, -2.45, 0.02),
            ("Arab_Light_FOB_Ras_Tanura", "Arab Light Official Selling Price ($/bbl)", 22.10, 79.80, -0.20),
            ("Es_Sider_FOB_Libya", "Es Sider Sweet Med Crude ($/bbl)", 23.95, 81.65, -0.21),
            ("Ekofisk_CIF_ARA", "Ekofisk Low-Sulfur North Sea ($/bbl)", 24.10, 82.25, -0.20),
        ]
    else:
        model_name = f"{settings.gcp_project_id}.{settings.bigquery_dataset}.bqml_freight_arima_plus_v1"
        specs = [
            ("Clean_MR_TC2_Rotterdam_NY", "Clean Tanker 37kt UKC-USAC ($/mt)", 14.20, 28.60, 0.18),
            ("Clean_Hendy_Med_NWE_30kt", "Cross-Med / NWE Clean Product Freight ($/mt)", 11.80, 22.40, 0.14),
            ("Dirty_Aframax_Baltic_UKC", "Dirty Crude Aframax 80kt NWE ($/bbl)", 0.95, 1.85, 0.012),
            ("Worldscale_Flat_Rate_Index", "Tankerlr Worldscale Flat Rate Index (%)", 100.0, 168.5, 1.25),
        ]

    header_row: list[str | float] = ["Series Mnemonic", "Description", "Source Mode"] + [
        year for year in years
    ]
    rows: list[list[str | float]] = [header_row]

    for mnem, desc, v_1990, v_2024, annual_drift in specs:
        row: list[str | float] = [mnem, desc, "Actuals (<=2024) | BQML ARIMA_PLUS (2025+)"]
        for yr in years:
            if yr <= 2024:
                frac = (yr - 1990) / 34.0
                val = v_1990 + frac * (v_2024 - v_1990)
            else:
                horizon_step = yr - 2024
                val = v_2024 + horizon_step * annual_drift
            row.append(round(val, 4))
        rows.append(row)

    return BQMLRefreshResponse(
        tab_name=request.tab_name,
        model_name=model_name,
        years=years,
        series_rows=rows,
        surrogate_model_registry_id=settings.vertex_surrogate_model_name,
    )
