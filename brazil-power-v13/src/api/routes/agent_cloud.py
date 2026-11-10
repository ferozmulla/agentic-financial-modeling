"""Cloud Run Remote MCP Server (SSE & Streamable HTTP) and Artifact/Export Gateway for Brazil Power v13."""

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
    call_mcp_tool,
    handle_jsonrpc_request,
    sanitize_artifact_filename,
)
from brazil_power_agent.session_store import (
    DEFAULT_BQ_LT_VIEW,
    DEFAULT_GCS_ARTIFACT_BUCKET,
    BrazilPowerSessionManager,
)
from brazil_power_agent.workbook_exporter import (
    DEFAULT_EXPORT_DIR,
    sanitize_export_filename,
)
from src.core.config import get_settings
from src.ingestion.realtime_edit_handler import handle_realtime_edit_event
from src.schemas.audit import RealTimeEditEventRequest

router = APIRouter(tags=["Cowork Remote MCP & Artifact Gateway"])


class ToolInvokeRequest(BaseModel):
    """Request body for POST /v1/agent/tools/{tool_name}."""

    arguments: dict[str, Any] = Field(default_factory=dict)
    session_id: str | None = Field(default=None, description="Optional scenario session identifier.")
    user_email: str = Field(default="cowork-mcp-client@comm-model-mod.iam.gserviceaccount.com")


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
                        workbook_name="Brazil Energy Model (v13) — Cowork Remote MCP",
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
                        who_client_platform="cowork-remote-mcp",
                    )
                    persisted += 1
    except Exception as exc:
        logger.warning("Cloud SQL 4-Ws audit persistence skipped/degraded: %s", exc)
    return persisted


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
