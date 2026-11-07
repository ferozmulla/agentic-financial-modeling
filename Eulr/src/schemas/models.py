"""Request, response, and domain schemas for the EULR 10-pass solver, upstream link hub, BQML, and 4-Ws audit."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class CellDeltaRange(BaseModel):
    sheet_name: str
    a1_range: str
    values: list[list[float | str | None]]


class ChecksDiagnosticSummary(BaseModel):
    total_rules: int = 180
    passed_rules: int = 180
    flagged_rules: int = 0
    max_arbitrage_violation_usd_bbl: float = 0.0
    sample_flags: list[str] = Field(default_factory=list)


class EquilibriumSolveRequest(BaseModel):
    spreadsheet_id: str = "central-eulr-202409"
    scenario_mode: Literal["base", "sensitivity"] = "base"
    carbon_mode: str = "Sensitivity with EU ETS cost and pass-through"
    carbon_allocation_mode: str = "Variable cost increase and product allocation"
    upstream_source_mode: Literal["eulr_baseline_cached", "peer_xlsx", "sharepoint_graph"] = (
        "eulr_baseline_cached"
    )
    max_iterations: int = Field(default=10, ge=1, le=50)
    driver_overrides: dict[str, float] = Field(
        default_factory=dict,
        description="Optional A1 driver edits such as {'KeyInputs!AT10': 1.0, 'Crudes!AU9': 85.0}",
    )
    pinned_overrides: dict[str, float] = Field(
        default_factory=dict,
        description="Optional #FEF3C7 pinned trader price overrides such as {'NWE Cif!AU122': 750.0}",
    )
    actor_email: str = "analyst@spglobal.com"


class EquilibriumSolveResponse(BaseModel):
    spreadsheet_id: str
    scenario_mode: str
    carbon_mode: str
    upstream_source_mode: str
    iterations_run: int
    converged: bool
    convergence_history: list[float]
    final_max_delta: float
    compute_ms: float
    pinned_override_count: int
    key_prices_2025_usd_mt: dict[str, float]
    key_margins_2025_usd_bbl: dict[str, float]
    checks_summary: ChecksDiagnosticSummary
    delta_ranges: list[CellDeltaRange]


class ScenarioCaseMetrics(BaseModel):
    case_id: str
    case_label: str
    scenario_mode: str
    carbon_enabled: bool
    nwe_fcc_margin_2025_usd_bbl: float
    nwe_hsk_margin_2025_usd_bbl: float
    med_fcc_margin_2025_usd_bbl: float
    nwe_diesel_en590_2025_usd_mt: float
    nwe_gasoline_2025_usd_mt: float
    nwe_jet_kero_2025_usd_mt: float
    nwe_lsfo_2025_usd_mt: float
    ulsd_gasoil_spread_2025_usd_mt: float


class ScenarioMatrixRequest(BaseModel):
    spreadsheet_id: str = "central-eulr-202409"
    upstream_source_mode: Literal["eulr_baseline_cached", "peer_xlsx", "sharepoint_graph"] = (
        "eulr_baseline_cached"
    )
    actor_email: str = "analyst@spglobal.com"


class ScenarioMatrixResponse(BaseModel):
    spreadsheet_id: str
    cases: list[ScenarioCaseMetrics]
    comparison_table_rows: list[list[str | float]]
    ai_attribution_summary: str
    model_used: str


class UpstreamSyncRequest(BaseModel):
    spreadsheet_id: str = "central-eulr-202409"
    target_mode: Literal["eulr_baseline_cached", "peer_xlsx", "sharepoint_graph"] = "peer_xlsx"
    actor_email: str = "analyst@spglobal.com"


class UpstreamSyncResponse(BaseModel):
    spreadsheet_id: str
    active_mode: str
    total_external_cells: int
    updated_peer_cells: int
    updated_by_workbook: dict[str, int]
    solve_result: EquilibriumSolveResponse


class OverrideRevertRequest(BaseModel):
    spreadsheet_id: str = "central-eulr-202409"
    target_cell_a1: str | None = Field(
        default=None,
        description="If None, reverts all active #FEF3C7 pinned overrides for spreadsheet_id.",
    )
    actor_email: str = "analyst@spglobal.com"


class OverrideRevertResponse(BaseModel):
    spreadsheet_id: str
    reverted_cells: list[str]
    remaining_override_count: int
    solve_result: EquilibriumSolveResponse


class PublishUploadRequest(BaseModel):
    spreadsheet_id: str = "central-eulr-202409"
    vintage_tag: str = "202409"
    actor_email: str = "analyst@spglobal.com"


class PublishUploadResponse(BaseModel):
    spreadsheet_id: str
    vintage_tag: str
    upload_series_count: int
    links_out_series_count: int
    retired_shooju_addin: bool = True
    published_at_utc: datetime


class BQMLRefreshRequest(BaseModel):
    tab_name: Literal["Macro_BQML", "Crudes_BQML", "Freight_BQML"] = "Crudes_BQML"
    horizon_end_year: int = 2050


class BQMLRefreshResponse(BaseModel):
    tab_name: str
    model_name: str
    years: list[int]
    series_rows: list[list[str | float]]
    surrogate_model_registry_id: str


class GovernedEditEventRequest(BaseModel):
    spreadsheet_id: str = "central-eulr-202409"
    copy_location_url: str = "https://docs.google.com/spreadsheets/d/central-eulr-202409/edit"
    actor_email: str = "trader@spglobal.com"
    sheet_name: str
    cell_a1: str
    before_value: float | str | None = None
    new_value: float | str | None = None
    before_formula: str | None = None
    new_formula: str | None = None
    structural_change_type: str | None = None
    row_shift_delta: int = 0


class GovernedEditEventResponse(BaseModel):
    event_id: str
    logged: bool
    suppressed: bool
    classification: str
    highlight_hex: str | None = None
    pinned_override_registered: bool = False
    why_ai_summary: str
    rollback_tier_hint: str
    metadata: dict[str, Any] = Field(default_factory=dict)
