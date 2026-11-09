"""Cloud Run Remote MCP Server, A2A Agent Card & Task Handler, and Artifact Gateway for Brazil Power v13."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Resolve brazil_power_agent whether running in monorepo or /app container
_THIS_FILE = Path(__file__).resolve()
_V13_ROOT = _THIS_FILE.parents[3]
_MONOREPO_AGENT_SRC = _V13_ROOT.parent / "brazil-power-agent" / "src"
_CONTAINER_AGENT_SRC = _V13_ROOT / "src"

for _cand in (str(_MONOREPO_AGENT_SRC), str(_CONTAINER_AGENT_SRC), str(_V13_ROOT)):
    if Path(_cand).is_dir() and _cand not in sys.path:
        sys.path.insert(0, _cand)

from brazil_power_agent.mcp_server import (
    MCP_PROTOCOL_VERSION,
    MCP_SERVER_NAME,
    MCP_SERVER_VERSION,
    MCP_TOOLS,
    TOOL_HANDLERS,
    build_compact_llm_payload,
    call_mcp_tool,
    format_multiline_llm_report,
    handle_jsonrpc_request,
    sanitize_artifact_filename,
)
from brazil_power_agent.session_store import (
    DEFAULT_BQ_LT_VIEW,
    DEFAULT_GCS_ARTIFACT_BUCKET,
    BrazilPowerSessionManager,
    normalize_technology_code,
)
from brazil_power_agent.workbook_exporter import (
    DEFAULT_CLOUD_GATEWAY_URL,
    DEFAULT_EXPORT_DIR,
    sanitize_export_filename,
)
from src.core.config import get_settings
from src.ingestion.realtime_edit_handler import handle_realtime_edit_event
from src.schemas.audit import RealTimeEditEventRequest

router = APIRouter(tags=["Gemini Cloud Agent & Remote MCP"])

GEMINI_ENTERPRISE_ENGINE_NAME = (
    "projects/1024543888590/locations/us/collections/default_collection/"
    "engines/commodity-modeling-gemini_1794154060332"
)
GEMINI_ENTERPRISE_CID = "cb0f4566-dfad-496c-9b28-3542d86a5367"


class ToolInvokeRequest(BaseModel):
    """Request body for POST /v1/agent/tools/{tool_name}."""

    arguments: dict[str, Any] = Field(default_factory=dict)
    session_id: str | None = Field(default=None, description="Optional scenario session identifier.")
    user_email: str = Field(default="gemini-enterprise-agent@comm-model-mod.iam.gserviceaccount.com")


class AgentChatRequest(BaseModel):
    """Request body for POST /v1/agent/chat."""

    prompt: str = Field(..., min_length=1, max_length=16000)
    session_id: str | None = Field(default=None)
    technology_code: str | None = Field(default=None)


def _get_cloud_session_manager(session_id: str | None = None) -> BrazilPowerSessionManager:
    """Create a BrazilPowerSessionManager scoped to session_id and backed by GCS."""
    safe_sid = re.sub(r"[^A-Za-z0-9_\-]", "", (session_id or "default")) or "default"
    is_cloud = bool(os.environ.get("K_SERVICE") or os.environ.get("ENV", "").lower() == "gcp")
    base_dir = Path("/tmp/brazil_power_sessions") if is_cloud else (Path.home() / ".gemini" / "jetski")
    base_dir.mkdir(parents=True, exist_ok=True)
    filename = (
        "brazil_power_agent_session.json"
        if safe_sid == "default"
        else f"brazil_power_agent_session_{safe_sid}.json"
    )
    return BrazilPowerSessionManager(session_path=base_dir / filename)


async def _record_cloud_sql_audit_for_changes(
    changes: list[dict[str, Any]],
    user_email: str,
) -> int:
    """Persist assumption changes to Cloud SQL PostgreSQL via handle_realtime_edit_event when DB is configured."""
    if not changes:
        return 0
    settings = get_settings()
    if settings.environment != "gcp" and not os.environ.get("DB_HOST"):
        return 0
    persisted = 0
    try:
        from src.db.session import AsyncSessionFactory

        async with AsyncSessionFactory() as db:
            async with db.begin():
                for item in changes:
                    cell_coord = str(item.get("cell", "C8")).replace("$", "").strip()
                    if not re.match(r"^[A-Z]{1,3}[1-9][0-9]{0,6}$", cell_coord):
                        cell_coord = "C8"
                    req = RealTimeEditEventRequest(
                        spreadsheet_id="1apbos5xVpK4yBLiRFxQqAEyPVNkkYQ2ZvgAASibYYJI",
                        workbook_name="Brazil Energy Model (v13) — Gemini Cloud Agent",
                        sheet_name=str(item.get("sheet", "General"))[:128],
                        cell_coord=cell_coord,
                        old_value=str(item.get("old_value", ""))[:500] if item.get("old_value") is not None else None,
                        new_value=str(item.get("new_value", ""))[:500] if item.get("new_value") is not None else None,
                        who_google_user=user_email,
                    )
                    await handle_realtime_edit_event(
                        session=db,
                        request=req,
                        who_iam_principal=user_email,
                        who_client_platform="gemini-enterprise-cloud-run",
                    )
                    persisted += 1
    except Exception as exc:
        logger.warning("Cloud SQL 4-Ws audit persistence skipped/degraded: %s", exc)
    return persisted


def build_a2a_agent_card(base_url: str | None = None) -> dict[str, Any]:
    """Build the A2A Protocol AgentCard JSON for Gemini Enterprise registration."""
    gateway = (base_url or DEFAULT_CLOUD_GATEWAY_URL).rstrip("/")
    return {
        "name": "brazil_power_v13_agent",
        "displayName": "Brazil Energy Model (v13) — 22-Tab Financial & LCOE Agent",
        "description": (
            "Interactive 22-Tab Brazil Power Generation & Hydrogen Financial Model (v13) running on Google Cloud Run, "
            "BigQuery ML (ARIMA_PLUS), Cloud Storage, and Cloud SQL 4-Ws Governance. Executes 21-point Tornado IRR "
            "sensitivity (calcule_tir1..12), 23-year BigQuery ML trajectory refreshes (LT Capex/Fuel/CF), 23-year "
            "LCOE horizon forecasts (lcoe_exec across 184 binary-search solves + Thermal ICB), 30-year Project & "
            "Shareholder DCF schedules (_01_CF.._12_CF + CVU/GF sweep), and 100% faithful 22-tab .xlsx & Google Sheets exports."
        ),
        "url": f"{gateway}/a2a/app",
        "version": MCP_SERVER_VERSION,
        "protocolVersion": "0.2.1",
        "provider": {
            "organization": "Commodity Modeling Sheets Platform",
            "url": gateway,
        },
        "capabilities": {
            "streaming": False,
            "pushNotifications": False,
            "stateTransitionHistory": True,
        },
        "authentication": {
            "schemes": ["None", "Bearer"],
        },
        "defaultInputModes": ["text", "text/plain", "application/json"],
        "defaultOutputModes": ["text", "text/markdown", "application/json"],
        "skills": [
            {
                "id": "brazil-power-model",
                "name": "Brazil Energy Model v13 Orchestrator",
                "description": (
                    "Full 22-tab interactive orchestrator for General!B5:N40 assumptions, Tornado IRR, BigQuery ML "
                    "refresh, LCOE horizon, 30-year DCF, and 22-tab .xlsx / Google Sheets exports."
                ),
                "tags": ["brazil-power", "energy-modeling", "lcoe", "dcf", "irr", "bigquery-ml"],
                "examples": [
                    "Run the Brazil Power v13 model",
                    "Show the General!C5:N40 baseline assumptions table across all 12 technologies",
                ],
            },
            {
                "id": "brazil-tornado",
                "name": "21-Point IRR Tornado Sensitivity (calcule_tir1..12)",
                "description": (
                    "Runs the 21-point 2-Stage Discrete Lattice Binary Search IRR sensitivity across CAPEX, Fuel, "
                    "WACC, Capacity Factor, O&M, and Financing for _01_CF.._12_CF and Output_1."
                ),
                "tags": ["tornado", "irr", "sensitivity", "calcule_tir"],
                "examples": [
                    "Run Tornado IRR sensitivity for Natural Gas CCGT (_06_CF)",
                    "Run Tornado sensitivity across all 12 technologies",
                ],
            },
            {
                "id": "brazil-bqml",
                "name": "BigQuery ML ARIMA_PLUS 23-Year Trajectory Refresh",
                "description": (
                    "Queries live BigQuery ML ARIMA_PLUS trajectories from comm-model-mod.sheets_commodity_mod_governance "
                    "and refreshes LT Capex!B8:J30, LT Fuel!B8:J30, and LT CF!B8:J30."
                ),
                "tags": ["bigquery-ml", "arima-plus", "lt-capex", "lt-fuel", "lt-cf"],
                "examples": [
                    "Refresh the 23-year BigQuery ML CAPEX, Fuel, and Capacity Factor trajectories",
                ],
            },
            {
                "id": "brazil-lcoe",
                "name": "23-Year Multi-Technology LCOE Horizon (lcoe_exec)",
                "description": (
                    "Executes 184 binary-search LCOE solves across 2024-2046 plus Thermal ICB dispatch on Output_3!B8:J31."
                ),
                "tags": ["lcoe", "output_3", "horizon-forecast", "icb"],
                "examples": [
                    "Run the 23-year LCOE horizon forecast on Output_3",
                ],
            },
            {
                "id": "brazil-dcf",
                "name": "30-Year Project & Shareholder DCF + Thermal CVU/GF Sweep",
                "description": (
                    "Computes the 30-year (2024-2053) horizontal cash-flow schedule (Rows 33-101, Col K..AN) and "
                    "10-point Thermal CVU / Physical Guarantee sweep (CVU_GF)."
                ),
                "tags": ["dcf", "cash-flow", "cvu-gf", "npv", "irr"],
                "examples": [
                    "Run the 30-year DCF cash flow analysis for Onshore Wind (_01_CF)",
                    "Run the 30-year DCF and CVU/GF sweep for Natural Gas CCGT (_06_CF)",
                ],
            },
        ],
    }


def _extract_tech_from_text(text: str, default_tech: str = "_06_CF") -> str:
    """Infer target technology code (_01_CF.._12_CF) from free-form prompt text."""
    upper = text.upper()
    for i in range(12, 0, -1):
        code = f"_{i:02d}_CF"
        if code in upper or f"{i:02d}_CF" in upper:
            return code
    keyword_map = [
        ("SOLAR", "_05_CF"),
        ("WIND", "_01_CF"),
        ("CCGT", "_06_CF"),
        ("GAS", "_06_CF"),
        ("COAL PC", "_07_CF"),
        ("CFBC", "_08_CF"),
        ("COAL", "_07_CF"),
        ("HYDRO", "_09_CF"),
        ("SHP", "_09_CF"),
        ("NUCLEAR", "_10_CF"),
        ("BATTERY", "_11_CF"),
        ("BESS", "_11_CF"),
        ("H2", "_12_CF"),
        ("HYDROGEN", "_12_CF"),
        ("WOODCHIP", "_04_CF"),
        ("RETROFIT", "_03_CF"),
        ("SUGARCANE", "_02_CF"),
        ("BIOMASS", "_02_CF"),
    ]
    for kw, code in keyword_map:
        if kw in upper:
            return code
    return default_tech


def execute_prompt_workflow(
    prompt: str,
    session_id: str | None = None,
    technology_code: str | None = None,
) -> dict[str, Any]:
    """Execute the appropriate Brazil Power v13 MCP tool workflow for an A2A or chat prompt."""
    mgr = _get_cloud_session_manager(session_id)
    lower = prompt.lower()
    tech = normalize_technology_code(technology_code) if technology_code else _extract_tech_from_text(prompt)

    executed_tools: list[str] = []
    sections: list[str] = []
    artifacts: list[dict[str, Any]] = []
    primary_payload: dict[str, Any] = {}

    if any(k in lower for k in ("export", "xlsx", "excel", "google sheet", "22-tab", "22 tab", "workbook")):
        fmt = "both" if ("both" in lower or ("xlsx" in lower and "sheet" in lower)) else (
            "google_sheets" if ("google sheet" in lower or "gsheet" in lower) else "xlsx"
        )
        res = call_mcp_tool("export_full_22tab_workbook", {"export_format": fmt}, session_mgr=mgr)
        executed_tools.append("export_full_22tab_workbook")
        primary_payload = res
        sections.append(format_multiline_llm_report("export_full_22tab_workbook", build_compact_llm_payload(res)))
    elif any(k in lower for k in ("tornado", "sensitivity", "calcule_tir", "tir")):
        target = "ALL" if "all" in lower else tech
        res = call_mcp_tool("run_tornado_sensitivity", {"technology_code": target}, session_mgr=mgr)
        executed_tools.append("run_tornado_sensitivity")
        primary_payload = res
        sections.append(format_multiline_llm_report("run_tornado_sensitivity", build_compact_llm_payload(res)))
    elif any(k in lower for k in ("bqml", "arima", "trajectory", "trajectories", "lt capex", "lt fuel", "lt cf", "time series", "timeseries")):
        res = call_mcp_tool(
            "run_bqml_timeseries_refresh",
            {"curve_types": ["CAPEX", "FUEL", "CF"], "apply_to_session_lt_tabs": True},
            session_mgr=mgr,
        )
        executed_tools.append("run_bqml_timeseries_refresh")
        primary_payload = res
        sections.append(format_multiline_llm_report("run_bqml_timeseries_refresh", build_compact_llm_payload(res)))
    elif any(k in lower for k in ("lcoe", "output_3", "output 3", "horizon", "184")):
        res = call_mcp_tool("run_lcoe_horizon_forecast", {"parity_mode": "strict_legacy_vba"}, session_mgr=mgr)
        executed_tools.append("run_lcoe_horizon_forecast")
        primary_payload = res
        sections.append(format_multiline_llm_report("run_lcoe_horizon_forecast", build_compact_llm_payload(res)))
    elif any(k in lower for k in ("dcf", "cash flow", "cashflow", "30-year", "30 year", "cvu", "waterfall", "npv")):
        res = call_mcp_tool(
            "run_dcf_cashflow_analysis",
            {"technology_code": tech, "include_cvu_gf_sweep": ("cvu" in lower or tech in ("_06_CF", "_07_CF", "_08_CF"))},
            session_mgr=mgr,
        )
        executed_tools.append("run_dcf_cashflow_analysis")
        primary_payload = res
        sections.append(format_multiline_llm_report("run_dcf_cashflow_analysis", build_compact_llm_payload(res)))
    elif any(k in lower for k in ("full", "complete", "end-to-end", "all analyses")):
        for t_name, t_args in [
            ("get_session_assumptions", {"include_full_general_tab": True}),
            ("run_tornado_sensitivity", {"technology_code": tech}),
            ("run_bqml_timeseries_refresh", {"curve_types": ["CAPEX", "FUEL", "CF"], "apply_to_session_lt_tabs": True}),
            ("run_lcoe_horizon_forecast", {"parity_mode": "strict_legacy_vba"}),
            ("run_dcf_cashflow_analysis", {"technology_code": tech}),
        ]:
            r = call_mcp_tool(t_name, t_args, session_mgr=mgr)
            executed_tools.append(t_name)
            primary_payload = r
            sections.append(format_multiline_llm_report(t_name, build_compact_llm_payload(r), include_artifact_markdown=False))
    else:
        res = call_mcp_tool("get_session_assumptions", {"include_full_general_tab": True}, session_mgr=mgr)
        executed_tools.append("get_session_assumptions")
        primary_payload = res
        sections.append(format_multiline_llm_report("get_session_assumptions", build_compact_llm_payload(res)))

    if primary_payload.get("artifact_markdown"):
        artifacts.append(
            {
                "name": Path(str(primary_payload.get("artifact_file_path", "brazil_v13_artifact.md"))).name,
                "cloud_artifact_url": primary_payload.get("cloud_artifact_url"),
                "gcs_artifact_uri": primary_payload.get("gcs_artifact_uri"),
                "parts": [{"type": "text", "text": primary_payload["artifact_markdown"]}],
            }
        )

    return {
        "executed_tools": executed_tools,
        "technology_code": tech,
        "response_markdown": "\n\n".join(sections),
        "artifacts": artifacts,
        "cloud_artifact_url": primary_payload.get("cloud_artifact_url"),
        "cloud_download_url": primary_payload.get("cloud_download_url"),
        "spreadsheet_url": primary_payload.get("spreadsheet_url"),
    }


@router.get("/.well-known/agent.json", summary="A2A Agent Card (Root Discovery)")
@router.get("/.well-known/agent-card.json", summary="A2A Agent Card (Standard Well-Known)")
@router.get("/a2a/app/.well-known/agent-card.json", summary="A2A Agent Card for Gemini Enterprise")
async def get_a2a_agent_card(request: Request) -> dict[str, Any]:
    """Return the Agent-to-Agent (A2A) AgentCard JSON metadata for Gemini Enterprise registration."""
    forwarded_proto = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("host", request.url.netloc)
    base_url = f"{forwarded_proto}://{host}" if host else DEFAULT_CLOUD_GATEWAY_URL
    return build_a2a_agent_card(base_url=base_url)


@router.post("/a2a/app", summary="A2A JSON-RPC 2.0 Task & Message Endpoint for Gemini Enterprise")
async def handle_a2a_jsonrpc(request: Request) -> dict[str, Any]:
    """Handle A2A JSON-RPC 2.0 requests (`message/send`, `tasks/send`, `tasks/get`) from Gemini Enterprise."""
    body = await request.json()
    req_id = body.get("id", str(uuid.uuid4()))
    method = str(body.get("method", "message/send"))
    params = body.get("params") or {}

    if method == "agent/authenticatedExtendedCard":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": build_a2a_agent_card(),
        }

    # Extract prompt text from A2A message parts or direct prompt field
    prompt_parts: list[str] = []
    message_obj = params.get("message") or body.get("message") or {}
    for part in message_obj.get("parts", []):
        if isinstance(part, dict) and part.get("text"):
            prompt_parts.append(str(part["text"]))
        elif isinstance(part, dict) and part.get("kind") == "text" and part.get(" content"):
            prompt_parts.append(str(part["content"]))
    if not prompt_parts and params.get("prompt"):
        prompt_parts.append(str(params["prompt"]))
    prompt_text = "\n".join(prompt_parts).strip() or "Show the General!C5:N40 baseline assumptions table"

    session_id = str(params.get("sessionId") or params.get("contextId") or message_obj.get("contextId") or "default")
    task_id = str(params.get("id") or message_obj.get("taskId") or uuid.uuid4())

    workflow_res = await asyncio.to_thread(
        execute_prompt_workflow,
        prompt=prompt_text,
        session_id=session_id,
    )

    response_message = {
        "role": "agent",
        "messageId": str(uuid.uuid4()),
        "taskId": task_id,
        "contextId": session_id,
        "parts": [
            {
                "kind": "text",
                "type": "text",
                "text": workflow_res["response_markdown"],
            }
        ],
    }

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": {
            "id": task_id,
            "contextId": session_id,
            "kind": "task",
            "status": {
                "state": "completed",
                "message": response_message,
            },
            "artifacts": workflow_res["artifacts"],
            "history": [message_obj, response_message] if message_obj else [response_message],
            "metadata": {
                "executed_tools": workflow_res["executed_tools"],
                "technology_code": workflow_res["technology_code"],
                "cloud_artifact_url": workflow_res["cloud_artifact_url"],
                "cloud_download_url": workflow_res["cloud_download_url"],
                "spreadsheet_url": workflow_res["spreadsheet_url"],
                "gemini_enterprise_engine": GEMINI_ENTERPRISE_ENGINE_NAME,
            },
        },
    }


_ACTIVE_SSE_QUEUES: dict[str, asyncio.Queue[str | None]] = {}


@router.post("/mcp", summary="Remote Streamable HTTP JSON-RPC 2.0 MCP Server")
@router.post("/v1/mcp", summary="Remote Streamable HTTP JSON-RPC 2.0 MCP Server (v1)")
@router.post("/mcp/sse", summary="Streamable HTTP Fallback on /mcp/sse")
async def handle_remote_mcp_http(request: Request) -> Response:
    """Process JSON-RPC 2.0 MCP requests (`initialize`, `tools/list`, `tools/call`) over Streamable HTTP."""
    req_obj = await request.json()
    session_id = request.headers.get("mcp-session-id") or request.query_params.get("session_id") or "default"
    mgr = _get_cloud_session_manager(session_id)

    if isinstance(req_obj, list):
        responses = []
        for item in req_obj:
            r = await asyncio.to_thread(handle_jsonrpc_request, item, mgr)
            if r is not None:
                responses.append(r)
        return Response(
            content=json.dumps(responses, ensure_ascii=False),
            media_type="application/json",
            headers={
                "Mcp-Session-Id": session_id,
                "X-Content-Type-Options": "nosniff",
            },
        )

    resp_obj = await asyncio.to_thread(handle_jsonrpc_request, req_obj, mgr)
    if resp_obj is None:
        return Response(
            status_code=202,
            headers={"Mcp-Session-Id": session_id, "X-Content-Type-Options": "nosniff"},
        )
    return Response(
        content=json.dumps(resp_obj, ensure_ascii=False),
        media_type="application/json",
        headers={
            "Mcp-Session-Id": session_id,
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/mcp", summary="Remote MCP SSE Stream (Root /mcp GET)")
@router.get("/mcp/sse", summary="Remote MCP Server-Sent Events (SSE) Endpoint")
async def handle_remote_mcp_sse(request: Request) -> StreamingResponse:
    """Provide full-duplex MCP SSE (`2024-11-05`) stream emitting `endpoint` and JSON-RPC `message` events."""
    session_id = re.sub(r"[^A-Za-z0-9_\-]", "", (request.query_params.get("session_id") or str(uuid.uuid4())))
    once = request.query_params.get("once") in ("1", "true")
    queue: asyncio.Queue[str | None] = asyncio.Queue()
    _ACTIVE_SSE_QUEUES[session_id] = queue

    async def _event_source():
        try:
            yield f"event: endpoint\ndata: /mcp/messages?session_id={session_id}\n\n"
            if once:
                return
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg_str = await asyncio.wait_for(queue.get(), timeout=15.0)
                    if msg_str is None:
                        break
                    yield f"event: message\ndata: {msg_str}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            if _ACTIVE_SSE_QUEUES.get(session_id) is queue:
                _ACTIVE_SSE_QUEUES.pop(session_id, None)

    return StreamingResponse(
        _event_source(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/mcp/messages", summary="Remote MCP SSE Message Posting Endpoint")
async def handle_remote_mcp_messages(request: Request) -> Response:
    """Process JSON-RPC 2.0 MCP messages posted by SSE clients and push responses onto the active SSE stream."""
    session_id = request.query_params.get("session_id") or request.headers.get("mcp-session-id") or "default"
    req_obj = await request.json()
    mgr = _get_cloud_session_manager(session_id)
    active_queue = _ACTIVE_SSE_QUEUES.get(session_id)

    if isinstance(req_obj, list):
        responses = []
        for item in req_obj:
            r = await asyncio.to_thread(handle_jsonrpc_request, item, mgr)
            if r is not None:
                responses.append(r)
                if active_queue is not None:
                    await active_queue.put(json.dumps(r, ensure_ascii=False))
        if active_queue is not None:
            return Response(content="Accepted", status_code=202, media_type="text/plain")
        return Response(content=json.dumps(responses, ensure_ascii=False), media_type="application/json")

    resp_obj = await asyncio.to_thread(handle_jsonrpc_request, req_obj, mgr)
    if active_queue is not None:
        if resp_obj is not None:
            await active_queue.put(json.dumps(resp_obj, ensure_ascii=False))
        return Response(
            content="Accepted",
            status_code=202,
            media_type="text/plain",
            headers={"X-Content-Type-Options": "nosniff"},
        )

    if resp_obj is None:
        return Response(status_code=202)
    return Response(
        content=json.dumps(resp_obj, ensure_ascii=False),
        media_type="application/json",
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.get("/v1/agent/tools", summary="List Available Brazil Power v13 Cloud MCP Tools")
async def list_cloud_agent_tools() -> dict[str, Any]:
    """Return the 7 registered MCP tools and active Google Cloud backend configuration."""
    return {
        "server_name": MCP_SERVER_NAME,
        "server_version": MCP_SERVER_VERSION,
        "protocol_version": MCP_PROTOCOL_VERSION,
        "cloud_backend": {
            "project_id": os.environ.get("GCP_PROJECT_ID", "comm-model-mod"),
            "region": "us-central1",
            "gcs_artifact_bucket": os.environ.get("GCS_ARTIFACT_BUCKET", DEFAULT_GCS_ARTIFACT_BUCKET),
            "bq_lt_view": os.environ.get("BQ_LT_TRAJECTORIES_VIEW", DEFAULT_BQ_LT_VIEW),
            "gemini_enterprise_engine": GEMINI_ENTERPRISE_ENGINE_NAME,
            "gemini_enterprise_cid": GEMINI_ENTERPRISE_CID,
        },
        "tools": MCP_TOOLS,
    }


@router.post("/v1/agent/tools/{tool_name}", summary="Execute a Brazil Power v13 MCP Tool on Google Cloud Run")
async def invoke_cloud_agent_tool(tool_name: str, payload: ToolInvokeRequest) -> dict[str, Any]:
    """Execute one of the 7 Brazil Power v13 MCP tools in Google Cloud Run with GCS, BigQuery ML, and Cloud SQL."""
    if tool_name not in TOOL_HANDLERS:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown MCP tool '{tool_name}'. Available tools: {sorted(TOOL_HANDLERS.keys())}",
        )
    mgr = _get_cloud_session_manager(payload.session_id)
    try:
        result = await asyncio.to_thread(
            call_mcp_tool,
            tool_name,
            arguments=payload.arguments,
            session_mgr=mgr,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if tool_name == "update_session_assumptions" and isinstance(result.get("changes"), list):
        db_count = await _record_cloud_sql_audit_for_changes(
            changes=result["changes"],
            user_email=payload.user_email,
        )
        result["cloud_sql_audit_rows_recorded"] = db_count

    return {
        "status": "ok",
        "tool_name": tool_name,
        "session_id": payload.session_id or "default",
        "execution_backend": "google_cloud_run",
        "result": result,
    }


@router.post("/v1/agent/chat", summary="Execute Natural Language Brazil Power v13 Agent Prompt on Cloud Run")
async def chat_with_cloud_agent(payload: AgentChatRequest) -> dict[str, Any]:
    """Execute a natural-language prompt against the Brazil Power v13 Cloud Agent."""
    workflow_res = await asyncio.to_thread(
        execute_prompt_workflow,
        prompt=payload.prompt,
        session_id=payload.session_id,
        technology_code=payload.technology_code,
    )
    return {
        "status": "ok",
        "session_id": payload.session_id or "default",
        **workflow_res,
    }


@router.get("/v1/agent/artifacts/{filename}", summary="Download Full Excel-Replica Markdown Artifact")
async def download_agent_artifact(filename: str) -> Response:
    """Serve a sanitized Markdown artifact file from local cache or Google Cloud Storage."""
    try:
        safe_name = sanitize_artifact_filename(filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    custom_dir = os.environ.get("BRAZIL_POWER_ARTIFACT_DIR")
    is_cloud = bool(os.environ.get("K_SERVICE") or os.environ.get("ENV", "").lower() == "gcp")
    base_dir = (
        Path(custom_dir).resolve()
        if custom_dir
        else (Path("/tmp/brazil_power_artifacts").resolve() if is_cloud else (Path.home() / ".gemini" / "jetski" / "artifacts").resolve())
    )
    candidate_path = (base_dir / safe_name).resolve()
    if not candidate_path.is_relative_to(base_dir):
        raise HTTPException(status_code=400, detail="Invalid artifact path.")

    content_bytes: bytes | None = None
    if candidate_path.is_file():
        content_bytes = candidate_path.read_bytes()
    else:
        bucket_name = os.environ.get("GCS_ARTIFACT_BUCKET", DEFAULT_GCS_ARTIFACT_BUCKET).strip()
        try:
            from google.cloud import storage

            client = storage.Client()
            blob = client.bucket(bucket_name).blob(f"agent_artifacts/{safe_name}")
            if blob.exists():
                content_bytes = blob.download_as_bytes()
        except Exception as exc:
            logger.warning("GCS artifact lookup failed for %s: %s", safe_name, exc)

    if content_bytes is None:
        raise HTTPException(status_code=404, detail=f"Artifact '{safe_name}' not found.")

    return Response(
        content=content_bytes,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )


@router.get("/v1/agent/exports/{filename}", summary="Download Exported 22-Tab Brazil Power v13 .xlsx Workbook")
async def download_agent_xlsx_export(filename: str) -> Response:
    """Serve a sanitized 22-tab .xlsx workbook export from local cache or Google Cloud Storage."""
    try:
        safe_name = sanitize_export_filename(filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    base_dir = DEFAULT_EXPORT_DIR.resolve()
    candidate_path = (base_dir / safe_name).resolve()
    if not candidate_path.is_relative_to(base_dir):
        raise HTTPException(status_code=400, detail="Invalid export path.")

    content_bytes: bytes | None = None
    if candidate_path.is_file():
        content_bytes = candidate_path.read_bytes()
    else:
        bucket_name = os.environ.get("GCS_ARTIFACT_BUCKET", DEFAULT_GCS_ARTIFACT_BUCKET).strip()
        try:
            from google.cloud import storage

            client = storage.Client()
            blob = client.bucket(bucket_name).blob(f"agent_exports/{safe_name}")
            if blob.exists():
                content_bytes = blob.download_as_bytes()
        except Exception as exc:
            logger.warning("GCS export lookup failed for %s: %s", safe_name, exc)

    if content_bytes is None:
        raise HTTPException(status_code=404, detail=f"Workbook export '{safe_name}' not found.")

    return Response(
        content=content_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )
