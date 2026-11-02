"""Quantitative solver routes for Google Sheets Apps Script and BigQuery Remote Function."""

from __future__ import annotations

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

router = APIRouter(tags=["solver"])


class GatewaySolveBody(BaseModel):
    """Optional request body for POST /v1/solve/{macro_name}."""

    workbook_id: str = Field(default="Regional Power Generation Techno-Economic Model")
    spreadsheet_id: str = Field(default="local-seed-spreadsheet-id")
    caller_google_user: str | None = None
    general_overrides: GeneralOverrides | None = None
    sheet_inputs: dict[str, dict[str, Any]] = Field(default_factory=dict)
    parity_mode: str = "strict_legacy_vba"


@router.post("/v1/solve/{macro_name}", response_model=SolveMacroResponse)
async def solve_macro_endpoint(
    macro_name: str,
    request: Request,
    payload: GatewaySolveBody | None = None,
    caller: CallerIdentity = Depends(verify_caller_identity),
) -> SolveMacroResponse:
    """Execute one of the 38 ported legacy VBA quantitative routines."""
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
    # Note: solver_run_telemetry is parked as a V2 backlog item per architecture decision.
    return MacroExecutionRegistry.execute(solve_req)


@router.post("/v1/bqml/solve", response_model=BQMLRemoteFunctionResponse)
async def bqml_remote_solve_endpoint(
    payload: BQMLRemoteFunctionRequest,
    _caller: CallerIdentity = Depends(verify_caller_identity),
) -> BQMLRemoteFunctionResponse:
    """BigQuery Remote Function HTTP endpoint (`fn_solve_lcoe`)."""
    return handle_bqml_remote_calls(payload)
