"""Structural governance, lineage, version history, and technical debt API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.routes.health import get_db_session
from src.core.security import CallerIdentity, verify_caller_identity
from src.db.repositories import GovernanceRepository

router = APIRouter(tags=["governance"])


@router.get("/v1/workbooks/{spreadsheet_id}/versions")
async def list_workbook_versions(
    spreadsheet_id: str,
    session: AsyncSession = Depends(get_db_session),
    _caller: CallerIdentity = Depends(verify_caller_identity),
) -> dict[str, Any]:
    """List committed structural checkpoint versions for a workbook."""
    repo = GovernanceRepository(session)
    versions = await repo.list_versions(spreadsheet_id)
    return {
        "spreadsheet_id": spreadsheet_id,
        "version_count": len(versions),
        "versions": [
            {
                "version_id": v.version_id,
                "parent_version_id": v.parent_version_id,
                "version_seq_num": v.version_seq_num,
                "sha256_hash": v.sha256_hash,
                "gcs_snapshot_uri": v.gcs_snapshot_uri,
                "total_sheets": v.total_sheets,
                "total_populated_cells": v.total_populated_cells,
                "total_formula_cells": v.total_formula_cells,
                "total_dag_edges": v.total_dag_edges,
                "structural_mutation_count": v.structural_mutation_count,
                "manual_override_count": v.manual_override_count,
                "commit_comment": v.commit_comment,
                "committed_by_google_user": v.committed_by_google_user,
                "created_at_utc": v.created_at_utc.isoformat() if v.created_at_utc else None,
            }
            for v in versions
        ],
    }


@router.get("/v1/workbooks/{spreadsheet_id}/audit-log")
async def get_workbook_audit_log(
    spreadsheet_id: str,
    change_type: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db_session),
    _caller: CallerIdentity = Depends(verify_caller_identity),
) -> dict[str, Any]:
    """Query immutable 4-Ws structural audit events for a workbook."""
    repo = GovernanceRepository(session)
    events = await repo.list_audit_events(
        spreadsheet_id=spreadsheet_id,
        change_type=change_type,
    )
    return {
        "spreadsheet_id": spreadsheet_id,
        "total_events": len(events),
        "events": events,
    }


@router.get("/v1/workbooks/{spreadsheet_id}/lineage")
async def get_cell_lineage(
    spreadsheet_id: str,
    sheet_name: str = Query(..., description="Worksheet name, e.g., _01_CF"),
    cell_coord: str = Query(..., description="Cell A1 coordinate, e.g., B18"),
    max_depth: int = Query(default=4, ge=1, le=10),
    session: AsyncSession = Depends(get_db_session),
    _caller: CallerIdentity = Depends(verify_caller_identity),
) -> dict[str, Any]:
    """Query upstream precedents and downstream dependents in the formula DAG."""
    repo = GovernanceRepository(session)
    latest = await repo.get_latest_version(spreadsheet_id)
    if latest is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No committed versions found for spreadsheet_id '{spreadsheet_id}'",
        )
    return await repo.get_lineage_subgraph(
        version_id=latest.version_id,
        sheet_name=sheet_name,
        cell_coord=cell_coord,
        max_depth=max_depth,
    )


@router.get("/v1/workbooks/{spreadsheet_id}/technical-debt")
async def get_workbook_technical_debt(
    spreadsheet_id: str,
    session: AsyncSession = Depends(get_db_session),
    _caller: CallerIdentity = Depends(verify_caller_identity),
) -> dict[str, Any]:
    """Return the automated legacy technical debt diagnostic report (FR-B04 / DEC-02)."""
    repo = GovernanceRepository(session)
    latest = await repo.get_latest_version(spreadsheet_id)
    if latest is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No committed versions found for spreadsheet_id '{spreadsheet_id}'",
        )
    items = await repo.list_technical_debt_items(latest.version_id)
    broken_names = [i for i in items if i["debt_category"] == "BROKEN_NAMED_RANGE"]
    return {
        "spreadsheet_id": spreadsheet_id,
        "version_id": latest.version_id,
        "total_technical_debt_items": len(items),
        "broken_named_ranges_count": len(broken_names),
        "items": items,
    }
