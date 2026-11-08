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

from brazil_power_agent.excel_renderer import ExcelLayoutRenderer
from brazil_power_agent.mcp_server import MCP_TOOLS, handle_jsonrpc_request
from brazil_power_agent.session_store import BrazilPowerSessionManager, SeedWorkbookLoader
from brazil_power_agent.workbook_exporter import export_full_22tab_workbook

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
]
