"""Hybrid ingestion routes (Path 1 Real-Time Edit Event & Path 2 Checkpoint)."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.routes.health import get_db_session
from src.core.security import CallerIdentity, verify_caller_identity
from src.ingestion.checkpoint_pipeline import execute_checkpoint_pipeline
from src.ingestion.realtime_edit_handler import handle_realtime_edit_event
from src.schemas.audit import (
    CheckpointIngestResponse,
    RealTimeEditEventRequest,
    RealTimeEditEventResponse,
)

router = APIRouter(tags=["ingestion"])


class CheckpointIngestRequest(BaseModel):
    """Payload for POST /v1/ingest/checkpoint."""

    spreadsheet_id: str = Field(..., min_length=1, max_length=128)
    workbook_name: str = Field(default="Regional Power Generation Techno-Economic Model")
    xlsm_file_path: str | None = None
    xlsm_base64: str | None = None
    sheets_grid_payload: dict[str, Any] | None = None
    commit_comment: str = Field(default="Governed model checkpoint")
    who_google_user: str | None = None


@router.post("/v1/ingest/edit-event", response_model=RealTimeEditEventResponse)
async def ingest_realtime_edit_event(
    request: Request,
    payload: RealTimeEditEventRequest,
    session: AsyncSession = Depends(get_db_session),
    caller: CallerIdentity = Depends(verify_caller_identity),
) -> RealTimeEditEventResponse:
    """Ingest a real-time Google Sheets onEdit cell event (Path 1)."""
    bq_sink = getattr(request.app.state, "bq_sink", None)
    async with session.begin():
        return await handle_realtime_edit_event(
            session=session,
            request=payload,
            who_iam_principal=caller.iam_principal,
            who_client_platform=caller.client_platform,
            bq_sink=bq_sink,
        )


@router.post("/v1/ingest/checkpoint", response_model=CheckpointIngestResponse)
async def ingest_checkpoint_snapshot(
    request: Request,
    payload: CheckpointIngestRequest,
    session: AsyncSession = Depends(get_db_session),
    caller: CallerIdentity = Depends(verify_caller_identity),
) -> CheckpointIngestResponse:
    """Ingest a full structural workbook checkpoint snapshot (Path 2)."""
    snapshot_store = getattr(request.app.state, "snapshot_store", None)
    bq_sink = getattr(request.app.state, "bq_sink", None)

    raw_bytes: bytes | None = None
    if payload.xlsm_file_path:
        path = Path(payload.xlsm_file_path).resolve()
        if not path.exists():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Workbook file not found: {payload.xlsm_file_path}",
            )
        raw_bytes = path.read_bytes()
    elif payload.xlsm_base64:
        raw_bytes = base64.b64decode(payload.xlsm_base64)
    elif payload.sheets_grid_payload is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Must provide xlsm_file_path, xlsm_base64, or sheets_grid_payload.",
        )

    async with session.begin():
        response, _graph = await execute_checkpoint_pipeline(
            session=session,
            spreadsheet_id=payload.spreadsheet_id,
            workbook_name=payload.workbook_name,
            raw_bytes=raw_bytes,
            grid_payload=payload.sheets_grid_payload,
            who_google_user=payload.who_google_user or caller.email,
            who_iam_principal=caller.iam_principal,
            who_client_platform=caller.client_platform,
            commit_comment=payload.commit_comment,
            snapshot_store=snapshot_store,
            bq_sink=bq_sink,
        )
        return response
