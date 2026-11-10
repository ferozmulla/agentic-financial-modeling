"""7 Remote MCP Tools and JSON-RPC 2.0 dispatcher for `eulr-bq-twin-mcp`."""

from __future__ import annotations

import json
import logging
from typing import Any

from eulr_bq_twin.bq_store import EulrDigitalTwinStore
from eulr_bq_twin.config import EulrTwinSettings, get_eulr_twin_settings
from eulr_bq_twin.renderer import (
    render_assumptions_markdown,
    render_bqml_outputs,
    render_equilibrium_outputs,
    render_hck_economics_outputs,
    render_scenario_matrix_outputs,
)
from eulr_bq_twin.solver_engine import EulrQuantitativeSolver
from eulr_bq_twin.xlsx_synthesizer import synthesize_eulr_workbook

logger = logging.getLogger(__name__)

MCP_SERVER_NAME = "eulr-bq-twin-mcp"
MCP_SERVER_VERSION = "1.0.0"
MCP_PROTOCOL_VERSION = "2024-11-05"

EULR_TWIN_MCP_TOOLS: list[dict[str, Any]] = [
    {
        "name": "get_eulr_session_assumptions",
        "description": (
            "Query the active session's European Refining Yardstick Margins (KeyInputs), EU ETS Carbon switches "
            "(Carbon!A5:A6), Benchmark Crudes, and NWE/MED CIF & FOB product prices directly from the BigQuery "
            "Digital Twin (`comm-model-mod.eulr_digital_twin`, zero Excel files)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Optional session identifier for isolated sparse delta overlay.",
                }
            },
            "additionalProperties": True,
        },
    },
    {
        "name": "update_eulr_session_overrides",
        "description": (
            "Persist driver overrides (`fcc_margin_shock_usd_bbl`, `dated_brent_usd_bbl`, `eu_ets_mode`, or `Sheet!Cell`), "
            "Pinned Price Overrides on circular pricing tabs (e.g. `{'NWE Cif!AU122': 750.0}`), or `reset_to_baseline=true` "
            "into BigQuery `dt_scenario_deltas` + immutable 4-Ws `dt_audit_events`."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "eu_ets_mode": {
                    "type": "string",
                    "enum": ["cost_and_allocation", "variable_cost_only", "carbon_off"],
                    "description": "Optional Carbon!A5:A6 EU ETS pass-through switch mode.",
                },
                "driver_overrides": {
                    "type": "object",
                    "description": "Driver overrides by alias (`fcc_margin_shock_usd_bbl`, `dated_brent_shock_usd_bbl`) or `Sheet!Cell`.",
                },
                "pinned_price_overrides": {
                    "type": "object",
                    "description": "Pinned product price overrides held fixed across all 10 Gauss-Seidel passes (e.g. `{'NWE Cif!AU122': 750.0}`).",
                },
                "reset_to_baseline": {
                    "type": "boolean",
                    "default": False,
                    "description": "When true, writes tombstones resetting the session to `lr202409_baseline`.",
                },
            },
            "additionalProperties": True,
        },
    },
    {
        "name": "run_eulr_equilibrium_solve",
        "description": (
            "Execute the 10-pass Gauss-Seidel circular equilibrium solver across all coupled EULR sheets "
            "(NWE/MED CIF & FOB, KeyInputs, Carbon, Crudes, Freight, IMOfuels, HCK, Checks), honoring active "
            "driver & Pinned Price overrides and optional 3-peer (`Uslr`/`Felr`/`Tankerlr`) upstream sync."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "max_iterations": {"type": "integer", "default": 10},
                "upstream_mode": {
                    "type": "string",
                    "enum": ["baseline_cached", "peer_synced"],
                    "default": "baseline_cached",
                },
                "eu_ets_mode": {
                    "type": "string",
                    "enum": ["cost_and_allocation", "variable_cost_only", "carbon_off"],
                },
                "fcc_margin_shock_usd_bbl": {"type": "number", "default": 0.0},
                "pinned_price_overrides": {"type": "object"},
            },
            "additionalProperties": True,
        },
    },
    {
        "name": "run_eulr_scenario_matrix",
        "description": (
            "Sweep all 6 European Refining, EU ETS Carbon Pass-Through (`Cost+Allocation`, `Variable Cost Only`, `Carbon Off`), "
            "FCC Margin Stress (`+/- $1.50/bbl`), and Live 3-Peer Upstream Sync (`Uslr`/`Felr`/`Tankerlr`) scenarios, "
            "returning comparison tables and ECharts v5 visual specs."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "target_year": {
                    "type": "integer",
                    "enum": [2024, 2025, 2030, 2035, 2040, 2045, 2050],
                    "default": 2035,
                },
            },
            "additionalProperties": True,
        },
    },
    {
        "name": "run_eulr_bqml_forecast_refresh",
        "description": (
            "Query live BigQuery ML `ARIMA_PLUS` 2025–2050 trajectories (`MACRO`, `CRUDES`, `FREIGHT`) from "
            "`comm-model-mod.eulr_digital_twin.vw_eulr_bqml_forecasts`, optionally inject into session drivers "
            "and re-solve 10-pass European equilibrium, returning tables and ECharts v5 specs."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "domain_groups": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["MACRO", "CRUDES", "FREIGHT"]},
                    "default": ["MACRO", "CRUDES", "FREIGHT"],
                },
                "apply_to_session": {"type": "boolean", "default": True},
            },
            "additionalProperties": True,
        },
    },
    {
        "name": "run_eulr_hck_and_ulsd_economics",
        "description": (
            "Evaluate 200 kb/d Sour Hydrocracker Project IRR & NPV across a 9-point conversion margin sweep "
            "(`2015 NWE HCK IRR`), Naphtha vs. Diesel mode revamp (`HCK naphtha revamp`), and ULSD 10ppm vs. "
            "0.1%S Gasoil cost-coverage spreads (`ULSD-GO_spread_econs`)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "discount_rate_wacc": {"type": "number", "default": 0.10},
            },
            "additionalProperties": True,
        },
    },
    {
        "name": "export_eulr_workbook",
        "description": (
            "Synthesize an 18-tab core analytical `.xlsx` workbook (or full 19-tab workbook with `include_upload_tab=true`) "
            "100% from BigQuery Digital Twin rows, resolving all 14,162 external SharePoint links to clean values while "
            "preserving all 343,546 internal `=Formulas` live and highlighting pinned prices in `#FDE68A` amber."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string"},
                "include_upload_tab": {
                    "type": "boolean",
                    "default": False,
                    "description": "False exports the fast 18 core pricing/analytical tabs; True adds the 93,935-cell UPLOAD tab.",
                },
                "upstream_mode": {
                    "type": "string",
                    "enum": ["baseline_cached", "peer_synced"],
                    "default": "baseline_cached",
                },
                "filename_prefix": {
                    "type": "string",
                    "default": "EULR_Refining_Digital_Twin",
                },
            },
            "additionalProperties": True,
        },
    },
]


class EulrMcpDispatcher:
    """Stateful singleton dispatcher serving MCP JSON-RPC 2.0 requests for `eulr-bq-twin-mcp`."""

    def __init__(
        self,
        store: EulrDigitalTwinStore | None = None,
        settings: EulrTwinSettings | None = None,
    ) -> None:
        self.settings = settings or get_eulr_twin_settings()
        self.store = store or EulrDigitalTwinStore(settings=self.settings)
        self.solver = EulrQuantitativeSolver(self.store)

    def dispatch_tool(
        self, tool_name: str, arguments: dict[str, Any] | None, default_session: str | None = None
    ) -> dict[str, Any]:
        args = arguments or {}
        sess_id = str(args.get("session_id") or default_session or self.settings.default_session_id)

        if tool_name == "get_eulr_session_assumptions":
            raw = self.solver.get_session_assumptions(sess_id)
            md = render_assumptions_markdown(raw)
            return {"session_id": sess_id, **md, "snapshot": raw}

        if tool_name == "update_eulr_session_overrides":
            raw = self.solver.apply_user_overrides(
                session_id=sess_id,
                driver_overrides=args.get("driver_overrides"),
                pinned_price_overrides=args.get("pinned_price_overrides"),
                eu_ets_mode=args.get("eu_ets_mode"),
                reset_to_baseline=bool(args.get("reset_to_baseline", False)),
            )
            md = render_assumptions_markdown(raw)
            return {
                "session_id": sess_id,
                "cells_written": raw.get("cells_written", 0),
                **md,
                "snapshot": raw,
            }

        if tool_name == "run_eulr_equilibrium_solve":
            solve_res = self.solver.solve_equilibrium(
                session_id=sess_id,
                max_iterations=int(args.get("max_iterations", 10)),
                upstream_mode=args.get("upstream_mode", "baseline_cached"),
                eu_ets_mode=args.get("eu_ets_mode"),
                fcc_margin_shock_usd_bbl=float(args.get("fcc_margin_shock_usd_bbl", 0.0)),
                extra_pinned_overrides=args.get("pinned_price_overrides"),
                persist_outputs=True,
            )
            rendered = render_equilibrium_outputs(solve_res)
            return {**solve_res, **rendered}

        if tool_name == "run_eulr_scenario_matrix":
            mat_res = self.solver.run_scenario_matrix(
                session_id=sess_id,
                target_year=int(args.get("target_year", 2035)),
            )
            rendered = render_scenario_matrix_outputs(mat_res)
            return {**mat_res, **rendered}

        if tool_name == "run_eulr_bqml_forecast_refresh":
            bqml_res = self.solver.run_bqml_forecast_refresh(
                session_id=sess_id,
                domain_groups=args.get("domain_groups"),
                apply_to_session=bool(args.get("apply_to_session", True)),
            )
            rendered = render_bqml_outputs(bqml_res)
            return {**bqml_res, **rendered}

        if tool_name == "run_eulr_hck_and_ulsd_economics":
            hck_res = self.solver.run_hck_and_ulsd_economics(
                session_id=sess_id,
                discount_rate_wacc=float(args.get("discount_rate_wacc", 0.10)),
            )
            rendered = render_hck_economics_outputs(hck_res)
            return {**hck_res, **rendered}

        if tool_name == "export_eulr_workbook":
            exp = synthesize_eulr_workbook(
                store=self.store,
                session_id=sess_id,
                include_upload_tab=bool(args.get("include_upload_tab", False)),
                upstream_mode=args.get("upstream_mode", "baseline_cached"),
                filename_prefix=str(args.get("filename_prefix", "EULR_Refining_Digital_Twin")),
            )
            summary_md = (
                f"### Synthesized EULR Digital Twin Workbook (`{exp['tabs_exported']}` Tabs)\n"
                f"- **Download Link**: [{exp['filename']}]({exp['download_url']})\n"
                f"- **Cells Synthesized**: `{exp['total_cells_written']:,}` | **Live Internal Formulas**: `{exp['live_internal_formulas']:,}` | "
                f"**External SharePoint Links Resolved**: `{exp['resolved_external_links']:,}` | **Pinned Cells Highlighted**: `{exp['pinned_cells_highlighted']}`"
            )
            return {**exp, "inline_markdown": summary_md}

        raise ValueError(f"Unknown MCP tool: {tool_name!r}")

    def handle_jsonrpc(
        self, payload: dict[str, Any], default_session: str | None = None
    ) -> dict[str, Any] | None:
        method = payload.get("method", "")
        req_id = payload.get("id")

        if method.startswith("notifications/"):
            return None

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {
                        "name": MCP_SERVER_NAME,
                        "version": MCP_SERVER_VERSION,
                    },
                },
            }

        if method == "ping":
            return {"jsonrpc": "2.0", "id": req_id, "result": {}}

        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"tools": EULR_TWIN_MCP_TOOLS},
            }

        if method == "tools/call":
            params = payload.get("params") or {}
            tname = params.get("name", "")
            targs = params.get("arguments") or {}
            try:
                res = self.dispatch_tool(tname, targs, default_session=default_session)
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(res)}],
                        "isError": False,
                    },
                }
            except Exception as exc:
                logger.exception("EULR MCP tool error (%s)", tname)
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps({"error": f"Tool execution failed: {exc}"}),
                            }
                        ],
                        "isError": True,
                    },
                }

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }
