"""Zero-Dependency JSON-RPC 2.0 Stdio MCP Server (`brazil-power-mcp`) for Brazil Power v13."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, BinaryIO, Callable

WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
V13_ROOT = WORKSPACE_ROOT / "brazil-power-v13"
AGENT_SRC_ROOT = Path(__file__).resolve().parents[1]

for _p in (str(AGENT_SRC_ROOT), str(V13_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from brazil_power_agent.session_store import (
    BrazilPowerSessionManager,
    normalize_technology_code,
)
from brazil_power_agent.workbook_exporter import (
    GOLDEN_GOOGLE_SHEET_ID,
    export_full_22tab_workbook as _export_workbook,
)

MCP_SERVER_NAME = "brazil-power-mcp"
MCP_SERVER_VERSION = "1.0.0"
MCP_PROTOCOL_VERSION = "2024-11-05"

TECHNOLOGY_ENUM = [
    "_01_CF",
    "_02_CF",
    "_03_CF",
    "_04_CF",
    "_05_CF",
    "_06_CF",
    "_07_CF",
    "_08_CF",
    "_09_CF",
    "_10_CF",
    "_11_CF",
    "_12_CF",
]

MCP_TOOLS: list[dict[str, Any]] = [
    {
        "name": "get_session_assumptions",
        "description": (
            "Return the current session's General!C5:N40 assumptions table (both baseline values from "
            "2023-11-27-Brazil_TT_v13_RJEB.xlsm and any staged scenario overrides with Baseline -> Current delta), "
            "formatted as an exact Excel-coordinate Markdown table."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "technologies": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Optional list of technology sheet codes ('_01_CF'..'_12_CF') to include in the compact inline "
                        "Excel table preview. Defaults to ['_01_CF', '_04_CF', '_05_CF', '_06_CF']."
                    ),
                },
                "include_full_general_tab": {
                    "type": "boolean",
                    "default": True,
                    "description": "When true, includes the complete 12-technology General!B5:N40 replica for side-pane Artifact rendering.",
                },
            },
            "additionalProperties": True,
        },
    },
    {
        "name": "update_session_assumptions",
        "description": (
            "Stage scenario assumption overrides in the persistent session store (e.g. "
            "{'_01_CF': {'fuel_cost_r_per_mmbtu': 6.50, 'real_wacc': 0.09}, '_06_CF': {'lead_time_years': 2}} "
            "or raw Excel coordinates {'General!C20': 6.50, 'General!H14': 2.0}) and return the formatted Excel diff table."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "overrides": {
                    "type": "object",
                    "description": (
                        "Mapping of technology codes ('_01_CF'..'_12_CF') to parameter dicts, or direct Excel cell "
                        "coordinates ('General!C20', 'General!H14', 'CVU_GF!C5') to numeric values."
                    ),
                },
                "reset_to_baseline": {
                    "type": "boolean",
                    "default": False,
                    "description": "If true, clears all previous session overrides and restores the seed baseline before applying overrides.",
                },
            },
            "additionalProperties": True,
        },
    },
    {
        "name": "run_tornado_sensitivity",
        "description": (
            "Execute the 21-point 2-Stage Discrete Lattice Binary Search IRR sensitivity macro (calcule_tir1..12), "
            "updating _0N_CF!E6:G12 and Output_1 in the session state and returning the exact Excel replica table "
            "plus an Apache ECharts V5 horizontal Tornado bar chart specification."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "technology_code": {
                    "type": "string",
                    "enum": [*TECHNOLOGY_ENUM, "ALL"],
                    "default": "_06_CF",
                    "description": "Target technology tab ('_01_CF'..'_12_CF' or 'ALL').",
                },
                "parity_mode": {
                    "type": "string",
                    "enum": ["strict_legacy_vba", "modern_corrected"],
                    "default": "strict_legacy_vba",
                    "description": "Solver convergence parity mode.",
                },
            },
            "required": ["technology_code"],
            "additionalProperties": True,
        },
    },
    {
        "name": "run_bqml_timeseries_refresh",
        "description": (
            "Query or refresh the 23-year BigQuery ML ARIMA_PLUS trajectories from "
            "comm-model-mod.sheets_commodity_mod_governance.vw_connected_sheets_lt_forecasts (with deterministic "
            "offline snapshot fallback), inject them into LT Capex!B8:J30, LT Fuel!B8:J30, and LT CF!B8:J30, "
            "and return Excel-layout trajectory tables plus an ECharts trajectory chart specification."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "curve_types": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["CAPEX", "FUEL", "CF"]},
                    "default": ["CAPEX", "FUEL", "CF"],
                    "description": "Which long-term forecast tabs to refresh ('CAPEX', 'FUEL', 'CF').",
                },
                "apply_to_session_lt_tabs": {
                    "type": "boolean",
                    "default": True,
                    "description": "If true, writes the refreshed trajectories into the active session's LT Capex, LT Fuel, and LT CF tabs.",
                },
            },
            "additionalProperties": True,
        },
    },
    {
        "name": "run_lcoe_horizon_forecast",
        "description": (
            "Execute lcoe_exec (184 binary-search LCOE solves across 2024-2046 plus Thermal ICB dispatch), "
            "updating Output_3!B9:J31 and Output_3!B3 in the session state and returning the inline summary table, "
            "full 23-year x 9-column Output_3 Excel replica table, and multi-series ECharts trajectory spec."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "parity_mode": {
                    "type": "string",
                    "enum": ["strict_legacy_vba", "modern_corrected"],
                    "default": "strict_legacy_vba",
                    "description": "Preserves Legacy Quirk 7 (Output_3!D9:D31 blank) when 'strict_legacy_vba'.",
                },
            },
            "additionalProperties": True,
        },
    },
    {
        "name": "run_dcf_cashflow_analysis",
        "description": (
            "Execute the vectorized 30-year (2024-2053) Project & Shareholder DCF cash flow schedule for any "
            "technology tab (_01_CF.._12_CF) plus optional 10-point Thermal CVU / Physical Guarantee (GF & ICB) sweep, "
            "returning the executive valuation block, 30-year horizontal Excel replica table, and ECharts cash-flow waterfall spec."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "technology_code": {
                    "type": "string",
                    "enum": TECHNOLOGY_ENUM,
                    "default": "_01_CF",
                    "description": "Target technology worksheet ('_01_CF'..'_12_CF').",
                },
                "start_year": {
                    "type": "integer",
                    "default": 2024,
                    "description": "Start year of the 30-year DCF cash-flow schedule (default 2024).",
                },
                "end_year": {
                    "type": "integer",
                    "default": 2053,
                    "description": "End year of the 30-year DCF cash-flow schedule (default 2053).",
                },
                "include_cvu_gf_sweep": {
                    "type": "boolean",
                    "description": "When true (or by default for thermal/sweep sheets), also runs calculo_cvu<N> 1D CVU & Physical Guarantee sweep.",
                },
                "run_cvu_gf_sweep": {
                    "type": "boolean",
                    "description": "Alias for include_cvu_gf_sweep to trigger the 10-point calculo_cvu<N> sweep.",
                },
            },
            "required": ["technology_code"],
            "additionalProperties": True,
        },
    },
    {
        "name": "export_full_22tab_workbook",
        "description": (
            "Export the complete 22-tab Brazil Power v13 workbook with all session assumption overrides and solved "
            "macro outputs applied, either as a 100% faithful 22-tab .xlsx workbook, a cloned 22-tab Google Sheet "
            "from Golden Sheet 1apbos5xVpK4yBLiRFxQqAEyPVNkkYQ2ZvgAASibYYJI, or both."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "export_format": {
                    "type": "string",
                    "enum": ["xlsx", "google_sheets", "both"],
                    "default": "xlsx",
                    "description": "Deliverable format: 'xlsx', 'google_sheets', or 'both'.",
                },
                "output_filename": {
                    "type": "string",
                    "description": "Optional filename for the exported 22-tab .xlsx file.",
                },
                "output_dir": {
                    "type": "string",
                    "description": "Optional output directory for the exported .xlsx file.",
                },
                "sheet_title": {
                    "type": "string",
                    "description": "Optional title for the cloned 22-tab Google Sheet.",
                },
            },
            "additionalProperties": True,
        },
    },
]


def _resolve_session_mgr(
    session_mgr: BrazilPowerSessionManager | None = None,
    session_path: str | Path | None = None,
) -> BrazilPowerSessionManager:
    """Resolve an active BrazilPowerSessionManager instance."""
    if session_mgr is not None:
        return session_mgr
    if session_path is not None:
        return BrazilPowerSessionManager(session_path=Path(session_path))
    return BrazilPowerSessionManager()


def get_session_assumptions(
    technologies: list[str] | None = None,
    include_full_general_tab: bool = True,
    session_path: str | None = None,
    session_mgr: BrazilPowerSessionManager | None = None,
) -> dict[str, Any]:
    """Tool 1: Return current session General!C5:N40 assumptions and Excel-layout Markdown tables."""
    mgr = _resolve_session_mgr(session_mgr=session_mgr, session_path=session_path)
    res = mgr.get_assumptions(
        technologies=technologies,
        include_full_general_tab=include_full_general_tab,
    )
    res["inline_markdown"] = res["inline_excel_table_md"]
    res["artifact_markdown"] = res["full_artifact_table_md"]
    res["echarts_option"] = None
    return res


def update_session_assumptions(
    overrides: dict[str, Any] | None = None,
    reset_to_baseline: bool = False,
    session_path: str | None = None,
    session_mgr: BrazilPowerSessionManager | None = None,
) -> dict[str, Any]:
    """Tool 2: Stage scenario assumption overrides and return Excel coordinate diff table."""
    mgr = _resolve_session_mgr(session_mgr=session_mgr, session_path=session_path)
    res = mgr.update_assumptions(
        overrides=overrides,
        reset_to_baseline=reset_to_baseline,
    )
    res["inline_markdown"] = res["inline_excel_table_md"]
    res["artifact_markdown"] = res["full_artifact_table_md"]
    res["echarts_option"] = None
    return res


def run_tornado_sensitivity(
    technology_code: str = "_06_CF",
    parity_mode: str = "strict_legacy_vba",
    session_path: str | None = None,
    session_mgr: BrazilPowerSessionManager | None = None,
) -> dict[str, Any]:
    """Tool 3: Run 21-point 2-Stage Discrete Lattice Binary Search IRR sensitivity (calcule_tir1..12)."""
    mgr = _resolve_session_mgr(session_mgr=session_mgr, session_path=session_path)
    res = mgr.run_tornado(
        technology_code=technology_code,
        parity_mode=parity_mode,
    )
    res["inline_markdown"] = res["inline_excel_table_md"]
    res["artifact_markdown"] = res["full_artifact_table_md"]
    res["echarts_option"] = res["echarts_spec"]
    return res


def run_bqml_timeseries_refresh(
    curve_types: list[str] | None = None,
    apply_to_session_lt_tabs: bool = True,
    session_path: str | None = None,
    session_mgr: BrazilPowerSessionManager | None = None,
) -> dict[str, Any]:
    """Tool 4: Refresh 23-year BigQuery ML ARIMA_PLUS trajectories into LT Capex, LT Fuel, and LT CF."""
    mgr = _resolve_session_mgr(session_mgr=session_mgr, session_path=session_path)
    res = mgr.run_bqml_refresh(
        curve_types=curve_types,
        apply_to_session_lt_tabs=apply_to_session_lt_tabs,
    )
    res["inline_markdown"] = res["inline_excel_table_md"]
    res["artifact_markdown"] = res["full_artifact_table_md"]
    res["echarts_option"] = res["echarts_spec"]
    return res


def run_lcoe_horizon_forecast(
    parity_mode: str = "strict_legacy_vba",
    session_path: str | None = None,
    session_mgr: BrazilPowerSessionManager | None = None,
) -> dict[str, Any]:
    """Tool 5: Execute lcoe_exec (184 solves across 2024-2046 + Thermal ICB dispatch on Output_3!B9:J31)."""
    mgr = _resolve_session_mgr(session_mgr=session_mgr, session_path=session_path)
    res = mgr.run_lcoe_horizon(parity_mode=parity_mode)
    res["inline_markdown"] = res["inline_excel_table_md"]
    res["artifact_markdown"] = res["full_artifact_table_md"]
    res["echarts_option"] = res["echarts_spec"]
    return res


def run_dcf_cashflow_analysis(
    technology_code: str = "_01_CF",
    start_year: int = 2024,
    end_year: int = 2053,
    include_cvu_gf_sweep: bool | None = None,
    run_cvu_gf_sweep: bool | None = None,
    analysis_type: str = "dcf",
    parity_mode: str = "strict_legacy_vba",
    session_path: str | None = None,
    session_mgr: BrazilPowerSessionManager | None = None,
) -> dict[str, Any]:
    """Tool 6: Execute 30-year DCF cash-flow engine (+ optional or thermal CVU/GF sweep)."""
    mgr = _resolve_session_mgr(session_mgr=session_mgr, session_path=session_path)
    norm_code = normalize_technology_code(technology_code)
    if norm_code == "ALL":
        norm_code = "_01_CF"

    res = mgr.run_dcf(
        technology_code=norm_code,
        start_year=start_year,
        end_year=end_year,
    )

    if include_cvu_gf_sweep is not None:
        do_cvu = bool(include_cvu_gf_sweep)
    elif run_cvu_gf_sweep is not None:
        do_cvu = bool(run_cvu_gf_sweep)
    elif analysis_type.lower() in ("cvu", "cvu_gf", "cvu_sweep", "both"):
        do_cvu = True
    else:
        do_cvu = norm_code in ("_06_CF", "_07_CF", "_08_CF")

    if do_cvu:
        cvu_res = mgr.run_cvu_gf_sweep(technology_code=norm_code, parity_mode=parity_mode)
        res["cvu_gf_sweep"] = cvu_res
        res["cvu_sweep_echarts_option"] = cvu_res["echarts_spec"]
        res["inline_excel_table_md"] = (
            res["inline_excel_table_md"] + "\n\n---\n\n" + cvu_res["inline_excel_table_md"]
        )
        res["inline_summary_table_md"] = res["inline_excel_table_md"]
        res["full_artifact_table_md"] = (
            res["full_artifact_table_md"] + "\n\n---\n\n" + cvu_res["full_artifact_table_md"]
        )

    res["inline_markdown"] = res["inline_excel_table_md"]
    res["artifact_markdown"] = res["full_artifact_table_md"]
    res["echarts_option"] = res["echarts_spec"]
    return res


def export_full_22tab_workbook(
    export_format: str = "xlsx",
    output_filename: str | None = None,
    filename: str | None = None,
    output_dir: str | None = None,
    sheet_title: str | None = None,
    golden_sheet_id: str = GOLDEN_GOOGLE_SHEET_ID,
    session_path: str | None = None,
    session_mgr: BrazilPowerSessionManager | None = None,
) -> dict[str, Any]:
    """Tool 7: Export the full 22-tab Brazil Power v13 workbook to .xlsx and/or Google Sheets."""
    mgr = _resolve_session_mgr(session_mgr=session_mgr, session_path=session_path)
    res = _export_workbook(
        session_mgr=mgr,
        export_format=export_format,
        output_dir=output_dir,
        filename=output_filename or filename,
        sheet_title=sheet_title,
        golden_sheet_id=golden_sheet_id,
    )
    if res.get("xlsx_path"):
        res["file_uri"] = Path(res["xlsx_path"]).resolve().as_uri()
    else:
        res["file_uri"] = None
    res["inline_excel_table_md"] = res["summary_md"]
    res["full_artifact_table_md"] = res["summary_md"]
    res["inline_markdown"] = res["summary_md"]
    res["artifact_markdown"] = res["summary_md"]
    res["echarts_option"] = None
    return res


TOOL_HANDLERS: dict[str, Callable[..., dict[str, Any]]] = {
    "get_session_assumptions": get_session_assumptions,
    "update_session_assumptions": update_session_assumptions,
    "run_tornado_sensitivity": run_tornado_sensitivity,
    "run_bqml_timeseries_refresh": run_bqml_timeseries_refresh,
    "run_lcoe_horizon_forecast": run_lcoe_horizon_forecast,
    "run_dcf_cashflow_analysis": run_dcf_cashflow_analysis,
    "export_full_22tab_workbook": export_full_22tab_workbook,
}


def call_mcp_tool(
    name: str,
    arguments: dict[str, Any] | None = None,
    session_mgr: BrazilPowerSessionManager | None = None,
) -> dict[str, Any]:
    """Dispatch one of the 7 MCP tools by name and return its structured dictionary output."""
    if name not in TOOL_HANDLERS:
        raise ValueError(f"Unknown MCP tool '{name}'. Available tools: {sorted(TOOL_HANDLERS.keys())}")
    kwargs = dict(arguments or {})
    if session_mgr is not None:
        kwargs["session_mgr"] = session_mgr
    return TOOL_HANDLERS[name](**kwargs)


dispatch_mcp_tool = call_mcp_tool



def handle_jsonrpc_request(
    request: dict[str, Any],
    session_mgr: BrazilPowerSessionManager | None = None,
) -> dict[str, Any] | None:
    """Process a single JSON-RPC 2.0 MCP request and return a JSON-RPC 2.0 response (or None for notifications)."""
    method = str(request.get("method", ""))
    req_id = request.get("id")
    params = request.get("params") or {}

    if method.startswith("notifications/") or req_id is None and method != "initialize":
        return None

    if method == "initialize":
        client_version = params.get("protocolVersion") or MCP_PROTOCOL_VERSION
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": client_version,
                "capabilities": {
                    "tools": {"listChanged": False},
                },
                "serverInfo": {
                    "name": MCP_SERVER_NAME,
                    "version": MCP_SERVER_VERSION,
                },
            },
        }

    if method == "ping":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {},
        }

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "tools": MCP_TOOLS,
            },
        }

    if method == "tools/call":
        tool_name = str(params.get("name", ""))
        arguments = params.get("arguments") or {}
        try:
            payload = call_mcp_tool(tool_name, arguments=arguments, session_mgr=session_mgr)
            serialized = json.dumps(payload, ensure_ascii=False)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": serialized,
                        }
                    ],
                    "structuredContent": payload,
                    "isError": False,
                },
            }
        except Exception as exc:
            err_payload = {
                "error": str(exc),
                "tool": tool_name,
            }
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(err_payload, ensure_ascii=False),
                        }
                    ],
                    "isError": True,
                },
            }

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {
            "code": -32601,
            "message": f"Method not found: {method}",
        },
    }


def serve_stdio_stream(
    in_stream: BinaryIO,
    out_stream: BinaryIO,
    session_mgr: BrazilPowerSessionManager | None = None,
) -> None:
    """Serve JSON-RPC 2.0 requests over stdio supporting both newline-delimited JSON and Content-Length framing."""
    active_mgr = session_mgr if session_mgr is not None else BrazilPowerSessionManager()

    while True:
        first_line = in_stream.readline()
        if not first_line:
            break

        stripped = first_line.strip()
        if not stripped:
            continue

        if stripped.lower().startswith(b"content-length:"):
            # Content-Length framed transport
            _, length_val = stripped.split(b":", 1)
            content_length = int(length_val.strip())
            # Consume remaining header lines until blank line
            while True:
                hdr_line = in_stream.readline()
                if not hdr_line or hdr_line in (b"\r\n", b"\n"):
                    break
            body_bytes = in_stream.read(content_length)
            if not body_bytes:
                break
            req_obj = json.loads(body_bytes.decode("utf-8"))
            resp_obj = handle_jsonrpc_request(req_obj, session_mgr=active_mgr)
            if resp_obj is not None:
                resp_bytes = json.dumps(resp_obj, ensure_ascii=False).encode("utf-8")
                header_bytes = f"Content-Length: {len(resp_bytes)}\r\n\r\n".encode("ascii")
                out_stream.write(header_bytes + resp_bytes)
                out_stream.flush()
        else:
            # Newline-delimited JSON-RPC 2.0 transport
            req_obj = json.loads(stripped.decode("utf-8"))
            resp_obj = handle_jsonrpc_request(req_obj, session_mgr=active_mgr)
            if resp_obj is not None:
                out_line = (json.dumps(resp_obj, ensure_ascii=False) + "\n").encode("utf-8")
                out_stream.write(out_line)
                out_stream.flush()


def build_mcp_server_config_entry(repo_root: str | Path | None = None) -> dict[str, Any]:
    """Build the `~/.gemini/config/mcp_config.json` server entry for `brazil-power-mcp`."""
    root_path = Path(repo_root).resolve() if repo_root is not None else WORKSPACE_ROOT
    agent_src = root_path / "brazil-power-agent" / "src"
    v13_dir = root_path / "brazil-power-v13"
    server_script = agent_src / "brazil_power_agent" / "mcp_server.py"
    return {
        "command": sys.executable or "python3",
        "args": [str(server_script)],
        "env": {
            "PYTHONPATH": f"{agent_src}:{v13_dir}",
        },
    }


def main() -> None:
    """Entry point for running `brazil-power-mcp` over stdio."""
    serve_stdio_stream(sys.stdin.buffer, sys.stdout.buffer)


if __name__ == "__main__":
    main()
