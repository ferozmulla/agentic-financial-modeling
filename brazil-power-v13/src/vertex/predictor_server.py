"""FastAPI server implementing Vertex AI Custom Prediction contract (AIP_HEALTH_ROUTE & AIP_PREDICT_ROUTE)."""

from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, HTTPException

from src.core.security import SecureHeadersMiddleware
from src.schemas.solver import SolveMacroRequest, VertexPredictRequest, VertexPredictResponse
from src.solver.macros.registry import MacroExecutionRegistry

AIP_HEALTH_ROUTE = os.environ.get("AIP_HEALTH_ROUTE", "/health")
AIP_PREDICT_ROUTE = os.environ.get("AIP_PREDICT_ROUTE", "/predict")

vertex_app = FastAPI(
    title="Vertex AI Custom Prediction — Vectorized Commodity LCOE Solver",
    version="1.0.0",
)
vertex_app.add_middleware(SecureHeadersMiddleware)


@vertex_app.get(AIP_HEALTH_ROUTE)
async def vertex_health() -> dict[str, Any]:
    """Vertex AI health check endpoint."""
    return {
        "status": "healthy",
        "model_id": "sheets-commodity-mod-lcoe-solver",
        "supported_macros_count": len(MacroExecutionRegistry.list_supported_macros()),
    }


@vertex_app.post(AIP_PREDICT_ROUTE, response_model=VertexPredictResponse)
async def vertex_predict(request: VertexPredictRequest) -> VertexPredictResponse:
    """Vertex AI prediction endpoint executing one or more solver macro instances."""
    predictions: list[dict[str, Any]] = []
    for item in request.instances:
        try:
            solve_req = SolveMacroRequest(
                macro_name=item.macro_name,
                workbook_id=item.workbook_id,
                spreadsheet_id=item.spreadsheet_id,
                general_overrides=item.general_overrides,
                sheet_inputs=item.sheet_inputs,
                parity_mode=item.parity_mode,
            )
            res = MacroExecutionRegistry.execute(solve_req)
            predictions.append(res.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return VertexPredictResponse(
        predictions=predictions,
        deployed_model_id="sheets-commodity-mod-lcoe-solver",
    )
