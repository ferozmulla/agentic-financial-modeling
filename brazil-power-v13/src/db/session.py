"""Async SQLAlchemy engine, session factory, advisory lock turnstile, and NFR-05 immutability triggers."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.core.config import get_settings
from src.db.models import Base

_ENGINES: dict[str, AsyncEngine] = {}
_LOCAL_LOCKS: dict[str, asyncio.Lock] = {}


def get_async_engine(database_url: str | None = None) -> AsyncEngine:
    """Return or create an AsyncEngine for the target database_url."""
    dsn = database_url or get_settings().database_url
    if dsn not in _ENGINES:
        if dsn.startswith("sqlite+aiosqlite:///"):
            db_file = dsn.removeprefix("sqlite+aiosqlite:///")
            if db_file and db_file != ":memory:":
                Path(db_file).parent.mkdir(parents=True, exist_ok=True)
        _ENGINES[dsn] = create_async_engine(dsn, future=True, echo=False)
    return _ENGINES[dsn]


def get_session_factory(database_url: str | None = None) -> async_sessionmaker[AsyncSession]:
    """Return an async_sessionmaker bound to the target database_url."""
    engine = get_async_engine(database_url)
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db_schema(database_url: str | None = None) -> None:
    """Create all 10 governance tables and install the NFR-05 append-only triggers on audit_events."""
    engine = get_async_engine(database_url)
    dsn = str(engine.url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if dsn.startswith("sqlite"):
            # Install SQLite equivalent of prevent_audit_events_mutation() trigger (NFR-05 / TEST-B07)
            await conn.execute(
                text(
                    """
                    CREATE TRIGGER IF NOT EXISTS trg_prevent_audit_events_update
                    BEFORE UPDATE ON audit_events
                    BEGIN
                        SELECT RAISE(ABORT, 'NFR-05 Governance Violation: prevent_audit_events_mutation — audit_events is strictly append-only.');
                    END;
                    """
                )
            )
            await conn.execute(
                text(
                    """
                    CREATE TRIGGER IF NOT EXISTS trg_prevent_audit_events_delete
                    BEFORE DELETE ON audit_events
                    BEGIN
                        SELECT RAISE(ABORT, 'NFR-05 Governance Violation: prevent_audit_events_mutation — audit_events is strictly append-only.');
                    END;
                    """
                )
            )
        else:
            # PostgreSQL / AlloyDB trigger from migrations/002_audit_immutability_trigger.sql
            await conn.execute(
                text(
                    """
                    CREATE OR REPLACE FUNCTION prevent_audit_events_mutation()
                    RETURNS TRIGGER AS $$
                    BEGIN
                        RAISE EXCEPTION 'NFR-05 Governance Violation: audit_events table is strictly append-only. % operations are prohibited.', TG_OP;
                    END;
                    $$ LANGUAGE plpgsql;
                    """
                )
            )
            await conn.execute(
                text(
                    "DROP TRIGGER IF EXISTS trg_prevent_audit_events_row_mutation ON audit_events;"
                )
            )
            await conn.execute(
                text(
                    """
                    CREATE TRIGGER trg_prevent_audit_events_row_mutation
                    BEFORE UPDATE OR DELETE ON audit_events
                    FOR EACH ROW EXECUTE FUNCTION prevent_audit_events_mutation();
                    """
                )
            )


@asynccontextmanager
async def acquire_spreadsheet_advisory_lock(
    session: AsyncSession,
    spreadsheet_id: str,
) -> AsyncIterator[None]:
    """Acquire AlloyDB transaction-scoped advisory lock pg_advisory_xact_lock(hashtext(:spreadsheet_id))."""
    bind = session.get_bind()
    dialect_name = bind.dialect.name if bind is not None else "sqlite"
    if dialect_name == "postgresql":
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:sid))"),
            {"sid": spreadsheet_id},
        )
        yield
    else:
        lock = _LOCAL_LOCKS.setdefault(spreadsheet_id, asyncio.Lock())
        async with lock:
            yield
