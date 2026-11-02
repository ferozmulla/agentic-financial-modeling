"""Health check routes for Cloud Run and deep readiness verification."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.db.session import get_session_factory
from src.solver.macros.registry import MacroExecutionRegistry

router = APIRouter(tags=["health"])


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding an AsyncSession."""
    factory = get_session_factory()
    async with factory() as session:
        yield session


@router.get("/health")
async def health_check() -> dict[str, str | int]:
    """Liveness check endpoint."""
    settings = get_settings()
    return {
        "status": "ok",
        "service": "commodity-modeling-gateway",
        "gcp_project_id": settings.gcp_project_id,
        "gcp_region": settings.gcp_region,
        "gemini_location": settings.gemini_location,
        "registered_macros": len(MacroExecutionRegistry.list_supported_macros()),
    }


@router.get("/v1/health/deep")
async def deep_health_check(
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, str | int]:
    """Deep readiness check verifying database connectivity and solver registry."""
    settings = get_settings()
    await session.execute(text("SELECT 1"))
    macros = MacroExecutionRegistry.list_supported_macros()
    return {
        "status": "healthy",
        "database": "connected",
        "gcp_project_id": settings.gcp_project_id,
        "gcp_region": settings.gcp_region,
        "bq_location": settings.bq_location,
        "gemini_location": settings.gemini_location,
        "registered_macro_count": len(macros),
    }
