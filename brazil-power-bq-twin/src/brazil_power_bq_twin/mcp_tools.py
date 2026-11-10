"""7 MCP Tools and JSON-RPC 2.0 dispatcher backed purely by the BigQuery Digital Twin."""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from brazil_power_bq_twin.bq_store import DigitalTwinStore
from brazil_power_bq_twin.config import TwinSettings, get_twin_settings
from brazil_power_bq_twin.models import CellDelta, index_to_col_letter
from brazil_power_bq_twin.renderer import TECH_CATALOG, normalize_multiline_markdown
from brazil_power_bq_twin.solver_engine import QuantitativeTwinSolver
from brazil_power_bq_twin.xlsx_synthesizer import export_digital_twin_workbook, sanitize_filename

logger = logging.getLogger(__name__)

MCP_SERVER_NAME = "brazil-power-bq-twin-mcp"
MCP_SERVER_VERSION = "1.0.0"
MCP_PROTOCOL_VERSION = "2024-11-05"

TECH_ENUM = list(TECH_CATALOG.keys())

TWIN_MCP_TOOLS: list[dict[str, Any]] = [
    {
        "name": "get_session_assumptions",
        "description": (
            "Query the active session's General!B5:N40 assumptions directly from the BigQuery Digital Twin "
            "(comm-model-mod.brazil_power_digital_twin, zero Excel files) and return Excel-layout Markdown tables."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "technologies": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of technology codes ('_01_CF'..'_12_CF') for inline preview.",
                }
            },
            "additionalProperties": True,
        },
    },
    {
        "name": "update_session_assumptions",
        "description": (
            "Append sparse cell overrides into BigQuery dt_scenario_deltas + 4-Ws dt_audit_events "
            "and return the updated General!B5:N40 Digital Twin Markdown table."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "overrides": {
                    "type": "object",
                    "description": "Technology parameter dict ({'_01_CF': {'fuel_cost': 6.5}}) or cell coords ({'General!C20': 6.5}).",
                },
                "reset_to_baseline": {
                    "type": "boolean",
                    "default": False,
                    "description": "When true, resets prior session deltas back to v13_baseline.",
                },
            },
            "additionalProperties": True,
        },
    },
    {
        "name": "run_tornado_sensitivity",
        "description": (
            "Execute the 21-point IRR Tornado sensitivity against the BigQuery Digital Twin, "
            "persisting solved outputs to dt_scenario_deltas and returning Markdown tables + ECharts JSON."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "technology_code": {
                    "type": "string",
                    "enum": [*TECH_ENUM, "ALL"],
                    "default": "_06_CF",
                }
            },
            "required": ["technology_code"],
            "additionalProperties": True,
        },
    },
    {
        "name": "run_bqml_timeseries_refresh",
        "description": (
            "Query live 23-year ARIMA_PLUS trajectories from brazil_power_digital_twin.vw_lt_forecasts, "
            "write them into LT Capex/Fuel/CF deltas, and return trajectory tables + ECharts JSON."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "curve_types": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["CAPEX", "FUEL", "CF"]},
                    "default": ["CAPEX", "FUEL", "CF"],
                },
                "apply_to_session_lt_tabs": {"type": "boolean", "default": True},
            },
            "additionalProperties": True,
        },
    },
    {
        "name": "run_lcoe_horizon_forecast",
        "description": (
            "Run the 23-year (2024-2046) multi-technology LCOE horizon forecast against the BigQuery Digital Twin, "
            "writing Output_3!B9:J31 deltas and returning milestone/full tables + ECharts JSON."
        ),
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": True},
    },
    {
        "name": "run_dcf_cashflow_analysis",
        "description": (
            "Execute the 30-year (2024-2053) Project & Equity DCF cash-flow schedule and optional 10-point "
            "Thermal CVU/GF sweep against the BigQuery Digital Twin."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "technology_code": {"type": "string", "enum": TECH_ENUM, "default": "_01_CF"},
                "start_year": {"type": "integer", "default": 2024},
                "end_year": {"type": "integer", "default": 2053},
                "include_cvu_gf_sweep": {"type": "boolean"},
            },
            "required": ["technology_code"],
            "additionalProperties": True,
        },
    },
    {
        "name": "export_full_22tab_workbook",
        "description": (
            "Synthesize a complete 22-tab .xlsx workbook and/or 22-tab Google Sheet purely from BigQuery Digital Twin "
            "rows, styles, formulas, and session deltas (zero template Excel files used)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "export_format": {
                    "type": "string",
                    "enum": ["xlsx", "google_sheets", "both"],
                    "default": "xlsx",
                },
                "output_filename": {"type": "string"},
                "sheet_title": {"type": "string"},
            },
            "additionalProperties": True,
        },
    },
]


def _save_artifact_markdown(
    artifact_filename: str,
    markdown_text: str,
    settings: TwinSettings,
) -> dict[str, str]:
    safe_name = sanitize_filename(artifact_filename, ".md")
    clean_md = normalize_multiline_markdown(markdown_text)
    art_dir = settings.local_artifact_dir
    art_dir.mkdir(parents=True, exist_ok=True)
    local_path = (art_dir / safe_name).resolve()
    local_path.write_text(clean_md, encoding="utf-8")

    out: dict[str, str] = {
        "artifact_filename": safe_name,
        "local_cache_path": str(local_path),
    }
    if os.environ.get("K_SERVICE") or os.environ.get("BQ_TWIN_UPLOAD_GCS", "").lower() in ("1", "true"):
        blob_key = f"{settings.gcs_artifacts_prefix}/{safe_name}"
        try:
            from google.cloud import storage

            client = storage.Client(project=settings.gcp_project_id)
            client.bucket(settings.gcs_bucket).blob(blob_key).upload_from_string(
                clean_md, content_type="text/markdown; charset=utf-8"
            )
            out["gcs_artifact_uri"] = f"gs://{settings.gcs_bucket}/{blob_key}"
            out["cloud_artifact_url"] = f"{settings.cloud_service_url.rstrip('/')}/v1/artifacts/{safe_name}"
        except Exception as exc:
            logger.warning("Artifact GCS upload skipped/failed: %s", exc)
    return out


def execute_twin_tool(
    tool_name: str,
    arguments: dict[str, Any] | None,
    store: DigitalTwinStore,
    session_id: str = "default",
    settings: TwinSettings | None = None,
) -> dict[str, Any]:
    """Execute one of the 7 Digital Twin MCP tools."""
    cfg = settings or get_twin_settings()
    args = dict(arguments or {})
    ver = cfg.default_version_id
    snapshot = store.get_baseline_snapshot(ver)
    overlay = store.get_session_overlay(session_id, ver)

    if tool_name == "get_session_assumptions":
        res = QuantitativeTwinSolver.extract_assumptions(
            snapshot=snapshot,
            overlay=overlay,
            technologies=args.get("technologies"),
        )
        res.update(_save_artifact_markdown("bq_twin_general_assumptions.md", res["full_artifact_table_md"], cfg))
        return res

    if tool_name == "update_session_assumptions":
        if args.get("reset_to_baseline"):
            store.reset_session(session_id, ver)
            overlay = store.get_session_overlay(session_id, ver)
        deltas, audits, changes = QuantitativeTwinSolver.stage_overrides(
            snapshot=snapshot,
            overlay=overlay,
            overrides=args.get("overrides"),
        )
        if deltas or audits:
            store.append_session_deltas(session_id, deltas, audit_rows=audits, version_id=ver)
            overlay = store.get_session_overlay(session_id, ver)
        res = QuantitativeTwinSolver.extract_assumptions(snapshot=snapshot, overlay=overlay)
        res["changes"] = changes
        res.update(_save_artifact_markdown("bq_twin_general_assumptions.md", res["full_artifact_table_md"], cfg))
        return res

    if tool_name == "run_tornado_sensitivity":
        tech = str(args.get("technology_code") or "_06_CF")
        res, deltas = QuantitativeTwinSolver.run_tornado_sensitivity(snapshot, overlay, tech)
        store.append_session_deltas(session_id, deltas, version_id=ver)
        fname = f"bq_twin_tornado_{res['technology_code'].lower()}.md"
        res.update(_save_artifact_markdown(fname, res["full_artifact_table_md"], cfg))
        return res

    if tool_name == "run_bqml_timeseries_refresh":
        bqml_data = store.fetch_bqml_trajectories()
        years = bqml_data.get("years") or list(range(2024, 2047))
        curves = bqml_data.get("curves") or {}
        selected_types = [str(c).upper() for c in (args.get("curve_types") or ["CAPEX", "FUEL", "CF"])]
        apply_tabs = bool(args.get("apply_to_session_lt_tabs", True))

        tab_for_type = {"CAPEX": "LT Capex", "FUEL": "LT Fuel", "CF": "LT CF"}
        deltas: list[CellDelta] = []
        now_iso = datetime.now(UTC).isoformat()

        if apply_tabs:
            for ctype in selected_types:
                t_name = tab_for_type.get(ctype)
                mat = curves.get(ctype) or []
                if not t_name or not mat:
                    continue
                for r_off, row_vals in enumerate(mat[:23]):
                    r_num = 8 + r_off
                    for c_off, val in enumerate(row_vals[:9]):
                        c_idx = 2 + c_off
                        deltas.append(
                            CellDelta(
                                sheet_name=t_name,
                                cell_coord=f"{index_to_col_letter(c_idx)}{r_num}",
                                row_num=r_num,
                                col_num=c_idx,
                                delta_kind="BQML_REFRESH",
                                numeric_value=float(val),
                                source_tool="run_bqml_timeseries_refresh",
                                updated_at=now_iso,
                            )
                        )
            if deltas:
                store.append_session_deltas(session_id, deltas, version_id=ver)

        md_lines = [
            "# BigQuery ML `ARIMA_PLUS` 23-Year Trajectory Refresh (`brazil_power_digital_twin.vw_lt_forecasts`)",
            f"- **Data Source**: `{bqml_data.get('data_source', 'bigquery_ml_digital_twin')}` | **Cells Updated**: `{len(deltas)}`",
            "",
            "| Year | CCGT Capex Idx | Wind Capex Idx | Solar Capex Idx | Wind CF | Solar CF |",
            "| :---: | ---: | ---: | ---: | ---: | ---: |",
        ]
        cap_m = curves.get("CAPEX") or [[1.0] * 9 for _ in years]
        cf_m = curves.get("CF") or [[0.45] * 9 for _ in years]
        for idx, yr in enumerate(years[:23]):
            c_row = cap_m[idx] if idx < len(cap_m) else [1.0] * 9
            f_row = cf_m[idx] if idx < len(cf_m) else [0.45] * 9
            md_lines.append(
                f"| `{yr}` | {c_row[0]:,.3f} | {c_row[4]:,.3f} | {c_row[5]:,.3f} | "
                f"{f_row[4] * 100.0:.1f}% | {f_row[5] * 100.0:.1f}% |"
            )
        full_md = normalize_multiline_markdown("\n".join(md_lines))
        echarts = {
            "title": {"text": "BigQuery ML ARIMA_PLUS 23-Year Trajectories (2024–2046)"},
            "tooltip": {"trigger": "axis"},
            "legend": {"data": ["Wind Capex Index", "Solar Capex Index"], "bottom": 0},
            "xAxis": {"type": "category", "data": [str(y) for y in years[:23]]},
            "yAxis": {"type": "value"},
            "series": [
                {"name": "Wind Capex Index", "type": "line", "data": [round(r[4], 3) for r in cap_m[:23]]},
                {"name": "Solar Capex Index", "type": "line", "data": [round(r[5], 3) for r in cap_m[:23]]},
            ],
        }
        res = {
            "data_source": bqml_data.get("data_source", "bigquery_ml_digital_twin"),
            "lt_cells_updated": len(deltas),
            "inline_markdown": full_md,
            "artifact_markdown": full_md,
            "full_artifact_table_md": full_md,
            "echarts_option": echarts,
        }
        res.update(_save_artifact_markdown("bq_twin_lt_trajectories.md", full_md, cfg))
        return res

    if tool_name == "run_lcoe_horizon_forecast":
        res, deltas = QuantitativeTwinSolver.run_lcoe_horizon(snapshot, overlay)
        store.append_session_deltas(session_id, deltas, version_id=ver)
        res.update(_save_artifact_markdown("bq_twin_output3_lcoe_horizon.md", res["full_artifact_table_md"], cfg))
        return res

    if tool_name == "run_dcf_cashflow_analysis":
        tech = str(args.get("technology_code") or "_01_CF")
        res, deltas = QuantitativeTwinSolver.run_dcf_and_cvu(
            snapshot=snapshot,
            overlay=overlay,
            technology_code=tech,
            start_year=int(args.get("start_year", 2024)),
            end_year=int(args.get("end_year", 2053)),
            include_cvu_sweep=args.get("include_cvu_gf_sweep"),
        )
        store.append_session_deltas(session_id, deltas, version_id=ver)
        fname = f"bq_twin_dcf_30yr_{res['technology_code'].lower()}.md"
        res.update(_save_artifact_markdown(fname, res["full_artifact_table_md"], cfg))
        return res

    if tool_name == "export_full_22tab_workbook":
        res = export_digital_twin_workbook(
            store=store,
            session_id=session_id,
            export_format=str(args.get("export_format") or "xlsx"),
            output_filename=args.get("output_filename"),
            output_dir=cfg.local_export_dir,
            sheet_title=args.get("sheet_title"),
            cloud_base_url=cfg.cloud_service_url,
        )
        res.update(_save_artifact_markdown("bq_twin_export_summary.md", res["full_artifact_table_md"], cfg))
        return res

    raise ValueError(f"Unknown MCP tool '{tool_name}'.")


def format_twin_mcp_report(tool_name: str, payload: dict[str, Any]) -> str:
    """Format Digital Twin tool result as multi-line Markdown for Cowork."""
    lines = [
        f"## Brazil Power v13 BigQuery Digital Twin Result: `{tool_name}`",
        "- **Backend**: `comm-model-mod.brazil_power_digital_twin` (`excel_files_used = 0`)",
    ]
    if payload.get("artifact_filename"):
        fn = payload["artifact_filename"]
        lines.append(
            f"- **Side-Pane Artifact Filename**: `{fn}` "
            f"(Call `write_to_file` with `TargetFile=\"<your_artifact_dir>/{fn}\"`, `Overwrite=true`, `UserFacing=true`)"
        )
    if payload.get("cloud_download_url"):
        lines.append(f"- **Cloud 22-Tab `.xlsx` Download URL**: {payload['cloud_download_url']}")
    if payload.get("spreadsheet_url"):
        lines.append(f"- **Synthesized 22-Tab Google Sheet URL**: {payload['spreadsheet_url']}")

    if payload.get("inline_markdown"):
        lines.extend(["", "### Inline Markdown Table", "", normalize_multiline_markdown(payload["inline_markdown"]).strip()])

    if isinstance(payload.get("echarts_option"), dict):
        lines.extend(
            [
                "",
                "### ECharts Option JSON (Pass to `render_chart`)",
                "```json",
                json.dumps(payload["echarts_option"], ensure_ascii=False),
                "```",
            ]
        )

    if payload.get("artifact_markdown"):
        lines.extend(
            [
                "",
                "### Full Multi-Line Artifact Markdown Replica (Preserve physical `\\n` newlines on every row)",
                "",
                normalize_multiline_markdown(payload["artifact_markdown"]).strip(),
            ]
        )
    return "\n".join(lines) + "\n"


def handle_twin_jsonrpc(
    request: dict[str, Any],
    store: DigitalTwinStore,
    session_id: str = "default",
    settings: TwinSettings | None = None,
) -> dict[str, Any] | None:
    """Process a single JSON-RPC 2.0 MCP request."""
    method = str(request.get("method", ""))
    req_id = request.get("id")
    params = request.get("params") or {}

    if method.startswith("notifications/") or (req_id is None and method != "initialize"):
        return None

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": params.get("protocolVersion") or MCP_PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": MCP_SERVER_NAME, "version": MCP_SERVER_VERSION},
            },
        }

    if method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TWIN_MCP_TOOLS}}

    if method == "tools/call":
        t_name = str(params.get("name", ""))
        t_args = params.get("arguments") or {}
        try:
            payload = execute_twin_tool(t_name, t_args, store=store, session_id=session_id, settings=settings)
            report_md = format_twin_mcp_report(t_name, payload)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": report_md}],
                    "isError": False,
                },
            }
        except Exception as exc:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps({"error": str(exc), "tool": t_name})}],
                    "isError": True,
                },
            }

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }
