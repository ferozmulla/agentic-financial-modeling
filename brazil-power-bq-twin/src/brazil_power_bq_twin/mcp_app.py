"""FastAPI Remote SSE & Streamable HTTP MCP Server for the isolated BigQuery Digital Twin."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from brazil_power_bq_twin.bq_store import BigQueryDigitalTwinStore, DigitalTwinStore
from brazil_power_bq_twin.config import TwinSettings, get_twin_settings
from brazil_power_bq_twin.mcp_tools import MCP_SERVER_NAME, MCP_SERVER_VERSION, handle_twin_jsonrpc
from brazil_power_bq_twin.xlsx_synthesizer import sanitize_filename

logger = logging.getLogger(__name__)

_ACTIVE_SSE_QUEUES: dict[str, asyncio.Queue[str | None]] = {}


def create_twin_mcp_app(
    store: DigitalTwinStore | None = None,
    settings: TwinSettings | None = None,
) -> FastAPI:
    """Create the isolated `brazil-power-bq-twin-mcp` FastAPI application."""
    cfg = settings or get_twin_settings()
    active_store: DigitalTwinStore = store if store is not None else BigQueryDigitalTwinStore(settings=cfg)

    app = FastAPI(
        title="Brazil Energy Model (v13) — Isolated BigQuery Digital Twin MCP Server",
        version=MCP_SERVER_VERSION,
    )
    app.state.twin_store = active_store
    app.state.twin_settings = cfg

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "service": MCP_SERVER_NAME,
            "version": MCP_SERVER_VERSION,
            "backend": "bigquery_digital_twin",
            "dataset": f"{cfg.gcp_project_id}.{cfg.bq_dataset}",
            "excel_files_used": 0,
        }

    @app.post("/mcp")
    @app.post("/mcp/sse")
    async def mcp_streamable_http(request: Request) -> Response:
        req_obj = await request.json()
        raw_sid = request.headers.get("mcp-session-id") or request.query_params.get("session_id") or "default"
        session_id = re.sub(r"[^A-Za-z0-9_\-]", "", raw_sid) or "default"

        if isinstance(req_obj, list):
            out = []
            for item in req_obj:
                r = await asyncio.to_thread(handle_twin_jsonrpc, item, active_store, session_id, cfg)
                if r is not None:
                    out.append(r)
            return Response(
                content=json.dumps(out, ensure_ascii=False),
                media_type="application/json",
                headers={"Mcp-Session-Id": session_id, "X-Content-Type-Options": "nosniff"},
            )

        resp_obj = await asyncio.to_thread(handle_twin_jsonrpc, req_obj, active_store, session_id, cfg)
        if resp_obj is None:
            return Response(status_code=202, headers={"Mcp-Session-Id": session_id, "X-Content-Type-Options": "nosniff"})
        return Response(
            content=json.dumps(resp_obj, ensure_ascii=False),
            media_type="application/json",
            headers={"Mcp-Session-Id": session_id, "X-Content-Type-Options": "nosniff"},
        )

    @app.get("/mcp")
    @app.get("/mcp/sse")
    async def mcp_sse_stream(request: Request) -> StreamingResponse:
        raw_sid = request.query_params.get("session_id") or str(uuid.uuid4())
        session_id = re.sub(r"[^A-Za-z0-9_\-]", "", raw_sid) or str(uuid.uuid4())
        once = request.query_params.get("once") in ("1", "true")
        queue: asyncio.Queue[str | None] = asyncio.Queue()
        _ACTIVE_SSE_QUEUES[session_id] = queue

        async def _gen():
            try:
                yield f"event: endpoint\ndata: /mcp/messages?session_id={session_id}\n\n"
                if once:
                    return
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        msg = await asyncio.wait_for(queue.get(), timeout=15.0)
                        if msg is None:
                            break
                        yield f"event: message\ndata: {msg}\n\n"
                    except asyncio.TimeoutError:
                        yield ": keepalive\n\n"
            finally:
                if _ACTIVE_SSE_QUEUES.get(session_id) is queue:
                    _ACTIVE_SSE_QUEUES.pop(session_id, None)

        return StreamingResponse(
            _gen(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @app.post("/mcp/messages")
    async def mcp_sse_messages(request: Request) -> Response:
        raw_sid = request.query_params.get("session_id") or request.headers.get("mcp-session-id") or "default"
        session_id = re.sub(r"[^A-Za-z0-9_\-]", "", raw_sid) or "default"
        req_obj = await request.json()
        active_q = _ACTIVE_SSE_QUEUES.get(session_id)

        resp_obj = await asyncio.to_thread(handle_twin_jsonrpc, req_obj, active_store, session_id, cfg)
        if active_q is not None:
            if resp_obj is not None:
                await active_q.put(json.dumps(resp_obj, ensure_ascii=False))
            return Response(content="Accepted", status_code=202, media_type="text/plain", headers={"X-Content-Type-Options": "nosniff"})

        if resp_obj is None:
            return Response(status_code=202)
        return Response(
            content=json.dumps(resp_obj, ensure_ascii=False),
            media_type="application/json",
            headers={"X-Content-Type-Options": "nosniff"},
        )

    def _serve_sanitized_download(filename: str, expected_ext: str, base_dir_attr: str, gcs_prefix: str, media_type: str) -> Response:
        try:
            safe_name = sanitize_filename(filename, expected_ext)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        base_dir = getattr(cfg, base_dir_attr).resolve()
        candidate = (base_dir / safe_name).resolve()
        if not candidate.is_relative_to(base_dir):
            raise HTTPException(status_code=400, detail="Invalid file path.")

        data_bytes: bytes | None = candidate.read_bytes() if candidate.is_file() else None
        if data_bytes is None:
            try:
                from google.cloud import storage

                blob = storage.Client(project=cfg.gcp_project_id).bucket(cfg.gcs_bucket).blob(f"{gcs_prefix}/{safe_name}")
                if blob.exists():
                    data_bytes = blob.download_as_bytes()
            except Exception as exc:
                logger.warning("GCS download lookup failed for %s: %s", safe_name, exc)

        if data_bytes is None:
            raise HTTPException(status_code=404, detail=f"File '{safe_name}' not found.")

        return Response(
            content=data_bytes,
            media_type=media_type,
            headers={
                "Content-Disposition": f'attachment; filename="{safe_name}"',
                "X-Content-Type-Options": "nosniff",
                "Cache-Control": "no-store",
            },
        )

    @app.get("/v1/exports/{filename}")
    async def download_synthesized_xlsx(filename: str) -> Response:
        return _serve_sanitized_download(
            filename=filename,
            expected_ext=".xlsx",
            base_dir_attr="local_export_dir",
            gcs_prefix=cfg.gcs_exports_prefix,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    @app.get("/v1/artifacts/{filename}")
    async def download_twin_artifact(filename: str) -> Response:
        return _serve_sanitized_download(
            filename=filename,
            expected_ext=".md",
            base_dir_attr="local_artifact_dir",
            gcs_prefix=cfg.gcs_artifacts_prefix,
            media_type="text/markdown; charset=utf-8",
        )

    return app


app = create_twin_mcp_app()
