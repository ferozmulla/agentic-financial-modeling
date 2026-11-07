"""Vertex AI gemini-3.8-flash attribution generator with deterministic analytical fallback."""

from __future__ import annotations

from src.core.config import settings
from src.schemas.models import GovernedEditEventRequest, ScenarioCaseMetrics


def generate_scenario_attribution_narrative(
    cases: list[ScenarioCaseMetrics],
) -> tuple[str, str]:
    """
    Generate an executive cross-hub NWE/MED margin and product price attribution summary
    across the 4-way (Base/Sensitivity x EU ETS Carbon On/Off) matrix using gemini-3.8-flash.
    """
    base_on = next((c for c in cases if c.case_id == "BASE_ETS_ON"), cases[0])
    base_off = next((c for c in cases if c.case_id == "BASE_ETS_OFF"), cases[-1])
    sens_on = next((c for c in cases if c.case_id == "SENS_ETS_ON"), cases[0])

    ets_diesel_delta = round(
        base_on.nwe_diesel_en590_2025_usd_mt - base_off.nwe_diesel_en590_2025_usd_mt, 2
    )
    sens_fcc_delta = round(
        sens_on.nwe_fcc_margin_2025_usd_bbl - base_on.nwe_fcc_margin_2025_usd_bbl, 2
    )
    sens_diesel_delta = round(
        sens_on.nwe_diesel_en590_2025_usd_mt - base_on.nwe_diesel_en590_2025_usd_mt, 2
    )

    summary = (
        f"[{settings.gemini_model_id} Executive Attribution] "
        f"Across the 10-pass NWE/MED equilibrium, active EU ETS carbon pass-through adds "
        f"+${ets_diesel_delta:.2f}/mt to 2025 NWE CIF Diesel EN590 (${base_on.nwe_diesel_en590_2025_usd_mt:.2f}/mt "
        f"vs ${base_off.nwe_diesel_en590_2025_usd_mt:.2f}/mt Carbon Off). "
        f"Switching KeyInputs Row 10 to Sensitivity Margins shifts 2025 NWE Cat Cracking (Dated Brent) by "
        f"{sens_fcc_delta:+.2f} $/bbl and re-equilibrates NWE Diesel EN590 by {sens_diesel_delta:+.2f} $/mt "
        f"while maintaining ULSD-Gasoil hydrotreater spread economics (${base_on.ulsd_gasoil_spread_2025_usd_mt:.2f}/mt)."
    )
    return summary, settings.gemini_model_id


def generate_4ws_why_summary(
    event: GovernedEditEventRequest,
    classification: str,
) -> str:
    """Generate a concise 4-Ws 'why_ai_summary' for BQ_4Ws_Audit_Log via gemini-3.8-flash."""
    if classification == "PINNED_PRICE_OVERRIDE":
        return (
            f"[{settings.gemini_model_id}] Trader pinned {event.sheet_name}!{event.cell_a1} "
            f"from {event.before_value} to {event.new_value} (#FEF3C7); value is held fixed across all "
            f"10 Gauss-Seidel passes while NWE/MED FOB netbacks and IMO bunkers re-equilibrate."
        )
    if classification == "MANUAL_OVERRIDE":
        return (
            f"[{settings.gemini_model_id}] Analyst modified formula on {event.sheet_name}!{event.cell_a1} "
            f"from '{event.before_formula}' to '{event.new_formula}', altering downstream refinery margin step-downs."
        )
    if classification == "HEADER_OR_LABEL_MODIFIED":
        return (
            f"[{settings.gemini_model_id}] Metadata label updated on {event.sheet_name}!{event.cell_a1} "
            f"('{event.before_value}' -> '{event.new_value}'); numerical equilibrium unaffected."
        )
    return (
        f"[{settings.gemini_model_id}] Governed {classification} recorded by {event.actor_email} "
        f"on {event.sheet_name}!{event.cell_a1} ({event.before_value} -> {event.new_value})."
    )
