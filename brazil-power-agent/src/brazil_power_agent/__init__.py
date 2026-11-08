"""Brazil Energy Model (v13) — Native Gemini App Skills & MCP Prototype Package."""

from __future__ import annotations

import sys
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
V13_ROOT = WORKSPACE_ROOT / "brazil-power-v13"
AGENT_SRC_ROOT = Path(__file__).resolve().parents[1]

for _p in (str(AGENT_SRC_ROOT), str(V13_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from typing import Any

__all__ = [
    "AGENT_SRC_ROOT",
    "MCP_TOOLS",
    "V13_ROOT",
    "WORKSPACE_ROOT",
    "BrazilPowerSessionManager",
    "ExcelLayoutRenderer",
    "SeedWorkbookLoader",
    "export_full_22tab_workbook",
    "handle_jsonrpc_request",
    "install_skills_and_mcp",
    "verify_skills_and_mcp_installed",
]


def __getattr__(name: str) -> Any:
    if name in ("install_skills_and_mcp", "verify_skills_and_mcp_installed"):
        from brazil_power_agent import install_customizations

        return getattr(install_customizations, name)
    if name == "ExcelLayoutRenderer":
        from brazil_power_agent.excel_renderer import ExcelLayoutRenderer

        return ExcelLayoutRenderer
    if name in ("MCP_TOOLS", "handle_jsonrpc_request"):
        from brazil_power_agent import mcp_server

        return getattr(mcp_server, name)
    if name in ("BrazilPowerSessionManager", "SeedWorkbookLoader"):
        from brazil_power_agent import session_store

        return getattr(session_store, name)
    if name == "export_full_22tab_workbook":
        from brazil_power_agent.workbook_exporter import export_full_22tab_workbook

        return export_full_22tab_workbook
    raise AttributeError(f"module 'brazil_power_agent' has no attribute {name!r}")
