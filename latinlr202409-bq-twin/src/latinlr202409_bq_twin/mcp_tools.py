"""JSON-RPC 2.0 MCP Tool Schemas & Dispatcher for `latinlr202409-bq-twin-mcp`."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import TwinSettings, get_twin_settings
from .models import BaselineSnapshot
from .solver_engine import CRUDE_TO_YIELDS_COL, LatinRefiningSolverEngine
from .xlsx_synthesizer import synthesize_workbook_from_snapshot

MCP_SERVER_NAME = "latinlr202409-bq-twin-mcp"
MCP_SERVER_VERSION = "1.0.0"
MCP_PROTOCOL_VERSION = "2024-11-05"

TWIN_MCP_TOOLS: list[dict[str, Any]] = [
    {
        "name": "get_latinlr202409_model_summary",
        "description": "Return metadata, active sheets, and Latin American crude assay roster for the `latinlr202409` BigQuery Digital Twin.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Optional scenario session ID."}
            },
        },
    },
    {
        "name": "run_latinlr202409_equilibrium_scenario",
        "description": "Run the deterministic circular equilibrium & Gross Product Worth (GPW) solver across the 13 Latin American crudes with optional `Sheet!Coord` overrides.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "overrides": {
                    "type": "object",
                    "description": "Map of `Sheet!Coord` (e.g. `Yields!F18`) to numeric override value.",
                },
                "why_context": {"type": "string", "description": "4-Ws governance audit reason."},
            },
        },
    },
    {
        "name": "export_latinlr202409_xlsx",
        "description": "Synthesize a path-safe `.xlsx` workbook from the BigQuery Digital Twin snapshot.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "default": "Latinlr202409_twin_export.xlsx"},
            },
        },
    },
]


class TwinMcpDispatcher:
    """Stateless/BigQuery-backed MCP tool dispatcher for `latinlr202409-bq-twin-mcp`."""

    def __init__(self, snapshot: BaselineSnapshot | None = None, settings: TwinSettings | None = None) -> None:
        self.settings = settings or get_twin_settings()
        self.snapshot = snapshot or BaselineSnapshot(
            workbook_id=self.settings.workbook_id,
            version_id=self.settings.base_version_id,
        )
        self.solver = LatinRefiningSolverEngine(self.snapshot)

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        args = arguments or {}
        if name == "get_latinlr202409_model_summary":
            return {
                "workbook_id": self.settings.workbook_id,
                "bq_dataset_id": self.settings.bq_dataset_id,
                "crude_assays": list(CRUDE_TO_YIELDS_COL.keys()),
                "loaded_sheets": list(self.snapshot.cells_by_sheet.keys()),
            }
        if name == "run_latinlr202409_equilibrium_scenario":
            overrides = args.get("overrides") or {}
            return self.solver.run_scenario(overrides_a1=overrides)
        if name == "export_latinlr202409_xlsx":
            fname = str(args.get("filename") or "Latinlr202409_twin_export.xlsx")
            out_path = synthesize_workbook_from_snapshot(
                self.snapshot, Path(self.settings.export_local_dir), fname
            )
            return {"exported_path": str(out_path), "filename": out_path.name}
        raise ValueError(f"Unknown MCP tool: {name!r}")
