"""Pydantic schemas for Pillar A Quantitative Solver, Vertex AI Custom Prediction, and BQML."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class CellRangeUpdate(BaseModel):
    """Represents a rectangular range update for Sheets.Spreadsheets.Values.batchUpdate."""

    sheet: str = Field(..., description="Target worksheet name (e.g., '_01_CF' or 'Output_3')")
    range: str = Field(..., description="A1 range notation (e.g., 'E6:G12' or 'B9:J31')")
    values: list[list[float | int | str | None]] = Field(
        ...,
        description="2D row-major array of values to write into the sheet range",
    )


class GeneralOverrides(BaseModel):
    """Optional batch-read overrides from General and LT sheets in Google Sheets."""

    general_c5_n40: list[list[Any]] = Field(default_factory=list)
    lt_capex_b8_j30: list[list[Any]] = Field(default_factory=list)
    lt_fuel_b8_j30: list[list[Any]] = Field(default_factory=list)
    lt_cf_b8_j30: list[list[Any]] = Field(default_factory=list)


class SolveMacroRequest(BaseModel):
    """Request payload sent by Google Apps Script SolverClient.gs to POST /v1/solve/{macro_name}."""

    macro_name: str = Field(..., min_length=1, max_length=64)
    workbook_id: str = Field(default="Regional Power Generation Techno-Economic Model")
    spreadsheet_id: str = Field(default="local-seed-spreadsheet-id")
    caller_google_user: str = Field(default="analyst@enterprise.com")
    general_overrides: GeneralOverrides | None = Field(default=None)
    sheet_inputs: dict[str, dict[str, Any]] = Field(default_factory=dict)
    parity_mode: Literal["strict_legacy_vba", "continuous_exact"] = Field(default="strict_legacy_vba")


class SolveMacroResponse(BaseModel):
    """Response payload returned to Google Apps Script SolverClient.gs."""

    macro_name: str
    workbook_id: str
    spreadsheet_id: str
    solve_count: int
    execution_time_ms: float
    execution_engine: str = Field(default="vertex-ai-vectorized-v1")
    parity_mode: str = Field(default="strict_legacy_vba")
    cell_updates: list[CellRangeUpdate] = Field(default_factory=list)
    flat_outputs: dict[str, float | str] = Field(
        default_factory=dict,
        description="Map of 'Sheet!Cell' -> solved value for direct O(1) parity assertions",
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


class VertexInstanceItem(BaseModel):
    """Single instance item inside Vertex AI AIP_PREDICT_ROUTE request."""

    macro_name: str
    workbook_id: str = "Regional Power Generation Techno-Economic Model"
    spreadsheet_id: str = "vertex-prediction-sheet"
    general_overrides: GeneralOverrides | None = None
    sheet_inputs: dict[str, dict[str, Any]] = Field(default_factory=dict)
    parity_mode: Literal["strict_legacy_vba", "continuous_exact"] = "strict_legacy_vba"


class VertexPredictRequest(BaseModel):
    """Standard Vertex AI Custom Prediction request contract: {'instances': [...], 'parameters': {...}}."""

    instances: list[VertexInstanceItem]
    parameters: dict[str, Any] = Field(default_factory=dict)


class VertexPredictResponse(BaseModel):
    """Standard Vertex AI Custom Prediction response contract: {'predictions': [...]}."""

    predictions: list[dict[str, Any]]
    deployed_model_id: str = "sheets-commodity-mod-lcoe-solver"


class BQMLRemoteFunctionRequest(BaseModel):
    """BigQuery Remote Function request payload: {'calls': [[macro_name, payload_json], ...]}."""

    requestId: str | None = None
    caller: str | None = None
    sessionUser: str | None = None
    userDefinedContext: dict[str, Any] = Field(default_factory=dict)
    calls: list[list[Any]]


class BQMLRemoteFunctionResponse(BaseModel):
    """BigQuery Remote Function response payload: {'replies': [...]}."""

    replies: list[Any]
    errorMessage: str | None = None
