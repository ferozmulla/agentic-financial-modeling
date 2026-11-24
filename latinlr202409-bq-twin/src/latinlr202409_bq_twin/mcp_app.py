"""Hardened Full-Duplex SSE + Streamable HTTP FastAPI MCP Server (`latinlr202409-bq-twin-mcp`)."""

from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse

from .config import settings
from .bq_store import BaseDigitalTwinStore
from .mcp_tools import McpDispatcher
from .xlsx_synthesizer import sanitize_export_filename

_SECURITY_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Cache-Control": "no-store",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
}


def build_twin_fastapi_app(
    dispatcher: Any,
    service_name: str,
    version: str,
    dataset_fqn: str,
    export_dir: Path,
    sanitize_fn: Any,
) -> FastAPI:
    """Create a production FastAPI app with `/health`, `/healthz`, `/mcp`, `/mcp/sse`, `/mcp/messages`, and `/v1/exports/{filename}`."""
    app = FastAPI(
        title=f"{service_name} — BigQuery Digital Twin Remote MCP Server",
        version=version,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    sse_queues: dict[str, asyncio.Queue[str]] = {}

    @app.get("/health")
    @app.get("/healthz")
    async def health() -> JSONResponse:
        return JSONResponse(
            content={
                "status": "ok",
                "service": service_name,
                "version": version,
                "bq_dataset": dataset_fqn,
                "excel_files_used": 0,
            },
            headers=_SECURITY_HEADERS,
        )

    @app.post("/mcp")
    @app.post("/mcp/sse")
    async def mcp_streamable_http(request: Request) -> Response:
        try:
            body = await request.json()
        except (ValueError, UnicodeDecodeError):
            return JSONResponse(status_code=400, content={"error": "Invalid JSON"}, headers=_SECURITY_HEADERS)
        session_id = request.headers.get("Mcp-Session-Id") or request.query_params.get("session_id") or "default"
        loop = asyncio.get_running_loop()
        resp = await loop.run_in_executor(None, dispatcher.handle_jsonrpc, body, session_id)
        if resp is None:
            return Response(status_code=202, headers={**_SECURITY_HEADERS, "Mcp-Session-Id": session_id})
        return JSONResponse(content=resp, headers={**_SECURITY_HEADERS, "Mcp-Session-Id": session_id})

    @app.get("/mcp")
    @app.get("/mcp/sse")
    async def mcp_sse_stream(request: Request) -> StreamingResponse:
        session_id = request.query_params.get("session_id") or str(uuid.uuid4())
        q: asyncio.Queue[str] = asyncio.Queue()
        sse_queues[session_id] = q

        async def _events() -> Any:
            try:
                yield f"event: endpoint\ndata: /mcp/messages?session_id={session_id}\n\n"
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        msg = await asyncio.wait_for(q.get(), timeout=15.0)
                        yield f"event: message\ndata: {msg}\n\n"
                    except TimeoutError:
                        yield ": keepalive\n\n"
            finally:
                sse_queues.pop(session_id, None)

        return StreamingResponse(
            _events(),
            media_type="text/event-stream",
            headers={**_SECURITY_HEADERS, "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )

    @app.post("/mcp/messages")
    async def mcp_sse_messages(request: Request, session_id: str = "default") -> Response:
        body = await request.json()
        loop = asyncio.get_running_loop()
        resp = await loop.run_in_executor(None, dispatcher.handle_jsonrpc, body, session_id)
        q = sse_queues.get(session_id)
        if q is not None:
            if resp is not None:
                await q.put(json.dumps(resp))
            return Response(content="Accepted", status_code=202, media_type="text/plain", headers=_SECURITY_HEADERS)
        if resp is None:
            return Response(status_code=202, headers=_SECURITY_HEADERS)
        return JSONResponse(content=resp, headers=_SECURITY_HEADERS)

    @app.get("/v1/exports/{filename}")
    async def download_export(filename: str) -> Response:
        try:
            safe_name = sanitize_fn(filename, ".xlsx")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        root = export_dir.resolve()
        candidate = (root / safe_name).resolve()
        if candidate.parent != root or not candidate.is_file():
            raise HTTPException(status_code=404, detail="Export not found")
        return Response(
            content=candidate.read_bytes(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                **_SECURITY_HEADERS,
                "Content-Disposition": f'attachment; filename="{safe_name}"',
            },
        )

    return app


# Initialize components
store = BaseDigitalTwinStore(
    project_id=settings.project_id,
    dataset_id=settings.dataset_id,
    workbook_id=settings.workbook_id,
    base_version_id=settings.base_version_id,
)

dispatcher = McpDispatcher(store)

app = build_twin_fastapi_app(
    dispatcher=dispatcher,
    service_name="latinlr202409-bq-twin-mcp",
    version="1.0.0",
    dataset_fqn=f"{settings.project_id}.{settings.dataset_id}",
    export_dir=settings.export_dir,
    sanitize_fn=sanitize_export_filename,
)
