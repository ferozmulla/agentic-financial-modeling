"""FastAPI application factory for the Enterprise Commodity Modeling Platform."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.api.routes import governance, governance_dashboard, health, ingest, solve, telemetry
from src.core.logging import get_logger
from src.core.security import SecureHeadersMiddleware
from src.db.bigquery_sink import BigQueryAnalyticalSink
from src.db.session import init_db_schema
from src.storage.snapshot_store import SnapshotStore, get_snapshot_store

logger = get_logger(__name__)


def create_app(
    snapshot_store: SnapshotStore | None = None,
    bq_sink: BigQueryAnalyticalSink | None = None,
) -> FastAPI:
    """Create and configure the FastAPI Gateway application."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        await init_db_schema()
        if not hasattr(app.state, "snapshot_store") or app.state.snapshot_store is None:
            app.state.snapshot_store = snapshot_store or get_snapshot_store()
        if not hasattr(app.state, "bq_sink") or app.state.bq_sink is None:
            app.state.bq_sink = bq_sink or BigQueryAnalyticalSink()
        yield

    app = FastAPI(
        title="Enterprise Commodity Modeling — Google Sheets Modernization & Governance Gateway",
        version="1.0.0",
        description=(
            "Pillar A Serverless Quantitative Solver & Pillar B AST/DAG Structural "
            "Governance Engine."
        ),
        lifespan=lifespan,
    )

    app.state.snapshot_store = snapshot_store or get_snapshot_store()
    app.state.bq_sink = bq_sink or BigQueryAnalyticalSink()

    app.add_middleware(SecureHeadersMiddleware)

    app.include_router(health.router)
    app.include_router(solve.router)
    app.include_router(ingest.router)
    app.include_router(governance.router)
    app.include_router(governance_dashboard.router)
    app.include_router(telemetry.router)

    return app


app = create_app()
