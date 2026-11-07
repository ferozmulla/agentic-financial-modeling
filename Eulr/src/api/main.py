"""FastAPI Cloud Run gateway (eulr-equilibrium-gateway) for Eulr202409."""

from __future__ import annotations

from fastapi import FastAPI

from src.bqml.forecaster import generate_bqml_breakout_tab_matrix
from src.core.config import settings
from src.diff.ast_differ import classify_governed_edit
from src.parser.r1c1_catalog import build_r1c1_catalog
from src.parser.upstream_link_hub import build_upstream_link_registry
from src.schemas.models import (
    BQMLRefreshRequest,
    BQMLRefreshResponse,
    EquilibriumSolveRequest,
    EquilibriumSolveResponse,
    GovernedEditEventRequest,
    GovernedEditEventResponse,
    OverrideRevertRequest,
    OverrideRevertResponse,
    PublishUploadRequest,
    PublishUploadResponse,
    ScenarioMatrixRequest,
    ScenarioMatrixResponse,
    UpstreamSyncRequest,
    UpstreamSyncResponse,
)
from src.solver.equilibrium_engine import solve_eulr_equilibrium
from src.solver.scenario_matrix import run_four_way_scenario_matrix
from src.solver.upload_publisher import publish_upload_and_links_out
from src.storage.repository import governance_repo
from src.vertex.explainer import generate_4ws_why_summary

app = FastAPI(
    title="EULR Commodity Modeling Equilibrium Gateway",
    version="2.0.0",
    description=(
        "10-Pass Gauss-Seidel Equilibrium Solver, SharePoint-Portable Upstream Link Hub, "
        "BigQuery ML Forecaster, and 4-Ws Governance Gateway for Eulr202409."
    ),
)


@app.get("/health")
@app.get("/healthz")
async def healthz() -> dict[str, object]:
    catalog = build_r1c1_catalog(settings.resolved_seed_path)
    return {
        "status": "ok",
        "service": settings.cloud_run_service_name,
        "gcp_project_id": settings.gcp_project_id,
        "gcp_region": settings.gcp_region,
        "bigquery_dataset": settings.bigquery_dataset,
        "gcs_snapshot_bucket": settings.gcs_snapshot_bucket,
        "gemini_model_id": settings.gemini_model_id,
        "vertex_surrogate_model": settings.vertex_surrogate_model_name,
        "total_formula_cells": catalog.total_formula_cells,
        "unique_r1c1_row_equations": catalog.unique_r1c1_row_equations,
        "cse_formula_cells": catalog.cse_formula_cells,
        "upstream_external_link_cells": catalog.upstream_external_link_cells,
    }


@app.post("/v1/eulr/solve", response_model=EquilibriumSolveResponse)
async def solve_endpoint(request: EquilibriumSolveRequest) -> EquilibriumSolveResponse:
    persisted = governance_repo.get_pinned_overrides(request.spreadsheet_id)
    for cell_key, val in request.pinned_overrides.items():
        if "!" in cell_key:
            sh_name, coord = cell_key.split("!", 1)
            persisted = governance_repo.upsert_pinned_override(
                request.spreadsheet_id, sh_name.strip("'"), coord, val
            )

    resp, _ = solve_eulr_equilibrium(request, persisted_overrides=persisted)

    governance_repo.append_audit_event(
        actor_email=request.actor_email,
        spreadsheet_id=request.spreadsheet_id,
        copy_location_url=f"https://docs.google.com/spreadsheets/d/{request.spreadsheet_id}/edit",
        sheet_name="KeyInputs",
        cell_a1="B4",
        classification="SOLVER_RUN",
        before_value=None,
        new_value=f"Diesel_EN590={resp.key_prices_2025_usd_mt['NWE_Diesel_EN590_CIF_ARA']}",
        before_formula=None,
        new_formula=None,
        why_ai_summary=(
            f"[{settings.gemini_model_id}] Executed 10-pass Gauss-Seidel equilibrium solve "
            f"(mode={request.scenario_mode}, upstream={request.upstream_source_mode}, "
            f"pinned_overrides={resp.pinned_override_count}) in {resp.compute_ms} ms."
        ),
        rollback_tier_hint="TIER_3_VERSION_HISTORY",
    )
    return resp


@app.post("/v1/eulr/scenario-matrix", response_model=ScenarioMatrixResponse)
async def scenario_matrix_endpoint(request: ScenarioMatrixRequest) -> ScenarioMatrixResponse:
    return run_four_way_scenario_matrix(request)


@app.post("/v1/eulr/sync-upstream", response_model=UpstreamSyncResponse)
async def sync_upstream_endpoint(request: UpstreamSyncRequest) -> UpstreamSyncResponse:
    registry = build_upstream_link_registry(
        settings.resolved_seed_path, settings.resolved_references_dir
    )
    persisted = governance_repo.get_pinned_overrides(request.spreadsheet_id)
    solve_req = EquilibriumSolveRequest(
        spreadsheet_id=request.spreadsheet_id,
        upstream_source_mode=request.target_mode,
        actor_email=request.actor_email,
    )
    solve_resp, _ = solve_eulr_equilibrium(solve_req, persisted_overrides=persisted)
    return UpstreamSyncResponse(
        spreadsheet_id=request.spreadsheet_id,
        active_mode=request.target_mode,
        total_external_cells=registry.total_external_formula_cells,
        updated_peer_cells=registry.total_peer_updated_cells
        if request.target_mode != "eulr_baseline_cached"
        else 0,
        updated_by_workbook=registry.updated_counts_by_workbook,
        solve_result=solve_resp,
    )


@app.post("/v1/eulr/override/revert", response_model=OverrideRevertResponse)
async def revert_override_endpoint(request: OverrideRevertRequest) -> OverrideRevertResponse:
    reverted, remaining = governance_repo.revert_pinned_overrides(
        request.spreadsheet_id, request.target_cell_a1
    )
    solve_req = EquilibriumSolveRequest(
        spreadsheet_id=request.spreadsheet_id,
        actor_email=request.actor_email,
        pinned_overrides={},
    )
    solve_resp, _ = solve_eulr_equilibrium(solve_req, persisted_overrides=remaining)
    return OverrideRevertResponse(
        spreadsheet_id=request.spreadsheet_id,
        reverted_cells=reverted,
        remaining_override_count=len(remaining),
        solve_result=solve_resp,
    )


@app.post("/v1/eulr/publish", response_model=PublishUploadResponse)
async def publish_upload_endpoint(request: PublishUploadRequest) -> PublishUploadResponse:
    return publish_upload_and_links_out(request)


@app.post("/v1/eulr/bqml/refresh", response_model=BQMLRefreshResponse)
async def refresh_bqml_endpoint(request: BQMLRefreshRequest) -> BQMLRefreshResponse:
    return generate_bqml_breakout_tab_matrix(request)


@app.post("/v1/ingest/edit-event", response_model=GovernedEditEventResponse)
async def ingest_edit_event_endpoint(
    request: GovernedEditEventRequest,
) -> GovernedEditEventResponse:
    cls = classify_governed_edit(request)
    if cls.suppressed:
        return GovernedEditEventResponse(
            event_id="suppressed",
            logged=False,
            suppressed=True,
            classification=cls.classification,
            highlight_hex=None,
            pinned_override_registered=False,
            why_ai_summary="Suppressed routine switch or R1C1-equivalent row shift.",
            rollback_tier_hint=cls.rollback_tier_hint,
        )

    pinned_registered = False
    if cls.is_pinned_override and request.new_value is not None:
        governance_repo.upsert_pinned_override(
            request.spreadsheet_id,
            request.sheet_name,
            request.cell_a1,
            float(request.new_value),
        )
        pinned_registered = True

    why_summary = generate_4ws_why_summary(request, cls.classification)
    rec = governance_repo.append_audit_event(
        actor_email=request.actor_email,
        spreadsheet_id=request.spreadsheet_id,
        copy_location_url=request.copy_location_url,
        sheet_name=request.sheet_name,
        cell_a1=request.cell_a1,
        classification=cls.classification,
        before_value=request.before_value,
        new_value=request.new_value,
        before_formula=request.before_formula,
        new_formula=request.new_formula,
        why_ai_summary=why_summary,
        rollback_tier_hint=cls.rollback_tier_hint,
    )
    return GovernedEditEventResponse(
        event_id=rec.event_id,
        logged=True,
        suppressed=False,
        classification=cls.classification,
        highlight_hex=cls.highlight_hex,
        pinned_override_registered=pinned_registered,
        why_ai_summary=why_summary,
        rollback_tier_hint=cls.rollback_tier_hint,
        metadata={"when_event_utc": rec.when_event_utc},
    )
