"""FastAPI Remote MCP Server (`eulr-bq-twin-mcp`) supporting Streamable HTTP + SSE transport."""

from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from google.cloud import storage

from eulr_bq_twin.config import get_eulr_twin_settings
from eulr_bq_twin.mcp_tools import MCP_SERVER_NAME, MCP_SERVER_VERSION, EulrMcpDispatcher
from eulr_bq_twin.xlsx_synthesizer import resolve_contained_export_path, sanitize_export_filename


def create_eulr_mcp_app(dispatcher: EulrMcpDispatcher | None = None) -> FastAPI:
    app = FastAPI(
        title="EULR European Refining Equilibrium — BigQuery Digital Twin Remote MCP",
        version=MCP_SERVER_VERSION,
        docs_url=None,
        redoc_url=None,
    )
    mcp_dispatcher = dispatcher or EulrMcpDispatcher()
    sse_queues: dict[str, asyncio.Queue[str]] = {}

    @app.get("/health")
    @app.get("/healthz")
    async def healthz() -> dict[str, Any]:
        return {
            "status": "ok",
            "service": MCP_SERVER_NAME,
            "version": MCP_SERVER_VERSION,
            "bq_dataset": f"{mcp_dispatcher.settings.gcp_project_id}.{mcp_dispatcher.settings.bq_dataset_id}",
            "gcs_vault": mcp_dispatcher.settings.gcs_vault_bucket,
        }

    @app.post("/mcp")
    async def mcp_streamable_http(request: Request) -> Response:
        body = await request.json()
        sess_hdr = request.headers.get("Mcp-Session-Id") or mcp_dispatcher.settings.default_session_id
        loop = asyncio.get_running_loop()
        resp = await loop.run_in_executor(
            None, mcp_dispatcher.handle_jsonrpc, body, sess_hdr
        )
        if resp is None:
            return Response(status_code=202)
        return JSONResponse(content=resp, headers={"X-Content-Type-Options": "nosniff"})

    @app.get("/mcp/sse")
    async def mcp_sse_connect(request: Request) -> StreamingResponse:
        session_id = str(uuid.uuid4())
        q: asyncio.Queue[str] = asyncio.Queue()
        sse_queues[session_id] = q
        msg_endpoint = f"/mcp/messages?session_id={session_id}"

        async def event_stream():
            try:
                yield f"event: endpoint\ndata: {msg_endpoint}\n\n"
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        payload_str = await asyncio.wait_for(q.get(), timeout=15.0)
                        yield f"event: message\ndata: {payload_str}\n\n"
                    except TimeoutError:
                        yield ": keepalive\n\n"
            finally:
                sse_queues.pop(session_id, None)

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @app.post("/mcp/messages")
    async def mcp_sse_message(request: Request, session_id: str) -> Response:
        q = sse_queues.get(session_id)
        if q is None:
            raise HTTPException(status_code=404, detail="Unknown or expired MCP SSE session")
        body = await request.json()
        loop = asyncio.get_running_loop()
        resp = await loop.run_in_executor(
            None, mcp_dispatcher.handle_jsonrpc, body, session_id
        )
        if resp is not None:
            await q.put(json.dumps(resp))
        return Response(status_code=202)

    @app.get("/v1/exports/{filename}")
    async def download_synthesized_workbook(filename: str) -> FileResponse:
        try:
            safe_name = sanitize_export_filename(filename)
            local_path = resolve_contained_export_path(
                Path(mcp_dispatcher.settings.export_local_dir), safe_name
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid filename") from exc

        if not local_path.exists() and mcp_dispatcher.settings.gcp_project_id != "offline-test":
            try:
                gcs = storage.Client(project=mcp_dispatcher.settings.gcp_project_id)
                bucket = gcs.bucket(mcp_dispatcher.settings.gcs_vault_bucket)
                blob = bucket.blob(f"{mcp_dispatcher.settings.gcs_export_prefix}/{safe_name}")
                if blob.exists():
                    blob.download_to_filename(str(local_path))
            except Exception:
                pass

        if not local_path.exists():
            raise HTTPException(status_code=404, detail="Export artifact not found")

        return FileResponse(
            path=str(local_path),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=safe_name,
            headers={
                "Content-Disposition": f'attachment; filename="{safe_name}"',
                "X-Content-Type-Options": "nosniff",
            },
        )

    return app


app = create_eulr_mcp_app()
