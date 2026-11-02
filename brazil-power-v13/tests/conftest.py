"""Shared PyTest fixtures for Pillar A Solver, Pillar B AST/DAG & Audit, E2E, and IaC tests."""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.config import Settings, get_settings
from src.db.session import get_session_factory, init_db_schema
from src.solver.workbook_context import WorkbookSolverContext, get_baseline_solver_context


@pytest.fixture(scope="session")
def test_settings() -> Settings:
    """Return test Settings instance."""
    return get_settings()


@pytest.fixture(scope="session")
def seed_xlsm_path(test_settings: Settings) -> Path:
    """Return path to read-only seed workbook 2023-11-27-Brazil_TT_v13_RJEB.xlsm."""
    assert test_settings.seed_workbook_path.exists(), (
        f"Missing seed workbook at {test_settings.seed_workbook_path}"
    )
    return test_settings.seed_workbook_path


@pytest.fixture(scope="session")
def solver_context() -> WorkbookSolverContext:
    """Return pre-warmed baseline WorkbookSolverContext."""
    return get_baseline_solver_context()


@pytest_asyncio.fixture()
async def db_session_factory(tmp_path: Path) -> async_sessionmaker[AsyncSession]:
    """Provide an isolated SQLite database with NFR-05 audit_events immutability triggers installed."""
    db_file = tmp_path / "test_governance.db"
    dsn = f"sqlite+aiosqlite:///{db_file}"
    await init_db_schema(dsn)
    return get_session_factory(dsn)
