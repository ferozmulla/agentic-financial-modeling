"""Quantitative solver routes for Google Sheets Apps Script and BigQuery Remote Function."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from src.bqml.remote_function_handler import handle_bqml_remote_calls
from src.core.security import CallerIdentity, verify_caller_identity
from src.schemas.solver import (
    BQMLRemoteFunctionRequest,
    BQMLRemoteFunctionResponse,
    GeneralOverrides,
    SolveMacroRequest,
    SolveMacroResponse,
)
from src.solver.macros.registry import MacroExecutionRegistry
from src.telemetry.tracker import telemetry_tracker

router = APIRouter(tags=["solver"])


class GatewaySolveBody(BaseModel):
    """Optional request body for POST /v1/solve/{macro_name}."""

    workbook_id: str = Field(default="Regional Power Generation Techno-Economic Model")
    spreadsheet_id: str = Field(default="local-seed-spreadsheet-id")
    caller_google_user: str | None = None
    general_overrides: GeneralOverrides | None = None
    sheet_inputs: dict[str, dict[str, Any]] = Field(default_factory=dict)
    parity_mode: str = "strict_legacy_vba"
    override_completed_at_utc: datetime | None = None


@router.post("/v1/solve/{macro_name}", response_model=SolveMacroResponse)
async def solve_macro_endpoint(
    macro_name: str,
    request: Request,
    payload: GatewaySolveBody | None = None,
    caller: CallerIdentity = Depends(verify_caller_identity),
) -> SolveMacroResponse:
    """Execute one of the 38 ported legacy VBA quantitative routines."""
    t0 = time.perf_counter()
    supported = set(MacroExecutionRegistry.list_supported_macros())
    if macro_name not in supported:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown macro '{macro_name}'. Supported count: {len(supported)}",
        )

    body = payload or GatewaySolveBody()
    solve_req = SolveMacroRequest(
        macro_name=macro_name,
        workbook_id=body.workbook_id,
        spreadsheet_id=body.spreadsheet_id,
        caller_google_user=body.caller_google_user or caller.email,
        general_overrides=body.general_overrides,
        sheet_inputs=body.sheet_inputs,
        parity_mode="continuous_exact" if body.parity_mode == "continuous_exact" else "strict_legacy_vba",
    )
    gw_ms = round(max((time.perf_counter() - t0) * 1000.0, 1.2), 2)
    result = MacroExecutionRegistry.execute(solve_req)
    telemetry_tracker.record_macro_solve(
        solve_req,
        result,
        gateway_overhead_ms=gw_ms,
        override_completed_at_utc=body.override_completed_at_utc,
    )
    return result


@router.post("/v1/bqml/solve", response_model=BQMLRemoteFunctionResponse)
async def bqml_remote_solve_endpoint(
    payload: BQMLRemoteFunctionRequest,
    _caller: CallerIdentity = Depends(verify_caller_identity),
) -> BQMLRemoteFunctionResponse:
    """BigQuery Remote Function HTTP endpoint (`fn_solve_lcoe`)."""
    t0 = time.perf_counter()
    result = handle_bqml_remote_calls(payload)
    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    telemetry_tracker.record_bqml_solve(payload, result, elapsed_ms=elapsed_ms)
    return result
